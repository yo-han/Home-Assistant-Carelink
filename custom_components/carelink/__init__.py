"""Medtronic arelink integration."""
from __future__ import annotations

import logging
import re

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.util.dt import DEFAULT_TIME_ZONE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)

from .api import CarelinkClient

from .const import (
    CLIENT,
    DOMAIN,
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
    SENSOR_KEY_LASTSG_TIMESTAMP,
    SENSOR_KEY_LASTSG_TREND,
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
)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


def convert_date_to_isodate(date):
    date_iso = re.sub("\.\d{3}Z$", "+00:00", date)

    return datetime.fromisoformat(date_iso).replace(tzinfo=None)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up carelink from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    config = entry.data
    patientId = None

    if "patientId" in config:
        patientId = config["patientId"]

    carelink_client = CarelinkClient(
        config[CONF_USERNAME],
        config[CONF_PASSWORD],
        config["country"],
        patientId,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {CLIENT: carelink_client}

    coordinator = CarelinkCoordinator(hass, entry, update_interval=SCAN_INTERVAL)

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

        self.client = hass.data[DOMAIN][entry.entry_id][CLIENT]
        self.timezone = hass.config.time_zone

    async def _async_update_data(self):

        data = {}
        last_sg = {}
        clientTimezone = DEFAULT_TIME_ZONE

        await self.client.login()
        recent_data = await self.client.get_recent_data()

        try:
            if "clientTimeZonseName" in recent_data:
                clientTimezone = recent_data["clientTimeZoneName"]

            data[SENSOR_KEY_CLIENT_TIMEZONE] = clientTimezone

            timezone_map = MS_TIMEZONE_TO_IANA_MAP.setdefault(
                clientTimezone, DEFAULT_TIME_ZONE
            )

            timezone = ZoneInfo(str(timezone_map))

            _LOGGER.debug("Using timezone %s", DEFAULT_TIME_ZONE)

        except Exception as error:
            _LOGGER.error(
                "Can not set timezone to %s. The error was: %s", timezone_map, error
            )
            timezone = ZoneInfo("Europe/London")

        _LOGGER.debug("Using timezone %s", DEFAULT_TIME_ZONE)

        recent_data["lastSG"] = recent_data.setdefault("lastSG", {})

        recent_data["activeInsulin"] = recent_data.setdefault("activeInsulin", {})
        recent_data["basal"] = recent_data.setdefault("basal", {})
        recent_data["lastAlarm"] = recent_data.setdefault("lastAlarm", {})
        recent_data["markers"] = recent_data.setdefault("markers", [])

        if "datetime" in recent_data["lastSG"]:
            # Last Glucose level sensors

            last_sg = recent_data["lastSG"]

            date_time_local = convert_date_to_isodate(last_sg["datetime"])

            # Update glucose data only if data was logged. Otherwise, keep the old data and
            # update the latest sensor state because it probably changed to an error state
            if last_sg["sg"] > 0:
                data[SENSOR_KEY_LASTSG_MMOL] = float(round(last_sg["sg"] * 0.0555, 2))
                data[SENSOR_KEY_LASTSG_MGDL] = last_sg["sg"]

            data[SENSOR_KEY_LASTSG_TIMESTAMP] = date_time_local.replace(tzinfo=timezone)
        else:
            data[SENSOR_KEY_LASTSG_MMOL] = UNAVAILABLE
            data[SENSOR_KEY_LASTSG_MGDL] = UNAVAILABLE
            data[SENSOR_KEY_LASTSG_TIMESTAMP] = UNAVAILABLE

        # Sensors

        data[SENSOR_KEY_PUMP_BATTERY_LEVEL] = recent_data.setdefault(
            "medicalDeviceBatteryLevelPercent", UNAVAILABLE
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

        if "amount" in recent_data["activeInsulin"]:
            # Active insulin sensor

            active_insulin = recent_data["activeInsulin"]

            data[SENSOR_KEY_ACTIVE_INSULIN] = recent_data["activeInsulin"].setdefault(
                "amount", UNAVAILABLE
            )

            if "datetime" in active_insulin:

                date_time_local = convert_date_to_isodate(active_insulin["datetime"])

                data[SENSOR_KEY_ACTIVE_INSULIN_ATTRS] = {
                    "last_update": date_time_local.replace(tzinfo=timezone)
                }
        else:
            data[SENSOR_KEY_ACTIVE_INSULIN] = UNAVAILABLE
            data[SENSOR_KEY_ACTIVE_INSULIN_ATTRS] = {}

        if "datetime" in recent_data["lastAlarm"]:
            # Last alarm sensor

            last_alarm = recent_data["lastAlarm"]

            date_time_local = convert_date_to_isodate(last_alarm["datetime"])

            data[SENSOR_KEY_LAST_ALARM] = date_time_local.replace(tzinfo=timezone)
            data[SENSOR_KEY_LAST_ALARM_ATTRS] = last_alarm
        else:
            data[SENSOR_KEY_LAST_ALARM] = None
            data[SENSOR_KEY_LAST_ALARM_ATTRS] = {}

        if (
            recent_data["basal"] is not None
            and "activeBasalPattern" in recent_data["basal"]
        ):
            data[SENSOR_KEY_ACTIVE_BASAL_PATTERN] = recent_data["basal"].setdefault(
                "activeBasalPattern", UNAVAILABLE
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
            "medicalDeviceSerialNumber", UNAVAILABLE
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


def get_last_marker(marker_type: str, markers: list) -> dict:
    """Retrieve last marker from type in 24h marker list"""

    try:
        filtered_array = [marker for marker in markers if marker["type"] == marker_type]
        sorted_array = sorted(
            filtered_array,
            key=lambda x: convert_date_to_isodate(x["dateTime"]),
            reverse=True,
        )

        last_marker = sorted_array[0]
        map(last_marker.pop, ["version", "kind", "index"])

        return {
            "DATETIME": convert_date_to_isodate(last_marker["dateTime"]),
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
