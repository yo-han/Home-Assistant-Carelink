"""Tests for binary sensor availability logic."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from custom_components.carelink.const import (
    DATA_STALE_TIMEOUT_HOURS,
    SENSOR_KEY_UPDATE_TIMESTAMP,
    BINARY_SENSOR_KEY_PUMP_COMM_STATE,
    is_data_stale,
)
from custom_components.carelink.binary_sensor import CarelinkBinarySensor
from homeassistant.components.binary_sensor import BinarySensorEntityDescription


class TestBinarySensorAvailability:
    """Test binary sensor availability checks."""

    @pytest.fixture
    def mock_coordinator(self):
        """Create a mock coordinator."""
        coordinator = MagicMock()
        coordinator.data = {}
        coordinator.last_update_success = True
        return coordinator

    @pytest.fixture
    def mock_binary_sensor_description(self):
        """Create a mock binary sensor description."""
        return BinarySensorEntityDescription(
            key=BINARY_SENSOR_KEY_PUMP_COMM_STATE,
            name="Pump Communication State",
        )

    def test_binary_sensor_available_with_fresh_data(
        self, mock_coordinator, mock_binary_sensor_description
    ):
        """Test that binary sensor is available with fresh data."""
        now = datetime.now(timezone.utc)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: now}
        
        sensor = CarelinkBinarySensor(
            coordinator=mock_coordinator,
            sensor_description=mock_binary_sensor_description,
            entity_name="Test Binary Sensor",
        )
        
        assert sensor.available is True

    def test_binary_sensor_unavailable_with_stale_data(
        self, mock_coordinator, mock_binary_sensor_description
    ):
        """Test that binary sensor is unavailable with stale data."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: old_time}
        
        sensor = CarelinkBinarySensor(
            coordinator=mock_coordinator,
            sensor_description=mock_binary_sensor_description,
            entity_name="Test Binary Sensor",
        )
        
        assert sensor.available is False

    def test_binary_sensor_unavailable_when_coordinator_fails(
        self, mock_coordinator, mock_binary_sensor_description
    ):
        """Test that binary sensor respects coordinator availability."""
        now = datetime.now(timezone.utc)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: now}
        mock_coordinator.last_update_success = False
        
        sensor = CarelinkBinarySensor(
            coordinator=mock_coordinator,
            sensor_description=mock_binary_sensor_description,
            entity_name="Test Binary Sensor",
        )
        
        # When coordinator fails, sensor should be unavailable
        # even if data would otherwise be fresh
        assert sensor.available is False

    def test_binary_sensor_unavailable_with_missing_timestamp(
        self, mock_coordinator, mock_binary_sensor_description
    ):
        """Test that binary sensor is unavailable when timestamp is missing."""
        mock_coordinator.data = {}
        
        sensor = CarelinkBinarySensor(
            coordinator=mock_coordinator,
            sensor_description=mock_binary_sensor_description,
            entity_name="Test Binary Sensor",
        )
        
        assert sensor.available is False

    def test_binary_sensor_unavailable_with_none_timestamp(
        self, mock_coordinator, mock_binary_sensor_description
    ):
        """Test that binary sensor is unavailable when timestamp is None."""
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: None}
        
        sensor = CarelinkBinarySensor(
            coordinator=mock_coordinator,
            sensor_description=mock_binary_sensor_description,
            entity_name="Test Binary Sensor",
        )
        
        assert sensor.available is False

    def test_binary_sensor_available_at_boundary_time(
        self, mock_coordinator, mock_binary_sensor_description
    ):
        """Test that binary sensor is available exactly at the timeout threshold."""
        now = datetime.now(timezone.utc)
        boundary_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS, seconds=-1)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: boundary_time}
        
        sensor = CarelinkBinarySensor(
            coordinator=mock_coordinator,
            sensor_description=mock_binary_sensor_description,
            entity_name="Test Binary Sensor",
        )
        
        assert sensor.available is True

    def test_multiple_binary_sensors_with_stale_data(self, mock_coordinator):
        """Test that all binary sensors become unavailable with stale data."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: old_time}
        
        # All binary sensors should be unavailable with stale data
        binary_sensor_keys = [
            BINARY_SENSOR_KEY_PUMP_COMM_STATE,
            "binary_sensor_sensor_comm_state",
            "binary_sensor_conduit_in_range",
            "binary_sensor_conduit_pump_in_range",
            "binary_sensor_conduit_sensor_in_range",
        ]
        
        for key in binary_sensor_keys:
            description = BinarySensorEntityDescription(key=key, name=key)
            sensor = CarelinkBinarySensor(
                coordinator=mock_coordinator,
                sensor_description=description,
                entity_name=f"Test {key}",
            )
            assert sensor.available is False, f"Binary sensor {key} should be unavailable"

    def test_binary_sensor_becomes_available_after_fresh_update(
        self, mock_coordinator, mock_binary_sensor_description
    ):
        """Test that binary sensor becomes available after receiving fresh data."""
        # Start with stale data
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=DATA_STALE_TIMEOUT_HOURS + 1)
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: old_time}
        
        sensor = CarelinkBinarySensor(
            coordinator=mock_coordinator,
            sensor_description=mock_binary_sensor_description,
            entity_name="Test Binary Sensor",
        )
        
        assert sensor.available is False
        
        # Update with fresh data
        mock_coordinator.data = {SENSOR_KEY_UPDATE_TIMESTAMP: now}
        
        # Should now be available
        assert sensor.available is True
