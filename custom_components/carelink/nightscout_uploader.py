import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
import re

import aiofiles
import httpx

from .const import (
    CARELINK_CODE_MAP,
)

NS_USER_AGENT= "Home Assistant Carelink"
DEDUP_RETENTION_HOURS = 25
TEMP_TARGET_MGDL = 150
# Grace past the banner's implied end (pump report time + remaining) before it is
# treated as stale/ended — guards against a cached banner and end-time jitter.
TEMP_TARGET_STALE_GRACE = timedelta(minutes=10)
# Two consecutive banners belong to the same session when their implied end times
# agree within this tolerance (absorbs integer-minute timeRemaining rounding).
TEMP_TARGET_END_TOLERANCE = timedelta(minutes=2)
DEBUG = False

_LOGGER = logging.getLogger(__name__)


def printdbg(msg):
    """Debug logger/print function"""
    _LOGGER.debug("Nightscout API: %s", msg)

    if DEBUG:
        print(msg)

class NightscoutUploader:
    """Nightscout Uploader library"""

    def __init__(
        self,
        nightscout_url,
        nightscout_secret,
        config_path=None,
        entry_id=None
    ):

        # Nightscout info
        self.__nightscout_url = nightscout_url.lower().rstrip('/')
        self.__hashedSecret = hashlib.sha1(nightscout_secret.encode('utf-8')).hexdigest()
        self.__is_reachable=False

        self._async_client = None
        self.__common_headers = {
            # Common browser headers
            'API-SECRET' : self.__hashedSecret,
            'Content-Type': "application/json",
            'User-Agent': NS_USER_AGENT,
            'Accept': 'application/json',
        }

        # Deduplication state
        if config_path and entry_id:
            self._dedup_file_path = os.path.join(
                config_path, f"carelink_ns_dedup_{entry_id}.json"
            )
        elif config_path or entry_id:
            _LOGGER.warning(
                "Deduplication disabled: both config_path and entry_id are required, "
                "got config_path=%s, entry_id=%s", config_path, entry_id
            )
            self._dedup_file_path = None
        else:
            self._dedup_file_path = None
        self._seen_fingerprints: dict[str, str] = {}
        self._dedup_loaded = False

        # Active temp target session state (persisted so the "post once per
        # session" guarantee survives restarts). The session identity is anchored
        # to the pump's reported end time (lastConduitDateTime + timeRemaining),
        # which is stable across polls of one session and in the past when the
        # banner is a stale cached snapshot.
        if self._dedup_file_path:
            self._temptarget_file_path = os.path.join(
                config_path, f"carelink_ns_temptarget_{entry_id}.json"
            )
        else:
            self._temptarget_file_path = None
        self._temp_target_session: dict | None = None
        self._temptarget_loaded = False

    async def async_client(self):
        """Return the httpx client."""
        if not self._async_client:
            self._async_client = await asyncio.to_thread(httpx.AsyncClient)

        return self._async_client

    async def close(self):
        """Close the HTTP client."""
        if self._async_client:
            await self._async_client.aclose()
            self._async_client = None

    @staticmethod
    def _compute_fingerprint(entry, data_type):
        """Compute a SHA-256 fingerprint for deduplication.

        Returns None for data types that should always be uploaded (devicestatus).
        """
        if data_type == "devicestatus":
            return None

        if data_type == "treatments":
            if entry.get("_dedupKey"):
                return hashlib.sha256(
                    str(entry["_dedupKey"]).encode("utf-8")
                ).hexdigest()
            key_fields = (
                str(entry.get("eventType", "")),
                str(entry.get("created_at", "")),
                str(entry.get("carbs", "")),
                str(entry.get("insulin", "")),
                str(entry.get("absolute", "")),
                str(entry.get("notes", "")),
                str(entry.get("glucose", "")),
            )
        elif data_type == "entries":
            key_fields = (
                str(entry.get("type", "")),
                str(entry.get("dateString", "")),
                str(entry.get("sgv", "")),
            )
        else:
            return None

        raw = "|".join(key_fields)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _load_dedup_state(self):
        """Load dedup state from disk (once per uploader lifetime)."""
        if self._dedup_loaded or not self._dedup_file_path:
            return
        try:
            async with aiofiles.open(self._dedup_file_path, mode="r") as f:
                self._seen_fingerprints = json.loads(await f.read())
        except FileNotFoundError:
            self._seen_fingerprints = {}
        except (json.JSONDecodeError, OSError) as error:
            _LOGGER.warning("Failed to load dedup state, starting fresh: %s", error)
            self._seen_fingerprints = {}
        self._dedup_loaded = True

    async def _save_dedup_state(self):
        """Persist dedup state to disk atomically."""
        if not self._dedup_file_path:
            return
        tmp_path = self._dedup_file_path + ".tmp"
        try:
            async with aiofiles.open(tmp_path, mode="w") as f:
                await f.write(json.dumps(self._seen_fingerprints))
            os.replace(tmp_path, self._dedup_file_path)
        except OSError as error:
            _LOGGER.warning("Failed to save dedup state: %s", error)

    async def _load_temptarget_state(self):
        """Load the active temp target session from disk (once per lifetime)."""
        if self._temptarget_loaded or not self._temptarget_file_path:
            return
        try:
            async with aiofiles.open(self._temptarget_file_path, mode="r") as f:
                self._temp_target_session = json.loads(await f.read())
        except FileNotFoundError:
            self._temp_target_session = None
        except (json.JSONDecodeError, OSError) as error:
            _LOGGER.warning("Failed to load temp target state, starting fresh: %s", error)
            self._temp_target_session = None
        self._temptarget_loaded = True

    async def _save_temptarget_state(self):
        """Persist the active temp target session to disk atomically."""
        if not self._temptarget_file_path:
            return
        tmp_path = self._temptarget_file_path + ".tmp"
        try:
            async with aiofiles.open(tmp_path, mode="w") as f:
                await f.write(json.dumps(self._temp_target_session))
            os.replace(tmp_path, self._temptarget_file_path)
        except OSError as error:
            _LOGGER.warning("Failed to save temp target state: %s", error)

    def _purge_old_fingerprints(self):
        """Remove fingerprints older than DEDUP_RETENTION_HOURS."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=DEDUP_RETENTION_HOURS)
        self._seen_fingerprints = {
            fp: ts for fp, ts in self._seen_fingerprints.items()
            if datetime.fromisoformat(ts) > cutoff
        }

    async def fetch_async(self, url, headers, params=None):
        """Perform an async get request."""
        client = await self.async_client()
        response = await client.get(
            url,
            headers=headers,
            params=params,
            follow_redirects=True,
            timeout=30,
        )
        return response

    async def post_async(self, url, headers, data=None, params=None):
        """Perform an async post request."""
        client = await self.async_client()
        response = await client.post(
            url,
            headers=headers,
            params=params,
            data=data,
            follow_redirects=True,
            timeout=30,
        )
        return response

    def __get_carbs(self, input_insulin, input_meal):
        result = dict()
        for marker in input_insulin:
            for entry in marker.items():
                for meal in input_meal:
                    if entry[0] in meal:
                        result[entry[0]]={"insulin" : entry[1] , "carb" : meal[entry[0]]}
        return result

    def __get_dict_values(self, input, key, value):
        result = list()
        for marker in input:
            markerDict=dict()
            if key in marker and marker["data"] and marker["data"]["dataValues"] and value in marker["data"]["dataValues"]:
                markerDict[marker[key]]=marker["data"]["dataValues"][value]
                result.append(markerDict)
        return result

    def __traverse(self, value, key=None):
        if isinstance(value, dict):
            for k, v in value.items():
                yield from self.__traverse(v, k)
        else:
            yield key, value

    def __get_treatments(self, input, key, value):
        result = list()
        for marker in input:
            markerDict=dict()
            isType=False
            for k, v in self.__traverse(marker):
                if key == k and v == value:
                    isType=True
                    break
            if isType:
                for entry in marker.items():
                    markerDict[entry[0]]=entry[1]
                result.append(markerDict)
        return result

    def __getDataStringFromIso(self, time, tz):
        dt = datetime.fromisoformat(time.replace(".000-00:00", ""))
        dt = dt.replace(tzinfo=tz)
        dt = dt.astimezone(tz)
        timestamp = dt.timestamp()
        date = int(timestamp * 1000)
        date_string = dt.isoformat()
        return date, date_string

    async def __setDeviceStatus(self, rawdata):
        printdbg("__setDeviceStatus()")
        try:
            data = self.__getDeviceStatus(rawdata)
        except Exception as error:
            printdbg(f"__setDeviceStatus() exception: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "devicestatus"
        )

    async def __setSGS(self, rawdata, tz):
        printdbg("__setSGS()")
        try:
            data = self.__getSGS(rawdata, tz)
        except Exception as error:
            printdbg(f"__setSGS() exception: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "entries"
        )

    async def __setBasal(self, rawdata, tz):
        printdbg("__setBasal()")
        try:
            data = self.__getBasal(rawdata, tz)
        except Exception as error:
            printdbg(f"__setBasal() exception: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setTempTarget(self, rawdata, tz):
        printdbg("__setTempTarget()")
        await self._load_temptarget_state()
        try:
            data = self.__getTempTarget(rawdata, tz, datetime.now(tz))
        except Exception as error:
            printdbg(f"__setTempTarget() exception: {error}")
            data = []
        result = await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )
        await self._save_temptarget_state()
        return result

    async def __setBolus(self, rawdata, tz):
        printdbg("__setBolus()")
        try:
            data = self.__getBolus(rawdata, tz)
        except Exception as error:
            printdbg(f"__setBolus() exception: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setAutoBolus(self, rawdata, tz):
        printdbg("__setAutoBolus()")
        try:
            data = self.__getAutoBolus(rawdata, tz)
        except Exception as error:
            printdbg(f"__setAutoBolus() exception: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setAlarms(self, rawdata, tz):
        printdbg("__setAlarms()")
        try:
            data = self.__getAlarms(rawdata, tz)
        except Exception as error:
            printdbg(f"__setAlarms() exception: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setMsgs(self, rawdata, tz):
        printdbg("__setMsgs()")
        try:
            data = self.__getMsgs(rawdata, tz)
        except Exception as error:
            printdbg(f"__setMsgs() exception: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setAlerts(self, rawdata, tz):
        printdbg("__setAlerts()")
        try:
            data = self.__getAlerts(rawdata, tz)
        except Exception as error:
            printdbg(f"__setAlerts() exception: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __set_data(self, host, data, data_type):
        printdbg("__set_data()")
        if len(data) == 0:
            return False
        success = True
        url = f"{host}/api/v1/{data_type}"
        skipped = 0
        uploaded = 0
        try:
            for entry in data:
                fingerprint = self._compute_fingerprint(entry, data_type)
                if fingerprint and fingerprint in self._seen_fingerprints:
                    skipped += 1
                    continue

                payload = {k: v for k, v in entry.items() if not k.startswith("_")}
                response = await self.post_async(url, headers=self.__common_headers, data=json.dumps(payload))
                if not response.status_code == 200:
                    raise ValueError("__set_data() session response is not OK " + str(response.status_code))

                uploaded += 1
                if fingerprint:
                    self._seen_fingerprints[fingerprint] = datetime.now(timezone.utc).isoformat()
        except httpx.TimeoutException as error:
            printdbg(f"__set_data() failed: request timeout - {error}")
            success = False
        except httpx.RequestError as error:
            printdbg(f"__set_data() failed: network error - {error}")
            success = False
        except ValueError as error:
            printdbg(f"__set_data() failed: {error}")
            success = False
        printdbg(f"__set_data() {data_type}: uploaded={uploaded}, skipped={skipped}")
        return success

    def __getMsgs(self, rawdata, tz):
        msgs = self.__get_treatments(rawdata.get("clearedNotifications", []), "type", "MESSAGE")
        return self.__getMsgEntries(msgs, tz)

    def __getAlarms(self, rawdata, tz):
        alarms = self.__get_treatments(rawdata.get("clearedNotifications", []), "type", "ALARM")
        return self.__getMsgEntries(alarms, tz)

    def __getAlerts(self, rawdata, tz):
        alerts = self.__get_treatments(rawdata.get("clearedNotifications", []), "type", "ALERT")
        return self.__getMsgEntries(alerts, tz)

    def __getMsgEntries(self, raw, tz):
        result = list()
        for msg in raw:
            date, date_string=self.__getDataStringFromIso(msg["dateTime"], tz)
            # Handle both numeric and string faultId values (Simplera sensor uses strings)
            fault_id = msg.get('faultId')
            try:
                message_id = CARELINK_CODE_MAP.get(int(fault_id), "Unknown") if fault_id is not None else "Unknown"
            except (ValueError, TypeError):
                message_id = str(fault_id) if fault_id else "Unknown"

            if "additionalInfo" in msg and "sg" in msg["additionalInfo"] and int(msg["additionalInfo"]["sg"]) < 400:
                result.append(dict(
                    timestamp=date,
                    enteredBy=NS_USER_AGENT,
                    created_at=date_string,
                    eventType="Note",
                    glucoseType="sensor",
                    glucose=float(msg["additionalInfo"]["sg"]),
                    notes=self.__getNote(message_id)
                    ))
            else:
                result.append(dict(
                    timestamp=date,
                    enteredBy=NS_USER_AGENT,
                    created_at=date_string,
                    eventType="Note",
                    notes=self.__getNote(message_id)
                    ))
        return result

    def __getNote(self, msg):
        return msg.replace("BC_SID_", "").replace("BC_MESSAGE_", "")

    def __getBolus(self, raw, tz):
        meal=self.__get_treatments(raw, "type", "MEAL")
        meal_carbs = self.__get_dict_values(meal, "timestamp", "amount")
        insulin=self.__get_treatments(raw, "type", "INSULIN")
        recomm=self.__get_treatments(insulin, "activationType", "RECOMMENDED")
        recomm_insulin=self.__get_dict_values(recomm, "timestamp", "deliveredFastAmount")
        bolus_carbs=self.__get_carbs(recomm_insulin, meal_carbs)
        return self.__getMealEntries(bolus_carbs, tz)

    def __getAutoBolus(self, raw, tz):
        insulin=self.__get_treatments(raw, "type", "INSULIN")
        autocorr=self.__get_treatments(insulin, "activationType", "AUTOCORRECTION")
        return self.__getAutoBolusEntries(autocorr, tz)

    def __getBasal(self, raw, tz):
        basal=self.__get_treatments(raw, "type", "AUTO_BASAL_DELIVERY")
        return self.__getBasalEntries(basal, tz)

    def __getTempTarget(self, rawdata, tz, now):
        banner = None
        for candidate in rawdata.get("pumpBannerState") or []:
            if candidate.get("type") == "TEMP_TARGET":
                banner = candidate
                break

        if banner is None:
            # No active temp target: end the current session (if any).
            self._temp_target_session = None
            return []

        time_remaining = banner.get("timeRemaining") or 0
        # Anchor the banner's end to the pump's last report time, not the wall
        # clock: this is stable across polls of one session, and already in the
        # past when CareLink keeps returning a cached banner after the pump
        # stopped reporting. Fall back to now only if the report time is missing.
        report_time = self.__parse_iso(rawdata.get("lastConduitDateTime"), tz) or now
        banner_end = report_time + timedelta(minutes=time_remaining)

        # Stale or already-ended banner: do not (re)create a session or upload.
        if now > banner_end + TEMP_TARGET_STALE_GRACE:
            self._temp_target_session = None
            return []

        # Start a new session when there is none, or when the end shifts beyond
        # the jitter tolerance (a cancel+restart, possibly missed between polls).
        session = self._temp_target_session
        if session is not None:
            try:
                prev_end = datetime.fromisoformat(session["end"])
            except (KeyError, TypeError, ValueError):
                prev_end = None
            if prev_end is None or abs(banner_end - prev_end) > TEMP_TARGET_END_TOLERANCE:
                session = None

        if session is None:
            created_at = now.isoformat()
            session = {
                "created_at": created_at,
                "dedup_key": f"Temporary Target|{created_at}",
                "duration": time_remaining,
                "end": banner_end.isoformat(),
            }
            self._temp_target_session = session

        return [dict(
            enteredBy=NS_USER_AGENT,
            eventType="Temporary Target",
            reason="Temp Target",
            duration=session["duration"],
            targetTop=TEMP_TARGET_MGDL,
            targetBottom=TEMP_TARGET_MGDL,
            created_at=session["created_at"],
            _dedupKey=session["dedup_key"],
            )]

    @staticmethod
    def __parse_iso(value, tz):
        """Parse a CareLink ISO timestamp; assume the site tz when none is given."""
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(re.sub(r"\.\d{3}Z$", "+00:00", value))
        except (ValueError, TypeError):
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt

    def __getSGS(self, raw, tz):
        sgs=self.__get_treatments(raw, "sensorState", "NO_ERROR_MESSAGE")
        return self.__getSGSEntries(sgs, tz)

    def __getBasalEntries(self, raw, tz):
        result = list()
        for basal in raw:
            _,date_string=self.__getDataStringFromIso(basal["timestamp"], tz)
            result.append(dict(
                enteredBy=NS_USER_AGENT,
                eventType="Temp Basal",
                duration=5,
                absolute=basal["data"]["dataValues"]["bolusAmount"],
                created_at=date_string,
                ))
        return result

    def __getAutoBolusEntries(self, raw, tz):
        result = list()
        for corr in raw:
            date, date_string=self.__getDataStringFromIso(corr["timestamp"], tz)
            result.append(dict(
                device=NS_USER_AGENT,
                timestamp=date,
                enteredBy=NS_USER_AGENT,
                created_at=date_string,
                eventType="Correction Bolus",
                insulin=corr["data"]["dataValues"]["deliveredFastAmount"],
                ))
        return result

    def __getMealEntries(self, meals, tz):
        result = list()
        for time, info in meals.items():
            date, date_string=self.__getDataStringFromIso(time, tz)
            result.append(dict(
                timestamp=date,
                enteredBy=NS_USER_AGENT,
                created_at=date_string,
                eventType="Meal",
                glucoseType="sensor",
                carbs=info["carb"],
                insulin=info["insulin"],
                ))
        return result

    def __ns_trend(self, present, past):
        if present["sg"] == 0 or past["sg"] == 0:
            return "null", "null"
        delta = present["sg"] - past["sg"]
        if delta == 0:
            trend = "Flat"
        elif delta < -30:
            trend = "TripleDown"
        elif delta < -15:
            trend = "DoubleDown"
        elif delta < -5:
            trend = "SingleDown"
        elif delta < 0:
            trend = "FortyFiveDown"
        elif delta > 30:
            trend = "TripleUp"
        elif delta > 15:
            trend = "DoubleUp"
        elif delta > 5:
            trend = "SingleUp"
        elif delta > 0:
            trend = "FortyFiveUp"
        else:
            trend = "NOT COMPUTABLE"
        return trend, delta

    def __getDeviceStatus(self, rawdata):
        return [dict(
            device=rawdata["medicalDeviceInformation"]["modelNumber"],
            pump=dict(
                battery=dict(
                    status=rawdata["conduitBatteryStatus"],
                    voltage=rawdata["conduitBatteryLevel"]),
                reservoir=rawdata["activeInsulin"]["amount"],
                status=dict(
                    status=rawdata["systemStatusMessage"],
                    suspended=rawdata["pumpSuspended"])))]

    def __getSGSEntries(self, sgs, tz):
        result = list()
        trend, delta="null", "null"
        for count, sg in enumerate(sgs):
            try:
                trend, delta = self.__ns_trend(sgs[count], sgs[count-1])
            except Exception:
                pass
            date, date_string=self.__getDataStringFromIso(sg["timestamp"], tz)
            result.append(dict(
                device=NS_USER_AGENT,
                direction=trend,
                delta=delta,
                type='sgv',
                sgv=float(sg["sg"]),
                date=date,
                dateString=date_string,
                noise=1))
        return result

    async def __slice_recent_data_for_transmission(self, recent_data, tz):
        # Sending device status
        response = await self.__setDeviceStatus(recent_data)
        if response:
            printdbg("sending device status was ok")
        # Sending all SGS
        sgs = recent_data.get("sgs")
        if sgs is not None:
            response = await self.__setSGS(sgs, tz)
            if response:
                printdbg("sending SGS entries was ok")
        else:
            printdbg("No SGS data available, skipping upload")
        # Sending Basal, Bolus, Auto Bolus (markers block)
        markers = recent_data.get("markers")
        if markers is not None:
            response = await self.__setBasal(markers, tz)
            if response:
                printdbg("sending basal was ok")
            response = await self.__setBolus(markers, tz)
            if response:
                printdbg("sending meal bolus was ok")
            response = await self.__setAutoBolus(markers, tz)
            if response:
                printdbg("sending auto bolus was ok")
        else:
            printdbg("No markers data available, skipping basal/bolus upload")
        # Sending Notifications (notificationHistory block)
        notification_history = recent_data.get("notificationHistory")
        if notification_history is not None:
            response = await self.__setAlarms(notification_history, tz)
            if response:
                printdbg("sending alarm notifications was ok")
            response = await self.__setMsgs(notification_history, tz)
            if response:
                printdbg("sending message notifications was ok")
            response = await self.__setAlerts(notification_history, tz)
            if response:
                printdbg("sending alert notifications was ok")
        else:
            printdbg("No notification history available, skipping notifications upload")
        # Sending Temp Target (pumpBannerState block)
        response = await self.__setTempTarget(recent_data, tz)
        if response:
            printdbg("sending temp target was ok")

    # Periodic upload to Nightscout
    async def send_recent_data(
        self, recent_data, timezone
    ):
        printdbg("__send_recent_data()")
        await self._load_dedup_state()
        self._purge_old_fingerprints()
        await self.__slice_recent_data_for_transmission(recent_data, timezone)
        await self._save_dedup_state()

    async def __test_server_connection(self):
        url = f"{self.__nightscout_url}/api/v1/devicestatus.json"
        response = await self.fetch_async(
                        url, headers=self.__common_headers, params={}
                    )
        if response.status_code == 200:
            self.__is_reachable = True

    # verify connection
    async def reachServer(self):
        """perform reach server check"""
        if not self.__is_reachable:
            await self.__test_server_connection()
        return self.__is_reachable

    def run_in_console(self, data):
        """If running this module directly"""
        print("Sending...")
        asyncio.run(self.reachServer())
        if self.__is_reachable:
            asyncio.run(self.send_recent_data(data))

if __name__ == "__main__":
    test_data={
                #fill me
            }
    parser = argparse.ArgumentParser(
        description="Simulate upload process to Nightscout with testdata"
    )
    parser.add_argument("-u", "--url", dest="url", help="Nightscout URL")
    parser.add_argument("-s", "--secret", dest="secret", help="Nightscout API Secret"
    )

    args = parser.parse_args()

    if args.url is None:
        raise ValueError("URL is required")

    if args.secret is None:
        raise ValueError("Secret is required")

    TESTAPI = NightscoutUploader(
        nightscout_url=args.url,
        nightscout_secret=args.secret
    )

    TESTAPI.run_in_console(test_data)
