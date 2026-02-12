"""Tests for the Carelink sensor platform."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest

from homeassistant.util import dt as dt_util

from custom_components.carelink.const import (
    COORDINATOR,
    DATA_STALE_TIMEOUT_HOURS,
    DEVICE_PUMP_MODEL,
    DEVICE_PUMP_NAME,
    DEVICE_PUMP_SERIAL,
    DOMAIN,
    INTEGRATION_NAME,
    SENSORS,
    SENSOR_KEY_UPDATE_TIMESTAMP,
    SENSOR_KEY_LASTSG_TIMESTAMP,
    SENSOR_KEY_LAST_ALARM,
    SENSOR_KEY_ACTIVE_NOTIFICATION,
)


@pytest.fixture
def mock_coordinator():
    """Create a mock coordinator."""
    coordinator = MagicMock()
    coordinator.data = {
        DEVICE_PUMP_SERIAL: "12345",
        DEVICE_PUMP_NAME: "Test Patient",
        DEVICE_PUMP_MODEL: "MiniMed 780G",
        SENSOR_KEY_UPDATE_TIMESTAMP: dt_util.utcnow(),
    }
    return coordinator


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock()
    hass.data = {DOMAIN: {}}
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    return entry


class TestCarelinkSensorEntity:
    """Tests for CarelinkSensorEntity."""

    def test_entity_name_with_device_name(self, mock_coordinator):
        """Test entity name includes device name when available."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        sensor_description = SENSORS[0]  # Use first sensor description
        entity = CarelinkSensorEntity(
            mock_coordinator, 
            sensor_description,
            f"{INTEGRATION_NAME} Test Patient {sensor_description.name}"
        )
        
        assert entity._attr_name == f"{INTEGRATION_NAME} Test Patient {sensor_description.name}"

    def test_entity_name_without_device_name(self, mock_coordinator):
        """Test entity name uses integration name when device name unavailable."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        sensor_description = SENSORS[0]
        entity = CarelinkSensorEntity(
            mock_coordinator,
            sensor_description,
            f"{INTEGRATION_NAME} {sensor_description.name}"
        )
        
        assert entity._attr_name == f"{INTEGRATION_NAME} {sensor_description.name}"

    def test_available_with_fresh_data(self, mock_coordinator):
        """Test entity is available when data is fresh."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        # Set recent timestamp
        mock_coordinator.data[SENSOR_KEY_UPDATE_TIMESTAMP] = dt_util.utcnow()
        
        sensor_description = SENSORS[0]
        entity = CarelinkSensorEntity(
            mock_coordinator,
            sensor_description,
            f"{INTEGRATION_NAME} {sensor_description.name}"
        )
        
        assert entity.available is True

    def test_available_with_stale_data(self, mock_coordinator):
        """Test entity is unavailable when data is stale."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        # Set old timestamp (more than DATA_STALE_TIMEOUT_HOURS ago)
        mock_coordinator.data[SENSOR_KEY_UPDATE_TIMESTAMP] = (
            dt_util.utcnow() - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        )
        
        sensor_description = SENSORS[0]
        entity = CarelinkSensorEntity(
            mock_coordinator,
            sensor_description,
            f"{INTEGRATION_NAME} {sensor_description.name}"
        )
        
        assert entity.available is False

    def test_available_with_missing_timestamp(self, mock_coordinator):
        """Test entity is unavailable when timestamp is missing."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        # Remove timestamp
        del mock_coordinator.data[SENSOR_KEY_UPDATE_TIMESTAMP]
        
        sensor_description = SENSORS[0]
        entity = CarelinkSensorEntity(
            mock_coordinator,
            sensor_description,
            f"{INTEGRATION_NAME} {sensor_description.name}"
        )
        
        assert entity.available is False

    def test_timestamp_sensor_always_available_when_stale(self, mock_coordinator):
        """Test timestamp sensors stay available even with stale data."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        # Set old timestamp
        mock_coordinator.data[SENSOR_KEY_UPDATE_TIMESTAMP] = (
            dt_util.utcnow() - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        )
        
        # Get timestamp sensor description
        timestamp_sensor = None
        for sensor_desc in SENSORS:
            if sensor_desc.key == SENSOR_KEY_UPDATE_TIMESTAMP:
                timestamp_sensor = sensor_desc
                break
        
        assert timestamp_sensor is not None, "Timestamp sensor not found"
        
        entity = CarelinkSensorEntity(
            mock_coordinator,
            timestamp_sensor,
            f"{INTEGRATION_NAME} {timestamp_sensor.name}"
        )
        
        # Timestamp sensors should remain available for troubleshooting
        assert entity.available is True

    def test_glucose_timestamp_sensor_always_available_when_stale(self, mock_coordinator):
        """Test glucose timestamp sensors stay available even with stale data."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        # Set old timestamp
        mock_coordinator.data[SENSOR_KEY_UPDATE_TIMESTAMP] = (
            dt_util.utcnow() - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        )
        
        # Get glucose timestamp sensor description
        glucose_timestamp_sensor = None
        for sensor_desc in SENSORS:
            if sensor_desc.key == SENSOR_KEY_LASTSG_TIMESTAMP:
                glucose_timestamp_sensor = sensor_desc
                break
        
        assert glucose_timestamp_sensor is not None, "Glucose timestamp sensor not found"
        
        entity = CarelinkSensorEntity(
            mock_coordinator,
            glucose_timestamp_sensor,
            f"{INTEGRATION_NAME} {glucose_timestamp_sensor.name}"
        )
        
        # Glucose timestamp sensors should remain available for troubleshooting
        assert entity.available is True

    def test_alarm_sensor_always_available_when_stale(self, mock_coordinator):
        """Test alarm sensors stay available even with stale data for safety."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        # Set old timestamp
        mock_coordinator.data[SENSOR_KEY_UPDATE_TIMESTAMP] = (
            dt_util.utcnow() - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        )
        
        # Get alarm sensor description
        alarm_sensor = None
        for sensor_desc in SENSORS:
            if sensor_desc.key == SENSOR_KEY_LAST_ALARM:
                alarm_sensor = sensor_desc
                break
        
        assert alarm_sensor is not None, "Alarm sensor not found"
        
        entity = CarelinkSensorEntity(
            mock_coordinator,
            alarm_sensor,
            f"{INTEGRATION_NAME} {alarm_sensor.name}"
        )
        
        # Alarm sensors must stay available for safety (users need to see last alarm)
        assert entity.available is True

    def test_notification_sensor_always_available_when_stale(self, mock_coordinator):
        """Test notification sensors stay available even with stale data for safety."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        # Set old timestamp
        mock_coordinator.data[SENSOR_KEY_UPDATE_TIMESTAMP] = (
            dt_util.utcnow() - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        )
        
        # Get notification sensor description
        notification_sensor = None
        for sensor_desc in SENSORS:
            if sensor_desc.key == SENSOR_KEY_ACTIVE_NOTIFICATION:
                notification_sensor = sensor_desc
                break
        
        assert notification_sensor is not None, "Notification sensor not found"
        
        entity = CarelinkSensorEntity(
            mock_coordinator,
            notification_sensor,
            f"{INTEGRATION_NAME} {notification_sensor.name}"
        )
        
        # Notification sensors must stay available for safety
        assert entity.available is True

    def test_unique_id(self, mock_coordinator):
        """Test unique_id is properly formatted."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        sensor_description = SENSORS[0]
        entity = CarelinkSensorEntity(
            mock_coordinator,
            sensor_description,
            f"{INTEGRATION_NAME} {sensor_description.name}"
        )
        
        expected_id = f"{DOMAIN.lower()}_{sensor_description.key}"
        assert entity.unique_id == expected_id

    def test_device_info(self, mock_coordinator):
        """Test device info is properly populated."""
        from custom_components.carelink.sensor import CarelinkSensorEntity
        
        sensor_description = SENSORS[0]
        entity = CarelinkSensorEntity(
            mock_coordinator,
            sensor_description,
            f"{INTEGRATION_NAME} {sensor_description.name}"
        )
        
        device_info = entity.device_info
        assert device_info["identifiers"] == {(DOMAIN, "12345")}
        assert device_info["name"] == "Test Patient"
        assert device_info["manufacturer"] == "Medtronic"
        assert device_info["model"] == "MiniMed 780G"
