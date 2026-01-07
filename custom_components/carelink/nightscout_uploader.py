import argparse
import asyncio
from datetime import datetime
import hashlib
import json
import logging

import httpx

from .const import (
    CARELINK_CODE_MAP,
)

NS_USER_AGENT= "Home Assistant Carelink"
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
        nightscout_secret
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

    @property
    def async_client(self):
        """Return the httpx client."""
        if not self._async_client:
            self._async_client = httpx.AsyncClient()

        return self._async_client

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
            printdbg(f"__setDeviceStatus() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "devicestatus"
        )

    async def __setSGS(self, rawdata, tz):
        printdbg("__setSGS()")
        try:
            data = self.__getSGS(rawdata, tz)
        except Exception as error:
            printdbg(f"__setSGS() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "entries"
        )

    async def __setBasal(self, rawdata, tz):
        printdbg("__setBasal()")
        try:
            data = self.__getBasal(rawdata, tz)
        except Exception as error:
            printdbg(f"__setBasal() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setBolus(self, rawdata, tz):
        printdbg("__setBolus()")
        try:
            data = self.__getBolus(rawdata, tz)
        except Exception as error:
            printdbg(f"__setBolus() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setAutoBolus(self, rawdata, tz):
        printdbg("__setAutoBolus()")
        try:
            data = self.__getAutoBolus(rawdata, tz)
        except Exception as error:
            printdbg(f"__setAutoBolus() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setAlarms(self, rawdata, tz):
        printdbg("__setAlarms()")
        try:
            data = self.__getAlarms(rawdata, tz)
        except Exception as error:
            printdbg(f"__setAlarms() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setMsgs(self, rawdata, tz):
        printdbg("__setMsgs()")
        try:
            data = self.__getMsgs(rawdata, tz)
        except Exception as error:
            printdbg(f"__setMsgs() exeption: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )

    async def __setAlerts(self, rawdata, tz):
        printdbg("__setAlerts()")
        try:
            data = self.__getAlerts(rawdata, tz)
        except Exception as error:
            printdbg(f"__setAlerts() exeption: {error}")
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
        try:
            for entry in data:
                response = await self.post_async(url, headers=self.__common_headers, data=json.dumps(entry))
                if not response.status_code == 200:
                    raise ValueError("__set_data() session response is not OK " + str(response.status_code))
        except Exception as error:
            printdbg(f"__set_data() failed: exception {error}")
            success = False
        return success

    def __getMsgs(self, rawdata, tz):
        msgs=self.__get_treatments(rawdata["clearedNotifications"], "type", "MESSAGE")
        return self.__getMsgEntries(msgs, tz)

    def __getAlarms(self, rawdata, tz):
        alarms=self.__get_treatments(rawdata["clearedNotifications"], "type", "ALARM")
        return self.__getMsgEntries(alarms, tz)

    def __getAlerts(self, rawdata, tz):
        alerts=self.__get_treatments(rawdata["clearedNotifications"], "type", "ALERT")
        return self.__getMsgEntries(alerts, tz)

    def __getMsgEntries(self, raw, tz):
        result = list()
        for msg in raw:
            date, date_string=self.__getDataStringFromIso(msg["dateTime"], tz)
            if "additionalInfo" in msg and "sg" in msg["additionalInfo"] and int(msg["additionalInfo"]["sg"]) < 400:
                result.append(dict(
                    timestamp=date,
                    enteredBy=NS_USER_AGENT,
                    created_at=date_string,
                    eventType="Note",
                    glucoseType="sensor",
                    glucose=float(msg["additionalInfo"]["sg"]),
                    notes=self.__getNote(CARELINK_CODE_MAP.setdefault(int(msg['faultId']), "Unknown"))
                    ))
            else:
                result.append(dict(
                    timestamp=date,
                    enteredBy=NS_USER_AGENT,
                    created_at=date_string,
                    eventType="Note",
                    notes=self.__getNote(CARELINK_CODE_MAP.setdefault(int(msg['faultId']), "Unknown"))
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
        response = await self.__setSGS(recent_data["sgs"], tz)
        if response:
            printdbg("sending SGS entries was ok")
        # Sending Basal
        response = await self.__setBasal(recent_data["markers"], tz)
        if response:
            printdbg("sending basal was ok")
        # Sending all Bolus
        response = await self.__setBolus(recent_data["markers"], tz)
        if response:
            printdbg("sending meal bolus was ok")
        # Sending all auto Bolus
        response = await self.__setAutoBolus(recent_data["markers"], tz)
        if response:
            printdbg("sending auto bolus was ok")
        # Sending alarms
        response = await self.__setAlarms(recent_data["notificationHistory"], tz)
        if response:
            printdbg("sending alarm notifications was ok")
        # Sending messages
        response = await self.__setMsgs(recent_data["notificationHistory"], tz)
        if response:
            printdbg("sending message notifications was ok")
        # Sending alerts
        response = await self.__setAlerts(recent_data["notificationHistory"], tz)
        if response:
            printdbg("sending alert notifications was ok")

    # Periodic upload to Nightscout
    async def send_recent_data(
        self, recent_data, timezone
    ):
        printdbg("__send_recent_data()")
        await self.__slice_recent_data_for_transmission(recent_data, timezone)

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