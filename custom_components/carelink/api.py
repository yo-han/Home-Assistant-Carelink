"""
 Carelink Client library
 Description:
   This library implements a client for the Medtronic Carelink API.
   It is a port of the original Java client by Bence Szász:
   https://github.com/benceszasz/CareLinkJavaClient
 Authors:
   Ondrej Wisniewski (ondrej.wisniewski *at* gmail.com)
   Johan Kuijt (github *at* w3f.nl)
 Changelog:
   09/05/2021 - Initial public release (Ondrej)
   06/06/2021 - Add check for expired token (Ondrej)
   19/09/2022 - Check for general BLE device family to support 770G (Ondrej)
   28/11/2022 - Async version of the library and console test option (Johan)
   29/11/2022 - Pylint problem modifications (Johan)
 Copyright 2021-2022, Ondrej Wisniewski
"""

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import base64
import aiofiles

import httpx

# Version string
VERSION = "0.4"

# Constants
AUTH_EXPIRE_DEADLINE_MINUTES = 10
AUTH_FILE_PREFIX = "carelink_logindata"
LEGACY_AUTH_FILE = "custom_components/carelink/logindata.json"
CARELINK_CONFIG_URL = "https://clcloud.minimed.eu/connect/carepartner/v13/discover/android/3.6"
AUTH_ERROR_CODES = [401,403]

DEBUG = False

_LOGGER = logging.getLogger(__name__)


def printdbg(msg):
    """Debug logger/print function"""
    _LOGGER.debug("Carelink API: %s", msg)

    if DEBUG:
        print(msg)

class CarelinkClient:
    """Carelink Client library"""

    def __init__(
        self,
        carelink_refresh_token,
        carelink_token,
        client_id,
        client_secret,
        mag_identifier,
        carelink_patient_id,
        config_path=None,
        entry_id=None
    ):

        # Auth info
        self.__carelink_refresh_token = carelink_refresh_token
        self.__carelink_access_token = carelink_token
        self.__client_id = client_id
        self.__client_secret = client_secret
        self.__mag_identifier = mag_identifier
        self.__token_data = None
        self.__access_token_payload = None
        # helper token data
        self.__auth_token_validto = None

        # Session info
        self.__carelink_patient_id = carelink_patient_id

        # Config path for storing auth file (unique per entry_id to support multiple instances)
        if entry_id:
            auth_filename = f"{AUTH_FILE_PREFIX}_{entry_id}.json"
        else:
            auth_filename = f"{AUTH_FILE_PREFIX}.json"

        if config_path:
            self.__auth_file_path = os.path.join(config_path, auth_filename)
            self.__legacy_auth_file_path = os.path.join(config_path, LEGACY_AUTH_FILE)
        else:
            self.__auth_file_path = auth_filename
            self.__legacy_auth_file_path = LEGACY_AUTH_FILE
        self.__session_user = None
        self.__session_username = None
        self.__session_config = None
        self.__session_country = None

        # State info
        self.__initialized = False
        self.__last_response_code = None

        self._async_client = None

        self.__common_headers = {
                # Common browser headers
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 10; Nexus 5X Build/QQ3A.200805.001)",
                }

    @property
    def async_client(self):
        """Return the httpx client."""
        if not self._async_client:
            self._async_client = httpx.AsyncClient()
        return self._async_client

    async def close(self):
        """Close the HTTP client."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

    async def fetch_async(self, url, headers, params=None):
        """Perform an async get request."""
        response = await self.async_client.get(
            url,
            headers=headers,
            params=params,
            follow_redirects=True,
            timeout=30,
        )
        return response

    async def post_async(self, url, headers, data=None, params=None):
        """Perform an async post request."""
        response = await self.async_client.post(
            url,
            headers=headers,
            params=params,
            data=data,
            follow_redirects=True,
            timeout=30,
        )
        return response

    async def __get_data(self, path, query_params, request_body):
        printdbg("__get_data()")
        if path is None:
            url = self.__session_config["baseUrlCumulus"] + "/display/message"
        else:
            url = path
        payload = query_params
        data = request_body
        jsondata = None

        # Get auth token
        if await self.__handle_authorization_token():
            try:
                # Add header
                headers = self.__common_headers
                if "mag-identifier" in self.__token_data:
                    headers["mag-identifier"] = self.__token_data["mag-identifier"]
                headers["Authorization"] = "Bearer " + self.__token_data["access_token"]
                if data is None:
                    headers["Accept"] = "application/json, text/plain, */*"
                    headers["Content-Type"] = "application/json; charset=utf-8"
                    response = await self.fetch_async(
                        url, headers=headers, params=payload
                    )
                    self.__last_response_code = response.status_code
                    if not response.status_code == 200:
                        raise ValueError(
                            f"__get_data() session response is not OK: {response.status_code}"
                        )
                else:
                    headers["Accept"] = (
                        "text/html,application/xhtml+xml,application/xml;q=0.9,"
                        "image/avif,image/webp,image/apng,*/*;q=0.8,"
                        "application/signed-exchange;v=b3;q=0.9"
                    )
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                    response = await self.post_async(url, headers=headers, data=data)
                    self.__last_response_code = response.status_code
                    if not response.status_code == 200:
                        raise ValueError(
                            f"__get_data() session response is not OK: {response.status_code}"
                        )
            except httpx.TimeoutException as error:
                printdbg(f"__get_data() failed: request timeout - {error}")
            except httpx.RequestError as error:
                printdbg(f"__get_data() failed: network error - {error}")
            except (ValueError, KeyError, json.JSONDecodeError) as error:
                printdbg(f"__get_data() failed: response error - {error}")
            else:
                jsondata = json.loads(response.text)

        return jsondata

    def __select_patient(self, patients):
        patient = None
        if patients is not None:
            for p in patients:
                if p["status"] == "ACTIVE":
                    patient = p
                    break
        return patient

    async def __get_patients(self):
        printdbg("__get_patients()")
        url = self.__session_config["baseUrlCareLink"] + "/links/patients"
        return await self.__get_data(
            url, None, None
        )

    async def __get_my_user(self):
        printdbg("__get_my_user()")
        url = self.__session_config["baseUrlCareLink"] + "/users/me"
        resp = await self.__get_data(
            url, None, None)
        return resp

    async def __get_config_settings(self):
        printdbg("__get_config_settings()")
        try:
            resp = await self.fetch_async(CARELINK_CONFIG_URL, self.__common_headers)
            self.__last_response_code = resp.status_code
            if not resp.status_code == 200:
                raise ValueError(
                    f"__get_config_settings() CARELINK_CONFIG_URL response is not OK: {resp.status_code}"
                )
            data = resp.json()
            region = None
            config = None

            for c in data["supportedCountries"]:
                try:
                    region = c[self.__session_country.upper()]["region"]
                    break
                except KeyError:
                    pass
            if region is None:
                raise ValueError(f"ERROR: country code {self.__session_country} is not supported")
            printdbg(f"User region: {region}")

            for c in data["CP"]:
                if c["region"] == region:
                    config = c
                    break
            if config is None:
                raise ValueError(f"ERROR: failed to get config base urls for region {region}")

            sso_configuration_key = config["UseSSOConfiguration"]

            resp = await self.fetch_async(config[sso_configuration_key], self.__common_headers)
            self.__last_response_code = resp.status_code
            if not resp.status_code == 200:
                raise ValueError(
                    f"__get_config_settings() SSOConfiguration response is not OK: {resp.status_code}"
                )
            sso_config = resp.json()
            hostname = sso_config["server"]["hostname"]
            port = sso_config["server"]["port"]
            prefix = sso_config["server"]["prefix"]
            sso_base_url = f"https://{hostname}:{port}/{prefix}"
            if sso_base_url.endswith('/'):
                sso_base_url = sso_base_url[:-1] # remove trailing slash if prefix is empty
            token_url = sso_base_url + sso_config["system_endpoints"]["token_endpoint_path"]
            config["token_url"] = token_url
        except Exception as e:
            printdbg(e)
        return config

    # Periodic data from CareLink Cloud
    async def __get_connect_display_message(
        self, username, role, patient_id=None
    ):
        printdbg("__get_connect_display_message()")

        # Build user json for request
        user_json = {"username": username, "role": role}

        if patient_id:
            user_json["patientId"] = patient_id

        request_body = json.dumps(user_json)
        recent_data = await self.__get_data(None, None, request_body)
        return recent_data

    async def _get_access_token_payload(self, token_data):
        printdbg("_get_access_token_payload()")
        try:
            token = token_data["access_token"]
        except (KeyError, TypeError):
            printdbg("no access token found")
            return None
        try:
            # Decode json web token payload
            payload_b64 = token.split('.')[1]
            payload_b64_bytes = payload_b64.encode()
            missing_padding = (4 - len(payload_b64_bytes) % 4) % 4
            if missing_padding:
                payload_b64_bytes += b'=' * missing_padding
            payload_bytes = base64.b64decode(payload_b64_bytes)
            payload = payload_bytes.decode()
            payload_json = json.loads(payload)

            # Get expiration time stamp
            token_validto = payload_json["exp"]
            token_validto -= 600
        except (KeyError, IndexError, ValueError, json.JSONDecodeError) as error:
            printdbg(f"Malformed access token: {error}")
            return None
        # Save expiration time
        token_dt = datetime.fromtimestamp(token_validto, tz=timezone.utc)
        self.__auth_token_validto = token_dt.strftime('%a %b %d %H:%M:%S UTC %Y')
        return payload_json

    async def __execute_init_procedure(self):
        printdbg("__execute_init_procedure()")
        if not self.__initialized:
            self.__token_data = await self._process_token_file(self.__auth_file_path)

            if self.__token_data is None:
                return
            self.__access_token_payload = await self._get_access_token_payload(self.__token_data)
            if self.__access_token_payload is None:
                return
            try:
                self.__session_country = self.__access_token_payload["token_details"]["country"]

                self.__session_config = await self.__get_config_settings()

                self.__session_username = self.__access_token_payload["token_details"]["preferred_username"]
                self.__session_user = await self.__get_my_user()

                if self.__session_user["role"] in ["CARE_PARTNER","CARE_PARTNER_OUS"]:
                    if not self.__carelink_patient_id:
                        session_patients = await self.__get_patients()
                        patient = self.__select_patient(session_patients)
                        if patient:
                            self.__carelink_patient_id = patient["username"]
                            printdbg("Found patient [REDACTED] [REDACTED] ([REDACTED])")
                        else:
                            printdbg("No patient found.")
            except Exception as error:
                printdbg(f"__execute_init_procedure() failed: exception {error}")
                if self.__last_response_code in AUTH_ERROR_CODES:
                    try:
                        if await self.__refresh_token(self.__session_config, self.__token_data):
                            if await self._get_access_token_payload(self.__token_data):
                                printdbg(f"New token is valid until {self.__auth_token_validto}")
                                await self._write_token_file(self.__token_data, self.__auth_file_path)
                    except Exception as e:
                        printdbg(e)
                    return
            self.__initialized = True
        return

    async def __refresh_token(self, config, token_data):
        printdbg("__refresh_token")
        success = False
        token_url = config["token_url"]

        user_data = {
                "refresh_token": token_data["refresh_token"],
                "client_id":     token_data["client_id"],
                "grant_type":    "refresh_token"
                }
        if "client_secret" in token_data:
            user_data["client_secret"] = token_data["client_secret"]
        try:
            headers = {}
            if "mag-identifier" in token_data:
                headers["mag-identifier"] = token_data["mag-identifier"]
            printdbg("Trying to refresh token")
            response = await self.post_async(url=token_url, headers=headers, data=user_data)
            self.__last_response_code = response.status_code
            if self.__last_response_code == 200:
                printdbg("Refreshed token successfully")
                response_data = response.json()
                self.__token_data["access_token"] = response_data["access_token"]
                self.__token_data["refresh_token"] = response_data["refresh_token"]
                success = True
            else:
                raise ValueError(f"Failed to refresh token ({self.__last_response_code})")
        except httpx.TimeoutException as error:
            printdbg(f"Token refresh failed: request timeout - {error}")
            success = False
        except httpx.RequestError as error:
            printdbg(f"Token refresh failed: network error - {error}")
            success = False
        except (ValueError, KeyError, json.JSONDecodeError) as error:
            printdbg(f"Token refresh failed: {error}")
            success = False
        return success

    async def __handle_authorization_token(self):
        printdbg("__handle_authorization_token()")
        if await self._get_access_token_payload(self.__token_data):
            auth_token_validto = self.__auth_token_validto
        else:
            printdbg("No valid token")
            return False

        token_time = datetime.strptime(auth_token_validto, '%a %b %d %H:%M:%S UTC %Y')
        token_time = token_time.replace(tzinfo=timezone.utc)
        time_remaining = token_time - datetime.now(tz=timezone.utc)
        if time_remaining < timedelta(seconds=AUTH_EXPIRE_DEADLINE_MINUTES * 60):
            printdbg(f"Current token is valid until {self.__auth_token_validto}")
            if await self.__refresh_token(self.__session_config, self.__token_data):
                if await self._get_access_token_payload(self.__token_data):
                    printdbg(f"New token is valid until {self.__auth_token_validto}")
                    await self._write_token_file(self.__token_data, self.__auth_file_path)
        return True

    # Wrapper for data retrival methods
    async def get_recent_data(self):
        """Get most recent data."""
        # Force login to get basic info
        if await self.__handle_authorization_token():
            if self.__session_user is None:
                _LOGGER.error("Session user is None. Cannot fetch recent data.")
                return None
            role = (
                "carepartner"
                if self.__session_user["role"]
                in ["CARE_PARTNER", "CARE_PARTNER_OUS"]
                else "patient"
            )
            return await self.__get_connect_display_message(
                self.__session_username,
                role,
                self.__carelink_patient_id,
            )
        return None

    async def _write_token_file(self, obj, filename):
        printdbg("_write_token_file()")
        directory = os.path.dirname(filename)
        if directory:
            await asyncio.to_thread(os.makedirs, directory, exist_ok=True)
        async with aiofiles.open(filename, 'w') as f:
            await f.write(json.dumps(obj, indent=4))

    async def _process_token_file(self, filename):
        printdbg("_process_token_file()")
        token_data = None
        file_exists = False
        used_legacy = False
        try:
            async with aiofiles.open(filename, mode="r") as f:
                token_data = json.loads(await f.read())
                file_exists = True
        except FileNotFoundError:
            printdbg(f"Authentification file {filename} does not exist.")
            # Try legacy location as fallback
            try:
                async with aiofiles.open(self.__legacy_auth_file_path, mode="r") as f:
                    token_data = json.loads(await f.read())
                    file_exists = True
                    used_legacy = True
                    printdbg(f"Found token file at legacy location: {self.__legacy_auth_file_path}")
            except FileNotFoundError:
                printdbg(f"Legacy auth file {self.__legacy_auth_file_path} also does not exist.")
            except (OSError, json.JSONDecodeError) as error:
                printdbg(f"ERROR: failed parsing legacy token file: {error}")
        except (OSError, json.JSONDecodeError) as error:
            printdbg(f"ERROR: failed parsing token file {filename}: {error}")
            file_exists = True  # File exists but failed to parse

        if file_exists:
            cfg_complete = True
            if token_data is not None:
                required_fields = ["access_token", "refresh_token", "client_id"]
                for field in required_fields:
                    if field not in token_data:
                        printdbg(f"ERROR: field {field} is missing from token file")
                        cfg_complete = False
            if not cfg_complete:
                token_data = None
            elif used_legacy and token_data is not None:
                # Copy token from legacy location to new location for future use
                printdbg(f"Copying token from legacy location to {filename}")
                await self._write_token_file(token_data, filename)
        else:
            if self.__carelink_access_token and self.__carelink_refresh_token and self.__client_id:
                printdbg("Found static configuration. Create Authentificaiton file.")
                token_data = {"access_token": self.__carelink_access_token,
                             "refresh_token": self.__carelink_refresh_token,
                             "client_id": self.__client_id,
                             }
                if self.__client_secret:
                    token_data["client_secret"] = self.__client_secret
                if self.__mag_identifier:
                    token_data["mag-identifier"] = self.__mag_identifier
                await self._write_token_file(token_data, filename)
            else:
                printdbg("ERROR: No sufficient configuration found")
        return token_data

    # Authentication methods
    async def login(self):
        """perform login"""
        if not self.__initialized:
            await self.__execute_init_procedure()
        return self.__initialized

    def run_in_console(self):
        """If running this module directly, print all the values in the console."""
        print("Reading...")
        asyncio.run(self.login())
        if self.__initialized:
            result = asyncio.run(self.get_recent_data())
            print(f"data: {result}")

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Retrieve recent data from last 24h from Medtronic Carelink."
    )
    parser.add_argument("-i", "--patientId", dest="carelink_patient", help="Carelink Patient ID")
    parser.add_argument("-t", "--token", dest="token", help="Carelink Token")
    parser.add_argument("-r", "--rtoken", dest="refresh_token", help="Refresh Token")
    parser.add_argument("-c", "--clientid", dest="client_id", help="Client ID")
    parser.add_argument("-s", "--secret", dest="client_secret", help="Client Secret")
    parser.add_argument("-m", "--mag", dest="mag_identifier", help="Mag Identifier")
    args = parser.parse_args()

    TESTAPI = CarelinkClient(
        carelink_token = args.token,
        carelink_patient_id = args.carelink_patient,
        carelink_refresh_token = args.refresh_token,
        client_id = args.client_id,
        client_secret = args.client_secret,
        mag_identifier = args.mag_identifier
    )

    TESTAPI.run_in_console()
