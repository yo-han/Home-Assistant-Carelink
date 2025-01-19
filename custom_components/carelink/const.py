"""Constants for the carelink integration."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
)

from homeassistant.helpers.entity import EntityCategory

UNAVAILABLE = None

DOMAIN = "carelink"
CLIENT = "carelink_client"
COORDINATOR = "coordinator"
UPLOADER = "nightscout_uploader"
SCAN_INTERVAL = "scan_interval"

SENSOR_KEY_LASTSG_MMOL = "last_sg_mmol"
SENSOR_KEY_LASTSG_MGDL = "last_sg_mgdl"
SENSOR_KEY_UPDATE_TIMESTAMP = "last_update_timestamp"
SENSOR_KEY_LASTSG_TIMESTAMP = "last_sg_timestamp"
SENSOR_KEY_LASTSG_TREND = "last_sg_trend"
SENSOR_KEY_SG_DELTA = "last_sg_delta"
SENSOR_KEY_PUMP_BATTERY_LEVEL = "pump_battery_level"
SENSOR_KEY_SENSOR_BATTERY_LEVEL = "sensor_battery_level"
SENSOR_KEY_CONDUIT_BATTERY_LEVEL = "conduit_battery_status"
SENSOR_KEY_SENSOR_DURATION_HOURS = "sensor_duration_hours"
SENSOR_KEY_SENSOR_DURATION_MINUTES = "sensor_duration_minutes"
SENSOR_KEY_RESERVOIR_LEVEL = "reservoir_level"
SENSOR_KEY_RESERVOIR_AMOUNT = "reservoir_amount"
SENSOR_KEY_RESERVOIR_REMAINING_UNITS = "reservoir_remaining_units"
SENSOR_KEY_ACTIVE_INSULIN = "active_insulin"
SENSOR_KEY_ACTIVE_INSULIN_ATTRS = "active_insulin_attributes"
SENSOR_KEY_LAST_ALARM = "last_alarm"
SENSOR_KEY_LAST_ALARM_ATTRS = "last_alarm_attributes"
SENSOR_KEY_ACTIVE_BASAL_PATTERN = "active_basal_pattern"
SENSOR_KEY_AVG_GLUCOSE_MMOL = "average_glucose_level_mmol"
SENSOR_KEY_AVG_GLUCOSE_MGDL = "average_glucose_level_mgdl"
SENSOR_KEY_BELOW_HYPO_LIMIT = "below_hypo_limit"
SENSOR_KEY_ABOVE_HYPER_LIMIT = "above_hyper_limit"
SENSOR_KEY_TIME_IN_RANGE = "time_in_range"
SENSOR_KEY_MAX_AUTO_BASAL_RATE = "max_auto_basal_rate"
SENSOR_KEY_SG_BELOW_LIMIT = "sg_below_limit"
SENSOR_KEY_LAST_MEAL_MARKER = "last_marker_meal"
SENSOR_KEY_LAST_MEAL_MARKER_ATTRS = "last_marker_meal_attributes"
SENSOR_KEY_ACTIVE_NOTIFICATION = "active_notification"
SENSOR_KEY_ACTIVE_NOTIFICATION_ATTRS = "active_notification_attributes"
SENSOR_KEY_LAST_INSULIN_MARKER = "last_marker_insulin"
SENSOR_KEY_LAST_INSULIN_MARKER_ATTRS = "last_marker_insulin_attributes"
SENSOR_KEY_LAST_AUTO_BASAL_DELIVERY_MARKER = "last_marker_auto_basal_delivery"
SENSOR_KEY_LAST_AUTO_BASAL_DELIVERY_MARKER_ATTRS = (
    "last_marker_auto_basal_delivery_attributes"
)
SENSOR_KEY_LAST_AUTO_MODE_STATUS_MARKER = "last_marker_auto_mode_status"
SENSOR_KEY_LAST_AUTO_MODE_STATUS_MARKER_ATTRS = (
    "last_marker_auto_mode_status_attributes"
)
SENSOR_KEY_LAST_LOW_GLUCOSE_SUSPENDED_MARKER = "last_marker_low_glucose_suspend"
SENSOR_KEY_LAST_LOW_GLUCOSE_SUSPENDED_MARKER_ATTRS = (
    "last_marker_low_glucose_suspend_attributes"
)

SENSOR_KEY_TIME_TO_NEXT_CALIB_HOURS = "time_to_next_calib_hours"

SENSOR_KEY_CLIENT_TIMEZONE = "client_timezone"
SENSOR_KEY_APP_MODEL_TYPE = "app_model_type"
SENSOR_KEY_MEDICAL_DEVICE_MANUFACTURER = "medical_device_manufacturer"
SENSOR_KEY_MEDICAL_DEVICE_MODEL_NUMBER = "medical_device_model_number"
SENSOR_KEY_MEDICAL_DEVICE_HARDWARE_REVISION = "medical_device_hardware_revision"
SENSOR_KEY_MEDICAL_DEVICE_FIRMWARE_REVISION = "medical_device_firmware_revision"
SENSOR_KEY_MEDICAL_DEVICE_SYSTEM_ID = "medical_device_system_id"

BINARY_SENSOR_KEY_PUMP_COMM_STATE = "binary_sensor_pump_comm_state"
BINARY_SENSOR_KEY_SENSOR_COMM_STATE = "binary_sensor_sensor_comm_state"
BINARY_SENSOR_KEY_CONDUIT_IN_RANGE = "binary_sensor_conduit_in_range"
BINARY_SENSOR_KEY_CONDUIT_PUMP_IN_RANGE = "binary_sensor_conduit_pump_in_range"
BINARY_SENSOR_KEY_CONDUIT_SENSOR_IN_RANGE = "binary_sensor_conduit_sensor_in_range"

DEVICE_PUMP_SERIAL = "pump serial"
DEVICE_PUMP_NAME = "pump name"
DEVICE_PUMP_MODEL = "pump model"

MMOL = "mmol/L"
MGDL = "mg/dL"
DATETIME = "date/time"
PERCENT = "%"
DURATION_HOUR = "h"
DURATION_MINUTE = "m"
UNITS = "units"

SENSORS = (
    SensorEntityDescription(
        key=SENSOR_KEY_LASTSG_MMOL,
        name="Last glucose level mmol",
        native_unit_of_measurement=MMOL,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION,
        icon="mdi:water",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LASTSG_MGDL,
        name="Last glucose level mg/dl",
        native_unit_of_measurement=MGDL,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION,
        icon="mdi:water",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LASTSG_TIMESTAMP,
        name="Last glucose update",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_UPDATE_TIMESTAMP,
        name="Last update",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LASTSG_TREND,
        name="Last glucose trend",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=None,
        icon="mdi:chart-line",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_SG_DELTA,
        name="Last glucose delta",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon="mdi:plus-minus-variant",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_PUMP_BATTERY_LEVEL,
        name="Pump battery level",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BATTERY,
        icon="mdi:battery",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_CONDUIT_BATTERY_LEVEL,
        name="Conduit battery level",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon="mdi:battery",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_SENSOR_BATTERY_LEVEL,
        name="Sensor battery level",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon="mdi:battery",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_SENSOR_DURATION_HOURS,
        name="Sensor duration hours",
        native_unit_of_measurement=DURATION_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon="mdi:clock",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_TIME_TO_NEXT_CALIB_HOURS,
        name="Sensor time to next calibration hours",
        native_unit_of_measurement=DURATION_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon="mdi:clock",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_SENSOR_DURATION_MINUTES,
        name="Sensor duration minutes",
        native_unit_of_measurement=DURATION_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon="mdi:clock",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_RESERVOIR_LEVEL,
        name="Reservoir level",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon="mdi:medication",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_RESERVOIR_REMAINING_UNITS,
        name="Reservoir remaining units",
        native_unit_of_measurement=UNITS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon="mdi:medication",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_RESERVOIR_AMOUNT,
        name="Reservoir amount",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon="mdi:medication",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_ACTIVE_INSULIN,
        name="Active insulin",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon="mdi:water-alert",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LAST_ALARM,
        name="Last alarm",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:clock",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_ACTIVE_BASAL_PATTERN,
        name="Active basal pattern",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=None,
        icon="mdi:chart-line",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_AVG_GLUCOSE_MMOL,
        name="Average glucose level mmol",
        native_unit_of_measurement=MMOL,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION,
        icon="mdi:chart-line",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_AVG_GLUCOSE_MGDL,
        name="Average glucose level mg/dl",
        native_unit_of_measurement=MGDL,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION,
        icon="mdi:chart-line",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_BELOW_HYPO_LIMIT,
        name="Below hypo limit",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon=None,
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_ABOVE_HYPER_LIMIT,
        name="Above hyper limit",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon=None,
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_TIME_IN_RANGE,
        name="Time in range",
        native_unit_of_measurement=PERCENT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon=None,
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_MAX_AUTO_BASAL_RATE,
        name="Max auto basal rate",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon=None,
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_SG_BELOW_LIMIT,
        name="Glucose below limit",
        native_unit_of_measurement=None,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=None,
        icon=None,
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LAST_MEAL_MARKER,
        name="Last meal marker",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-alert",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_ACTIVE_NOTIFICATION,
        name="Active Notification",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:alarm-light",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LAST_INSULIN_MARKER,
        name="Last insulin marker",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-alert",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LAST_AUTO_BASAL_DELIVERY_MARKER,
        name="Last auto basal delivery marker",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-alert",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LAST_AUTO_MODE_STATUS_MARKER,
        name="Last auto mode status marker",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-alert",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_LAST_LOW_GLUCOSE_SUSPENDED_MARKER,
        name="Last low glucose suspended marker",
        native_unit_of_measurement=None,
        state_class=None,
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-alert",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_CLIENT_TIMEZONE,
        name="Timezone",
        device_class=None,
        native_unit_of_measurement=None,
        state_class=None,
        icon="mdi:calendar-clock",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_APP_MODEL_TYPE,
        name="App model type",
        device_class=None,
        native_unit_of_measurement=None,
        state_class=None,
        icon="mdi:application",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_MEDICAL_DEVICE_MANUFACTURER,
        name="Manufacturer",
        device_class=None,
        native_unit_of_measurement=None,
        state_class=None,
        icon="mdi:factory",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_MEDICAL_DEVICE_MODEL_NUMBER,
        name="Model number",
        device_class=None,
        native_unit_of_measurement=None,
        state_class=None,
        icon="mdi:code-tags",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_MEDICAL_DEVICE_HARDWARE_REVISION,
        name="Hardware revision",
        device_class=None,
        native_unit_of_measurement=None,
        state_class=None,
        icon="mdi:code-tags",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_MEDICAL_DEVICE_FIRMWARE_REVISION,
        name="Firmware revision",
        device_class=None,
        native_unit_of_measurement=None,
        state_class=None,
        icon="mdi:code-tags",
        entity_category=None,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_MEDICAL_DEVICE_SYSTEM_ID,
        name="System id",
        device_class=None,
        native_unit_of_measurement=None,
        state_class=None,
        icon="mdi:code-tags",
        entity_category=None,
    ),
)

BINARY_SENSORS = (
    SensorEntityDescription(
        key=BINARY_SENSOR_KEY_PUMP_COMM_STATE,
        name="Pump communitation state",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:bluetooth-connect",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=BINARY_SENSOR_KEY_SENSOR_COMM_STATE,
        name="Sensor communitation state",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:bluetooth-connect",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=BINARY_SENSOR_KEY_CONDUIT_IN_RANGE,
        name="Conduit in range",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:bluetooth-connect",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=BINARY_SENSOR_KEY_CONDUIT_PUMP_IN_RANGE,
        name="Conduit pump in range",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:bluetooth-connect",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key=BINARY_SENSOR_KEY_CONDUIT_SENSOR_IN_RANGE,
        name="Conduit sensor in range",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        icon="mdi:bluetooth-connect",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

CARELINK_CODE_MAP = {
    817 : "BC_SID_SG_APPROACH_HIGH_LIMIT_CHECK_BG",
    776 : "BC_SID_WAIT_AT_LEAST_15_MINUTES",
    780 : "BC_SID_MOVE_PUMP_CLOSER_TO_MINILINK",
    781 : "BC_SID_MOVE_AWAY_FROM_ELECTR_DEVICES",
    795 : "BC_SID_ENSURE_CONNECTION_SECURE",
    820 : "BC_MESSAGE_BASAL_STARTED",
    798 : "BC_SID_IF_NEW_SENSR_SELCT_START_NEW_ELSE_REWIND",
    775 : "BC_SID_CHECK_BG_AND_CALIBRATE_SENSOR",
    869 : "BC_SID_CHECK_BG_AND_CALIBRATE_SENSOR_TO_RECEIVE",
    817 : "BC_SID_SG_APPROACH_HIGH_LIMIT_CHECK_BG",
    784 : "BC_SID_SG_RISE_RAPID",
    105 : "BC_MESSAGE_TIME_REMAINING_CHANGE_RESERVOIR",
    816 : "BC_SID_HIGH_SG_CHECK_BG",
    827 : "BC_MESSAGE_SG_UNDER_50_MG_DL",
    802 : "BC_SID_LOW_SD_CHECK_BG"
}

MS_TIMEZONE_TO_IANA_MAP = {
    "Egypt Standard Time": "Africa/Cairo",
    "Morocco Standard Time": "Africa/Casablanca",
    "South Africa Standard Time": "Africa/Johannesburg",
    "South Sudan Standard Time": "Africa/Juba",
    "Sudan Standard Time": "Africa/Khartoum",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "E. Africa Standard Time": "Africa/Nairobi",
    "Sao Tome Standard Time": "Africa/Sao_Tome",
    "Libya Standard Time": "Africa/Tripoli",
    "Namibia Standard Time": "Africa/Windhoek",
    "Aleutian Standard Time": "America/Adak",
    "Alaskan Standard Time": "America/Anchorage",
    "Tocantins Standard Time": "America/Araguaina",
    "Paraguay Standard Time": "America/Asuncion",
    "Bahia Standard Time": "America/Bahia",
    "SA Pacific Standard Time": "America/Bogota",
    "Argentina Standard Time": "America/Buenos_Aires",
    "Eastern Standard Time (Mexico)": "America/Cancun",
    "Venezuela Standard Time": "America/Caracas",
    "SA Eastern Standard Time": "America/Cayenne",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time (Mexico)": "America/Chihuahua",
    "Central Brazilian Standard Time": "America/Cuiaba",
    "Mountain Standard Time": "America/Denver",
    "Greenland Standard Time": "America/Godthab",
    "Turks And Caicos Standard Time": "America/Grand_Turk",
    "Central America Standard Time": "America/Guatemala",
    "Atlantic Standard Time": "America/Halifax",
    "Cuba Standard Time": "America/Havana",
    "US Eastern Standard Time": "America/Indianapolis",
    "SA Western Standard Time": "America/La_Paz",
    "Pacific Standard Time": "America/Los_Angeles",
    "Central Standard Time (Mexico)": "America/Mexico_City",
    "Saint Pierre Standard Time": "America/Miquelon",
    "Montevideo Standard Time": "America/Montevideo",
    "Eastern Standard Time": "America/New_York",
    "US Mountain Standard Time": "America/Phoenix",
    "Haiti Standard Time": "America/Port-au-Prince",
    "Magallanes Standard Time": "America/Punta_Arenas",
    "Canada Central Standard Time": "America/Regina",
    "Pacific SA Standard Time": "America/Santiago",
    "E. South America Standard Time": "America/Sao_Paulo",
    "Newfoundland Standard Time": "America/St_Johns",
    "Pacific Standard Time (Mexico)": "America/Tijuana",
    "Yukon Standard Time": "America/Whitehorse",
    "Central Asia Standard Time": "Asia/Almaty",
    "Jordan Standard Time": "Asia/Amman",
    "Arabic Standard Time": "Asia/Baghdad",
    "Azerbaijan Standard Time": "Asia/Baku",
    "SE Asia Standard Time": "Asia/Bangkok",
    "Altai Standard Time": "Asia/Barnaul",
    "Middle East Standard Time": "Asia/Beirut",
    "India Standard Time": "Asia/Calcutta",
    "Transbaikal Standard Time": "Asia/Chita",
    "Sri Lanka Standard Time": "Asia/Colombo",
    "Syria Standard Time": "Asia/Damascus",
    "Bangladesh Standard Time": "Asia/Dhaka",
    "Arabian Standard Time": "Asia/Dubai",
    "West Bank Standard Time": "Asia/Hebron",
    "W. Mongolia Standard Time": "Asia/Hovd",
    "North Asia East Standard Time": "Asia/Irkutsk",
    "Israel Standard Time": "Asia/Jerusalem",
    "Afghanistan Standard Time": "Asia/Kabul",
    "Russia Time Zone 11": "Asia/Kamchatka",
    "Pakistan Standard Time": "Asia/Karachi",
    "Nepal Standard Time": "Asia/Katmandu",
    "North Asia Standard Time": "Asia/Krasnoyarsk",
    "Magadan Standard Time": "Asia/Magadan",
    "N. Central Asia Standard Time": "Asia/Novosibirsk",
    "Omsk Standard Time": "Asia/Omsk",
    "North Korea Standard Time": "Asia/Pyongyang",
    "Qyzylorda Standard Time": "Asia/Qyzylorda",
    "Myanmar Standard Time": "Asia/Rangoon",
    "Arab Standard Time": "Asia/Riyadh",
    "Sakhalin Standard Time": "Asia/Sakhalin",
    "Korea Standard Time": "Asia/Seoul",
    "China Standard Time": "Asia/Shanghai",
    "Singapore Standard Time": "Asia/Singapore",
    "Russia Time Zone 10": "Asia/Srednekolymsk",
    "Taipei Standard Time": "Asia/Taipei",
    "West Asia Standard Time": "Asia/Tashkent",
    "Georgian Standard Time": "Asia/Tbilisi",
    "Iran Standard Time": "Asia/Tehran",
    "Tokyo Standard Time": "Asia/Tokyo",
    "Tomsk Standard Time": "Asia/Tomsk",
    "Ulaanbaatar Standard Time": "Asia/Ulaanbaatar",
    "Vladivostok Standard Time": "Asia/Vladivostok",
    "Yakutsk Standard Time": "Asia/Yakutsk",
    "Ekaterinburg Standard Time": "Asia/Yekaterinburg",
    "Caucasus Standard Time": "Asia/Yerevan",
    "Azores Standard Time": "Atlantic/Azores",
    "Cape Verde Standard Time": "Atlantic/Cape_Verde",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "Cen. Australia Standard Time": "Australia/Adelaide",
    "E. Australia Standard Time": "Australia/Brisbane",
    "AUS Central Standard Time": "Australia/Darwin",
    "Aus Central W. Standard Time": "Australia/Eucla",
    "Tasmania Standard Time": "Australia/Hobart",
    "Lord Howe Standard Time": "Australia/Lord_Howe",
    "W. Australia Standard Time": "Australia/Perth",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "UTC-11": "Etc/GMT+11",
    "Dateline Standard Time": "Etc/GMT+12",
    "UTC-02": "Etc/GMT+2",
    "UTC-08": "Etc/GMT+8",
    "UTC-09": "Etc/GMT+9",
    "UTC+12": "Etc/GMT-12",
    "UTC+13": "Etc/GMT-13",
    "UTC": "Etc/UTC",
    "Astrakhan Standard Time": "Europe/Astrakhan",
    "W. Europe Standard Time": "Europe/Berlin",
    "GTB Standard Time": "Europe/Bucharest",
    "Central Europe Standard Time": "Europe/Budapest",
    "E. Europe Standard Time": "Europe/Chisinau",
    "Turkey Standard Time": "Europe/Istanbul",
    "Kaliningrad Standard Time": "Europe/Kaliningrad",
    "FLE Standard Time": "Europe/Kiev",
    "GMT Standard Time": "Europe/London",
    "Greenwich Mean Time": "Europe/London",
    "Belarus Standard Time": "Europe/Minsk",
    "Russian Standard Time": "Europe/Moscow",
    "Romance Standard Time": "Europe/Paris",
    "Russia Time Zone 3": "Europe/Samara",
    "Saratov Standard Time": "Europe/Saratov",
    "Volgograd Standard Time": "Europe/Volgograd",
    "Central European Standard Time": "Europe/Warsaw",
    "Central European Summer Time": "Europe/Amsterdam",
    "Mauritius Standard Time": "Indian/Mauritius",
    "Samoa Standard Time": "Pacific/Apia",
    "New Zealand Standard Time": "Pacific/Auckland",
    "Bougainville Standard Time": "Pacific/Bougainville",
    "Chatham Islands Standard Time": "Pacific/Chatham",
    "Easter Island Standard Time": "Pacific/Easter",
    "Fiji Standard Time": "Pacific/Fiji",
    "Central Pacific Standard Time": "Pacific/Guadalcanal",
    "Hawaiian Standard Time": "Pacific/Honolulu",
    "Line Islands Standard Time": "Pacific/Kiritimati",
    "Marquesas Standard Time": "Pacific/Marquesas",
    "Norfolk Standard Time": "Pacific/Norfolk",
    "West Pacific Standard Time": "Pacific/Port_Moresby",
    "Tonga Standard Time": "Pacific/Tongatapu",
    "tzone://Microsoft/Utc": "UTC",
}
