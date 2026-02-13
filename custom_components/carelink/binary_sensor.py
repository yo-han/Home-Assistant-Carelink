from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
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
    COORDINATOR,
    DEVICE_PUMP_MODEL,
    DEVICE_PUMP_NAME,
    DEVICE_PUMP_SERIAL,
    DOMAIN,
    INTEGRATION_NAME,
    BINARY_SENSORS,
)
from .helpers import is_data_stale


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up carelink sensor platform."""

    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    entities = []
    # Get device name from coordinator data for entity naming
    device_name = coordinator.data.get(DEVICE_PUMP_NAME, None)

    for sensor_description in BINARY_SENSORS:
        if device_name:
            entity_name = f"{INTEGRATION_NAME} {device_name} {sensor_description.name}"
        else:
            entity_name = f"{INTEGRATION_NAME} {sensor_description.name}"

        entities.append(
            # pylint: disable=too-many-function-args
            CarelinkConnectivityEntity(
                coordinator, sensor_description, entity_name)
        )

    async_add_entities(entities)


class CarelinkConnectivityEntity(CoordinatorEntity, BinarySensorEntity):
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
        self._attr_name = entity_name

    @property
    def unique_id(self) -> str:
        return f"{DOMAIN.lower()}_{self.sensor_description.key}"

    @property
    def device_class(self) -> BinarySensorDeviceClass:
        return self.sensor_description.device_class

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

    @property
    def is_on(self) -> bool:
        """Return the status of the requested attribute."""
        return self.coordinator.data.setdefault(self.sensor_description.key, None) is True

    @property
    def entity_category(self):
        return self.sensor_description.entity_category

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Check coordinator availability and data staleness
        return super().available and not is_data_stale(
            self.coordinator.data, self.sensor_description.key
        )