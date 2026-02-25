"""Tandem Diabetes Source API client.

Implements OIDC/PKCE authentication against source.tandemdiabetes.com (US)
and source.eu.tandemdiabetes.com (EU) to fetch pump data for Tandem t:slim
insulin pumps.

Authentication flow:
1. POST credentials to login API
2. GET authorization endpoint with PKCE challenge (follows redirects to get code)
3. POST code + verifier to token endpoint (gets access_token + id_token)
4. Decode JWT id_token to extract pumperId and accountId

Data sources:
- Tandem Source API: pump metadata (serial, model, last upload)
- ControlIQ API: therapy timeline (CGM, bolus, basal) and summary statistics
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import ssl
import struct
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse, parse_qs

import certifi
import httpx

_LOGGER = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
)


class TandemAuthError(Exception):
    """Raised when authentication fails."""


class TandemApiError(Exception):
    """Raised when an API call fails."""


# ── Binary pump event decoder ────────────────────────────────────────
# The Tandem Source pumpevents API returns base64-encoded binary data.
# Each record is 26 bytes (big-endian). Format based on tconnectsync
# event parser (https://github.com/jwoglom/tconnectsync).

EVENT_LEN = 26
TANDEM_EPOCH = 1199145600  # 2008-01-01 00:00:00 (local pump time)

# Event type IDs we care about
EVT_BASAL_RATE_CHANGE = 3
EVT_PUMPING_SUSPENDED = 11
EVT_PUMPING_RESUMED = 12
EVT_BG_READING_TAKEN = 16
EVT_BOLUS_COMPLETED = 20
EVT_BOLEX_COMPLETED = 21
EVT_CARTRIDGE_FILLED = 33
EVT_CARBS_ENTERED = 48
EVT_CANNULA_FILLED = 61
EVT_TUBING_FILLED = 63
EVT_AA_USER_MODE_CHANGE = 229
EVT_AA_PCM_CHANGE = 230
EVT_CGM_DATA_GXB = 256
EVT_BASAL_DELIVERY = 279
EVT_BOLUS_DELIVERY = 280


def decode_pump_events(raw_b64: str) -> list[dict]:
    """Decode base64-encoded binary pump events into a list of dicts.

    Each returned dict contains:
        event_id: int - event type identifier
        event_name: str - human-readable event name
        timestamp: datetime - event timestamp (UTC)
        seq: int - sequence number
        ... event-specific fields
    """
    try:
        raw_bytes = base64.b64decode(raw_b64)
    except Exception as e:
        _LOGGER.error("Failed to base64-decode pump events: %s", e)
        return []

    num_events = len(raw_bytes) // EVENT_LEN
    _LOGGER.debug(
        "Decoding %d pump events (%d bytes)", num_events, len(raw_bytes)
    )

    events = []
    event_id_counts: dict[int, int] = {}
    for i in range(num_events):
        chunk = raw_bytes[i * EVENT_LEN : (i + 1) * EVENT_LEN]
        if len(chunk) < EVENT_LEN:
            break

        # Header (bytes 0-9)
        source_and_id = struct.unpack_from(">H", chunk, 0)[0]
        event_id = source_and_id & 0x0FFF
        ts_raw = struct.unpack_from(">I", chunk, 2)[0]
        seq = struct.unpack_from(">I", chunk, 6)[0]
        payload = chunk[10:26]  # 16-byte data payload

        # Tandem timestamps are LOCAL pump time (seconds since 2008-01-01
        # midnight local).  Create a naive datetime so the coordinator can
        # attach the correct pump timezone via .replace(tzinfo=tz).
        ts = datetime.utcfromtimestamp(TANDEM_EPOCH + ts_raw)
        event_id_counts[event_id] = event_id_counts.get(event_id, 0) + 1

        evt = {
            "event_id": event_id,
            "timestamp": ts,
            "seq": seq,
        }

        # Parse event-specific payload fields
        if event_id == EVT_CGM_DATA_GXB:
            evt["event_name"] = "CGM"
            # uint16 at payload offset 4 = glucose in mg/dL
            glucose = struct.unpack_from(">H", payload, 4)[0]
            # int8 at payload offset 0 = rate of change (* 0.1 mg/dL/min)
            rate_raw = struct.unpack_from(">b", payload, 0)[0]
            status = struct.unpack_from(">H", payload, 2)[0]
            evt["glucose_mgdl"] = glucose
            evt["rate_of_change"] = round(rate_raw * 0.1, 1)
            evt["status"] = status  # 0=normal, 1=high, 2=low

        elif event_id == EVT_BOLUS_COMPLETED:
            evt["event_name"] = "BolusCompleted"
            bolus_id = struct.unpack_from(">H", payload, 0)[0]
            completion = struct.unpack_from(">H", payload, 2)[0]
            iob = struct.unpack_from(">f", payload, 4)[0]
            delivered = struct.unpack_from(">f", payload, 8)[0]
            requested = struct.unpack_from(">f", payload, 12)[0]
            evt["bolus_id"] = bolus_id
            evt["completion_status"] = completion  # 3 = Completed
            evt["iob"] = round(iob, 2)
            evt["insulin_delivered"] = round(delivered, 2)
            evt["insulin_requested"] = round(requested, 2)

        elif event_id == EVT_BOLUS_DELIVERY:
            evt["event_name"] = "BolusDelivery"
            bolus_type = struct.unpack_from(">B", payload, 0)[0]
            status = struct.unpack_from(">B", payload, 1)[0]
            bolus_id = struct.unpack_from(">H", payload, 2)[0]
            requested_now = struct.unpack_from(">H", payload, 4)[0]
            correction = struct.unpack_from(">H", payload, 8)[0]
            delivered_total = struct.unpack_from(">H", payload, 12)[0]
            evt["bolus_type"] = bolus_type
            evt["delivery_status"] = status  # 0=completed, 1=started
            evt["bolus_id"] = bolus_id
            evt["requested_now_mu"] = requested_now  # milliunits
            evt["correction_mu"] = correction
            evt["delivered_total_mu"] = delivered_total
            evt["insulin_delivered"] = round(delivered_total / 1000.0, 3)

        elif event_id == EVT_BASAL_RATE_CHANGE:
            evt["event_name"] = "BasalRateChange"
            commanded = struct.unpack_from(">f", payload, 0)[0]
            base_rate = struct.unpack_from(">f", payload, 4)[0]
            max_rate = struct.unpack_from(">f", payload, 8)[0]
            change_type = struct.unpack_from(">B", payload, 13)[0]
            evt["commanded_rate"] = round(commanded, 3)
            evt["base_rate"] = round(base_rate, 3)
            evt["max_rate"] = round(max_rate, 3)
            evt["change_type"] = change_type

        elif event_id == EVT_BASAL_DELIVERY:
            evt["event_name"] = "BasalDelivery"
            commanded_source = struct.unpack_from(">H", payload, 2)[0]
            profile_rate = struct.unpack_from(">H", payload, 4)[0]
            commanded_rate = struct.unpack_from(">H", payload, 6)[0]
            evt["commanded_source"] = commanded_source
            evt["profile_rate_mu"] = profile_rate  # milliunits/hr
            evt["commanded_rate_mu"] = commanded_rate
            evt["commanded_rate"] = round(commanded_rate / 1000.0, 3)

        elif event_id == EVT_PUMPING_SUSPENDED:
            evt["event_name"] = "PumpingSuspended"
            suspend_reason = struct.unpack_from(">B", payload, 0)[0]
            insulin_amount = struct.unpack_from(">f", payload, 4)[0]
            reason_map = {
                0: "User", 1: "Alarm", 2: "Malfunction", 3: "Auto (PLGS)",
            }
            evt["suspend_reason"] = reason_map.get(
                suspend_reason, f"Reason_{suspend_reason}"
            )
            evt["suspend_reason_id"] = suspend_reason
            evt["insulin_amount"] = round(insulin_amount, 2)

        elif event_id == EVT_PUMPING_RESUMED:
            evt["event_name"] = "PumpingResumed"
            pre_resume_state = struct.unpack_from(">B", payload, 0)[0]
            insulin_amount = struct.unpack_from(">f", payload, 4)[0]
            evt["pre_resume_state"] = pre_resume_state
            evt["insulin_amount"] = round(insulin_amount, 2)

        elif event_id == EVT_BG_READING_TAKEN:
            evt["event_name"] = "BGReading"
            bg = struct.unpack_from(">H", payload, 0)[0]
            iob = struct.unpack_from(">f", payload, 4)[0]
            entry_type = struct.unpack_from(">B", payload, 8)[0]
            type_map = {0: "Manual", 1: "Dexcom EGV"}
            evt["bg_mgdl"] = bg
            evt["iob"] = round(iob, 2)
            evt["entry_type"] = type_map.get(entry_type, f"Type_{entry_type}")

        elif event_id == EVT_BOLEX_COMPLETED:
            evt["event_name"] = "BolexCompleted"
            # Same structure as BOLUS_COMPLETED
            bolus_id = struct.unpack_from(">H", payload, 0)[0]
            completion = struct.unpack_from(">H", payload, 2)[0]
            iob = struct.unpack_from(">f", payload, 4)[0]
            delivered = struct.unpack_from(">f", payload, 8)[0]
            requested = struct.unpack_from(">f", payload, 12)[0]
            evt["bolus_id"] = bolus_id
            evt["completion_status"] = completion
            evt["iob"] = round(iob, 2)
            evt["insulin_delivered"] = round(delivered, 2)
            evt["insulin_requested"] = round(requested, 2)

        elif event_id == EVT_CARTRIDGE_FILLED:
            evt["event_name"] = "CartridgeFilled"
            insulin_volume = struct.unpack_from(">f", payload, 0)[0]
            evt["insulin_volume"] = round(insulin_volume, 1)

        elif event_id == EVT_CARBS_ENTERED:
            evt["event_name"] = "CarbsEntered"
            carbs = struct.unpack_from(">f", payload, 0)[0]
            evt["carbs"] = round(carbs)

        elif event_id == EVT_CANNULA_FILLED:
            evt["event_name"] = "CannulaFilled"
            prime_size = struct.unpack_from(">f", payload, 0)[0]
            completion = struct.unpack_from(">H", payload, 4)[0]
            evt["prime_size"] = round(prime_size, 2)
            evt["completion_status"] = completion

        elif event_id == EVT_TUBING_FILLED:
            evt["event_name"] = "TubingFilled"
            prime_size = struct.unpack_from(">f", payload, 0)[0]
            completion = struct.unpack_from(">H", payload, 4)[0]
            evt["prime_size"] = round(prime_size, 2)
            evt["completion_status"] = completion

        elif event_id == EVT_AA_USER_MODE_CHANGE:
            evt["event_name"] = "UserModeChange"
            current_mode = struct.unpack_from(">B", payload, 0)[0]
            previous_mode = struct.unpack_from(">B", payload, 1)[0]
            mode_map = {
                0: "Normal", 1: "Sleep", 2: "Exercise", 3: "Eating Soon",
            }
            evt["current_mode"] = mode_map.get(
                current_mode, f"Mode_{current_mode}"
            )
            evt["previous_mode"] = mode_map.get(
                previous_mode, f"Mode_{previous_mode}"
            )
            evt["current_mode_id"] = current_mode
            evt["previous_mode_id"] = previous_mode

        elif event_id == EVT_AA_PCM_CHANGE:
            evt["event_name"] = "PCMChange"
            current_pcm = struct.unpack_from(">B", payload, 0)[0]
            previous_pcm = struct.unpack_from(">B", payload, 1)[0]
            pcm_map = {
                0: "No Control", 1: "Open Loop", 2: "Pining",
                3: "Closed Loop",
            }
            evt["current_pcm"] = pcm_map.get(
                current_pcm, f"PCM_{current_pcm}"
            )
            evt["previous_pcm"] = pcm_map.get(
                previous_pcm, f"PCM_{previous_pcm}"
            )

        else:
            evt["event_name"] = f"Event_{event_id}"
            continue  # Skip events we don't need

        events.append(evt)

    # Log event ID distribution for diagnostics
    _LOGGER.debug(
        "Tandem: Raw event ID counts: %s",
        dict(sorted(event_id_counts.items()))
    )

    return events


class TandemSourceClient:
    """Async API client for Tandem Diabetes Source platform."""

    LOGIN_PAGE_URL = "https://sso.tandemdiabetes.com/"

    _REGION_URLS = {
        "EU": {
            "LOGIN_API": "https://tdcservices.eu.tandemdiabetes.com/accounts/api/login",
            "AUTHORIZE": "https://tdcservices.eu.tandemdiabetes.com/accounts/api/connect/authorize",
            "TOKEN": "https://tdcservices.eu.tandemdiabetes.com/accounts/api/connect/token",
            "JWKS": "https://tdcservices.eu.tandemdiabetes.com/accounts/api/.well-known/openid-configuration/jwks",
            "ISSUER": "https://tdcservices.eu.tandemdiabetes.com/accounts/api",
            "CLIENT_ID": "1519e414-eeec-492e-8c5e-97bea4815a10",
            "SOURCE_URL": "https://source.eu.tandemdiabetes.com/",
            "REDIRECT_URI": "https://source.eu.tandemdiabetes.com/authorize/callback",
            "TDC_BASE": "https://tdcservices.eu.tandemdiabetes.com/",
        },
        "US": {
            "LOGIN_API": "https://tdcservices.tandemdiabetes.com/accounts/api/login",
            "AUTHORIZE": "https://tdcservices.tandemdiabetes.com/accounts/api/connect/authorize",
            "TOKEN": "https://tdcservices.tandemdiabetes.com/accounts/api/connect/token",
            "JWKS": "https://tdcservices.tandemdiabetes.com/accounts/api/.well-known/openid-configuration/jwks",
            "ISSUER": "https://tdcservices.tandemdiabetes.com/accounts/api",
            "CLIENT_ID": "0oa27ho9tpZE9Arjy4h7",
            "SOURCE_URL": "https://source.tandemdiabetes.com/",
            "REDIRECT_URI": "https://sso.tandemdiabetes.com/auth/callback",
            "TDC_BASE": "https://tdcservices.tandemdiabetes.com/",
        },
    }

    def __init__(self, email: str, password: str, region: str = "EU"):
        self.email = email
        self.password = password
        self.region = region.upper()
        if self.region not in self._REGION_URLS:
            raise ValueError(f"Invalid region '{region}'. Must be 'US' or 'EU'.")
        self.urls = self._REGION_URLS[self.region]

        self.access_token: str | None = None
        self.id_token: str | None = None
        self.pumper_id: str | None = None
        self.account_id: str | None = None
        self.token_expires_at: float = 0

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client.

        Creates the SSL context in an executor to avoid blocking the event loop
        with load_verify_locations().
        """
        if self._client is None or self._client.is_closed:
            loop = asyncio.get_running_loop()
            ssl_ctx = await loop.run_in_executor(
                None,
                lambda: ssl.create_default_context(cafile=certifi.where()),
            )
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
                headers={"User-Agent": USER_AGENT},
                verify=ssl_ctx,
            )
        return self._client

    @staticmethod
    def _generate_code_verifier() -> str:
        """Generate a high-entropy PKCE code verifier."""
        return base64.urlsafe_b64encode(os.urandom(64)).decode("utf-8").rstrip("=")

    @staticmethod
    def _generate_code_challenge(verifier: str) -> str:
        """Generate S256 code challenge from verifier."""
        digest = hashlib.sha256(verifier.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    def _needs_login(self) -> bool:
        """Check if we need to (re)authenticate."""
        if not self.access_token:
            return True
        # Re-login 5 minutes before expiry
        return time.time() >= (self.token_expires_at - 300)

    async def login(self) -> bool:
        """Perform OIDC/PKCE authentication.

        Returns True on success, raises TandemAuthError on failure.
        """
        if not self._needs_login():
            return True

        client = await self._get_client()

        _LOGGER.debug("Tandem: Starting OIDC login for %s region", self.region)

        # Step 1: Initialize session (establish cookies)
        try:
            await client.get(self.LOGIN_PAGE_URL)
        except httpx.HTTPError as e:
            raise TandemAuthError(f"Cannot reach login page: {e}") from e

        # Step 2: POST credentials to login API
        try:
            login_resp = await client.post(
                self.urls["LOGIN_API"],
                json={"username": self.email, "password": self.password},
                headers={"Referer": self.LOGIN_PAGE_URL},
            )
        except httpx.HTTPError as e:
            raise TandemAuthError(f"Login request failed: {e}") from e

        if login_resp.status_code != 200:
            raise TandemAuthError(
                f"Login failed with HTTP {login_resp.status_code}"
            )

        login_json = login_resp.json()
        if login_json.get("status") != "SUCCESS":
            raise TandemAuthError("Login rejected by server")

        _LOGGER.debug("Tandem: Login credentials accepted")

        # Step 3: OIDC authorize with PKCE
        code_verifier = self._generate_code_verifier()
        code_challenge = self._generate_code_challenge(code_verifier)

        auth_params = {
            "client_id": self.urls["CLIENT_ID"],
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": self.urls["REDIRECT_URI"],
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        try:
            auth_resp = await client.get(
                self.urls["AUTHORIZE"] + "?" + urlencode(auth_params),
                headers={"Referer": self.LOGIN_PAGE_URL},
            )
        except httpx.HTTPError as e:
            raise TandemAuthError(f"Authorization request failed: {e}") from e

        # Extract authorization code from redirect URL
        final_url = str(auth_resp.url)
        parsed = urlparse(final_url)
        query_params = parse_qs(parsed.query)

        if "code" not in query_params:
            raise TandemAuthError(
                "No authorization code received in redirect"
            )

        auth_code = query_params["code"][0]
        _LOGGER.debug("Tandem: Got authorization code")

        # Step 4: Exchange code for tokens
        token_data = {
            "grant_type": "authorization_code",
            "client_id": self.urls["CLIENT_ID"],
            "code": auth_code,
            "redirect_uri": self.urls["REDIRECT_URI"],
            "code_verifier": code_verifier,
        }

        try:
            token_resp = await client.post(
                self.urls["TOKEN"],
                data=token_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.HTTPError as e:
            raise TandemAuthError(f"Token exchange failed: {e}") from e

        if token_resp.status_code // 100 != 2:
            raise TandemAuthError(
                f"Token exchange failed with HTTP {token_resp.status_code}"
            )

        token_json = token_resp.json()

        if "access_token" not in token_json:
            raise TandemAuthError("Missing access_token in token response")
        if "id_token" not in token_json:
            raise TandemAuthError("Missing id_token in token response")

        self.access_token = token_json["access_token"]
        self.id_token = token_json["id_token"]
        self.token_expires_at = time.time() + token_json.get("expires_in", 3600)

        # Step 5: Decode JWT to get pumperId and accountId
        self._extract_jwt_claims()

        _LOGGER.info(
            "Tandem: Login successful (pumperId=%s, region=%s)",
            self.pumper_id,
            self.region,
        )
        return True

    def _extract_jwt_claims(self):
        """Extract claims from the id_token JWT payload.

        We skip cryptographic verification since we received the token over
        HTTPS directly from the token endpoint.
        """
        parts = self.id_token.split(".")
        if len(parts) != 3:
            raise TandemAuthError("Invalid JWT format")

        # Base64url decode the payload (middle part)
        payload = parts[1]
        # Add padding
        payload += "=" * (4 - len(payload) % 4)

        try:
            claims = json.loads(base64.urlsafe_b64decode(payload))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
            raise TandemAuthError("Cannot decode JWT payload") from e

        self.pumper_id = claims.get("pumperId")
        self.account_id = claims.get("accountId")

        if not self.pumper_id:
            raise TandemAuthError("No pumperId found in JWT claims")

        _LOGGER.debug(
            "Tandem: JWT decoded - pumperId=%s, accountId=%s",
            self.pumper_id,
            self.account_id,
        )

    def _api_headers(self) -> dict:
        """Get headers for authenticated API requests."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": USER_AGENT,
        }

    async def _api_get(self, url: str, _retries: int = 2) -> dict:
        """Make an authenticated GET request with automatic re-login on 401.

        Retries transient network errors (connection reset, timeout, DNS)
        up to ``_retries`` times with a short back-off.
        """
        client = await self._get_client()
        last_exc: Exception | None = None

        for attempt in range(_retries + 1):
            try:
                resp = await client.get(url, headers=self._api_headers())
                break
            except (httpx.ConnectError, httpx.ReadError, httpx.WriteError,
                    httpx.PoolTimeout, httpx.ConnectTimeout,
                    httpx.ReadTimeout) as exc:
                last_exc = exc
                if attempt < _retries:
                    wait = 2 ** (attempt + 1)  # 2s, 4s
                    _LOGGER.debug(
                        "Tandem: transient error on %s (attempt %d/%d), "
                        "retrying in %ds: %s",
                        url, attempt + 1, _retries + 1, wait, exc,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise TandemApiError(
                        f"API GET {url} failed after {_retries + 1} attempts: "
                        f"{exc}"
                    ) from last_exc

        if resp.status_code == 401:
            _LOGGER.info("Tandem: Got 401, attempting re-login")
            self.access_token = None
            await self.login()
            resp = await client.get(url, headers=self._api_headers())

        if resp.status_code != 200:
            raise TandemApiError(
                f"API GET failed ({resp.status_code})"
            )

        return resp.json()

    # ── Tandem Source API endpoints ──────────────────────────────────────

    async def get_pumper_info(self) -> dict:
        """Get user and pump information."""
        return await self._api_get(
            f"{self.urls['SOURCE_URL']}api/pumpers/pumpers/{self.pumper_id}"
        )

    async def get_pump_event_metadata(self) -> list:
        """Get pump event metadata (serial, model, last upload, etc.).

        Returns a list of dicts, one per pump on the account. Each dict has:
        tconnectDeviceId, serialNumber, modelNumber, minDateWithEvents,
        maxDateWithEvents, lastUpload, patientName, patientDateOfBirth,
        patientCareGiver, softwareVersion, partNumber
        """
        return await self._api_get(
            f"{self.urls['SOURCE_URL']}api/reports/reportsfacade/"
            f"{self.pumper_id}/pumpeventmetadata"
        )

    # ── ControlIQ API endpoints ──────────────────────────────────────────
    # These use the TDC services base URL and may or may not accept the
    # Tandem Source OIDC access token. Failures are handled gracefully.

    async def get_therapy_timeline(
        self, start_date: str, end_date: str
    ) -> dict | None:
        """Fetch therapy timeline data (basal, bolus, CGM readings).

        Args:
            start_date: Date in MM-DD-YYYY format
            end_date: Date in MM-DD-YYYY format

        Returns dict with 'basal', 'bolus', 'cgm' keys, or None if unavailable.
        """
        try:
            user_guid = self.account_id or self.pumper_id
            url = (
                f"{self.urls['TDC_BASE']}tconnect/controliq/api/therapytimeline/"
                f"users/{user_guid}?startDate={start_date}&endDate={end_date}"
            )
            return await self._api_get(url)
        except (TandemApiError, httpx.HTTPError) as e:
            _LOGGER.debug("Therapy timeline not available: %s", e)
            return None

    async def get_dashboard_summary(
        self, start_date: str, end_date: str
    ) -> dict | None:
        """Fetch dashboard summary statistics.

        Args:
            start_date: Date in MM-DD-YYYY format
            end_date: Date in MM-DD-YYYY format

        Returns dict with averageReading, timeInUsePercent, etc. or None.
        """
        try:
            user_guid = self.account_id or self.pumper_id
            url = (
                f"{self.urls['TDC_BASE']}tconnect/controliq/api/summary/"
                f"users/{user_guid}?startDate={start_date}&endDate={end_date}"
            )
            return await self._api_get(url)
        except (TandemApiError, httpx.HTTPError) as e:
            _LOGGER.debug("Dashboard summary not available: %s", e)
            return None

    async def get_therapy_events(
        self, start_date: str, end_date: str
    ) -> dict | None:
        """Fetch therapy events used by the webui Therapy Timeline.

        Args:
            start_date: Date in MM-DD-YYYY format
            end_date: Date in MM-DD-YYYY format
        """
        try:
            user_guid = self.account_id or self.pumper_id
            url = (
                f"{self.urls['TDC_BASE']}tconnect/therapyevents/api/"
                f"TherapyEvents/{start_date}/{end_date}/false?userId={user_guid}"
            )
            _LOGGER.debug("Tandem: Attempting therapy_events API: %s", url)
            result = await self._api_get(url)
            _LOGGER.debug("Tandem: therapy_events returned type=%s", type(result).__name__)
            return result
        except (TandemApiError, httpx.HTTPError) as e:
            _LOGGER.debug("Therapy events API not available: %s", e)
            return None

    async def get_pump_events(
        self, device_id: str | int, start_date: str, end_date: str
    ) -> list[dict] | None:
        """Fetch and decode pump events from the Source Reports API.

        The pumpevents endpoint returns base64-encoded binary data using
        Tandem's proprietary 26-byte record format. This method fetches the
        raw response, decodes the binary, and returns structured event dicts.

        Args:
            device_id: tconnectDeviceId from pump metadata
            start_date: Date in YYYY-MM-DD format
            end_date: Date in YYYY-MM-DD format

        Returns list of decoded event dicts, or None if unavailable.
        """
        try:
            user_id = self.pumper_id or self.account_id

            # Request event types we need for sensor data
            event_ids = (
                "256,"   # CGM_DATA_GXB (glucose readings)
                "20,"    # BOLUS_COMPLETED (IOB, delivered, requested)
                "21,"    # BOLEX_COMPLETED (extended bolus completion)
                "280,"   # BOLUS_DELIVERY (bolus details)
                "3,"     # BASAL_RATE_CHANGE (basal rates)
                "279,"   # BASAL_DELIVERY (commanded rates)
                "11,"    # PUMPING_SUSPENDED
                "12,"    # PUMPING_RESUMED
                "16,"    # BG_READING_TAKEN (manual BG)
                "33,"    # CARTRIDGE_FILLED
                "48,"    # CARBS_ENTERED
                "61,"    # CANNULA_FILLED (site change)
                "63,"    # TUBING_FILLED
                "229,"   # AA_USER_MODE_CHANGE (sleep/exercise)
                "230"    # AA_PCM_CHANGE (Control-IQ mode)
            )

            url = (
                f"{self.urls['SOURCE_URL']}api/reports/reportsfacade/"
                f"pumpevents/{user_id}/{device_id}"
                f"?minDate={start_date}&maxDate={end_date}"
                f"&eventIds={event_ids}"
            )

            _LOGGER.debug(
                "Tandem: Fetching pump events: minDate=%s, maxDate=%s",
                start_date, end_date,
            )
            _LOGGER.debug("Tandem: Pump events URL: %s", url)

            # The pumpevents endpoint returns base64-encoded binary,
            # wrapped in a JSON string. Use _api_get which calls resp.json()
            # to unwrap the JSON string layer, then decode the binary.
            raw_response = await self._api_get(url)

            if not raw_response:
                _LOGGER.warning("Tandem: Pump events API returned no data")
                return None

            if isinstance(raw_response, str):
                # Base64-encoded binary wrapped in JSON string
                events = decode_pump_events(raw_response)
                _LOGGER.debug(
                    "Tandem: Decoded %d pump events from binary data",
                    len(events),
                )
                return events if events else None
            elif isinstance(raw_response, list):
                # Already decoded (unlikely but handle gracefully)
                _LOGGER.debug(
                    "Tandem: Pump events returned as list (%d items)",
                    len(raw_response),
                )
                return raw_response
            else:
                _LOGGER.warning(
                    "Tandem: Unexpected pump events response type: %s",
                    type(raw_response),
                )
                return None

        except (TandemApiError, httpx.HTTPError) as e:
            _LOGGER.error("Pump events API failed: %s", e, exc_info=True)
            return None

    # ── Unified data fetch ───────────────────────────────────────────────

    async def get_recent_data(self, pump_timezone: str | None = None) -> dict:
        """Fetch all available recent data from Tandem Source APIs.

        Parallelises independent API calls where possible.

        Args:
            pump_timezone: IANA timezone string (e.g. "Europe/London").
                           Used for the date range so we don't miss recent
                           data when the HA server is in a different zone.
                           Falls back to UTC if not provided.

        Returns a unified dict with keys:
            pump_metadata: dict or None
            pumper_info: dict or None
            pump_events: list or None  (from Source Reports API)
            therapy_timeline: dict or None  (from ControlIQ, often unavailable)
            dashboard_summary: dict or None  (from ControlIQ, often unavailable)
        """
        from zoneinfo import ZoneInfo

        try:
            tz = ZoneInfo(pump_timezone) if pump_timezone else ZoneInfo("UTC")
        except (KeyError, TypeError):
            tz = ZoneInfo("UTC")

        now_pump = datetime.now(tz)
        yesterday_pump = now_pump - timedelta(days=1)

        data: dict = {
            "pump_metadata": None,
            "pumper_info": None,
            "pump_events": None,
            "therapy_timeline": None,
            "dashboard_summary": None,
        }

        # ── Phase 1: metadata + pumper_info in parallel ──────────────
        metadata_result, pumper_result = await asyncio.gather(
            self._fetch_pump_metadata(),
            self._fetch_pumper_info(),
            return_exceptions=True,
        )

        if isinstance(metadata_result, BaseException):
            _LOGGER.warning("Failed to fetch pump metadata: %s", metadata_result)
        else:
            data["pump_metadata"] = metadata_result

        if isinstance(pumper_result, BaseException):
            _LOGGER.warning("Failed to fetch pumper info: %s", pumper_result)
        else:
            data["pumper_info"] = pumper_result

        # ── Phase 2: pump_events (needs device_id from metadata) ─────
        device_id = None
        if data["pump_metadata"]:
            device_id = data["pump_metadata"].get("tconnectDeviceId")

        if device_id:
            start_iso = yesterday_pump.strftime("%Y-%m-%d")
            end_iso = now_pump.strftime("%Y-%m-%d")
            try:
                data["pump_events"] = await self.get_pump_events(
                    device_id, start_iso, end_iso
                )
            except Exception as e:
                _LOGGER.warning("Failed to fetch pump events: %s", e)
        else:
            _LOGGER.debug(
                "Tandem: No tconnectDeviceId in metadata, skipping pump events"
            )

        # ── Phase 3: ControlIQ fallback (parallel) ───────────────────
        if not data["pump_events"]:
            start_mm = yesterday_pump.strftime("%m-%d-%Y")
            end_mm = now_pump.strftime("%m-%d-%Y")

            _LOGGER.debug(
                "Tandem: No pump_events, trying ControlIQ for %s to %s (tz=%s)",
                start_mm, end_mm, tz,
            )

            timeline_result, summary_result = await asyncio.gather(
                self.get_therapy_timeline(start_mm, end_mm),
                self.get_dashboard_summary(start_mm, end_mm),
                return_exceptions=True,
            )

            if isinstance(timeline_result, BaseException):
                _LOGGER.debug("Therapy timeline not available: %s", timeline_result)
            else:
                data["therapy_timeline"] = timeline_result

            if isinstance(summary_result, BaseException):
                _LOGGER.debug("Dashboard summary not available: %s", summary_result)
            else:
                data["dashboard_summary"] = summary_result

            if not data["therapy_timeline"]:
                _LOGGER.debug(
                    "Tandem: ControlIQ therapy timeline not available "
                    "(Source OIDC token may not be accepted by ControlIQ API)"
                )

        return data

    async def _fetch_pump_metadata(self) -> dict | None:
        """Fetch and extract first pump metadata entry."""
        metadata_list = await self.get_pump_event_metadata()
        if metadata_list and isinstance(metadata_list, list) and len(metadata_list) > 0:
            return metadata_list[0]
        if isinstance(metadata_list, dict):
            return metadata_list
        return None

    async def _fetch_pumper_info(self) -> dict | None:
        """Fetch pumper info."""
        return await self.get_pumper_info()

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


def parse_dotnet_date(date_str) -> datetime | None:
    """Parse .NET /Date(epoch_ms)/ or /Date(epoch_ms+offset)/ format.

    Also handles plain ISO 8601 date strings and epoch integers.
    Always returns UTC-aware datetimes so callers can safely use .astimezone().
    """
    if date_str is None:
        return None

    if isinstance(date_str, (int, float)):
        return datetime.fromtimestamp(
            date_str / 1000 if date_str > 1e12 else date_str,
            tz=timezone.utc,
        )

    if isinstance(date_str, str):
        # .NET date format: /Date(1234567890000)/ or /Date(1234567890000+0000)/
        match = re.match(r"/Date\((\d+)([+-]\d+)?\)/", date_str)
        if match:
            epoch_ms = int(match.group(1))
            return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)

        # ISO 8601 format
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            # Convert to UTC and keep timezone-aware
            return dt.astimezone(timezone.utc)
        except (ValueError, AttributeError):
            pass

    return None
