# Temp Target support — design

**Date:** 2026-07-27
**Status:** Approved

## Goal

Expose the MiniMed 780G "Temp Target" (exercise mode) on/off state so Home
Assistant automations can react to it (e.g. warn when the user leaves home for a
walk without having enabled temp target), and record it in Nightscout as a
Temporary Target treatment.

## Data source

The Carelink Carepartner `recent_data` (patientData) response carries a
`pumpBannerState` field: a list of active pump banners. When temp target is on,
it contains an entry:

```json
{ "type": "TEMP_TARGET", "timeRemaining": <minutes> }
```

The list is empty when temp target is off. This is the only field in the payload
that carries temp-target state (verified against a live fetch on device
MMT-1886 / 780G; a `grep` of the raw response for temp/target/exercise found no
other occurrence). The `TEMP_TARGET` enum string and the `{type, timeRemaining}`
shape are confirmed against the canonical client this integration is ported
from: `benceszasz/CareLinkJavaClient` `PumpBannerState.java`.

Because the banner is a **live snapshot** (a decreasing `timeRemaining`), not a
timestamped event, it needs different handling from the marker/SG data that the
rest of the integration uploads.

## Part A — Home Assistant binary sensor

New binary sensor "Temp target", following the existing binary-sensor pattern.

1. **`const.py`**
   - Add `BINARY_SENSOR_KEY_TEMP_TARGET = "binary_sensor_temp_target"` and
     `BINARY_SENSOR_KEY_TEMP_TARGET_ATTRS = "binary_sensor_temp_target_attributes"`.
   - Add one entry to `BINARY_SENSORS`: name `"Temp target"`, icon `mdi:run`,
     `device_class=None` (renders as On/Off, matching the Carelink app wording),
     `entity_category=None`.

2. **`__init__.py`** (`_async_update_data`)
   - `recent_data["pumpBannerState"] = recent_data.setdefault("pumpBannerState", [])`.
   - Find the first entry whose `type == "TEMP_TARGET"`.
   - `data[BINARY_SENSOR_KEY_TEMP_TARGET] = <bool: entry found>`.
   - When on: `data[..._ATTRS] = {"time_remaining": <timeRemaining minutes>}`.
     When off: `{}`.

3. **`binary_sensor.py`**
   - Add an `extra_state_attributes` property to `CarelinkConnectivityEntity`,
     mirroring `sensor.py`:
     `return self.coordinator.data.setdefault(f"{self.sensor_description.key}_attributes", {})`.
   - The existing five connectivity binary sensors have no `_attributes` key set,
     so they get `{}` — no behavioural change for them.

Availability follows the existing staleness rule via `is_data_stale`: if the pump
has not reported in `DATA_STALE_TIMEOUT_HOURS` (2h), the sensor goes unavailable
like the other binary sensors. Automations key off the entity being `off`.

## Part B — Nightscout Temporary Target treatment

Upload a single Nightscout "Temporary Target" treatment per temp-target session.

The banner's `timeRemaining` decreases every poll, so a per-poll upload would
create overlapping, shrinking treatments. **Session end time
(`now + timeRemaining`, quantized to the minute) is stable across polls**, so it
is used as the deduplication identity.

- In the uploader, read `recent_data["pumpBannerState"]`. If a `TEMP_TARGET`
  entry is present, build one treatment:
  - `eventType = "Temporary Target"`
  - `created_at = now` (ISO, in the site timezone, matching other treatments)
  - `duration = timeRemaining` (minutes)
  - `targetTop = targetBottom = 150` (mg/dL — the 780G's fixed temp target;
    Nightscout stores targets in mg/dL internally, as SGVs are uploaded)
  - `reason = "Temp Target"`
  - `enteredBy = NS_USER_AGENT`
- Attach a private `_dedupKey = f"temptarget|{end_minute_iso}"` field.
  `_compute_fingerprint` returns `sha256(_dedupKey)` when that field is present;
  `__set_data` strips `_dedupKey` from the payload before POST.
- Routed through the existing dedup file (persisted, purged after
  `DEDUP_RETENTION_HOURS` = 25h). Result: posted exactly once per session, even
  across Home Assistant restarts.
- Wired into `__slice_recent_data_for_transmission` as a new
  `__setTempTarget(recent_data, tz)` step (guarded like the others).

### Deliberate limitations (YAGNI, approved)

- **No early-cancel on the falling edge.** Nightscout auto-expires the target by
  its `duration`. If the user ends temp target early on the pump, Nightscout
  shows it slightly longer than reality. Early-cancel would require edge-state
  tracking for marginal benefit and is out of scope.
- **Target hardcoded to 150 mg/dL**, not configurable — this is the 780G's fixed
  temp target value.

## Testing

- `test_init.py`: coordinator parsing.
  - `pumpBannerState` with a `TEMP_TARGET` entry → `data[key] is True` and
    `time_remaining` attribute set to the banner's `timeRemaining`.
  - Empty / absent `pumpBannerState` → `data[key] is False`, attrs `{}`.
- `test_nightscout_uploader.py`:
  - `TEMP_TARGET` present → one `Temporary Target` treatment posted with the
    expected fields and no `_dedupKey` in the POST body.
  - Two consecutive polls of the same session → posted once (dedup by end time).

## Verification

The `TEMP_TARGET` string is confirmed against the canonical Java client, but a
live occurrence cannot be observed until temp target is actually enabled on the
pump. After implementation, enable temp target once on the device and re-fetch to
confirm end-to-end (binary sensor turns on with `time_remaining`; one Nightscout
Temporary Target appears).
