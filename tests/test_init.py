"""Tests for the Carelink integration __init__ module."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.carelink import (
    convert_date_to_isodate,
    get_active_notification,
    get_last_marker,
    get_sg,
    sanitize_for_logging,
)


class TestSanitizeForLogging:
    """Tests for the sanitize_for_logging function."""

    def test_sanitize_simple_dict(self):
        """Test sanitizing a simple dictionary with PII."""
        data = {"firstName": "John", "lastName": "Doe", "pumpBatteryLevel": 75}
        result = sanitize_for_logging(data)

        assert result["firstName"] == "[REDACTED]"
        assert result["lastName"] == "[REDACTED]"
        assert result["pumpBatteryLevel"] == 75

    def test_sanitize_nested_dict(self):
        """Test sanitizing nested dictionaries."""
        data = {
            "user": {
                "firstName": "John",
                "email": "john@example.com",
                "settings": {"theme": "dark"},
            }
        }
        result = sanitize_for_logging(data)

        assert result["user"]["firstName"] == "[REDACTED]"
        assert result["user"]["email"] == "[REDACTED]"
        assert result["user"]["settings"]["theme"] == "dark"

    def test_sanitize_list(self):
        """Test sanitizing a list containing dictionaries."""
        data = [
            {"firstName": "John", "status": "active"},
            {"firstName": "Jane", "status": "inactive"},
        ]
        result = sanitize_for_logging(data)

        assert result[0]["firstName"] == "[REDACTED]"
        assert result[0]["status"] == "active"
        assert result[1]["firstName"] == "[REDACTED]"
        assert result[1]["status"] == "inactive"

    def test_sanitize_max_depth(self):
        """Test that max depth prevents infinite recursion."""
        # Create deeply nested structure
        data = {"level": 0}
        current = data
        for i in range(15):
            current["nested"] = {"level": i + 1}
            current = current["nested"]

        result = sanitize_for_logging(data)
        # Should not raise an error and should handle deep nesting
        assert result is not None

    def test_sanitize_all_pii_fields(self):
        """Test that all known PII fields are redacted."""
        data = {
            "firstName": "John",
            "lastName": "Doe",
            "username": "johndoe",
            "patientId": "12345",
            "conduitSerialNumber": "ABC123",
            "medicalDeviceSerialNumber": "XYZ789",
            "systemId": "SYS001",
            "email": "john@example.com",
            "phone": "555-1234",
            "emailAddress": "john@test.com",
            "phoneNumber": "555-5678",
            "address": "123 Main St",
            "dateOfBirth": "1990-01-01",
            "dob": "1990-01-01",
            "deviceSerialNumber": "DEV123",
        }
        result = sanitize_for_logging(data)

        for key in data.keys():
            assert result[key] == "[REDACTED]"

    def test_sanitize_non_dict_values(self):
        """Test sanitizing preserves non-dict values."""
        data = {"name": "test", "count": 42, "active": True, "rate": 1.5}
        result = sanitize_for_logging(data)

        assert result["name"] == "test"
        assert result["count"] == 42
        assert result["active"] is True
        assert result["rate"] == 1.5


class TestConvertDateToIsodate:
    """Tests for the convert_date_to_isodate function."""

    def test_convert_standard_format(self):
        """Test converting standard ISO format with milliseconds."""
        date_str = "2024-01-15T12:00:00.000Z"
        result = convert_date_to_isodate(date_str)

        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 12
        assert result.minute == 0
        assert result.second == 0
        assert result.tzinfo is None

    def test_convert_different_milliseconds(self):
        """Test converting with different millisecond values."""
        date_str = "2024-06-20T15:30:45.123Z"
        result = convert_date_to_isodate(date_str)

        assert result.year == 2024
        assert result.month == 6
        assert result.day == 20
        assert result.hour == 15
        assert result.minute == 30
        assert result.second == 45


class TestGetSg:
    """Tests for the get_sg function."""

    def test_get_sg_first_position(self):
        """Test getting the most recent SG reading."""
        sgs = [
            {
                "timestamp": "2024-01-15T12:00:00.000Z",
                "sg": 120,
                "sensorState": "NO_ERROR_MESSAGE",
            },
            {
                "timestamp": "2024-01-15T11:55:00.000Z",
                "sg": 118,
                "sensorState": "NO_ERROR_MESSAGE",
            },
        ]
        result = get_sg(sgs, 0)

        assert result is not None
        assert result["sg"] == 120

    def test_get_sg_second_position(self):
        """Test getting the second most recent SG reading."""
        sgs = [
            {
                "timestamp": "2024-01-15T12:00:00.000Z",
                "sg": 120,
                "sensorState": "NO_ERROR_MESSAGE",
            },
            {
                "timestamp": "2024-01-15T11:55:00.000Z",
                "sg": 118,
                "sensorState": "NO_ERROR_MESSAGE",
            },
        ]
        result = get_sg(sgs, 1)

        assert result is not None
        assert result["sg"] == 118

    def test_get_sg_empty_list(self):
        """Test getting SG from empty list returns None."""
        result = get_sg([], 0)
        assert result is None

    def test_get_sg_position_out_of_range(self):
        """Test getting SG at position beyond list length."""
        sgs = [
            {
                "timestamp": "2024-01-15T12:00:00.000Z",
                "sg": 120,
                "sensorState": "NO_ERROR_MESSAGE",
            }
        ]
        result = get_sg(sgs, 5)
        assert result is None

    def test_get_sg_filters_error_states(self):
        """Test that readings with error states are filtered out."""
        sgs = [
            {
                "timestamp": "2024-01-15T12:00:00.000Z",
                "sg": 120,
                "sensorState": "SENSOR_ERROR",
            },
            {
                "timestamp": "2024-01-15T11:55:00.000Z",
                "sg": 118,
                "sensorState": "NO_ERROR_MESSAGE",
            },
        ]
        result = get_sg(sgs, 0)

        # Should return the non-error reading as most recent
        assert result is not None
        assert result["sg"] == 118

    def test_get_sg_sorts_by_timestamp(self):
        """Test that readings are sorted by timestamp (newest first)."""
        sgs = [
            {
                "timestamp": "2024-01-15T11:55:00.000Z",
                "sg": 115,
                "sensorState": "NO_ERROR_MESSAGE",
            },
            {
                "timestamp": "2024-01-15T12:05:00.000Z",
                "sg": 125,
                "sensorState": "NO_ERROR_MESSAGE",
            },
            {
                "timestamp": "2024-01-15T12:00:00.000Z",
                "sg": 120,
                "sensorState": "NO_ERROR_MESSAGE",
            },
        ]
        result = get_sg(sgs, 0)

        # Should return the reading with the latest timestamp
        assert result is not None
        assert result["sg"] == 125


class TestGetActiveNotification:
    """Tests for the get_active_notification function.

    NOTE: There appears to be a bug in get_active_notification() where it returns
    None when clearedNotifications is empty, but logically an alarm with no
    cleared notifications should be considered active (returning last_alarm).
    These tests document the current behavior, not necessarily the correct behavior.
    """

    def test_active_notification_empty_cleared_list(self):
        """Test behavior with empty cleared notifications list.

        BUG: When clearedNotifications is empty, the function returns None
        because the `if filtered_array:` block is not entered and there's no
        explicit return statement. Logically, if no notifications have been
        cleared, the alarm should still be active (return last_alarm).
        """
        last_alarm = {
            "dateTime": "2024-01-15T12:00:00.000Z",
            "GUID": "alarm-guid-123",
            "faultId": 123,
        }
        notifications = {"clearedNotifications": []}

        result = get_active_notification(last_alarm, notifications)

        # Current behavior: returns None when clearedNotifications is empty
        # Expected behavior: should return last_alarm (alarm is active)
        assert result is None

    def test_notification_is_cleared(self):
        """Test that None is returned if notification is cleared."""
        last_alarm = {
            "dateTime": "2024-01-15T12:00:00.000Z",
            "GUID": "alarm-guid-123",
            "faultId": 123,
        }
        notifications = {
            "clearedNotifications": [
                {
                    "dateTime": "2024-01-15T12:05:00.000Z",
                    "referenceGUID": "alarm-guid-123",
                }
            ]
        }

        result = get_active_notification(last_alarm, notifications)

        assert result is None

    def test_notification_different_guid_not_cleared(self):
        """Test notification returned when different GUID is cleared."""
        last_alarm = {
            "dateTime": "2024-01-15T12:00:00.000Z",
            "GUID": "alarm-guid-123",
            "faultId": 123,
        }
        notifications = {
            "clearedNotifications": [
                {
                    "dateTime": "2024-01-15T12:05:00.000Z",
                    "referenceGUID": "different-guid-456",
                }
            ]
        }

        result = get_active_notification(last_alarm, notifications)

        assert result == last_alarm


class TestGetLastMarker:
    """Tests for the get_last_marker function."""

    def test_get_last_meal_marker(self):
        """Test getting the last meal marker."""
        markers = [
            {
                "type": "MEAL",
                "timestamp": "2024-01-15T12:00:00.000Z",
                "amount": 50,
                "version": 1,
                "kind": "meal",
                "index": 0,
                "views": [],
            },
            {
                "type": "MEAL",
                "timestamp": "2024-01-15T08:00:00.000Z",
                "amount": 30,
                "version": 1,
                "kind": "meal",
                "index": 1,
                "views": [],
            },
        ]

        result = get_last_marker("MEAL", markers)

        assert result is not None
        assert "DATETIME" in result
        assert "ATTRS" in result
        # Should be the more recent marker
        assert result["ATTRS"]["amount"] == 50
        # Should have removed version, kind, index, views
        assert "version" not in result["ATTRS"]
        assert "kind" not in result["ATTRS"]
        assert "index" not in result["ATTRS"]
        assert "views" not in result["ATTRS"]

    def test_get_last_insulin_marker(self):
        """Test getting the last insulin marker."""
        markers = [
            {
                "type": "INSULIN",
                "timestamp": "2024-01-15T12:00:00.000Z",
                "amount": 5.0,
                "version": 1,
                "kind": "insulin",
                "index": 0,
                "views": [],
            },
        ]

        result = get_last_marker("INSULIN", markers)

        assert result is not None
        assert result["ATTRS"]["amount"] == 5.0

    def test_get_marker_empty_list(self):
        """Test getting marker from empty list returns None."""
        result = get_last_marker("MEAL", [])
        assert result is None

    def test_get_marker_type_not_found(self):
        """Test getting marker of non-existent type returns None."""
        markers = [
            {
                "type": "MEAL",
                "timestamp": "2024-01-15T12:00:00.000Z",
                "amount": 50,
                "version": 1,
                "kind": "meal",
                "index": 0,
                "views": [],
            },
        ]

        result = get_last_marker("AUTO_BASAL_DELIVERY", markers)
        assert result is None

    def test_get_last_marker_sorts_by_timestamp(self):
        """Test markers are sorted by timestamp (newest first)."""
        markers = [
            {
                "type": "MEAL",
                "timestamp": "2024-01-15T08:00:00.000Z",
                "amount": 30,
                "version": 1,
                "kind": "meal",
                "index": 0,
                "views": [],
            },
            {
                "type": "MEAL",
                "timestamp": "2024-01-15T18:00:00.000Z",
                "amount": 60,
                "version": 1,
                "kind": "meal",
                "index": 1,
                "views": [],
            },
            {
                "type": "MEAL",
                "timestamp": "2024-01-15T12:00:00.000Z",
                "amount": 45,
                "version": 1,
                "kind": "meal",
                "index": 2,
                "views": [],
            },
        ]

        result = get_last_marker("MEAL", markers)

        # Should return the 18:00 marker (most recent)
        assert result["ATTRS"]["amount"] == 60


class TestMigrateLegacyLogindata:
    """Tests for the _migrate_legacy_logindata function."""

    def test_migrate_legacy_file_exists(self, tmp_path):
        """Test migration when legacy file exists and new file doesn't."""
        from custom_components.carelink import _migrate_legacy_logindata, LEGACY_AUTH_FILE
        from custom_components.carelink.api import AUTH_FILE_PREFIX

        # Create the legacy directory structure
        legacy_dir = tmp_path / "custom_components" / "carelink"
        legacy_dir.mkdir(parents=True)
        legacy_file = legacy_dir / "logindata.json"
        legacy_file.write_text('{"access_token": "test123"}')

        entry_id = "test_entry_123"
        new_filename = f"{AUTH_FILE_PREFIX}_{entry_id}.json"

        # Run migration
        _migrate_legacy_logindata(str(tmp_path), entry_id)

        # Check new file exists with correct content
        new_file = tmp_path / new_filename
        assert new_file.exists()
        assert new_file.read_text() == '{"access_token": "test123"}'

        # Check legacy file is removed
        assert not legacy_file.exists()

    def test_migrate_no_legacy_file(self, tmp_path):
        """Test migration does nothing when legacy file doesn't exist."""
        from custom_components.carelink import _migrate_legacy_logindata
        from custom_components.carelink.api import AUTH_FILE_PREFIX

        entry_id = "test_entry_456"
        new_filename = f"{AUTH_FILE_PREFIX}_{entry_id}.json"

        # Run migration (no legacy file exists)
        _migrate_legacy_logindata(str(tmp_path), entry_id)

        # Check no new file was created
        new_file = tmp_path / new_filename
        assert not new_file.exists()

    def test_migrate_new_file_already_exists(self, tmp_path):
        """Test migration skips if new file already exists."""
        from custom_components.carelink import _migrate_legacy_logindata, LEGACY_AUTH_FILE
        from custom_components.carelink.api import AUTH_FILE_PREFIX

        # Create the legacy directory structure and file
        legacy_dir = tmp_path / "custom_components" / "carelink"
        legacy_dir.mkdir(parents=True)
        legacy_file = legacy_dir / "logindata.json"
        legacy_file.write_text('{"access_token": "old_token"}')

        entry_id = "test_entry_789"
        new_filename = f"{AUTH_FILE_PREFIX}_{entry_id}.json"

        # Create the new file already
        new_file = tmp_path / new_filename
        new_file.write_text('{"access_token": "new_token"}')

        # Run migration
        _migrate_legacy_logindata(str(tmp_path), entry_id)

        # Check new file wasn't overwritten
        assert new_file.read_text() == '{"access_token": "new_token"}'

        # Check legacy file still exists (not removed since migration was skipped)
        assert legacy_file.exists()
