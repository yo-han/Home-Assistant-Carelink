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
from datetime import datetime, timedelta
import json
import logging
import time
import base64
from urllib.parse import parse_qsl, urlparse, urlunparse

import httpx

# Version string
VERSION = "0.3"

# Constants
CARELINK_CONNECT_SERVER_EU = "carelink.minimed.eu"
CARELINK_CONNECT_SERVER_US = "carelink.minimed.com"
CARELINK_LANGUAGE_EN = "en"
CARELINK_AUTH_TOKEN_COOKIE_NAME = "auth_tmp_token"
CARELINK_TOKEN_VALIDTO_COOKIE_NAME = "c_token_valid_to"
AUTH_EXPIRE_DEADLINE_MINUTES = 10

DEBUG = True

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
        carelink_country,
        carelink_token,
        carelink_patient_id=None,
    ):

        # User info
        self.__carelink_country = carelink_country.lower()
        _LOGGER.debug("Carelink country: %s", self.__carelink_country)
        self.__carelink_auth_token = carelink_token
        self.__auth_token_validto = None
        
        self.__carelink_patient_id = carelink_patient_id

        # Session info
        self.__session_user = None
        self.__session_profile = None
        self.__session_country_settings = None
        self.__session_monitor_data = None

        # State info
        self.__logged_in = False
        self.__last_data_success = False
        self.__last_response_code = None
        self.__last_error_message = None

        self._async_client = None
        self._cookies = None
        self.__common_headers = {
             # Common browser headers
             "Accept-Language": "en;q=0.9, *;q=0.8",
             "Connection": "keep-alive",
             "sec-ch-ua":"\"Google Chrome\";v=\"115\", \" Not;A Brand\";v=\"99\", \"Chromium\";v=\"115\"",
             "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
             "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
         }


    @property
    def async_client(self):
        """Return the httpx client."""
        if not self._async_client:
            self._async_client = httpx.AsyncClient()

        return self._async_client

    def get_last_data_success(self):
        """Return __last_data_success."""
        return self.__last_data_success

    def get_last_response_code(self):
        """Return __last_response_code."""
        return self.__last_response_code

    def getlast_error_message(self):
        """Return __last_error_message."""
        return self.__last_error_message

    def __carelink_server(self):
        """Return carelink server domain by country."""
        return (
            CARELINK_CONNECT_SERVER_US
            if self.__carelink_country == "us"
            else CARELINK_CONNECT_SERVER_EU
        )

    def __extract_response_data(self, response_body, begstr, endstr):
        """Return a clean stripped response_body by using begstr and endstr."""
        beg = response_body.find(begstr) + len(begstr)
        end = response_body.find(endstr, beg)
        return response_body[beg:end].strip('"')

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

    async def __get_data(self, host, path, query_params, request_body):
        printdbg("__get_data()")
        self.__last_data_success = False
        if host is None:
            url = path
        else:
            url = "https://" + host + "/" + path
        payload = query_params
        data = request_body
        jsondata = None

        # Get auth token
        auth_token = await self.__get_authorization_token()
        if auth_token is not None:
            try:
                # Add header
                headers = self.__common_headers
                headers["Authorization"] = auth_token
                if data is None:
                    headers["Accept"] = "application/json, text/plain, */*"
                    headers["Content-Type"] = "application/json; charset=utf-8"
                    response = await self.fetch_async(
                        url, headers=headers, params=payload
                    )
                    self.__last_response_code = response.status_code
                    if not response.status_code == 200:
                        raise ValueError(
                            "__get_data() session get response is not OK"
                            + str(response.status_code)
                        )
                else:
                    headers[
                        "Accept"
                    ] = "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9"
                    headers["Content-Type"] = "application/x-www-form-urlencoded"
                    response = await self.post_async(url, headers=headers, data=data)
                    self.__last_response_code = response.status_code
                    if not response.status_code == 200:
                        printdbg(response.status_code)
                        raise ValueError(
                            "__get_data() session get response is not OK"
                            + str(response.status_code)
                        )
            # pylint: disable=broad-except
            except Exception as error:
                printdbg(f"__get_data() failed: exception {error}")
            else:
                jsondata = json.loads(response.text)
                self.__last_data_success = True

        return jsondata

    async def __get_my_user(self):
        printdbg("__get_my_user()")
        return await self.__get_data(
            self.__carelink_server(), "patient/users/me", None, None
        )

    async def __get_my_profile(self):
        printdbg("__get_my_profile()")
        return await self.__get_data(
            self.__carelink_server(), "patient/users/me/profile", None, None
        )

    async def __get_country_settings(self, country, language):
        printdbg("__get_country_settings()")
        query_params = {"countryCode": country, "language": language}
        return await self.__get_data(
            self.__carelink_server(), "patient/countries/settings", query_params, None
        )

    async def __get_monitor_data(self):
        printdbg("__get_monitor_data()")
        return await self.__get_data(
            self.__carelink_server(),
            "patient/monitor/data",
            None,
            None,
        )

    # Old last24hours webapp data

    async def __get_last24_hours(self):
        printdbg("__get_last24_hours")
        query_params = {
            "cpSerialNumber": "NONE",
            "msgType": "last24hours",
            "requestTime": str(int(time.time() * 1000)),
        }
        return await self.__get_data(
            self.__carelink_server(), "patient/connect/data", query_params, None
        )

    # Periodic data from CareLink Cloud

    async def __get_connect_display_message(
        self, username, role, endpoint_url, patient_id=None
    ):
        printdbg("__get_connect_display_message()")

        # Build user json for request
        user_json = {"username": username, "role": role}

        if patient_id:
            user_json["patientId"] = patient_id

        request_body = json.dumps(user_json)
        recent_data = await self.__get_data(None, endpoint_url, None, request_body)
        if recent_data is not None:
            self.__correct_time_in_recent_data(recent_data)
        return recent_data

    def __correct_time_in_recent_data(self, recent_data):
        # TODO
        pass

    async def __execute_login_procedure(self):

        last_login_success = False
        self.__last_error_message = None
        try:
            # Clear cookies
            self.async_client.cookies.clear()

            # Clear basic infos
            self.__session_user = None
            self.__session_profile = None
            self.__session_country_settings = None
            self.__session_monitor_data = None

            # Get sessions infos if required
            if self.__session_user is None:
                self.__session_user = await self.__get_my_user()
            if self.__session_profile is None:
                self.__session_profile = await self.__get_my_profile()
            if self.__session_country_settings is None:
                self.__session_country_settings = await self.__get_country_settings(
                    self.__carelink_country, CARELINK_LANGUAGE_EN
                )
            if self.__session_monitor_data is None:
                self.__session_monitor_data = await self.__get_monitor_data()

            # Set login success if everything was ok:
            if (
                self.__session_user is not None
                and self.__session_profile is not None
                and self.__session_country_settings is not None
                and self.__session_monitor_data is not None
            ):
                last_login_success = True

        # pylint: disable=broad-except
        except Exception as error:
            printdbg(f"__execute_login_procedure() failed: exception {error}")
            self.__last_error_message = error

        self.__logged_in = last_login_success

        return last_login_success

    async def __checkAuthorizationToken(self):
        if self.__carelink_auth_token == None:
            printdbg("No initial token found")
            return False
        try:
            # Decode json web token payload
            payload_b64 = self.__carelink_auth_token.split('.')[1]
            payload_b64_bytes = payload_b64.encode()
            missing_padding = (4 - len(payload_b64_bytes) % 4) % 4
            #print("missing_padding: %d" % missing_padding)
            if missing_padding:
                payload_b64_bytes += b'=' * missing_padding
            payload_bytes = base64.b64decode(payload_b64_bytes)
            payload = payload_bytes.decode()
            payload_json = json.loads(payload)

            # Get expiration time stamp
            token_validto = payload_json["exp"]
            token_validto -= 600
        except:
            printdbg("Malformed initial token")
            return False

        # Check expiration time stamp
        tdiff = token_validto - time.time()
        if tdiff < 0:
            printdbg("Initial token has expired %ds ago" % abs(tdiff))
            return False
              # Save expiration time
        self.__auth_token_validto = datetime.utcfromtimestamp(token_validto).strftime('%a %b %d %H:%M:%S UTC %Y')
      
        printdbg("Initial token expires in %ds (%s)" % (tdiff,self.__auth_token_validto))
        return True

    async def __refreshToken(self, token):
        printdbg("Trying to refresh token")

        if token == None:
            printdbg("__refreshToken() no token to refresh")
            return False

        success = True
        url = "https://" + self.__carelink_server() + "/patient/sso/reauth"
        headers = self.__common_headers
        headers["Accept"] = "application/json, text/plain, */*"
        headers["Authorization"] = "Bearer " + token
        try:
            response = await self.fetch_async(url, headers = headers)
            self.__last_response_code = response.status_code
            if response.status_code == 200:
                printdbg("Token successfully refreshed")
            else:
                printdbg(response.status_code)
                raise ValueError("session post response is not OK")
        except Exception as e:
            printdbg(e)
            printdbg("Failed to refresh token (%d)" % response.status_code)
            success = False
        return success


    async def __get_authorization_token(self):
        try:
            auth_token = self.async_client.cookies[CARELINK_AUTH_TOKEN_COOKIE_NAME]
            auth_token_validto = self.async_client.cookies[CARELINK_TOKEN_VALIDTO_COOKIE_NAME]
        except:
            auth_token = self.__carelink_auth_token
            auth_token_validto = self.__auth_token_validto

            if auth_token == None or auth_token_validto == None:
                printdbg("No valid token")
                return None
            
        if (datetime.strptime(auth_token_validto, '%a %b %d %H:%M:%S UTC %Y') - datetime.utcnow()) < timedelta(seconds=AUTH_EXPIRE_DEADLINE_MINUTES*60):
            if await self.__refreshToken(auth_token):
                self.__carelink_auth_token = self.async_client.cookies[CARELINK_AUTH_TOKEN_COOKIE_NAME]
                self.__auth_token_validto = self.async_client.cookies[CARELINK_TOKEN_VALIDTO_COOKIE_NAME]
                # TODO: save token to file to reuse at restart
                printdbg("New token is valid until " + self.__auth_token_validto)
            else:
                # Refresh failed, manual login needed
                printdbg("Manual login needed")
                return None
            
        # there can be only one
        return "Bearer " + self.__carelink_auth_token

    # Wrapper for data retrival methods

    async def get_recent_data(self):
        """Get most recent data."""
        # Force login to get basic info
        if await self.__get_authorization_token() is not None:
            if (
                self.__carelink_country == "us"
                or "BLE" in self.__session_monitor_data["deviceFamily"]
            ):
                role = (
                    "carepartner"
                    if self.__session_user["role"]
                    in ["CARE_PARTNER", "CARE_PARTNER_OUS"]
                    else "patient"
                )
                return await self.__get_connect_display_message(
                    self.__session_profile["username"],
                    role,
                    self.__session_country_settings["blePereodicDataEndpoint"],
                    self.__carelink_patient_id,
                )
            else:
                return await self.__get_last24_hours()
        else:
            return None

    # Authentication methods
    async def login(self):
        """perform login"""
        if not self.__logged_in:
            if await self.__checkAuthorizationToken():
                await self.__execute_login_procedure()
        return self.__logged_in

    def run_in_console(self):
        """If running this module directly, print all the values in the console."""
        print("Reading...")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(asyncio.gather(self.login(), return_exceptions=False))
        if self.__logged_in:
            loop = asyncio.get_event_loop()
            results = loop.run_until_complete(
                asyncio.gather(
                    self.get_recent_data(),
                    return_exceptions=False,
                )
            )
            print(f"data: {results[0]}")


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Retrieve recent data from last 24h from Medtronic Carelink."
    )
    parser.add_argument("-t", "--token", dest="token", help="Carelink Token")
    parser.add_argument(
        "-i", "--patientId", dest="carelink_patient", help="Carelink Patient ID"
    )
    parser.add_argument(
        "-c",
        "--country",
        dest="country",
        help="Carelink Country (US, NL, DE, AU, UK, etc)",
    )

    args = parser.parse_args()

    if args.country is None:
        raise ValueError("Country is required")

    if args.token is None:
        raise ValueError("Token is required")

    TESTAPI = CarelinkClient(
        carelink_country=args.country,
        carelink_token = args.token,
        carelink_patient_id = args.carelink_patient
    )

    TESTAPI.run_in_console()
