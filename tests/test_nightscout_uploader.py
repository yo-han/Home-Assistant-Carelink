"""Tests for the Nightscout uploader."""
import json
import os
from datetime import datetime, timedelta, timezone
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

    async def test_async_client_method(self, mock_nightscout_uploader):
        """Test async_client method creates client on first access."""
        client = await mock_nightscout_uploader.async_client()
        assert client is not None
        # Second access should return same client
        assert await mock_nightscout_uploader.async_client() is client

    async def test_close(self, mock_nightscout_uploader):
        """Test closing the HTTP client."""
        # Create client first
        _ = await mock_nightscout_uploader.async_client()
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


class TestNightscoutDeduplication:
    """Tests for deduplication logic."""

    def test_fingerprint_same_treatment_is_stable(self):
        """Same treatment data produces the same fingerprint."""
        entry = {
            "eventType": "Meal",
            "created_at": "2024-01-15T12:00:00+01:00",
            "carbs": 45,
            "insulin": 3.5,
        }
        fp1 = NightscoutUploader._compute_fingerprint(entry, "treatments")
        fp2 = NightscoutUploader._compute_fingerprint(entry, "treatments")
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex length

    def test_fingerprint_different_treatments(self):
        """Different treatment data produces different fingerprints."""
        entry_a = {
            "eventType": "Meal",
            "created_at": "2024-01-15T12:00:00+01:00",
            "carbs": 45,
            "insulin": 3.5,
        }
        entry_b = {
            "eventType": "Meal",
            "created_at": "2024-01-15T13:00:00+01:00",
            "carbs": 30,
            "insulin": 2.0,
        }
        fp_a = NightscoutUploader._compute_fingerprint(entry_a, "treatments")
        fp_b = NightscoutUploader._compute_fingerprint(entry_b, "treatments")
        assert fp_a != fp_b

    def test_fingerprint_same_entry_is_stable(self):
        """Same SGS entry data produces the same fingerprint."""
        entry = {
            "type": "sgv",
            "dateString": "2024-01-15T12:00:00+01:00",
            "sgv": 120.0,
        }
        fp1 = NightscoutUploader._compute_fingerprint(entry, "entries")
        fp2 = NightscoutUploader._compute_fingerprint(entry, "entries")
        assert fp1 == fp2
        assert len(fp1) == 64

    def test_fingerprint_different_entries(self):
        """Different SGS entry data produces different fingerprints."""
        entry_a = {
            "type": "sgv",
            "dateString": "2024-01-15T12:00:00+01:00",
            "sgv": 120.0,
        }
        entry_b = {
            "type": "sgv",
            "dateString": "2024-01-15T12:05:00+01:00",
            "sgv": 125.0,
        }
        fp_a = NightscoutUploader._compute_fingerprint(entry_a, "entries")
        fp_b = NightscoutUploader._compute_fingerprint(entry_b, "entries")
        assert fp_a != fp_b

    def test_devicestatus_not_deduplicated(self):
        """Devicestatus entries should not produce a fingerprint."""
        entry = {"device": "MMT-1780", "pump": {"battery": {"status": "OK"}}}
        fp = NightscoutUploader._compute_fingerprint(entry, "devicestatus")
        assert fp is None

    async def test_duplicate_entries_not_uploaded(self, mock_nightscout_uploader):
        """POST is only called once per unique entry, duplicates are skipped."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(
            mock_nightscout_uploader, "post_async", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response

            treatment = {
                "eventType": "Meal",
                "created_at": "2024-01-15T12:00:00+01:00",
                "carbs": 45,
                "insulin": 3.5,
            }

            # First call: should upload
            result = await mock_nightscout_uploader._NightscoutUploader__set_data(
                "https://nightscout.example.com", [treatment], "treatments"
            )
            assert result is True
            assert mock_post.call_count == 1

            # Second call with same data: should skip
            result = await mock_nightscout_uploader._NightscoutUploader__set_data(
                "https://nightscout.example.com", [treatment], "treatments"
            )
            assert result is True
            # Still only 1 call - duplicate was skipped
            assert mock_post.call_count == 1

    async def test_failed_upload_allows_retry(self, mock_nightscout_uploader):
        """If POST fails, the fingerprint is not stored so retry is possible."""
        mock_response_fail = MagicMock()
        mock_response_fail.status_code = 500

        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200

        treatment = {
            "eventType": "Correction Bolus",
            "created_at": "2024-01-15T14:00:00+01:00",
            "insulin": 1.0,
        }

        with patch.object(
            mock_nightscout_uploader, "post_async", new_callable=AsyncMock
        ) as mock_post:
            # First attempt fails
            mock_post.return_value = mock_response_fail
            result = await mock_nightscout_uploader._NightscoutUploader__set_data(
                "https://nightscout.example.com", [treatment], "treatments"
            )
            assert result is False

            # Fingerprint should NOT be in seen set
            fp = NightscoutUploader._compute_fingerprint(treatment, "treatments")
            assert fp not in mock_nightscout_uploader._seen_fingerprints

            # Retry succeeds
            mock_post.return_value = mock_response_ok
            result = await mock_nightscout_uploader._NightscoutUploader__set_data(
                "https://nightscout.example.com", [treatment], "treatments"
            )
            assert result is True
            assert fp in mock_nightscout_uploader._seen_fingerprints

    async def test_dedup_persists_to_file(self, tmp_path):
        """A new uploader instance reads previously saved dedup state."""
        uploader1 = NightscoutUploader(
            nightscout_url="https://test.com",
            nightscout_secret="secret",
            config_path=str(tmp_path),
            entry_id="persist_test",
        )

        # Simulate a seen fingerprint and save
        uploader1._seen_fingerprints["abc123"] = datetime.now(timezone.utc).isoformat()
        await uploader1._save_dedup_state()

        # New instance should load the saved state
        uploader2 = NightscoutUploader(
            nightscout_url="https://test.com",
            nightscout_secret="secret",
            config_path=str(tmp_path),
            entry_id="persist_test",
        )
        await uploader2._load_dedup_state()
        assert "abc123" in uploader2._seen_fingerprints

    async def test_purge_removes_old_fingerprints(self, mock_nightscout_uploader):
        """Fingerprints older than 25 hours are removed by purge."""
        now = datetime.now(timezone.utc)
        old_ts = (now - timedelta(hours=26)).isoformat()
        recent_ts = (now - timedelta(hours=1)).isoformat()

        mock_nightscout_uploader._seen_fingerprints = {
            "old_fp": old_ts,
            "recent_fp": recent_ts,
        }

        mock_nightscout_uploader._purge_old_fingerprints()

        assert "old_fp" not in mock_nightscout_uploader._seen_fingerprints
        assert "recent_fp" in mock_nightscout_uploader._seen_fingerprints

    def test_unknown_data_type_returns_none(self):
        """Unknown data types should return None (no deduplication)."""
        entry = {"foo": "bar"}
        fp = NightscoutUploader._compute_fingerprint(entry, "unknown_type")
        assert fp is None

    async def test_load_handles_corrupted_json(self, tmp_path):
        """Corrupted JSON in dedup file falls back to empty dict."""
        uploader = NightscoutUploader(
            nightscout_url="https://test.com",
            nightscout_secret="secret",
            config_path=str(tmp_path),
            entry_id="corrupt_test",
        )
        # Write invalid JSON to the dedup file
        dedup_file = os.path.join(str(tmp_path), "carelink_ns_dedup_corrupt_test.json")
        with open(dedup_file, "w") as f:
            f.write("{not valid json")

        await uploader._load_dedup_state()

        assert uploader._seen_fingerprints == {}
        assert uploader._dedup_loaded is True

    async def test_load_idempotency(self, tmp_path):
        """Second call to _load_dedup_state does not overwrite in-memory changes."""
        uploader = NightscoutUploader(
            nightscout_url="https://test.com",
            nightscout_secret="secret",
            config_path=str(tmp_path),
            entry_id="idempotent_test",
        )

        # First load (no file exists, starts empty)
        await uploader._load_dedup_state()
        assert uploader._seen_fingerprints == {}

        # Add a fingerprint in memory
        uploader._seen_fingerprints["new_fp"] = datetime.now(timezone.utc).isoformat()

        # Second load should be a no-op (guard by _dedup_loaded)
        await uploader._load_dedup_state()
        assert "new_fp" in uploader._seen_fingerprints


class TestNightscoutTempTarget:
    """Tests for temp target -> Nightscout Temporary Target upload."""

    def _now(self):
        return datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

    def test_temp_target_treatment_fields(self, mock_nightscout_uploader):
        raw = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 45}]}
        result = mock_nightscout_uploader._NightscoutUploader__getTempTarget(
            raw, ZoneInfo("UTC"), self._now()
        )
        assert len(result) == 1
        entry = result[0]
        assert entry["eventType"] == "Temporary Target"
        assert entry["duration"] == 45
        assert entry["targetTop"] == 150
        assert entry["targetBottom"] == 150
        assert entry["reason"] == "Temp Target"
        assert "_dedupKey" in entry

    def test_no_temp_target_returns_empty(self, mock_nightscout_uploader):
        raw = {"pumpBannerState": []}
        result = mock_nightscout_uploader._NightscoutUploader__getTempTarget(
            raw, ZoneInfo("UTC"), self._now()
        )
        assert result == []

    def test_missing_banner_key_returns_empty(self, mock_nightscout_uploader):
        result = mock_nightscout_uploader._NightscoutUploader__getTempTarget(
            {}, ZoneInfo("UTC"), self._now()
        )
        assert result == []

    def test_dedupkey_stable_across_polls(self, mock_nightscout_uploader):
        # Poll 1: 45 min remaining at 12:00
        raw1 = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 45}]}
        e1 = mock_nightscout_uploader._NightscoutUploader__getTempTarget(
            raw1, ZoneInfo("UTC"), self._now()
        )[0]
        # Poll 2: 40 min remaining at 12:05 (same active session)
        raw2 = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 40}]}
        later = self._now() + timedelta(minutes=5)
        e2 = mock_nightscout_uploader._NightscoutUploader__getTempTarget(
            raw2, ZoneInfo("UTC"), later
        )[0]
        assert e1["_dedupKey"] == e2["_dedupKey"]

    def test_dedupkey_stable_across_sub_minute_polls(self, mock_nightscout_uploader):
        # Regression: 30s poll interval + integer-minute timeRemaining must not
        # produce two dedup keys for the same session (would double-post).
        raw1 = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 45}]}
        t1 = datetime(2024, 1, 15, 12, 0, 10, tzinfo=ZoneInfo("UTC"))
        e1 = mock_nightscout_uploader._NightscoutUploader__getTempTarget(
            raw1, ZoneInfo("UTC"), t1
        )[0]
        raw2 = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 44}]}
        t2 = datetime(2024, 1, 15, 12, 0, 40, tzinfo=ZoneInfo("UTC"))
        e2 = mock_nightscout_uploader._NightscoutUploader__getTempTarget(
            raw2, ZoneInfo("UTC"), t2
        )[0]
        assert e1["_dedupKey"] == e2["_dedupKey"]

    def test_new_session_after_gap_has_distinct_key(self, mock_nightscout_uploader):
        get = mock_nightscout_uploader._NightscoutUploader__getTempTarget
        on = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 45}]}
        off = {"pumpBannerState": []}
        e1 = get(on, ZoneInfo("UTC"), self._now())[0]
        # Temp target turns off -> session ends
        assert get(off, ZoneInfo("UTC"), self._now() + timedelta(minutes=50)) == []
        # A brand new session starts later -> must be a distinct dedup identity
        e2 = get(on, ZoneInfo("UTC"), self._now() + timedelta(hours=3))[0]
        assert e1["_dedupKey"] != e2["_dedupKey"]

    def test_duration_anchored_to_session_start(self, mock_nightscout_uploader):
        get = mock_nightscout_uploader._NightscoutUploader__getTempTarget
        # First seen at 12:00 with 45 min remaining
        e1 = get(
            {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 45}]},
            ZoneInfo("UTC"), self._now()
        )[0]
        # A later successful poll (e.g. after a failed first POST) at 12:05 with
        # 40 remaining must keep the original duration so the end stays 12:45.
        e2 = get(
            {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 40}]},
            ZoneInfo("UTC"), self._now() + timedelta(minutes=5)
        )[0]
        assert e1["duration"] == 45
        assert e2["duration"] == 45
        assert e2["created_at"] == e1["created_at"]

    async def test_stale_persisted_session_not_reused(self, tmp_path):
        on = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 45}]}
        # Session A: starts 12:00, ends ~12:45
        up1 = NightscoutUploader(
            nightscout_url="https://test.com",
            nightscout_secret="secret",
            config_path=str(tmp_path),
            entry_id="tt_stale",
        )
        await up1._load_temptarget_state()
        a = up1._NightscoutUploader__getTempTarget(on, ZoneInfo("UTC"), self._now())[0]
        await up1._save_temptarget_state()

        # Restart long after A ended; a brand new session B is active.
        up2 = NightscoutUploader(
            nightscout_url="https://test.com",
            nightscout_secret="secret",
            config_path=str(tmp_path),
            entry_id="tt_stale",
        )
        await up2._load_temptarget_state()
        b = up2._NightscoutUploader__getTempTarget(
            on, ZoneInfo("UTC"), self._now() + timedelta(hours=2)
        )[0]
        assert b["_dedupKey"] != a["_dedupKey"]

    def test_live_banner_past_end_does_not_rotate(self, mock_nightscout_uploader):
        # A continuously-live (or CareLink-cached) banner in the SAME running
        # process must not rotate the session once its estimated end passes;
        # rotating would post another overlapping Temporary Target.
        get = mock_nightscout_uploader._NightscoutUploader__getTempTarget
        on = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 5}]}
        e1 = get(on, ZoneInfo("UTC"), self._now())[0]  # ends ~12:05
        # Same banner still returned an hour later, no off edge observed.
        e2 = get(on, ZoneInfo("UTC"), self._now() + timedelta(hours=1))[0]
        assert e1["_dedupKey"] == e2["_dedupKey"]

    async def test_session_persists_across_restart(self, tmp_path):
        raw = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 45}]}
        now = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("UTC"))

        uploader1 = NightscoutUploader(
            nightscout_url="https://test.com",
            nightscout_secret="secret",
            config_path=str(tmp_path),
            entry_id="tt_persist",
        )
        await uploader1._load_temptarget_state()
        e1 = uploader1._NightscoutUploader__getTempTarget(raw, ZoneInfo("UTC"), now)[0]
        await uploader1._save_temptarget_state()

        # New instance (simulated restart) reads the active session and reuses it
        uploader2 = NightscoutUploader(
            nightscout_url="https://test.com",
            nightscout_secret="secret",
            config_path=str(tmp_path),
            entry_id="tt_persist",
        )
        await uploader2._load_temptarget_state()
        later = now + timedelta(minutes=5)
        e2 = uploader2._NightscoutUploader__getTempTarget(raw, ZoneInfo("UTC"), later)[0]
        assert e1["_dedupKey"] == e2["_dedupKey"]

    def test_fingerprint_uses_dedupkey(self):
        e1 = {"eventType": "Temporary Target", "created_at": "a", "_dedupKey": "tt|12:45"}
        e2 = {"eventType": "Temporary Target", "created_at": "b", "_dedupKey": "tt|12:45"}
        e3 = {"eventType": "Temporary Target", "created_at": "a", "_dedupKey": "tt|13:00"}
        fp1 = NightscoutUploader._compute_fingerprint(e1, "treatments")
        fp2 = NightscoutUploader._compute_fingerprint(e2, "treatments")
        fp3 = NightscoutUploader._compute_fingerprint(e3, "treatments")
        assert fp1 == fp2          # same session -> deduped despite different created_at
        assert fp1 != fp3          # different session end -> distinct
        assert len(fp1) == 64

    async def test_set_data_strips_dedupkey_from_body(self, mock_nightscout_uploader):
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch.object(
            mock_nightscout_uploader, "post_async", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response
            entry = {
                "eventType": "Temporary Target",
                "duration": 45,
                "created_at": "2024-01-15T12:00:00+00:00",
                "_dedupKey": "Temporary Target|2024-01-15T12:45:00+00:00",
            }
            await mock_nightscout_uploader._NightscoutUploader__set_data(
                "https://nightscout.example.com", [entry], "treatments"
            )
            posted_body = json.loads(mock_post.call_args.kwargs["data"])
            assert "_dedupKey" not in posted_body
            assert posted_body["eventType"] == "Temporary Target"

    async def test_temp_target_uploaded_once_per_session(self, mock_nightscout_uploader):
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch.object(
            mock_nightscout_uploader, "post_async", new_callable=AsyncMock
        ) as mock_post:
            mock_post.return_value = mock_response
            entry = {
                "eventType": "Temporary Target",
                "duration": 45,
                "created_at": "2024-01-15T12:00:00+00:00",
                "_dedupKey": "Temporary Target|2024-01-15T12:45:00+00:00",
            }
            await mock_nightscout_uploader._NightscoutUploader__set_data(
                "https://nightscout.example.com", [entry], "treatments"
            )
            # Second poll, different created_at, same session end (same _dedupKey)
            entry2 = dict(entry, created_at="2024-01-15T12:05:00+00:00")
            await mock_nightscout_uploader._NightscoutUploader__set_data(
                "https://nightscout.example.com", [entry2], "treatments"
            )
            assert mock_post.call_count == 1
