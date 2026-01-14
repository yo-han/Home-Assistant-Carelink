#!/usr/bin/env python3
###############################################################################
#
#  Carelink Token Tool - Docker Edition
#
#  Based on the original carelink_carepartner_api_login.py by @palmarci
#  Modified for use in a Docker container with noVNC
#
###############################################################################

import argparse
import base64
import hashlib
import json
import os
import random
import re
import string
import uuid
import secrets
import time
from time import sleep
import sys

import requests
import OpenSSL
from seleniumwire import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.common.exceptions import NoSuchElementException

# Configuration
REQUEST_TIMEOUT = 30  # seconds
LOGIN_TIMEOUT = 600   # 10 minutes max wait for user to complete login


def random_b64_str(length):
    random_chars = ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length + 10))
    base64_string = base64.b64encode(random_chars.encode('utf-8')).decode('utf-8')
    return base64_string[:length]


def random_uuid():
    return str(uuid.UUID(bytes=secrets.token_bytes(16)))


def random_android_model():
    models = ['SM-G973F', "SM-G988U1", "SM-G981W", "SM-G9600"]
    random.shuffle(models)
    return models[0]


def random_device_id():
    return hashlib.sha256(os.urandom(40)).hexdigest()


def create_csr(keypair, cn, ou, dc, o):
    req = OpenSSL.crypto.X509Req()
    req.get_subject().CN = cn
    req.get_subject().OU = ou
    req.get_subject().DC = dc
    req.get_subject().O = o
    req.set_pubkey(keypair)
    req.sign(keypair, 'sha256')
    csr = OpenSSL.crypto.dump_certificate_request(OpenSSL.crypto.FILETYPE_PEM, req)
    return csr


def reformat_csr(csr):
    csr = csr.decode()
    csr = csr.replace("\n", "")
    csr = csr.replace("-----BEGIN CERTIFICATE REQUEST-----", "")
    csr = csr.replace("-----END CERTIFICATE REQUEST-----", "")
    csr_raw = base64.b64decode(csr.encode())
    csr = base64.urlsafe_b64encode(csr_raw).decode()
    return csr


def do_captcha(url, redirect_url):
    # Check for pre-filled credentials
    username = os.environ.get('CARELINK_USERNAME', '')
    password = os.environ.get('CARELINK_PASSWORD', '')
    has_credentials = bool(username and password)

    print("\n" + "=" * 50)
    print("BROWSER OPENING")
    print("=" * 50)
    print("\nPlease go to your browser window (noVNC tab)")
    if has_credentials:
        print("\nCredentials will be auto-filled!")
        print("You only need to solve the CAPTCHA.")
    else:
        print("\nComplete the following steps:")
        print("  1. Enter your Carelink credentials")
        print("  2. Solve the CAPTCHA")
        print("  3. Complete the login")
    print("\nWaiting for login to complete...")
    print(f"(Timeout: {LOGIN_TIMEOUT // 60} minutes)")
    print("=" * 50 + "\n")

    # Configure Firefox for container environment
    options = Options()
    options.set_preference("browser.tabs.warnOnClose", False)
    options.set_preference("browser.sessionstore.resume_from_crash", False)

    # Configure geckodriver service
    service = Service(
        executable_path="/usr/local/bin/geckodriver",
        log_output="/dev/null"
    )

    # Use seleniumwire options
    seleniumwire_options = {
        'disable_encoding': True
    }

    driver = webdriver.Firefox(
        service=service,
        options=options,
        seleniumwire_options=seleniumwire_options
    )

    # Maximize window for better visibility in noVNC
    driver.maximize_window()
    driver.get(url)

    # Auto-fill credentials if provided
    if has_credentials:
        try:
            sleep(3)  # Wait for page to load
            username_filled = False
            password_filled = False

            for selector in ['#username', '#email', 'input[name="username"]',
                           'input[name="email"]', 'input[type="email"]',
                           'input[name="loginfmt"]', '#loginfmt']:
                try:
                    elem = driver.find_element("css selector", selector)
                    elem.clear()
                    elem.send_keys(username)
                    username_filled = True
                    print("Username auto-filled")
                    break
                except NoSuchElementException:
                    continue

            sleep(0.5)

            for selector in ['#password', 'input[name="password"]',
                           'input[type="password"]', '#passwd']:
                try:
                    elem = driver.find_element("css selector", selector)
                    elem.clear()
                    elem.send_keys(password)
                    password_filled = True
                    print("Password auto-filled")
                    break
                except NoSuchElementException:
                    continue

            if username_filled and password_filled:
                print("\nCredentials filled! Please solve the CAPTCHA.")
            else:
                print("\nCould not auto-fill all fields. Please enter manually.")
        except Exception as e:
            print(f"\nAuto-fill failed: {e}")
            print("Please enter credentials manually.")

    # Wait for login with timeout
    start_time = time.time()
    while True:
        # Check timeout
        if time.time() - start_time > LOGIN_TIMEOUT:
            driver.quit()
            raise Exception(f"Login timeout - no successful login within {LOGIN_TIMEOUT // 60} minutes")

        for request in driver.requests:
            if request.response:
                if request.response.status_code == 302:
                    if "location" in request.response.headers:
                        location = request.response.headers["location"]
                        if redirect_url in location:
                            # Use more specific regex to avoid capturing extra params
                            code_match = re.search(r"code=([^&]+)", location)
                            if code_match:
                                code = code_match.group(1)
                                state = None
                                state_match = re.search(r"state=([^&]+)", location)
                                if state_match:
                                    state = state_match.group(1)
                                print("\nLogin successful! Closing browser...")
                                driver.quit()
                                return (code, state)
        sleep(0.1)


def resolve_endpoint_config(discovery_url, is_us_region=False):
    print(f"Discovering endpoint configuration (Region: {'US' if is_us_region else 'EU'})...")
    response = requests.get(discovery_url, timeout=REQUEST_TIMEOUT)
    discover_resp = json.loads(response.text)
    sso_url = None
    is_auth0 = False

    for c in discover_resp["CP"]:
        if c['region'].lower() == "us" and is_us_region:
            key = c['UseSSOConfiguration']
            sso_url = c[key]
            if "Auth0" in key:
                is_auth0 = True
        elif c['region'].lower() == "eu" and not is_us_region:
            key = c['UseSSOConfiguration']
            sso_url = c[key]
            if "Auth0" in key:
                is_auth0 = True

    if sso_url is None:
        raise Exception("Could not get SSO config url")

    sso_response = requests.get(sso_url, timeout=REQUEST_TIMEOUT)
    sso_config = json.loads(sso_response.text)
    api_base_url = f"https://{sso_config['server']['hostname']}:{sso_config['server']['port']}/{sso_config['server']['prefix']}"
    if api_base_url.endswith('/'):
        api_base_url = api_base_url[:-1]

    print(f"Found endpoint: {api_base_url}")
    print(f"Authentication type: {'Auth0' if is_auth0 else 'Standard'}")

    return sso_config, api_base_url, is_auth0


def write_datafile(obj, filename):
    with open(filename, 'w') as f:
        json.dump(obj, f, indent=4)
    print(f"\nToken data saved to: {filename}")


def do_login_non_auth0(endpoint_config, logindata_file, rsa_keysize):
    sso_config, api_base_url, is_auth0 = endpoint_config

    # Step 1: Initialize client
    print("\nStep 1/4: Initializing client...")
    data = {
        'client_id': sso_config['oauth']['client']['client_ids'][0]['client_id'],
        "nonce": random_uuid()
    }
    headers = {
        'device-id': base64.b64encode(random_device_id().encode()).decode()
    }
    client_init_url = api_base_url + sso_config["mag"]["system_endpoints"]["client_credential_init_endpoint_path"]
    client_init_req = requests.post(client_init_url, data=data, headers=headers, timeout=REQUEST_TIMEOUT)
    client_init_response = json.loads(client_init_req.text)

    # Step 2: Prepare authorization
    print("Step 2/4: Preparing authorization...")
    client_code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8')
    client_code_verifier = re.sub('[^a-zA-Z0-9]+', '', client_code_verifier)
    client_code_challange = hashlib.sha256(client_code_verifier.encode('utf-8')).digest()
    client_code_challange = base64.urlsafe_b64encode(client_code_challange).decode('utf-8')
    client_code_challange = client_code_challange.replace('=', '')

    client_state = random_b64_str(22)
    auth_params = {
        'client_id': client_init_response["client_id"],
        'response_type': 'code',
        'display': 'social_login',
        'scope': sso_config["oauth"]["client"]["client_ids"][0]['scope'],
        'redirect_uri': sso_config["oauth"]["client"]["client_ids"][0]['redirect_uri'],
        'code_challenge': client_code_challange,
        'code_challenge_method': 'S256',
        'state': client_state
    }
    authorize_url = api_base_url + sso_config["oauth"]["system_endpoints"]["authorization_endpoint_path"]
    auth_response = requests.get(authorize_url, params=auth_params, timeout=REQUEST_TIMEOUT)
    providers = json.loads(auth_response.text)
    captcha_url = providers["providers"][0]["provider"]["auth_url"]

    # Step 3: Browser login
    print("Step 3/4: Browser login required...")
    captcha_code, captcha_sso_state = do_captcha(
        captcha_url,
        sso_config["oauth"]["client"]["client_ids"][0]['redirect_uri']
    )

    # Step 4: Device registration
    print("Step 4/4: Registering device and obtaining tokens...")
    register_device_id = random_device_id()
    client_auth_str = f"{client_init_response['client_id']}:{client_init_response['client_secret']}"

    android_model = random_android_model()
    android_model_safe = re.sub(r"[^a-zA-Z0-9]", "", android_model)
    keypair = OpenSSL.crypto.PKey()
    keypair.generate_key(OpenSSL.crypto.TYPE_RSA, rsa_keysize)
    csr = create_csr(
        keypair,
        "socialLogin",
        register_device_id,
        android_model_safe,
        sso_config["oauth"]["client"]["organization"]
    )

    reg_headers = {
        'device-name': base64.b64encode(android_model.encode()).decode(),
        'authorization': f"Bearer {captcha_code}",
        'cert-format': 'pem',
        'client-authorization': "Basic " + base64.b64encode(client_auth_str.encode()).decode(),
        'create-session': 'true',
        'code-verifier': client_code_verifier,
        'device-id': base64.b64encode(register_device_id.encode()).decode(),
        "redirect-uri": sso_config["oauth"]["client"]["client_ids"][0]['redirect_uri']
    }
    csr = reformat_csr(csr)
    reg_url = api_base_url + sso_config["mag"]["system_endpoints"]["device_register_endpoint_path"]
    reg_req = requests.post(reg_url, headers=reg_headers, data=csr, timeout=REQUEST_TIMEOUT)

    if reg_req.status_code != 200:
        error_desc = json.loads(reg_req.text).get("error_description", "Unknown error")
        raise Exception(f'Could not register device: {error_desc}')

    # Get token
    token_req_url = api_base_url + sso_config["oauth"]["system_endpoints"]["token_endpoint_path"]
    token_req_data = {
        "assertion": reg_req.headers["id-token"],
        "client_id": client_init_response['client_id'],
        "client_secret": client_init_response['client_secret'],
        'scope': sso_config["oauth"]["client"]["client_ids"][0]['scope'],
        "grant_type": reg_req.headers["id-token-type"]
    }
    token_req = requests.post(
        token_req_url,
        headers={"mag-identifier": reg_req.headers["mag-identifier"]},
        data=token_req_data,
        timeout=REQUEST_TIMEOUT
    )

    if token_req.status_code != 200:
        raise Exception("Could not get token data from server")

    token_data = json.loads(token_req.text)
    token_data["client_id"] = token_req_data["client_id"]
    token_data["client_secret"] = token_req_data["client_secret"]
    del token_data["expires_in"]
    del token_data["token_type"]
    token_data["mag-identifier"] = reg_req.headers["mag-identifier"]

    write_datafile(token_data, logindata_file)
    return token_data


def do_login_auth0(endpoint_config, logindata_file):
    sso_config, api_base_url, is_auth0 = endpoint_config

    print("\nStep 1/2: Preparing authorization...")
    auth_params = {
        'client_id': sso_config['client']['client_id'],
        'response_type': 'code',
        'scope': sso_config["client"]["scope"],
        'redirect_uri': sso_config["client"]['redirect_uri'],
        'audience': sso_config["client"]["audience"]
    }
    authorize_url = api_base_url + sso_config["system_endpoints"]["authorization_endpoint_path"]
    captcha_url = f"{authorize_url}?{'&'.join(f'{key}={value}' for key, value in auth_params.items())}"

    print("Step 2/2: Browser login required...")
    captcha_code, captcha_sso_state = do_captcha(
        captcha_url,
        sso_config["client"]["redirect_uri"]
    )

    print("\nExchanging code for tokens...")
    token_req_url = api_base_url + sso_config["system_endpoints"]["token_endpoint_path"]
    token_req_data = {
        "grant_type": "authorization_code",
        "client_id": sso_config["client"]["client_id"],
        "code": captcha_code,
        "redirect_uri": sso_config["client"]["redirect_uri"],
    }
    token_req = requests.post(token_req_url, data=token_req_data, timeout=REQUEST_TIMEOUT)

    if token_req.status_code != 200:
        print(f"Error response: {token_req.text}")
        raise Exception("Could not get token data from server")

    token_data = json.loads(token_req.text)
    token_data["client_id"] = token_req_data["client_id"]
    del token_data["expires_in"]
    del token_data["token_type"]

    write_datafile(token_data, logindata_file)
    return token_data


def do_login(endpoint_config, logindata_file, rsa_keysize):
    sso_config, api_base_url, is_auth0 = endpoint_config

    if is_auth0:
        return do_login_auth0(endpoint_config, logindata_file)
    else:
        return do_login_non_auth0(endpoint_config, logindata_file, rsa_keysize)


def read_data_file(file):
    if os.path.isfile(file):
        try:
            with open(file, "r") as f:
                token_data = json.load(f)
            required_fields = ["access_token", "refresh_token", "client_id"]
            for field in required_fields:
                if field not in token_data:
                    print(f"Warning: Field '{field}' is missing from existing data file")
                    return None
            return token_data
        except json.JSONDecodeError:
            print("Warning: Could not parse existing data file")
            return None
    return None


def main():
    # Configuration
    default_logindata_file = "logindata.json"
    discovery_url = 'https://clcloud.minimed.eu/connect/carepartner/v13/discover/android/3.6'
    rsa_keysize = 2048

    # Parse command line / environment
    parser = argparse.ArgumentParser(description='Carelink Token Tool')
    parser.add_argument('--us', help='Use US region (default: EU)',
                        default=False, action='store_true')
    parser.add_argument(
        "--output",
        help="Output path for logindata.json (env: CARELINK_OUTPUT_FILE)",
        default=None,
    )
    args = parser.parse_args()

    # Also check environment variable (support multiple formats)
    region_env = os.environ.get('CARELINK_REGION', '').lower().strip()
    is_us_region = args.us or region_env in ('--us', 'us', 'true', '1')

    output_env = os.environ.get("CARELINK_OUTPUT_FILE", "").strip()
    logindata_file = output_env or args.output or default_logindata_file

    print("\n" + "=" * 50)
    print("   CARELINK TOKEN TOOL")
    print("=" * 50)
    print(f"\nRegion: {'United States' if is_us_region else 'Europe'}")
    print(f"Output: {os.path.abspath(logindata_file)}")

    # Check for existing token file
    token_data = read_data_file(logindata_file)

    if token_data is not None:
        print("\nExisting token file found!")
        print(f"Delete {os.path.basename(logindata_file)} to generate new tokens.")
        return

    print("\nStarting login process...")

    try:
        endpoint_config = resolve_endpoint_config(discovery_url, is_us_region=is_us_region)
        token_data = do_login(endpoint_config, logindata_file, rsa_keysize)
        print("\n" + "=" * 50)
        print("   LOGIN SUCCESSFUL!")
        print("=" * 50)
    except Exception as e:
        print("\n" + "=" * 50)
        print("   LOGIN FAILED")
        print("=" * 50)
        print(f"\nError: {str(e)}")
        print("\nPlease try again or check your credentials.")
        sys.exit(1)


if __name__ == "__main__":
    main()
