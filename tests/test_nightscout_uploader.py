"""Tests for the Nightscout uploader."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.carelink.nightscout_uploader import NightscoutUploader


class TestNightscoutUploaderInit:
    """Tests for NightscoutUploader initialization."""

    def test_init(self, mock_nightscout_uploader):
        """Test NightscoutUploader initialization."""
        assert mock_nightscout_uploader is not None
        assert mock_nightscout_uploader._async_client is None

    def test_init_url_normalization(self):
        """Test URL normalization (lowercase, trailing slash removal)."""
        uploader = NightscoutUploader(
            nightscout_url="HTTPS://NIGHTSCOUT.EXAMPLE.COM/",
            nightscout_secret="secret",
        )
        # URL should be lowercased and trailing slash removed
        assert str(uploader._NightscoutUploader__nightscout_url) == "https://nightscout.example.com"


    def test_init_secret_hashing(self):
        """Test that secret is hashed with SHA1."""
        uploader = NightscoutUploader(
            nightscout_url="https://test.com",
            nightscout_secret="testsecret",
        )
        # SHA1 hash of "testsecret" should be stored
        assert uploader._NightscoutUploader__hashedSecret is not None
        assert len(uploader._NightscoutUploader__hashedSecret) == 40  # SHA1 hex length


class TestNightscoutUploaderClient:
    """Tests for HTTP client management."""

    def test_async_client_property(self, mock_nightscout_uploader):
        """Test async_client property creates client on first access."""
        client = mock_nightscout_uploader.async_client
        assert client is not None
        # Second access should return same client
        assert mock_nightscout_uploader.async_client is client

    async def test_close(self, mock_nightscout_uploader):
        """Test closing the HTTP client."""
        # Create client first
        _ = mock_nightscout_uploader.async_client
        assert mock_nightscout_uploader._async_client is not None

        # Close it
        await mock_nightscout_uploader.close()
        assert mock_nightscout_uploader._async_client is None

    async def test_close_when_not_initialized(self, mock_nightscout_uploader):
        """Test closing when client was never created."""
        await mock_nightscout_uploader.close()
        assert mock_nightscout_uploader._async_client is None


class TestNightscoutUploaderRequests:
    """Tests for HTTP request methods."""

    async def test_fetch_async(self, mock_nightscout_uploader):
        """Test fetch_async method."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_nightscout_uploader._async_client = mock_client

        response = await mock_nightscout_uploader.fetch_async(
            "https://test.com", headers={}
        )

        assert response.status_code == 200
        mock_client.get.assert_called_once()

    async def test_post_async(self, mock_nightscout_uploader):
        """Test post_async method."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_nightscout_uploader._async_client = mock_client

        response = await mock_nightscout_uploader.post_async(
            "https://test.com", headers={}, data="{}"
        )

        assert response.status_code == 200
        mock_client.post.assert_called_once()


class TestNightscoutUploaderServerConnection:
    """Tests for server connection testing."""

    async def test_reach_server_success(self, mock_nightscout_uploader):
        """Test successful server connection."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(
            mock_nightscout_uploader, "fetch_async", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            result = await mock_nightscout_uploader.reachServer()

            assert result is True

    async def test_reach_server_failure(self, mock_nightscout_uploader):
        """Test failed server connection."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch.object(
            mock_nightscout_uploader, "fetch_async", new_callable=AsyncMock
        ) as mock_fetch:
            mock_fetch.return_value = mock_response

            result = await mock_nightscout_uploader.reachServer()

            assert result is False


class TestNightscoutDataTransformation:
    """Tests for data transformation methods."""

    def test_ns_trend_flat(self, mock_nightscout_uploader):
        """Test trend calculation for flat glucose."""
        present = {"sg": 100}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        assert trend == "Flat"
        assert delta == 0

    def test_ns_trend_single_up(self, mock_nightscout_uploader):
        """Test trend calculation for slight increase."""
        present = {"sg": 110}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        assert trend == "SingleUp"
        assert delta == 10

    def test_ns_trend_single_down(self, mock_nightscout_uploader):
        """Test trend calculation for slight decrease."""
        present = {"sg": 90}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        assert trend == "SingleDown"
        assert delta == -10

    def test_ns_trend_double_up(self, mock_nightscout_uploader):
        """Test trend calculation for rapid increase."""
        present = {"sg": 120}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        assert trend == "DoubleUp"
        assert delta == 20

    def test_ns_trend_double_down(self, mock_nightscout_uploader):
        """Test trend calculation for rapid decrease."""
        present = {"sg": 80}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        assert trend == "DoubleDown"
        assert delta == -20

    def test_ns_trend_zero_values(self, mock_nightscout_uploader):
        """Test trend calculation with zero glucose values."""
        present = {"sg": 0}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        assert trend == "null"
        assert delta == "null"

    # Boundary tests for trend thresholds
    def test_ns_trend_triple_up(self, mock_nightscout_uploader):
        """Test trend for delta > 30 (TripleUp)."""
        present = {"sg": 131}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        assert trend == "TripleUp"
        assert delta == 31

    def test_ns_trend_triple_down(self, mock_nightscout_uploader):
        """Test trend for delta < -30 (TripleDown)."""
        present = {"sg": 69}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        assert trend == "TripleDown"
        assert delta == -31

    def test_ns_trend_boundary_double_up_at_30(self, mock_nightscout_uploader):
        """Test trend at boundary delta=30 (should be DoubleUp, not TripleUp)."""
        present = {"sg": 130}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        # delta=30 is NOT > 30, so should be DoubleUp (delta > 15)
        assert trend == "DoubleUp"
        assert delta == 30

    def test_ns_trend_boundary_double_down_at_minus_30(self, mock_nightscout_uploader):
        """Test trend at boundary delta=-30 (should be DoubleDown, not TripleDown)."""
        present = {"sg": 70}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        # delta=-30 is NOT < -30, so should be DoubleDown (delta < -15)
        assert trend == "DoubleDown"
        assert delta == -30

    def test_ns_trend_boundary_single_up_at_15(self, mock_nightscout_uploader):
        """Test trend at boundary delta=15 (should be SingleUp, not DoubleUp)."""
        present = {"sg": 115}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        # delta=15 is NOT > 15, so should be SingleUp (delta > 5)
        assert trend == "SingleUp"
        assert delta == 15

    def test_ns_trend_boundary_single_down_at_minus_15(self, mock_nightscout_uploader):
        """Test trend at boundary delta=-15 (should be SingleDown, not DoubleDown)."""
        present = {"sg": 85}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        # delta=-15 is NOT < -15, so should be SingleDown (delta < -5)
        assert trend == "SingleDown"
        assert delta == -15

    def test_ns_trend_forty_five_up(self, mock_nightscout_uploader):
        """Test trend for small positive delta (FortyFiveUp)."""
        present = {"sg": 103}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        # delta=3 is > 0 but not > 5, so FortyFiveUp
        assert trend == "FortyFiveUp"
        assert delta == 3

    def test_ns_trend_forty_five_down(self, mock_nightscout_uploader):
        """Test trend for small negative delta (FortyFiveDown)."""
        present = {"sg": 97}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        # delta=-3 is < 0 but not < -5, so FortyFiveDown
        assert trend == "FortyFiveDown"
        assert delta == -3

    def test_ns_trend_boundary_forty_five_up_at_5(self, mock_nightscout_uploader):
        """Test trend at boundary delta=5 (should be FortyFiveUp, not SingleUp)."""
        present = {"sg": 105}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        # delta=5 is NOT > 5, so should be FortyFiveUp (delta > 0)
        assert trend == "FortyFiveUp"
        assert delta == 5

    def test_ns_trend_boundary_forty_five_down_at_minus_5(self, mock_nightscout_uploader):
        """Test trend at boundary delta=-5 (should be FortyFiveDown, not SingleDown)."""
        present = {"sg": 95}
        past = {"sg": 100}

        trend, delta = mock_nightscout_uploader._NightscoutUploader__ns_trend(
            present, past
        )

        # delta=-5 is NOT < -5, so should be FortyFiveDown (delta < 0)
        assert trend == "FortyFiveDown"
        assert delta == -5

    def test_get_note(self, mock_nightscout_uploader):
        """Test note formatting."""
        result = mock_nightscout_uploader._NightscoutUploader__getNote(
            "BC_SID_TEST_MESSAGE"
        )
        assert result == "TEST_MESSAGE"

        result = mock_nightscout_uploader._NightscoutUploader__getNote(
            "BC_MESSAGE_ANOTHER_TEST"
        )
        assert result == "ANOTHER_TEST"
