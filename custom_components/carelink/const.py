"""Constants for the carelink integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)

DOMAIN = "carelink"
CLIENT = "carelink_client"

SENSOR_KEY_LASTSG_MMOL = "last_sg_mmol"
SENSOR_KEY_LASTSG_MGDL = "last_sg_mgdl"
SENSOR_KEY_LASTSG_TIMESTAMP = "last_sg_timestamp"
SENSOR_KEY_LASTSG_SENSOR_STATE = "last_sg_sensor_state"
SENSOR_KEY_BATTERY_LEVEL = "battery_level"
SENSOR_KEY_RESERVOIR_LEVEL = "reservoir level"
SENSOR_STATE = "sensor state"

DEVICE_PUMP_SERIAL = "pump serial"
DEVICE_PUMP_NAME = "pump name"
DEVICE_PUMP_MODEL = "pump model"

MMOL = "mmol/l"
MGDL = "mg/dl"
MOLAR_CONCENTRATION = "molar concentration"
DATETIME = "date/time"
PERCENT = "%"

SENSORS = (
    SensorEntityDescription(
        key=SENSOR_KEY_LASTSG_MMOL,
        name="Last suger glucose level mmol",
        native_unit_of_measurement=MMOL,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=MOLAR_CONCENTRATION,
        icon="mdi:water",
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LASTSG_MGDL,
        name="Last suger glucose level mg/dl",
        native_unit_of_measurement=MGDL,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=MOLAR_CONCENTRATION,
        icon="mdi:water",
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LASTSG_TIMESTAMP,
        name="Last sensor update",
        native_unit_of_measurement=DATETIME,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LASTSG_SENSOR_STATE,
        name="Last sensor state",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=None,
        icon="mdi:alert-circle",
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_BATTERY_LEVEL,
        name="Battery level",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.TOTAL,
        device_class=SensorDeviceClass.BATTERY,
        icon="mdi:battery",
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_RESERVOIR_LEVEL,
        name="Reservoir level",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.TOTAL,
        device_class=None,
        icon="mdi:medication",
    ),
    SensorEntityDescription(
        key=SENSOR_STATE,
        name="Sensor state",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=None,
        icon="mdi:leak",
    ),
)
