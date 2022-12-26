"""Medtronic arelink integration."""
from __future__ import annotations

import logging

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)

from .api import CarelinkClient

from .const import (
    CLIENT,
    DOMAIN,
    COORDINATOR,
    DEVICE_PUMP_MODEL,
    DEVICE_PUMP_NAME,
    DEVICE_PUMP_SERIAL,
    DOMAIN,
    SENSOR_KEY_PUMP_BATTERY_LEVEL,
    SENSOR_KEY_CONDUIT_BATTERY_LEVEL,
    SENSOR_KEY_SENSOR_BATTERY_LEVEL,
    SENSOR_KEY_SENSOR_DURATION_HOURS,
    SENSOR_KEY_SENSOR_DURATION_MINUTES,
    SENSOR_KEY_LASTSG_MGDL,
    SENSOR_KEY_LASTSG_MMOL,
    SENSOR_KEY_LASTSG_SENSOR_STATE,
    SENSOR_KEY_LASTSG_TIMESTAMP,
    SENSOR_KEY_LASTSG_TREND,
    SENSOR_KEY_RESERVOIR_LEVEL,
    SENSOR_KEY_RESERVOIR_AMOUNT,
    SENSOR_KEY_RESERVOIR_REMAINING_UNITS,
    SENSOR_STATE,
    BINARY_SENSOR_KEY_PUMP_COMM_STATE,
    BINARY_SENSOR_KEY_SENSOR_COMM_STATE,
    BINARY_SENSOR_KEY_CONDUIT_IN_RANGE,
    BINARY_SENSOR_KEY_CONDUIT_PUMP_IN_RANGE,
    BINARY_SENSOR_KEY_CONDUIT_SENSOR_IN_RANGE,
    MS_TIMEZONE_TO_IANA_MAP,
)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up carelink from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    config = entry.data
    carelink_client = CarelinkClient(
        config[CONF_USERNAME], config[CONF_PASSWORD], config["country"]
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {CLIENT: carelink_client}

    coordinator = CarelinkCoordinator(hass, entry, update_interval=SCAN_INTERVAL)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        COORDINATOR: coordinator,
    }

    hass.config_entries.async_setup_platforms(entry, PLATFORMS)

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

        await self.client.login()
        recent_data = await self.client.get_recent_data()

        TIMEZONE = ZoneInfo(MS_TIMEZONE_TO_IANA_MAP[recent_data["clientTimeZoneName"]])

        if "datetime" in recent_data["lastSG"]:
            ## Last Glucose level sensors

            last_sg = recent_data["lastSG"]

            date_time_local = datetime.strptime(
                last_sg["datetime"], "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=None)

            # Update glucose data only if data was logged. Otherwise, keep the old data and
            # update the latest sensor state because it probably changed to an error state
            if last_sg["sg"] > 0:
                data[SENSOR_KEY_LASTSG_MMOL] = float(round(last_sg["sg"] * 0.0555, 2))
                data[SENSOR_KEY_LASTSG_MGDL] = last_sg["sg"]

            data[SENSOR_KEY_LASTSG_TIMESTAMP] = date_time_local.replace(tzinfo=TIMEZONE)
            data[SENSOR_KEY_LASTSG_SENSOR_STATE] = last_sg["sensorState"]
        else:
            data[SENSOR_KEY_LASTSG_MMOL] = None
            data[SENSOR_KEY_LASTSG_MGDL] = None
            data[SENSOR_KEY_LASTSG_TIMESTAMP] = None
            data[SENSOR_KEY_LASTSG_SENSOR_STATE] = None

        ## Sensors

        data[SENSOR_KEY_PUMP_BATTERY_LEVEL] = recent_data[
            "medicalDeviceBatteryLevelPercent"
        ]
        data[SENSOR_KEY_CONDUIT_BATTERY_LEVEL] = recent_data["conduitBatteryLevel"]
        data[SENSOR_KEY_SENSOR_BATTERY_LEVEL] = recent_data["gstBatteryLevel"]
        data[SENSOR_KEY_SENSOR_DURATION_HOURS] = recent_data["sensorDurationHours"]
        data[SENSOR_KEY_SENSOR_DURATION_MINUTES] = recent_data["sensorDurationMinutes"]
        data[SENSOR_KEY_RESERVOIR_LEVEL] = recent_data["reservoirLevelPercent"]
        data[SENSOR_KEY_RESERVOIR_AMOUNT] = recent_data["reservoirAmount"]
        data[SENSOR_KEY_RESERVOIR_REMAINING_UNITS] = recent_data[
            "reservoirRemainingUnits"
        ]
        data[SENSOR_STATE] = recent_data["sensorState"]
        data[SENSOR_KEY_LASTSG_TREND] = recent_data["lastSGTrend"]

        ## Binary Sensors

        data[BINARY_SENSOR_KEY_PUMP_COMM_STATE] = recent_data["pumpCommunicationState"]
        data[BINARY_SENSOR_KEY_SENSOR_COMM_STATE] = recent_data["gstCommunicationState"]
        data[BINARY_SENSOR_KEY_CONDUIT_IN_RANGE] = recent_data["conduitInRange"]
        data[BINARY_SENSOR_KEY_CONDUIT_PUMP_IN_RANGE] = recent_data[
            "conduitMedicalDeviceInRange"
        ]
        data[BINARY_SENSOR_KEY_CONDUIT_SENSOR_IN_RANGE] = recent_data[
            "conduitSensorInRange"
        ]

        ## Device info

        data[DEVICE_PUMP_SERIAL] = recent_data["medicalDeviceSerialNumber"]
        data[DEVICE_PUMP_NAME] = (
            recent_data["firstName"] + " " + recent_data["lastName"]
        )
        data[DEVICE_PUMP_MODEL] = recent_data["pumpModelNumber"]

        _LOGGER.debug("_async_update_data: %s", data)

        return data
