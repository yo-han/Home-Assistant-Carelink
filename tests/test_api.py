"""Tests for the Carelink API client."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from custom_components.carelink.api import CarelinkClient


class TestCarelinkClient:
    """Tests for CarelinkClient."""

    def test_init(self, mock_carelink_client):
        """Test CarelinkClient initialization."""
        assert mock_carelink_client is not None
        assert mock_carelink_client._async_client is None

    def test_async_client_property(self, mock_carelink_client):
        """Test async_client property creates client on first access."""
        client = mock_carelink_client.async_client
        assert client is not None
        # Second access should return same client
        assert mock_carelink_client.async_client is client

    async def test_close(self, mock_carelink_client):
        """Test closing the HTTP client."""
        # Create client first
        _ = mock_carelink_client.async_client
        assert mock_carelink_client._async_client is not None

        # Close it
        await mock_carelink_client.close()
        assert mock_carelink_client._async_client is None

    async def test_close_when_not_initialized(self, mock_carelink_client):
        """Test closing when client was never created."""
        # Should not raise
        await mock_carelink_client.close()
        assert mock_carelink_client._async_client is None

    async def test_fetch_async(self, mock_carelink_client):
        """Test fetch_async method."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"test": "data"}'

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_carelink_client._async_client = mock_client

        response = await mock_carelink_client.fetch_async(
            "https://test.com", headers={"Authorization": "Bearer test"}
        )

        assert response.status_code == 200
        mock_client.get.assert_called_once()

    async def test_post_async(self, mock_carelink_client):
        """Test post_async method."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_carelink_client._async_client = mock_client

        response = await mock_carelink_client.post_async(
            "https://test.com",
            headers={"Content-Type": "application/json"},
            data={"key": "value"},
        )

        assert response.status_code == 200
        mock_client.post.assert_called_once()

    async def test_fetch_async_timeout(self, mock_carelink_client):
        """Test fetch_async handles timeout exception."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))
        mock_carelink_client._async_client = mock_client

        with pytest.raises(httpx.TimeoutException):
            await mock_carelink_client.fetch_async(
                "https://test.com", headers={"Authorization": "Bearer test"}
            )

    async def test_fetch_async_request_error(self, mock_carelink_client):
        """Test fetch_async handles request error."""
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
        mock_carelink_client._async_client = mock_client

        with pytest.raises(httpx.RequestError):
            await mock_carelink_client.fetch_async(
                "https://test.com", headers={"Authorization": "Bearer test"}
            )

    async def test_post_async_timeout(self, mock_carelink_client):
        """Test post_async handles timeout exception."""
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))
        mock_carelink_client._async_client = mock_client

        with pytest.raises(httpx.TimeoutException):
            await mock_carelink_client.post_async(
                "https://test.com",
                headers={"Content-Type": "application/json"},
                data={"key": "value"},
            )

    async def test_post_async_request_error(self, mock_carelink_client):
        """Test post_async handles request error."""
        mock_client = MagicMock()
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Connection failed"))
        mock_carelink_client._async_client = mock_client

        with pytest.raises(httpx.RequestError):
            await mock_carelink_client.post_async(
                "https://test.com",
                headers={"Content-Type": "application/json"},
                data={"key": "value"},
            )


class TestTokenProcessing:
    """Tests for token processing methods."""

    async def test_get_access_token_payload_valid(self, mock_carelink_client, mock_token_data):
        """Test extracting payload from valid JWT token."""
        result = await mock_carelink_client._get_access_token_payload(mock_token_data)

        assert result is not None
        assert "token_details" in result
        assert result["token_details"]["country"] == "NL"

    async def test_get_access_token_payload_missing_token(self, mock_carelink_client):
        """Test handling missing access token."""
        result = await mock_carelink_client._get_access_token_payload({})
        assert result is None

    async def test_get_access_token_payload_invalid_token(self, mock_carelink_client):
        """Test handling invalid/malformed token."""
        result = await mock_carelink_client._get_access_token_payload(
            {"access_token": "invalid_token_without_dots"}
        )
        assert result is None

    async def test_get_access_token_payload_none_input(self, mock_carelink_client):
        """Test handling None input."""
        result = await mock_carelink_client._get_access_token_payload(None)
        assert result is None


class TestWriteTokenFile:
    """Tests for token file writing."""

    async def test_write_token_file(self, mock_carelink_client, tmp_path):
        """Test writing token file."""
        token_file = tmp_path / "token.json"
        token_data = {"access_token": "test", "refresh_token": "test"}

        await mock_carelink_client._write_token_file(token_data, str(token_file))

        assert token_file.exists()
        with open(token_file) as f:
            saved_data = json.load(f)
        assert saved_data == token_data

    async def test_write_token_file_creates_directory(self, mock_carelink_client, tmp_path):
        """Test that writing token file creates parent directories."""
        token_file = tmp_path / "subdir" / "token.json"
        token_data = {"access_token": "test"}

        await mock_carelink_client._write_token_file(token_data, str(token_file))

        assert token_file.exists()


class TestProcessTokenFile:
    """Tests for token file processing."""

    async def test_process_token_file_valid(self, mock_carelink_client, tmp_path, mock_token_data):
        """Test processing a valid token file."""
        token_file = tmp_path / "token.json"
        with open(token_file, "w") as f:
            json.dump(mock_token_data, f)

        result = await mock_carelink_client._process_token_file(str(token_file))

        assert result is not None
        assert result["access_token"] == mock_token_data["access_token"]

    async def test_process_token_file_not_exists(self, mock_carelink_client, tmp_path):
        """Test processing non-existent token file with no static config."""
        token_file = tmp_path / "nonexistent.json"

        # Client has no static config set
        mock_carelink_client._CarelinkClient__carelink_access_token = None
        mock_carelink_client._CarelinkClient__carelink_refresh_token = None
        mock_carelink_client._CarelinkClient__client_id = None

        result = await mock_carelink_client._process_token_file(str(token_file))

        assert result is None

    async def test_process_token_file_missing_required_fields(
        self, mock_carelink_client, tmp_path
    ):
        """Test processing token file with missing required fields."""
        token_file = tmp_path / "token.json"
        incomplete_data = {"access_token": "test"}  # Missing refresh_token and client_id

        with open(token_file, "w") as f:
            json.dump(incomplete_data, f)

        result = await mock_carelink_client._process_token_file(str(token_file))

        assert result is None

    async def test_process_token_file_invalid_json(self, mock_carelink_client, tmp_path):
        """Test processing token file with invalid JSON."""
        token_file = tmp_path / "token.json"
        with open(token_file, "w") as f:
            f.write("not valid json {{{")

        result = await mock_carelink_client._process_token_file(str(token_file))

        assert result is None

    async def test_process_token_file_permission_error(self, mock_carelink_client, tmp_path):
        """Test processing token file with permission error (OSError)."""
        token_file = tmp_path / "token.json"

        # Client has no static config set
        mock_carelink_client._CarelinkClient__carelink_access_token = None
        mock_carelink_client._CarelinkClient__carelink_refresh_token = None
        mock_carelink_client._CarelinkClient__client_id = None

        with patch("builtins.open", side_effect=OSError("Permission denied")):
            result = await mock_carelink_client._process_token_file(str(token_file))

        assert result is None
