"""Support for Carelink."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging

import pytz

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    CLIENT,
    DEVICE_PUMP_MODEL,
    DEVICE_PUMP_NAME,
    DEVICE_PUMP_SERIAL,
    DOMAIN,
    SENSOR_KEY_PUMP_BATTERY_LEVEL,
    SENSOR_KEY_SENSOR_BATTERY_LEVEL,
    SENSOR_KEY_SENSOR_BATTERY_STATUS,
    SENSOR_KEY_LASTSG_MGDL,
    SENSOR_KEY_LASTSG_MMOL,
    SENSOR_KEY_LASTSG_SENSOR_STATE,
    SENSOR_KEY_LASTSG_TIMESTAMP,
    SENSOR_KEY_LASTSG_TREND,
    SENSOR_KEY_RESERVOIR_LEVEL,
    SENSOR_KEY_RESERVOIR_AMOUNT,
    SENSOR_KEY_RESERVOIR_REMAINING_UNITS,
    SENSOR_STATE,
    SENSORS,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=180)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up carelink sensor platform."""

    coordinator = CarelinkCoordinator(
        hass, entry, update_interval=SCAN_INTERVAL)

    await coordinator.async_config_entry_first_refresh()

    entities = []

    for sensor_description in SENSORS:

        entity_name = f"{DOMAIN} {sensor_description.name}"

        entities.append(
            # pylint: disable=too-many-function-args
            CarelinkSensorEntity(coordinator, sensor_description, entity_name)
        )

    async_add_entities(entities)


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

        if "datetime" in recent_data["lastSG"]:
            last_sg = recent_data["lastSG"]

            # Actually not UTC but a local datetime with UTC timezone returned by Carelink, so
            # the timezone is stripped and the date showed as is because it will be probably
            # in the prefered timezone
            date_time_local = datetime.strptime(
                last_sg["datetime"], "%Y-%m-%dT%H:%M:%S.000Z"
            )
            time_zone = datetime.now(pytz.timezone(
                "Europe/Amsterdam")).strftime("%z")

            # Update glucose data only if data was logged. Otherwise, keep the old data and
            # update the latest sensor state because it probably changed to an error state
            if last_sg["sg"] > 0:
                data[SENSOR_KEY_LASTSG_MMOL] = float(
                    round(last_sg["sg"] * 0.0555, 2))
                data[SENSOR_KEY_LASTSG_MGDL] = last_sg["sg"]

            data[SENSOR_KEY_LASTSG_TIMESTAMP] = datetime.fromisoformat(
                date_time_local.strftime(
                    "%Y-%m-%d %H:%M:%S") + time_zone[0:3] + ":00"
            )
            data[SENSOR_KEY_LASTSG_SENSOR_STATE] = last_sg["sensorState"]
        else:
            data[SENSOR_KEY_LASTSG_MMOL] = None
            data[SENSOR_KEY_LASTSG_MGDL] = None
            data[SENSOR_KEY_LASTSG_TIMESTAMP] = None
            data[SENSOR_KEY_LASTSG_SENSOR_STATE] = None

        data[SENSOR_KEY_PUMP_BATTERY_LEVEL] = recent_data["medicalDeviceBatteryLevelPercent"]
        data[SENSOR_KEY_SENSOR_BATTERY_LEVEL] = recent_data["conduitBatteryLevel"]
        data[SENSOR_KEY_SENSOR_BATTERY_STATUS] = recent_data["conduitBatteryStatus"]
        data[SENSOR_KEY_RESERVOIR_LEVEL] = recent_data["reservoirLevelPercent"]
        data[SENSOR_KEY_RESERVOIR_AMOUNT] = recent_data["reservoirAmount"]
        data[SENSOR_KEY_RESERVOIR_REMAINING_UNITS] = recent_data["reservoirRemainingUnits"]
        data[SENSOR_STATE] = recent_data["sensorState"]
        data[SENSOR_KEY_LASTSG_TREND] = recent_data["lastSGTrend"]

        data[DEVICE_PUMP_SERIAL] = recent_data["medicalDeviceSerialNumber"]
        data[DEVICE_PUMP_NAME] = (
            recent_data["firstName"] + " " + recent_data["lastName"]
        )
        data[DEVICE_PUMP_MODEL] = recent_data["pumpModelNumber"]

        _LOGGER.debug("_async_update_data: %s", data)

        return data


class CarelinkSensorEntity(CoordinatorEntity, SensorEntity):
    """Carelink Sensor."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        sensor_description,
        entity_name,
    ):
        """Pass coordinator to CoordinatorEntity."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.sensor_description = sensor_description
        self.entity_name = entity_name

    @property
    def name(self) -> str:
        return self.sensor_description.name

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN.lower()}_{self.sensor_description.key}"

    @property
    def native_value(self) -> float:
        return self.coordinator.data[self.sensor_description.key]

    @property
    def device_class(self) -> SensorDeviceClass:
        return self.sensor_description.device_class

    @property
    def native_unit_of_measurement(self) -> str:
        return self.sensor_description.native_unit_of_measurement

    @property
    def state_class(self) -> SensorStateClass:
        return self.sensor_description.state_class

    @property
    def icon(self) -> str:
        return self.sensor_description.icon

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return DeviceInfo(
            identifiers={
                # Serial numbers are unique identifiers within a specific domain
                (DOMAIN, self.coordinator.data[DEVICE_PUMP_SERIAL])
            },
            name=self.coordinator.data[DEVICE_PUMP_NAME],
            manufacturer="Medtronic",
            model=self.coordinator.data[DEVICE_PUMP_MODEL],
        )
