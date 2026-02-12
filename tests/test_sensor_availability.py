"""Tests for sensor availability logic."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.carelink.const import (
    DATA_STALE_TIMEOUT_HOURS,
    SENSOR_KEY_UPDATE_TIMESTAMP,
    SENSOR_KEY_LASTSG_TIMESTAMP,
    SENSOR_KEY_LAST_ALARM,
    SENSOR_KEY_ACTIVE_NOTIFICATION,
    SENSOR_KEY_LASTSG_MGDL,
    is_data_stale,
)
from custom_components.carelink.sensor import CarelinkSensor
from homeassistant.components.sensor import SensorEntityDescription


class TestSensorAvailability:
    """Test sensor availability checks."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.data = {}
        coordinator.last_update_success = True
        return coordinator

    @pytest.fixture
    def mock_sensor_description(self):
        """Create a mock sensor description for regular sensors."""
        return SensorEntityDescription(
            key=SENSOR_KEY_LASTSG_MGDL,
            name="Last SG mg/dL",
        )

    @pytest.fixture
    def mock_timestamp_sensor_description(self):
        """Create a mock sensor description for timestamp sensors."""
        return SensorEntityDescription(
            key=SENSOR_KEY_UPDATE_TIMESTAMP,
            name="Last Update",
        )

    @pytest.fixture
    def mock_alarm_sensor_description(self):
        """Create a mock sensor description for alarm sensors."""
        return SensorEntityDescription(
            key=SENSOR_KEY_LAST_ALARM,
            name="Last Alarm",
        )

    def test_is_data_stale_with_fresh_data(self):
        """Test that fresh data is not considered stale."""
        now = datetime.now(timezone.utc)
        coordinator_data = {SENSOR_KEY_UPDATE_TIMESTAMP: now}
        
        assert not is_data_stale(coordinator_data, SENSOR_KEY_LASTSG_MGDL)

    def test_is_data_stale_with_old_data(self):
        """Test that old data is considered stale."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        coordinator_data = {SENSOR_KEY_UPDATE_TIMESTAMP: old_time}
        
        assert is_data_stale(coordinator_data, SENSOR_KEY_LASTSG_MGDL)

    def test_is_data_stale_with_boundary_time(self):
        """Test that data exactly at the timeout threshold is not stale."""
        now = datetime.now(timezone.utc)
        boundary_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS, seconds=-1)
        coordinator_data = {SENSOR_KEY_UPDATE_TIMESTAMP: boundary_time}
        
        assert not is_data_stale(coordinator_data, SENSOR_KEY_LASTSG_MGDL)

    def test_is_data_stale_with_none_timestamp(self):
        """Test that None timestamp is considered stale."""
        coordinator_data = {SENSOR_KEY_UPDATE_TIMESTAMP: None}
        
        assert is_data_stale(coordinator_data, SENSOR_KEY_LASTSG_MGDL)

    def test_is_data_stale_with_missing_timestamp(self):
        """Test that missing timestamp is considered stale."""
        coordinator_data = {}
        
        assert is_data_stale(coordinator_data, SENSOR_KEY_LASTSG_MGDL)

    def test_regular_sensor_available_with_fresh_data(
        self, mock_coordinator, mock_sensor_description
    ):
        """Test that regular sensor is available with fresh data."""
        now = datetime.now(timezone.utc)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: now}
        
        sensor = CarelinkSensor(
            coordinator=mock_coordinator,
            sensor_description=mock_sensor_description,
            entity_name="Test Sensor",
        )
        
        assert sensor.available is True

    def test_regular_sensor_unavailable_with_stale_data(
        self, mock_coordinator, mock_sensor_description
    ):
        """Test that regular sensor is unavailable with stale data."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: old_time}
        
        sensor = CarelinkSensor(
            coordinator=mock_coordinator,
            sensor_description=mock_sensor_description,
            entity_name="Test Sensor",
        )
        
        assert sensor.available is False

    def test_timestamp_sensor_always_available_with_stale_data(
        self, mock_coordinator, mock_timestamp_sensor_description
    ):
        """Test that timestamp sensors remain available even with stale data."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: old_time}
        
        sensor = CarelinkSensor(
            coordinator=mock_coordinator,
            sensor_description=mock_timestamp_sensor_description,
            entity_name="Last Update",
        )
        
        # Timestamp sensors should always be available for troubleshooting
        assert sensor.available is True

    def test_alarm_sensor_always_available_with_stale_data(
        self, mock_coordinator, mock_alarm_sensor_description
    ):
        """Test that alarm sensors remain available even with stale data (CRITICAL SAFETY)."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: old_time}
        
        sensor = CarelinkSensor(
            coordinator=mock_coordinator,
            sensor_description=mock_alarm_sensor_description,
            entity_name="Last Alarm",
        )
        
        # Alarm sensors must remain available for safety - users need to see
        # the last alarm even if connectivity drops
        assert sensor.available is True

    def test_sensor_unavailable_when_coordinator_fails(
        self, mock_coordinator, mock_sensor_description
    ):
        """Test that sensor respects coordinator availability."""
        now = datetime.now(timezone.utc)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: now}
        mock_coordinator.last_update_success = False
        
        sensor = CarelinkSensor(
            coordinator=mock_coordinator,
            sensor_description=mock_sensor_description,
            entity_name="Test Sensor",
        )
        
        # When coordinator fails, sensor should be unavailable
        # even if data would otherwise be fresh
        assert sensor.available is False

    def test_timestamp_sensor_respects_coordinator_state(
        self, mock_coordinator, mock_timestamp_sensor_description
    ):
        """Test that timestamp sensors respect coordinator availability."""
        now = datetime.now(timezone.utc)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: now}
        mock_coordinator.last_update_success = False
        
        sensor = CarelinkSensor(
            coordinator=mock_coordinator,
            sensor_description=mock_timestamp_sensor_description,
            entity_name="Last Update",
        )
        
        # Even timestamp sensors should respect coordinator state
        assert sensor.available is False

    def test_all_always_available_sensors(self, mock_coordinator):
        """Test that all sensors marked as always available work correctly."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: old_time}
        
        # These sensors should always be available with stale data
        always_available_keys = [
            SENSOR_KEY_UPDATE_TIMESTAMP,
            SENSOR_KEY_LASTSG_TIMESTAMP,
            SENSOR_KEY_LAST_ALARM,
            SENSOR_KEY_ACTIVE_NOTIFICATION,
        ]
        
        for key in always_available_keys:
            description = SensorEntityDescription(key=key, name=key)
            sensor = CarelinkSensor(
                coordinator=mock_coordinator,
                sensor_description=description,
                entity_name=f"Test {key}",
            )
            assert sensor.available is True, f"Sensor {key} should be available"

    def test_regular_sensors_unavailable_with_stale_data(self, mock_coordinator):
        """Test that regular sensors become unavailable with stale data."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: old_time}
        
        # Regular sensors should be unavailable with stale data
        regular_sensor_keys = [
            SENSOR_KEY_LASTSG_MGDL,
            "reservoir_level",
            "pump_battery_level",
            "active_insulin",
        ]
        
        for key in regular_sensor_keys:
            description = SensorEntityDescription(key=key, name=key)
            sensor = CarelinkSensor(
                coordinator=mock_coordinator,
                sensor_description=description,
                entity_name=f"Test {key}",
            )
            assert sensor.available is False, f"Sensor {key} should be unavailable"
