"""Carelink Authentication Module for Home Assistant Add-on."""
import base64
import hashlib
import json
import logging
import os
import random
import re
import secrets
import string
import uuid
from time import sleep

import requests
import OpenSSL
from seleniumwire import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service

logger = logging.getLogger(__name__)

# Configuration
DISCOVERY_URL = "https://clcloud.minimed.eu/connect/carepartner/v13/discover/android/3.6"
RSA_KEYSIZE = 2048


class CarelinkAuth:
    """Handle Carelink authentication flow."""

    def __init__(self, region: str = "eu", output_file: str = "logindata.json"):
        """Initialize the auth handler."""
        self.region = region.lower()
        self.output_file = output_file
        self.is_us_region = self.region == "us"

    def login(self) -> bool:
        """Perform the login process and save tokens."""
        try:
            logger.info(f"Starting login for region: {self.region}")
            endpoint_config = self._resolve_endpoint_config()

            sso_config, api_base_url, is_auth0 = endpoint_config

            if is_auth0:
                token_data = self._do_login_auth0(endpoint_config)
            else:
                token_data = self._do_login_non_auth0(endpoint_config)

            if token_data:
                self._write_datafile(token_data)
                logger.info(f"Token saved to {self.output_file}")
                return True

            return False

        except Exception as e:
            logger.exception(f"Login failed: {e}")
            raise

    def _resolve_endpoint_config(self):
        """Resolve the API endpoint configuration."""
        discover_resp = requests.get(DISCOVERY_URL).json()
        sso_url = None
        is_auth0 = False

        for c in discover_resp["CP"]:
            if c["region"].lower() == "us" and self.is_us_region:
                key = c["UseSSOConfiguration"]
                sso_url = c[key]
                is_auth0 = "Auth0" in key
            elif c["region"].lower() == "eu" and not self.is_us_region:
                key = c["UseSSOConfiguration"]
                sso_url = c[key]
                is_auth0 = "Auth0" in key

        if sso_url is None:
            raise Exception("Could not get SSO config url")

        sso_config = requests.get(sso_url).json()

        if is_auth0:
            api_base_url = sso_config.get("issuer", "").rstrip("/")
        else:
            api_base_url = f"https://{sso_config['server']['hostname']}:{sso_config['server']['port']}/{sso_config['server']['prefix']}"
            if api_base_url.endswith("/"):
                api_base_url = api_base_url[:-1]

        return sso_config, api_base_url, is_auth0

    def _create_browser(self):
        """Create a Firefox browser instance."""
        options = Options()

        # Run in headless mode for the add-on
        # Users won't see the browser, but Selenium will handle the flow
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        # Set preferences
        options.set_preference("browser.download.folderList", 2)
        options.set_preference("browser.helperApps.alwaysAsk.force", False)

        service = Service(executable_path="/usr/local/bin/geckodriver")

        driver = webdriver.Firefox(options=options, service=service)
        return driver

    def _do_captcha(self, url: str, redirect_url: str):
        """Handle the OAuth login flow via browser."""
        logger.info("Opening browser for login...")
        driver = self._create_browser()

        try:
            driver.get(url)
            logger.info(f"Navigated to login page")

            # Wait for the redirect with the auth code
            max_wait = 300  # 5 minutes timeout
            waited = 0

            while waited < max_wait:
                for request in driver.requests:
                    if request.response:
                        if request.response.status_code == 302:
                            if "location" in request.response.headers:
                                location = request.response.headers["location"]
                                if redirect_url in location:
                                    code_match = re.search(r"code=([^&]+)", location)
                                    if code_match:
                                        code = code_match.group(1)
                                        state = None
                                        state_match = re.search(r"state=([^&]+)", location)
                                        if state_match:
                                            state = state_match.group(1)
                                        logger.info("Got authorization code")
                                        return (code, state)
                sleep(0.5)
                waited += 0.5

            raise Exception("Login timeout - no authorization code received")

        finally:
            driver.quit()

    def _do_login_auth0(self, endpoint_config):
        """Perform Auth0 login flow."""
        sso_config, api_base_url, _ = endpoint_config

        auth_params = {
            "client_id": sso_config["client"]["client_id"],
            "response_type": "code",
            "scope": sso_config["client"]["scope"],
            "redirect_uri": sso_config["client"]["redirect_uri"],
            "audience": sso_config["client"]["audience"],
        }

        authorize_url = api_base_url + sso_config["system_endpoints"]["authorization_endpoint_path"]
        captcha_url = f"{authorize_url}?{'&'.join(f'{key}={value}' for key, value in auth_params.items())}"

        captcha_code, _ = self._do_captcha(captcha_url, sso_config["client"]["redirect_uri"])

        token_req_url = api_base_url + sso_config["system_endpoints"]["token_endpoint_path"]
        token_req_data = {
            "grant_type": "authorization_code",
            "client_id": sso_config["client"]["client_id"],
            "code": captcha_code,
            "redirect_uri": sso_config["client"]["redirect_uri"],
        }

        token_resp = requests.post(token_req_url, data=token_req_data)
        if token_resp.status_code != 200:
            raise Exception(f"Could not get token: {token_resp.text}")

        token_data = token_resp.json()
        token_data["client_id"] = token_req_data["client_id"]

        # Remove unnecessary fields
        token_data.pop("expires_in", None)
        token_data.pop("token_type", None)

        return token_data

    def _do_login_non_auth0(self, endpoint_config):
        """Perform non-Auth0 (MAG) login flow."""
        sso_config, api_base_url, _ = endpoint_config

        # Step 1: Initialize client
        data = {
            "client_id": sso_config["oauth"]["client"]["client_ids"][0]["client_id"],
            "nonce": str(uuid.UUID(bytes=secrets.token_bytes(16))),
        }
        headers = {
            "device-id": base64.b64encode(hashlib.sha256(os.urandom(40)).hexdigest().encode()).decode()
        }

        client_init_url = api_base_url + sso_config["mag"]["system_endpoints"]["client_credential_init_endpoint_path"]
        client_init_resp = requests.post(client_init_url, data=data, headers=headers).json()

        # Step 2: Prepare authorization
        client_code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode("utf-8")
        client_code_verifier = re.sub("[^a-zA-Z0-9]+", "", client_code_verifier)
        client_code_challenge = hashlib.sha256(client_code_verifier.encode("utf-8")).digest()
        client_code_challenge = base64.urlsafe_b64encode(client_code_challenge).decode("utf-8").replace("=", "")

        client_state = self._random_b64_str(22)
        auth_params = {
            "client_id": client_init_resp["client_id"],
            "response_type": "code",
            "display": "social_login",
            "scope": sso_config["oauth"]["client"]["client_ids"][0]["scope"],
            "redirect_uri": sso_config["oauth"]["client"]["client_ids"][0]["redirect_uri"],
            "code_challenge": client_code_challenge,
            "code_challenge_method": "S256",
            "state": client_state,
        }

        authorize_url = api_base_url + sso_config["oauth"]["system_endpoints"]["authorization_endpoint_path"]
        providers = requests.get(authorize_url, params=auth_params).json()
        captcha_url = providers["providers"][0]["provider"]["auth_url"]

        # Step 3: OAuth login
        captcha_code, _ = self._do_captcha(captcha_url, sso_config["oauth"]["client"]["client_ids"][0]["redirect_uri"])

        # Step 4: Device registration
        register_device_id = hashlib.sha256(os.urandom(40)).hexdigest()
        client_auth_str = f"{client_init_resp['client_id']}:{client_init_resp['client_secret']}"

        android_model = random.choice(["SM-G973F", "SM-G988U1", "SM-G981W", "SM-G9600"])
        android_model_safe = re.sub(r"[^a-zA-Z0-9]", "", android_model)

        keypair = OpenSSL.crypto.PKey()
        keypair.generate_key(OpenSSL.crypto.TYPE_RSA, RSA_KEYSIZE)
        csr = self._create_csr(keypair, "socialLogin", register_device_id, android_model_safe,
                               sso_config["oauth"]["client"]["organization"])

        reg_headers = {
            "device-name": base64.b64encode(android_model.encode()).decode(),
            "authorization": f"Bearer {captcha_code}",
            "cert-format": "pem",
            "client-authorization": "Basic " + base64.b64encode(client_auth_str.encode()).decode(),
            "create-session": "true",
            "code-verifier": client_code_verifier,
            "device-id": base64.b64encode(register_device_id.encode()).decode(),
            "redirect-uri": sso_config["oauth"]["client"]["client_ids"][0]["redirect_uri"],
        }

        csr = self._reformat_csr(csr)
        reg_url = api_base_url + sso_config["mag"]["system_endpoints"]["device_register_endpoint_path"]
        reg_resp = requests.post(reg_url, headers=reg_headers, data=csr)

        if reg_resp.status_code != 200:
            raise Exception(f"Could not register: {reg_resp.json().get('error_description', reg_resp.text)}")

        # Step 5: Get token
        token_req_url = api_base_url + sso_config["oauth"]["system_endpoints"]["token_endpoint_path"]
        token_req_data = {
            "assertion": reg_resp.headers["id-token"],
            "client_id": client_init_resp["client_id"],
            "client_secret": client_init_resp["client_secret"],
            "scope": sso_config["oauth"]["client"]["client_ids"][0]["scope"],
            "grant_type": reg_resp.headers["id-token-type"],
        }

        token_resp = requests.post(
            token_req_url,
            headers={"mag-identifier": reg_resp.headers["mag-identifier"]},
            data=token_req_data
        )

        if token_resp.status_code != 200:
            raise Exception("Could not get token data")

        token_data = token_resp.json()
        token_data["client_id"] = token_req_data["client_id"]
        token_data["client_secret"] = token_req_data["client_secret"]
        token_data["mag-identifier"] = reg_resp.headers["mag-identifier"]

        # Remove unnecessary fields
        token_data.pop("expires_in", None)
        token_data.pop("token_type", None)

        return token_data

    def _create_csr(self, keypair, cn, ou, dc, o):
        """Create a Certificate Signing Request."""
        req = OpenSSL.crypto.X509Req()
        req.get_subject().CN = cn
        req.get_subject().OU = ou
        req.get_subject().DC = dc
        req.get_subject().O = o
        req.set_pubkey(keypair)
        req.sign(keypair, "sha256")
        return OpenSSL.crypto.dump_certificate_request(OpenSSL.crypto.FILETYPE_PEM, req)

    def _reformat_csr(self, csr):
        """Reformat CSR for the API."""
        csr = csr.decode()
        csr = csr.replace("\n", "")
        csr = csr.replace("-----BEGIN CERTIFICATE REQUEST-----", "")
        csr = csr.replace("-----END CERTIFICATE REQUEST-----", "")
        csr_raw = base64.b64decode(csr.encode())
        return base64.urlsafe_b64encode(csr_raw).decode()

    def _random_b64_str(self, length):
        """Generate a random base64 string."""
        random_chars = "".join(random.choice(string.ascii_letters + string.digits) for _ in range(length + 10))
        base64_string = base64.b64encode(random_chars.encode("utf-8")).decode("utf-8")
        return base64_string[:length]

    def _write_datafile(self, obj):
        """Write token data to file."""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)

        with open(self.output_file, "w") as f:
            json.dump(obj, f, indent=4)

        logger.info(f"Wrote token data to {self.output_file}")
