# Temp Target Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the MiniMed 780G "Temp Target" (exercise mode) on/off state as a Home Assistant binary sensor with a `time_remaining` attribute, and record each temp-target session in Nightscout as a Temporary Target treatment.

**Architecture:** Temp target lives in the Carelink response field `pumpBannerState` (a list of live banners). A module-level parse helper feeds a new binary sensor via the coordinator. The Nightscout uploader emits one Temporary Target treatment per session, deduplicated on the stable session end time.

**Tech Stack:** Python, Home Assistant custom component, pytest / pytest-asyncio.

## Global Constraints

- Follow the existing binary-sensor pattern: entries in `BINARY_SENSORS` use `SensorEntityDescription` (not `BinarySensorEntityDescription`).
- Temp target value on the 780G is fixed at **150 mg/dL**; Nightscout stores targets in mg/dL internally.
- `TEMP_TARGET` banner shape (confirmed vs. canonical `CareLinkJavaClient`): `{"type": "TEMP_TARGET", "timeRemaining": <int minutes>}`.
- No early-cancel of the Nightscout target on the falling edge (out of scope, approved).
- Tests must run under the existing suite: `python -m pytest` from repo root (HA modules are mocked in `tests/conftest.py`).

---

### Task 1: Home Assistant temp target binary sensor

**Files:**
- Modify: `custom_components/carelink/const.py` (add keys + `BINARY_SENSORS` entry)
- Modify: `custom_components/carelink/__init__.py` (add `get_temp_target` helper + coordinator wiring)
- Modify: `custom_components/carelink/binary_sensor.py` (add `extra_state_attributes`)
- Test: `tests/test_init.py` (unit tests for `get_temp_target`)

**Interfaces:**
- Produces: `get_temp_target(pump_banner_state: list | None) -> tuple[bool, int | None]` — returns `(is_on, time_remaining_minutes)`.
- Produces: const `BINARY_SENSOR_KEY_TEMP_TARGET = "binary_sensor_temp_target"`, `BINARY_SENSOR_KEY_TEMP_TARGET_ATTRS = "binary_sensor_temp_target_attributes"`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_init.py` (import `get_temp_target` in the existing top import from `custom_components.carelink`):

```python
class TestGetTempTarget:
    """Tests for the get_temp_target function."""

    def test_temp_target_on(self):
        banners = [{"type": "TEMP_TARGET", "timeRemaining": 45}]
        assert get_temp_target(banners) == (True, 45)

    def test_temp_target_off_empty(self):
        assert get_temp_target([]) == (False, None)

    def test_temp_target_none(self):
        assert get_temp_target(None) == (False, None)

    def test_temp_target_other_banner_ignored(self):
        banners = [{"type": "TEMP_BASAL", "timeRemaining": 30}]
        assert get_temp_target(banners) == (False, None)

    def test_temp_target_found_among_others(self):
        banners = [
            {"type": "TEMP_BASAL", "timeRemaining": 30},
            {"type": "TEMP_TARGET", "timeRemaining": 20},
        ]
        assert get_temp_target(banners) == (True, 20)
```

Update the import at the top of `tests/test_init.py`:

```python
from custom_components.carelink import (
    convert_date_to_isodate,
    get_active_notification,
    get_last_marker,
    get_sg,
    get_temp_target,
    sanitize_for_logging,
)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_init.py::TestGetTempTarget -v`
Expected: FAIL with `ImportError: cannot import name 'get_temp_target'`

- [ ] **Step 3: Add const keys and BINARY_SENSORS entry**

In `custom_components/carelink/const.py`, after the existing `BINARY_SENSOR_KEY_*` definitions (around line 90), add:

```python
BINARY_SENSOR_KEY_TEMP_TARGET = "binary_sensor_temp_target"
BINARY_SENSOR_KEY_TEMP_TARGET_ATTRS = "binary_sensor_temp_target_attributes"
```

In the `BINARY_SENSORS` tuple (ends at line 495), add a final entry before the closing `)`:

```python
    SensorEntityDescription(
        key=BINARY_SENSOR_KEY_TEMP_TARGET,
        name="Temp target",
        device_class=None,
        icon="mdi:run",
        entity_category=None,
    ),
```

- [ ] **Step 4: Add the `get_temp_target` helper and wire the coordinator**

In `custom_components/carelink/__init__.py`, add the import to the `from .const import (...)` block:

```python
    BINARY_SENSOR_KEY_TEMP_TARGET,
    BINARY_SENSOR_KEY_TEMP_TARGET_ATTRS,
```

Add a module-level helper next to the other helpers (e.g. after `get_last_marker`, near line 645):

```python
def get_temp_target(pump_banner_state: list) -> tuple[bool, int | None]:
    """Return (is_on, time_remaining_minutes) for the temp target banner."""
    for banner in pump_banner_state or []:
        if banner.get("type") == "TEMP_TARGET":
            return True, banner.get("timeRemaining")
    return False, None
```

In `_async_update_data`, in the "Binary Sensors" block (after the existing
`BINARY_SENSOR_KEY_CONDUIT_SENSOR_IN_RANGE` assignment near line 528), add:

```python
        pump_banner_state = recent_data.setdefault("pumpBannerState", [])
        temp_target_on, temp_target_remaining = get_temp_target(pump_banner_state)
        data[BINARY_SENSOR_KEY_TEMP_TARGET] = temp_target_on
        data[BINARY_SENSOR_KEY_TEMP_TARGET_ATTRS] = (
            {"time_remaining": temp_target_remaining} if temp_target_on else {}
        )
```

- [ ] **Step 5: Add `extra_state_attributes` to the binary sensor entity**

In `custom_components/carelink/binary_sensor.py`, add a property to
`CarelinkConnectivityEntity` (mirroring `sensor.py`), after the `is_on` property:

```python
    @property
    def extra_state_attributes(self):
        attr_key = "{}_attributes".format(self.sensor_description.key)

        return self.coordinator.data.setdefault(attr_key, {})
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_init.py -v`
Expected: PASS (new `TestGetTempTarget` tests pass; existing tests still pass)

- [ ] **Step 7: Commit**

```bash
git add custom_components/carelink/const.py custom_components/carelink/__init__.py custom_components/carelink/binary_sensor.py tests/test_init.py
git commit -m "feat: add temp target binary sensor"
```

---

### Task 2: Nightscout Temporary Target upload

**Files:**
- Modify: `custom_components/carelink/nightscout_uploader.py` (constant, `__getTempTarget`, `__setTempTarget`, `_compute_fingerprint`, `__set_data`, `__slice_recent_data_for_transmission`)
- Test: `tests/test_nightscout_uploader.py`

**Interfaces:**
- Consumes: existing `NightscoutUploader.__set_data`, `_compute_fingerprint`, `NS_USER_AGENT`.
- Produces: `__getTempTarget(recent_data, tz, now) -> list[dict]` — 0 or 1 treatment dict, each with an `eventType="Temporary Target"`, `duration`, `targetTop`/`targetBottom` (150), `reason`, `created_at`, and a private `_dedupKey`.
- Produces: `_compute_fingerprint` returns `sha256(entry["_dedupKey"])` when the treatment entry has a `_dedupKey`; `__set_data` strips keys beginning with `_` from the POST body.

- [ ] **Step 1: Write the failing tests**

Add a new class to `tests/test_nightscout_uploader.py` (the file already imports
`datetime`, `timedelta`, `timezone`, `ZoneInfo`, `json`, `MagicMock`, `AsyncMock`,
`patch`, and `NightscoutUploader`):

```python
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
        # Poll 1: 45 min remaining at 12:00 -> ends 12:45
        raw1 = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 45}]}
        e1 = mock_nightscout_uploader._NightscoutUploader__getTempTarget(
            raw1, ZoneInfo("UTC"), self._now()
        )[0]
        # Poll 2: 40 min remaining at 12:05 -> still ends 12:45
        raw2 = {"pumpBannerState": [{"type": "TEMP_TARGET", "timeRemaining": 40}]}
        later = self._now() + timedelta(minutes=5)
        e2 = mock_nightscout_uploader._NightscoutUploader__getTempTarget(
            raw2, ZoneInfo("UTC"), later
        )[0]
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_nightscout_uploader.py::TestNightscoutTempTarget -v`
Expected: FAIL (`__getTempTarget` does not exist; `_dedupKey` not honored)

- [ ] **Step 3: Add the constant and `__getTempTarget` / `__setTempTarget`**

In `custom_components/carelink/nightscout_uploader.py`, near the top constants
(after `DEDUP_RETENTION_HOURS`, around line 17), add:

```python
TEMP_TARGET_MGDL = 150
```

Add these two methods to the `NightscoutUploader` class, next to the other
`__get*` / `__set*` methods (e.g. after `__getBasal`, around line 408):

```python
    def __getTempTarget(self, rawdata, tz, now):
        result = list()
        for banner in rawdata.get("pumpBannerState") or []:
            if banner.get("type") == "TEMP_TARGET":
                time_remaining = banner.get("timeRemaining") or 0
                end_dt = (now + timedelta(minutes=time_remaining)).replace(
                    second=0, microsecond=0
                )
                result.append(dict(
                    enteredBy=NS_USER_AGENT,
                    eventType="Temporary Target",
                    reason="Temp Target",
                    duration=time_remaining,
                    targetTop=TEMP_TARGET_MGDL,
                    targetBottom=TEMP_TARGET_MGDL,
                    created_at=now.isoformat(),
                    _dedupKey=f"Temporary Target|{end_dt.isoformat()}",
                    ))
                break
        return result

    async def __setTempTarget(self, rawdata, tz):
        printdbg("__setTempTarget()")
        try:
            data = self.__getTempTarget(rawdata, tz, datetime.now(tz))
        except Exception as error:
            printdbg(f"__setTempTarget() exception: {error}")
            data = []
        return await self.__set_data(
            self.__nightscout_url, data, "treatments"
        )
```

- [ ] **Step 4: Honor `_dedupKey` in `_compute_fingerprint` and strip it in `__set_data`**

In `_compute_fingerprint`, at the start of the `treatments` branch (line 93), add:

```python
        if data_type == "treatments":
            if entry.get("_dedupKey"):
                return hashlib.sha256(
                    str(entry["_dedupKey"]).encode("utf-8")
                ).hexdigest()
            key_fields = (
```

In `__set_data`, change the POST body to exclude private (`_`-prefixed) keys.
Replace the existing line 326:

```python
                response = await self.post_async(url, headers=self.__common_headers, data=json.dumps(entry))
```

with:

```python
                payload = {k: v for k, v in entry.items() if not k.startswith("_")}
                response = await self.post_async(url, headers=self.__common_headers, data=json.dumps(payload))
```

- [ ] **Step 5: Wire temp target into the upload cycle**

In `__slice_recent_data_for_transmission`, after the notification-history block
(before the method ends, around line 553), add:

```python
        # Sending Temp Target (pumpBannerState block)
        response = await self.__setTempTarget(recent_data, tz)
        if response:
            printdbg("sending temp target was ok")
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_nightscout_uploader.py -v`
Expected: PASS (new `TestNightscoutTempTarget` tests pass; existing tests still pass)

- [ ] **Step 7: Commit**

```bash
git add custom_components/carelink/nightscout_uploader.py tests/test_nightscout_uploader.py
git commit -m "feat: upload temp target to Nightscout as Temporary Target"
```

---

### Task 3: Full suite + live verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole test suite**

Run: `python -m pytest`
Expected: PASS (all existing + new tests)

- [ ] **Step 2: Live end-to-end check (manual, needs the device)**

Have the wife enable Temp Target on the 780G, then re-fetch live data
(reuse the scratch fetch approach against `token-tool/output/logindata.json`) and
confirm `pumpBannerState` contains a `{"type": "TEMP_TARGET", "timeRemaining": N}`
entry. Confirm in Home Assistant that the "Temp target" binary sensor is `on`
with a `time_remaining` attribute, and that one "Temporary Target" treatment
appears in Nightscout. This is the only step that validates the live banner shape
end-to-end, since the field is empty whenever temp target is off.
```
