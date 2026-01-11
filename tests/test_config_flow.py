"""Tests for the Carelink config flow."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.carelink.config_flow import (
    CannotConnect,
    InvalidAuth,
    validate_input,
)


class TestValidateInput:
    """Tests for the validate_input function."""

    async def test_validate_input_success(self):
        """Test successful validation."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.carelink.config_flow.CarelinkClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.login = AsyncMock(return_value=True)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            data = {
                "cl_token": "test_token",
                "cl_refresh_token": "test_refresh",
                "cl_client_id": "test_client_id",
                "cl_client_secret": "test_secret",
                "cl_mag_identifier": "test_mag",
                "patientId": "test_patient",
            }

            result = await validate_input(mock_hass, data)

            assert result == {"title": "Carelink"}
            mock_client.login.assert_called_once()
            mock_client.close.assert_called_once()

    async def test_validate_input_invalid_auth(self):
        """Test validation with invalid credentials."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.carelink.config_flow.CarelinkClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.login = AsyncMock(return_value=False)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            data = {
                "cl_token": "invalid_token",
                "cl_refresh_token": "invalid_refresh",
            }

            with pytest.raises(InvalidAuth):
                await validate_input(mock_hass, data)

    async def test_validate_input_nightscout_success(self):
        """Test validation with valid Nightscout configuration."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.carelink.config_flow.CarelinkClient"
        ) as mock_client_class, patch(
            "custom_components.carelink.config_flow.NightscoutUploader"
        ) as mock_uploader_class:
            mock_client = MagicMock()
            mock_client.login = AsyncMock(return_value=True)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            mock_uploader = MagicMock()
            mock_uploader.reachServer = AsyncMock(return_value=True)
            mock_uploader.close = AsyncMock()
            mock_uploader_class.return_value = mock_uploader

            data = {
                "cl_token": "test_token",
                "cl_refresh_token": "test_refresh",
                "nightscout_url": "https://nightscout.example.com",
                "nightscout_api": "secret123",
            }

            result = await validate_input(mock_hass, data)

            assert result == {"title": "Carelink"}
            mock_uploader.reachServer.assert_called_once()

    async def test_validate_input_nightscout_unreachable(self):
        """Test validation when Nightscout server is unreachable."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.carelink.config_flow.CarelinkClient"
        ) as mock_client_class, patch(
            "custom_components.carelink.config_flow.NightscoutUploader"
        ) as mock_uploader_class:
            mock_client = MagicMock()
            mock_client.login = AsyncMock(return_value=True)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            mock_uploader = MagicMock()
            mock_uploader.reachServer = AsyncMock(return_value=False)
            mock_uploader.close = AsyncMock()
            mock_uploader_class.return_value = mock_uploader

            data = {
                "cl_token": "test_token",
                "cl_refresh_token": "test_refresh",
                "nightscout_url": "https://nightscout.example.com",
                "nightscout_api": "secret123",
            }

            with pytest.raises(CannotConnect):
                await validate_input(mock_hass, data)

    async def test_validate_input_nightscout_url_only(self):
        """Test validation fails when only URL is provided."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.carelink.config_flow.CarelinkClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.login = AsyncMock(return_value=True)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            data = {
                "cl_token": "test_token",
                "cl_refresh_token": "test_refresh",
                "nightscout_url": "https://nightscout.example.com",
                # Missing nightscout_api
            }

            with pytest.raises(CannotConnect):
                await validate_input(mock_hass, data)

    async def test_validate_input_nightscout_api_only(self):
        """Test validation fails when only API key is provided."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.carelink.config_flow.CarelinkClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.login = AsyncMock(return_value=True)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            data = {
                "cl_token": "test_token",
                "cl_refresh_token": "test_refresh",
                "nightscout_api": "secret123",
                # Missing nightscout_url
            }

            with pytest.raises(CannotConnect):
                await validate_input(mock_hass, data)

    async def test_validate_input_invalid_url_scheme(self):
        """Test validation fails with invalid URL scheme."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.carelink.config_flow.CarelinkClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.login = AsyncMock(return_value=True)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            data = {
                "cl_token": "test_token",
                "cl_refresh_token": "test_refresh",
                "nightscout_url": "ftp://nightscout.example.com",
                "nightscout_api": "secret123",
            }

            with pytest.raises(CannotConnect):
                await validate_input(mock_hass, data)

    async def test_validate_input_url_without_host(self):
        """Test validation fails with URL without host."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.carelink.config_flow.CarelinkClient"
        ) as mock_client_class:
            mock_client = MagicMock()
            mock_client.login = AsyncMock(return_value=True)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            data = {
                "cl_token": "test_token",
                "cl_refresh_token": "test_refresh",
                "nightscout_url": "https://",
                "nightscout_api": "secret123",
            }

            with pytest.raises(CannotConnect):
                await validate_input(mock_hass, data)

    async def test_validate_input_strips_url_whitespace(self):
        """Test that URL whitespace is stripped."""
        mock_hass = MagicMock()

        with patch(
            "custom_components.carelink.config_flow.CarelinkClient"
        ) as mock_client_class, patch(
            "custom_components.carelink.config_flow.NightscoutUploader"
        ) as mock_uploader_class:
            mock_client = MagicMock()
            mock_client.login = AsyncMock(return_value=True)
            mock_client.close = AsyncMock()
            mock_client_class.return_value = mock_client

            mock_uploader = MagicMock()
            mock_uploader.reachServer = AsyncMock(return_value=True)
            mock_uploader.close = AsyncMock()
            mock_uploader_class.return_value = mock_uploader

            data = {
                "cl_token": "test_token",
                "cl_refresh_token": "test_refresh",
                "nightscout_url": "  https://nightscout.example.com  ",
                "nightscout_api": "secret123",
            }

            await validate_input(mock_hass, data)

            # URL should be stripped
            assert data["nightscout_url"] == "https://nightscout.example.com"


class TestExceptionClasses:
    """Tests for custom exception classes."""

    def test_cannot_connect_exception(self):
        """Test CannotConnect exception can be raised."""
        with pytest.raises(CannotConnect):
            raise CannotConnect()

    def test_invalid_auth_exception(self):
        """Test InvalidAuth exception can be raised."""
        with pytest.raises(InvalidAuth):
            raise InvalidAuth()
