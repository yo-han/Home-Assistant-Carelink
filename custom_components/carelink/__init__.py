"""Medtronic arelink integration."""
from __future__ import annotations

import logging
import re

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.util.dt import DEFAULT_TIME_ZONE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)

from .api import CarelinkClient
from .nightscout_uploader import NightscoutUploader

from .const import (
    CLIENT,
    UPLOADER,
    DOMAIN,
    SCAN_INTERVAL,
    COORDINATOR,
    UNAVAILABLE,
    DEVICE_PUMP_MODEL,
    DEVICE_PUMP_NAME,
    DEVICE_PUMP_SERIAL,
    SENSOR_KEY_PUMP_BATTERY_LEVEL,
    SENSOR_KEY_CONDUIT_BATTERY_LEVEL,
    SENSOR_KEY_SENSOR_BATTERY_LEVEL,
    SENSOR_KEY_SENSOR_DURATION_HOURS,
    SENSOR_KEY_SENSOR_DURATION_MINUTES,
    SENSOR_KEY_LASTSG_MGDL,
    SENSOR_KEY_LASTSG_MMOL,
    SENSOR_KEY_UPDATE_TIMESTAMP,
    SENSOR_KEY_LASTSG_TIMESTAMP,
    SENSOR_KEY_LASTSG_TREND,
    SENSOR_KEY_SG_DELTA,
    SENSOR_KEY_RESERVOIR_LEVEL,
    SENSOR_KEY_RESERVOIR_AMOUNT,
    SENSOR_KEY_RESERVOIR_REMAINING_UNITS,
    SENSOR_KEY_ACTIVE_INSULIN,
    SENSOR_KEY_ACTIVE_INSULIN_ATTRS,
    SENSOR_KEY_LAST_ALARM,
    SENSOR_KEY_LAST_ALARM_ATTRS,
    SENSOR_KEY_ACTIVE_BASAL_PATTERN,
    SENSOR_KEY_AVG_GLUCOSE_MMOL,
    SENSOR_KEY_AVG_GLUCOSE_MGDL,
    SENSOR_KEY_BELOW_HYPO_LIMIT,
    SENSOR_KEY_ABOVE_HYPER_LIMIT,
    SENSOR_KEY_TIME_IN_RANGE,
    SENSOR_KEY_MAX_AUTO_BASAL_RATE,
    SENSOR_KEY_SG_BELOW_LIMIT,
    SENSOR_KEY_LAST_MEAL_MARKER,
    SENSOR_KEY_LAST_MEAL_MARKER_ATTRS,
    SENSOR_KEY_ACTIVE_NOTIFICATION,
    SENSOR_KEY_ACTIVE_NOTIFICATION_ATTRS,
    SENSOR_KEY_LAST_INSULIN_MARKER,
    SENSOR_KEY_LAST_INSULIN_MARKER_ATTRS,
    SENSOR_KEY_LAST_AUTO_BASAL_DELIVERY_MARKER,
    SENSOR_KEY_LAST_AUTO_BASAL_DELIVERY_MARKER_ATTRS,
    SENSOR_KEY_LAST_AUTO_MODE_STATUS_MARKER,
    SENSOR_KEY_LAST_AUTO_MODE_STATUS_MARKER_ATTRS,
    SENSOR_KEY_LAST_LOW_GLUCOSE_SUSPENDED_MARKER,
    SENSOR_KEY_LAST_LOW_GLUCOSE_SUSPENDED_MARKER_ATTRS,
    BINARY_SENSOR_KEY_PUMP_COMM_STATE,
    BINARY_SENSOR_KEY_SENSOR_COMM_STATE,
    BINARY_SENSOR_KEY_CONDUIT_IN_RANGE,
    BINARY_SENSOR_KEY_CONDUIT_PUMP_IN_RANGE,
    BINARY_SENSOR_KEY_CONDUIT_SENSOR_IN_RANGE,
    SENSOR_KEY_CLIENT_TIMEZONE,
    SENSOR_KEY_APP_MODEL_TYPE,
    SENSOR_KEY_MEDICAL_DEVICE_MANUFACTURER,
    SENSOR_KEY_MEDICAL_DEVICE_MODEL_NUMBER,
    SENSOR_KEY_MEDICAL_DEVICE_HARDWARE_REVISION,
    SENSOR_KEY_MEDICAL_DEVICE_FIRMWARE_REVISION,
    SENSOR_KEY_MEDICAL_DEVICE_SYSTEM_ID,
    MS_TIMEZONE_TO_IANA_MAP,
    SENSOR_KEY_TIME_TO_NEXT_CALIB_HOURS,
    CARELINK_CODE_MAP,
)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

_LOGGER = logging.getLogger(__name__)


def convert_date_to_isodate(date):
    date_iso = re.sub(r"\.\d{3}Z$", "+00:00", date)

    return datetime.fromisoformat(date_iso).replace(tzinfo=None)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up carelink from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    config = entry.data

    carelink_client = CarelinkClient(
        config["cl_refresh_token"],
        config["cl_token"],
        config["cl_client_id"],
        config["cl_client_secret"],
        config["cl_mag_identifier"],
        config["patientId"]
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {CLIENT: carelink_client}

    if config["nightscout_url"] and config["nightscout_api"]:
        nightscout_uploader = NightscoutUploader(
            config["nightscout_url"],
            config["nightscout_api"]
        )
        hass.data.setdefault(DOMAIN, {})[entry.entry_id].update({UPLOADER: nightscout_uploader})

    coordinator = CarelinkCoordinator(hass, entry, update_interval=timedelta(seconds=config[SCAN_INTERVAL]))

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class CarelinkCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(self, hass: HomeAssistant, entry, update_interval: timedelta):

        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)

        self.uploader = None
        self.client = hass.data[DOMAIN][entry.entry_id][CLIENT]
        self.timezone = hass.config.time_zone

        if UPLOADER in hass.data[DOMAIN][entry.entry_id]:
            self.uploader = hass.data[DOMAIN][entry.entry_id][UPLOADER]

    async def _async_update_data(self):

        data = {}
        client_timezone = DEFAULT_TIME_ZONE

        await self.client.login()
        recent_data = await self.client.get_recent_data()

        if recent_data is None:
            recent_data = dict()
        if recent_data and 'patientData' in recent_data:
            recent_data=recent_data['patientData']

        _LOGGER.debug("Before Data parsing %s", recent_data)
        try:
            if recent_data is not None and "clientTimeZoneName" in recent_data:
                client_timezone = recent_data["clientTimeZoneName"]

            data[SENSOR_KEY_CLIENT_TIMEZONE] = client_timezone

            timezone_map = MS_TIMEZONE_TO_IANA_MAP.setdefault(
                client_timezone, DEFAULT_TIME_ZONE
            )

            timezone = ZoneInfo(str(timezone_map))

            _LOGGER.debug("Using timezone %s", DEFAULT_TIME_ZONE)

        except Exception as error:
            _LOGGER.error(
                "Can not set timezone to %s. The error was: %s", timezone_map, error
            )
            timezone = ZoneInfo("Europe/London")

        _LOGGER.debug("Using timezone %s", DEFAULT_TIME_ZONE)

        # nightscout uploader
        if self.uploader:
            await self.uploader.send_recent_data(recent_data, timezone)

        recent_data["lastConduitDateTime"] = recent_data.setdefault("lastConduitDateTime", "")
        recent_data["activeInsulin"] = recent_data.setdefault("activeInsulin", {})
        recent_data["therapyAlgorithmState"] = recent_data.setdefault("therapyAlgorithmState", {})
        recent_data["lastAlarm"] = recent_data.setdefault("lastAlarm", {})
        recent_data["markers"] = recent_data.setdefault("markers", [])
        recent_data["sgs"] = recent_data.setdefault("sgs", [])

        # Last Update fetch

        if recent_data["lastConduitDateTime"]:
            date_time_local = convert_date_to_isodate(recent_data["lastConduitDateTime"])
            data[SENSOR_KEY_UPDATE_TIMESTAMP] = date_time_local.replace(tzinfo=timezone)

        # Last Glucose level sensors

        current_sg = get_sg(recent_data["sgs"], 0)
        prev_sg = get_sg(recent_data["sgs"], 1)

        if current_sg and "timestamp" in current_sg:
            date_time_local = convert_date_to_isodate(current_sg["timestamp"])
            data[SENSOR_KEY_LASTSG_TIMESTAMP] = date_time_local.replace(tzinfo=timezone)
            data[SENSOR_KEY_LASTSG_MMOL] = float(round(current_sg["sg"] * 0.0555, 2))
            data[SENSOR_KEY_LASTSG_MGDL] = current_sg["sg"]
            if prev_sg:
                data[SENSOR_KEY_SG_DELTA] = (float(current_sg["sg"]) - float(prev_sg["sg"]))

        # Sensors

        data[SENSOR_KEY_PUMP_BATTERY_LEVEL] = recent_data.setdefault(
            "pumpBatteryLevelPercent", UNAVAILABLE
        )
        data[SENSOR_KEY_CONDUIT_BATTERY_LEVEL] = recent_data.setdefault(
            "conduitBatteryLevel", UNAVAILABLE
        )
        data[SENSOR_KEY_SENSOR_BATTERY_LEVEL] = recent_data.setdefault(
            "gstBatteryLevel", UNAVAILABLE
        )
        data[SENSOR_KEY_SENSOR_DURATION_HOURS] = recent_data.setdefault(
            "sensorDurationHours", UNAVAILABLE
        )
        data[SENSOR_KEY_SENSOR_DURATION_MINUTES] = recent_data.setdefault(
            "sensorDurationMinutes", UNAVAILABLE
        )
        data[SENSOR_KEY_RESERVOIR_LEVEL] = recent_data.setdefault(
            "reservoirLevelPercent", UNAVAILABLE
        )
        data[SENSOR_KEY_RESERVOIR_AMOUNT] = recent_data.setdefault(
            "reservoirAmount", UNAVAILABLE
        )
        data[SENSOR_KEY_RESERVOIR_REMAINING_UNITS] = recent_data.setdefault(
            "reservoirRemainingUnits", UNAVAILABLE
        )
        data[SENSOR_KEY_LASTSG_TREND] = recent_data.setdefault(
            "lastSGTrend", UNAVAILABLE
        )

        data[SENSOR_KEY_TIME_TO_NEXT_CALIB_HOURS] = recent_data.setdefault(
            "timeToNextCalibHours", UNAVAILABLE
        )

        if recent_data["activeInsulin"] and "amount" in recent_data["activeInsulin"]:
            # Active insulin sensor
            active_insulin = recent_data["activeInsulin"]

            amount = recent_data["activeInsulin"].setdefault(
                "amount", UNAVAILABLE
            )
            if amount is not None and float(amount) >= 0:
                data[SENSOR_KEY_ACTIVE_INSULIN] = round(float(amount), 2)

                if "datetime" in active_insulin:
                    date_time_local = convert_date_to_isodate(active_insulin["datetime"])

                    data[SENSOR_KEY_ACTIVE_INSULIN_ATTRS] = {
                        "last_update": date_time_local.replace(tzinfo=timezone)
                    }
        else:
            data[SENSOR_KEY_ACTIVE_INSULIN] = UNAVAILABLE
            data[SENSOR_KEY_ACTIVE_INSULIN_ATTRS] = {}

        if "dateTime" in recent_data["lastAlarm"]:
            # Last alarm sensor
            last_alarm = recent_data["lastAlarm"]

            date_time_local = convert_date_to_isodate(last_alarm["dateTime"])

            last_alarm["dateTime"]=date_time_local
            last_alarm["messageId"] = CARELINK_CODE_MAP.setdefault(int(last_alarm["faultId"]), "UNKNOWN")
            
            data[SENSOR_KEY_LAST_ALARM] = date_time_local.replace(tzinfo=timezone)
            data[SENSOR_KEY_LAST_ALARM_ATTRS] = last_alarm
            active_notification = get_active_notification(last_alarm, recent_data["notificationHistory"])

            if active_notification:
                data[SENSOR_KEY_ACTIVE_NOTIFICATION] = date_time_local.replace(tzinfo=timezone)
                data[SENSOR_KEY_ACTIVE_NOTIFICATION_ATTRS] = last_alarm
            else:
                data[SENSOR_KEY_ACTIVE_NOTIFICATION] = UNAVAILABLE
                data[SENSOR_KEY_ACTIVE_NOTIFICATION_ATTRS] = {}
        else:
            data[SENSOR_KEY_LAST_ALARM] = UNAVAILABLE
            data[SENSOR_KEY_LAST_ALARM_ATTRS] = {}
            data[SENSOR_KEY_ACTIVE_NOTIFICATION] = UNAVAILABLE
            data[SENSOR_KEY_ACTIVE_NOTIFICATION_ATTRS] = {}

        if (
            recent_data["therapyAlgorithmState"] is not None
            and "autoModeShieldState" in recent_data["therapyAlgorithmState"]
        ):
            data[SENSOR_KEY_ACTIVE_BASAL_PATTERN] = recent_data["therapyAlgorithmState"].setdefault(
                "autoModeShieldState", UNAVAILABLE
            )
        else:
            data[SENSOR_KEY_ACTIVE_BASAL_PATTERN] = UNAVAILABLE

        averageSGRaw = recent_data.setdefault("averageSG", UNAVAILABLE)
        if averageSGRaw is not None:
            data[SENSOR_KEY_AVG_GLUCOSE_MMOL] = float(
                round(recent_data.setdefault("averageSG", UNAVAILABLE) * 0.0555, 2)
            )
        data[SENSOR_KEY_AVG_GLUCOSE_MGDL] = recent_data.setdefault(
            "averageSG", UNAVAILABLE
        )
        data[SENSOR_KEY_BELOW_HYPO_LIMIT] = recent_data.setdefault(
            "belowHypoLimit", UNAVAILABLE
        )
        data[SENSOR_KEY_ABOVE_HYPER_LIMIT] = recent_data.setdefault(
            "aboveHyperLimit", UNAVAILABLE
        )
        data[SENSOR_KEY_TIME_IN_RANGE] = recent_data.setdefault(
            "timeInRange", UNAVAILABLE
        )
        data[SENSOR_KEY_MAX_AUTO_BASAL_RATE] = recent_data.setdefault(
            "maxAutoBasalRate", UNAVAILABLE
        )
        data[SENSOR_KEY_SG_BELOW_LIMIT] = recent_data.setdefault(
            "sgBelowLimit", UNAVAILABLE
        )

        last_meal_marker = get_last_marker("MEAL", recent_data["markers"])

        if last_meal_marker is not None:
            data[SENSOR_KEY_LAST_MEAL_MARKER] = last_meal_marker["DATETIME"].replace(
                tzinfo=timezone
            )
            data[SENSOR_KEY_LAST_MEAL_MARKER_ATTRS] = last_meal_marker["ATTRS"]
        else:
            data[SENSOR_KEY_LAST_MEAL_MARKER] = UNAVAILABLE

        last_insuline_marker = get_last_marker("INSULIN", recent_data["markers"])

        if last_insuline_marker is not None:
            data[SENSOR_KEY_LAST_INSULIN_MARKER] = last_insuline_marker[
                "DATETIME"
            ].replace(tzinfo=timezone)
            data[SENSOR_KEY_LAST_INSULIN_MARKER_ATTRS] = last_insuline_marker["ATTRS"]
        else:
            data[SENSOR_KEY_LAST_INSULIN_MARKER] = UNAVAILABLE

        last_autobasal_marker = get_last_marker(
            "AUTO_BASAL_DELIVERY", recent_data["markers"]
        )

        if last_autobasal_marker is not None:
            data[SENSOR_KEY_LAST_AUTO_BASAL_DELIVERY_MARKER] = last_autobasal_marker[
                "DATETIME"
            ].replace(tzinfo=timezone)
            data[
                SENSOR_KEY_LAST_AUTO_BASAL_DELIVERY_MARKER_ATTRS
            ] = last_autobasal_marker["ATTRS"]
        else:
            data[SENSOR_KEY_LAST_AUTO_BASAL_DELIVERY_MARKER] = UNAVAILABLE

        last_auto_mode_status_marker = get_last_marker(
            "AUTO_MODE_STATUS", recent_data["markers"]
        )

        if last_auto_mode_status_marker is not None:
            data[
                SENSOR_KEY_LAST_AUTO_MODE_STATUS_MARKER
            ] = last_auto_mode_status_marker["DATETIME"].replace(tzinfo=timezone)
            data[
                SENSOR_KEY_LAST_AUTO_MODE_STATUS_MARKER_ATTRS
            ] = last_auto_mode_status_marker["ATTRS"]
        else:
            data[SENSOR_KEY_LAST_AUTO_MODE_STATUS_MARKER] = UNAVAILABLE

        last_low_glucose_marker = get_last_marker(
            "LOW_GLUCOSE_SUSPENDED", recent_data["markers"]
        )

        if last_low_glucose_marker is not None:
            data[
                SENSOR_KEY_LAST_LOW_GLUCOSE_SUSPENDED_MARKER
            ] = last_low_glucose_marker["DATETIME"].replace(tzinfo=timezone)
            data[
                SENSOR_KEY_LAST_LOW_GLUCOSE_SUSPENDED_MARKER_ATTRS
            ] = last_low_glucose_marker["ATTRS"]
        else:
            data[SENSOR_KEY_LAST_LOW_GLUCOSE_SUSPENDED_MARKER] = UNAVAILABLE

        # Binary Sensors

        data[BINARY_SENSOR_KEY_PUMP_COMM_STATE] = recent_data.setdefault(
            "pumpCommunicationState", UNAVAILABLE
        )
        data[BINARY_SENSOR_KEY_SENSOR_COMM_STATE] = recent_data.setdefault(
            "gstCommunicationState", UNAVAILABLE
        )
        data[BINARY_SENSOR_KEY_CONDUIT_IN_RANGE] = recent_data.setdefault(
            "conduitInRange", UNAVAILABLE
        )
        data[BINARY_SENSOR_KEY_CONDUIT_PUMP_IN_RANGE] = recent_data.setdefault(
            "conduitMedicalDeviceInRange", UNAVAILABLE
        )
        data[BINARY_SENSOR_KEY_CONDUIT_SENSOR_IN_RANGE] = recent_data.setdefault(
            "conduitSensorInRange", UNAVAILABLE
        )

        # Device info

        data[DEVICE_PUMP_SERIAL] = recent_data.setdefault(
            "conduitSerialNumber", UNAVAILABLE
        )
        data[DEVICE_PUMP_NAME] = (
            recent_data.setdefault("firstName", "Name")
            + " "
            + recent_data.setdefault("lastName", "Unvailable")
        )
        data[DEVICE_PUMP_MODEL] = recent_data.setdefault("pumpModelNumber", UNAVAILABLE)

        data[SENSOR_KEY_APP_MODEL_TYPE] = recent_data.setdefault(
            "appModelType", UNAVAILABLE
        )

        # Add device info when available

        if "medicalDeviceInformation" in recent_data:

            data[SENSOR_KEY_MEDICAL_DEVICE_MANUFACTURER] = recent_data[
                "medicalDeviceInformation"
            ].setdefault("manufacturer", UNAVAILABLE)

            data[SENSOR_KEY_MEDICAL_DEVICE_MODEL_NUMBER] = recent_data[
                "medicalDeviceInformation"
            ].setdefault("modelNumber", UNAVAILABLE)

            data[SENSOR_KEY_MEDICAL_DEVICE_HARDWARE_REVISION] = recent_data[
                "medicalDeviceInformation"
            ].setdefault("hardwareRevision", UNAVAILABLE)

            data[SENSOR_KEY_MEDICAL_DEVICE_FIRMWARE_REVISION] = recent_data[
                "medicalDeviceInformation"
            ].setdefault("firmwareRevision", UNAVAILABLE)
            data[SENSOR_KEY_MEDICAL_DEVICE_SYSTEM_ID] = recent_data[
                "medicalDeviceInformation"
            ].setdefault("systemId", UNAVAILABLE)

        _LOGGER.debug("_async_update_data: %s", data)

        return data

def get_sg(sgs: list, pos: int) -> dict:
    """Retrieve previous sg from list"""

    try:
        array = [sg for sg in sgs if "sensorState" in sg.keys() and sg["sensorState"] == "NO_ERROR_MESSAGE"]
        sorted_array = sorted(
            array,
            key=lambda x: convert_date_to_isodate(x["timestamp"]),
            reverse=True,
        )

        if len(sorted_array) > pos:
            return sorted_array[pos]
        else:
            return None
    except Exception as error:
        _LOGGER.error(
            "the sg data could not be tracked correctly. A unknown error happened while parsing the data.",
            error,
        )
        return None

def get_active_notification(last_alarm: list, notifications: list) -> dict:
    """Retrieve active notification from notifications list"""
    try:
        filtered_array = notifications["clearedNotifications"]
        if filtered_array:
            sorted_array = sorted(
                filtered_array,
                key=lambda x: convert_date_to_isodate(x["dateTime"]),
                reverse=True,
            )
            for entry in sorted_array:
                if last_alarm["GUID"] == entry["referenceGUID"]:
                    return None
            return last_alarm
    except Exception as error:
        _LOGGER.error(
            "Check if your Carelink data contains an active notification, it seems to be missing.", error
        )
        return last_alarm

def get_last_marker(marker_type: str, markers: list) -> dict:
    """Retrieve last marker from type in 24h marker list"""

    try:
        filtered_array = [marker for marker in markers if marker["type"] == marker_type]
        sorted_array = sorted(
            filtered_array,
            key=lambda x: convert_date_to_isodate(x["timestamp"]),
            reverse=True,
        )

        last_marker = sorted_array[0]
        for k in ["version", "kind", "index", "views"]:
            last_marker.pop(k, None)
        return {
            "DATETIME": convert_date_to_isodate(last_marker["timestamp"]),
            "ATTRS": last_marker,
        }
    except (IndexError, KeyError) as index_error:
        _LOGGER.debug(
            "the marker with type '%s' could not be tracked correctly. Check if your Carelink data contains a key with the name %s, it seems to be missing.",
            marker_type,
            index_error,
        )
        return None
    except Exception as error:
        _LOGGER.error(
            "the marker with type '%s' could not be tracked correctly. A unknown error happened while parsing the data.",
            error,
        )
        return None
