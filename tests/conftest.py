"""Fixtures for Carelink tests."""
import sys
from typing import Any
from unittest.mock import MagicMock

import pytest


def _create_mock_modules() -> dict[str, MagicMock]:
    """Create mock modules for homeassistant dependencies."""
    mock_modules = {
        'homeassistant': MagicMock(),
        'homeassistant.components': MagicMock(),
        'homeassistant.components.sensor': MagicMock(),
        'homeassistant.components.binary_sensor': MagicMock(),
        'homeassistant.config_entries': MagicMock(),
        'homeassistant.const': MagicMock(),
        'homeassistant.core': MagicMock(),
        'homeassistant.data_entry_flow': MagicMock(),
        'homeassistant.exceptions': MagicMock(),
        'homeassistant.helpers': MagicMock(),
        'homeassistant.helpers.entity': MagicMock(),
        'homeassistant.helpers.entity_platform': MagicMock(),
        'homeassistant.helpers.update_coordinator': MagicMock(),
        'homeassistant.util': MagicMock(),
        'homeassistant.util.dt': MagicMock(),
    }

    # Set up Platform enum mock
    mock_modules['homeassistant.const'].Platform = MagicMock()
    mock_modules['homeassistant.const'].Platform.SENSOR = 'sensor'
    mock_modules['homeassistant.const'].Platform.BINARY_SENSOR = 'binary_sensor'

    # Set up default timezone mock
    mock_modules['homeassistant.util.dt'].DEFAULT_TIME_ZONE = 'UTC'

    # Set up HomeAssistantError mock
    class MockHomeAssistantError(Exception):
        """Mock HomeAssistant error."""
        pass

    mock_modules['homeassistant.exceptions'].HomeAssistantError = MockHomeAssistantError

    # Set up FlowResultType mock
    mock_modules['homeassistant.data_entry_flow'].FlowResultType = MagicMock()
    mock_modules['homeassistant.data_entry_flow'].FlowResultType.FORM = 'form'
    mock_modules['homeassistant.data_entry_flow'].FlowResultType.CREATE_ENTRY = 'create_entry'

    return mock_modules


# Store original modules for cleanup
_original_modules: dict[str, Any] = {}
_mock_modules = _create_mock_modules()

# Save originals and apply mocks
for key in _mock_modules:
    _original_modules[key] = sys.modules.get(key)
sys.modules.update(_mock_modules)

# Now we can import our modules
from custom_components.carelink.api import CarelinkClient
from custom_components.carelink.nightscout_uploader import NightscoutUploader


def pytest_sessionfinish(session, exitstatus):
    """Clean up sys.modules after test session."""
    for key, original in _original_modules.items():
        if original is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = original


@pytest.fixture
def mock_token_data() -> dict[str, str]:
    """Return mock token data.

    Note: The JWT token contains a hardcoded expiration (exp: 9999999999 = Nov 2286)
    to ensure tests don't fail due to token expiration. The payload contains:
    - exp: 9999999999
    - token_details: {"country": "NL", "preferred_username": "testuser"}
    """
    return {
        "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjk5OTk5OTk5OTksInRva2VuX2RldGFpbHMiOnsiY291bnRyeSI6Ik5MIiwicHJlZmVycmVkX3VzZXJuYW1lIjoidGVzdHVzZXIifX0.fake",
        "refresh_token": "mock_refresh_token",
        "client_id": "mock_client_id",
        "client_secret": "mock_client_secret",
        "mag-identifier": "mock_mag_identifier",
    }


@pytest.fixture
def mock_recent_data() -> dict[str, Any]:
    """Return mock recent data from Carelink API."""
    return {
        "clientTimeZoneName": "Europe/Amsterdam",
        "lastConduitDateTime": "2024-01-15T12:00:00.000Z",
        "pumpBatteryLevelPercent": 75,
        "conduitBatteryLevel": 100,
        "gstBatteryLevel": 80,
        "sensorDurationHours": 120,
        "sensorDurationMinutes": 30,
        "reservoirLevelPercent": 50,
        "reservoirAmount": 100,
        "reservoirRemainingUnits": 50,
        "lastSGTrend": "FLAT",
        "timeToNextCalibHours": 6,
        "averageSG": 120,
        "belowHypoLimit": 5,
        "aboveHyperLimit": 10,
        "timeInRange": 85,
        "maxAutoBasalRate": 2.5,
        "sgBelowLimit": 70,
        "pumpCommunicationState": True,
        "gstCommunicationState": True,
        "conduitInRange": True,
        "conduitMedicalDeviceInRange": True,
        "conduitSensorInRange": True,
        "conduitSerialNumber": "MOCK123456",
        "firstName": "Test",
        "lastName": "User",
        "pumpModelNumber": "MMT-1780",
        "appModelType": "Guardian",
        "activeInsulin": {
            "amount": 2.5,
            "datetime": "2024-01-15T11:30:00.000Z",
        },
        "lastAlarm": {
            "dateTime": "2024-01-15T10:00:00.000Z",
            "faultId": 123,
            "GUID": "mock-guid",
        },
        "therapyAlgorithmState": {
            "autoModeShieldState": "SAFE_BASAL",
        },
        "markers": [],
        "sgs": [
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
        ],
        "notificationHistory": {
            "clearedNotifications": [],
        },
        "medicalDeviceInformation": {
            "manufacturer": "Medtronic",
            "modelNumber": "MMT-1780",
            "hardwareRevision": "1.0",
            "firmwareRevision": "2.0",
            "systemId": "MOCK_SYSTEM_ID",
        },
    }


@pytest.fixture
def mock_carelink_client(mock_token_data: dict[str, str]) -> CarelinkClient:
    """Return a CarelinkClient instance for testing."""
    client = CarelinkClient(
        carelink_refresh_token=mock_token_data["refresh_token"],
        carelink_token=mock_token_data["access_token"],
        client_id=mock_token_data["client_id"],
        client_secret=mock_token_data["client_secret"],
        mag_identifier=mock_token_data["mag-identifier"],
        carelink_patient_id="mock_patient_id",
    )
    return client


@pytest.fixture
def mock_nightscout_uploader() -> NightscoutUploader:
    """Return a NightscoutUploader instance for testing."""
    uploader = NightscoutUploader(
        nightscout_url="https://nightscout.example.com",
        nightscout_secret="mock_api_secret",
    )
    return uploader
