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
create overlapping, shrinking treatments. The dedup identity is anchored to the
**first poll that observes the session** (its `created_at`), tracked as an active
session in the uploader. This avoids reconstructing identity from the wall clock
plus the integer-minute `timeRemaining`, which is unstable: with sub-minute poll
intervals (the config allows 30s), `now + timeRemaining` estimates straddle
minute boundaries and would produce distinct keys for one session.

- The uploader holds an active-session record
  `{"created_at", "dedup_key", "duration"}`, persisted to
  `carelink_ns_temptarget_{entry_id}.json` (atomic write, mirroring the dedup
  state) so the guarantee survives restarts.
- On each poll, read `recent_data["pumpBannerState"]`:
  - No `TEMP_TARGET` entry → clear the active session, upload nothing.
  - `TEMP_TARGET` present and no active session → start one: `created_at = now`,
    `dedup_key = f"Temporary Target|{created_at}"`, `duration = timeRemaining`
    (the initial remaining minutes, kept fixed for the session).
  - `TEMP_TARGET` present with an active session → reuse the stored record.
- A loaded session whose estimated end (`created_at + duration`) is more than
  `TEMP_TARGET_STALE_GRACE` (10 min) in the past is discarded before reuse, so a
  restart spanning the end of one session and the start of another does not
  reuse the old identity for the new session.
- Build one treatment: `eventType = "Temporary Target"`, `created_at` (session
  start), `duration` (the session's initial remaining minutes, so the end stays
  anchored even if the first POST fails and a later poll retries),
  `targetTop = targetBottom = 150`
  (mg/dL — the 780G's fixed temp target; Nightscout stores targets in mg/dL),
  `reason = "Temp Target"`, `enteredBy = NS_USER_AGENT`, and a private
  `_dedupKey = session["dedup_key"]`.
- `_compute_fingerprint` returns `sha256(_dedupKey)` when that field is present;
  `__set_data` strips `_`-prefixed keys from the payload before POST. Routed
  through the existing dedup file (persisted, purged after
  `DEDUP_RETENTION_HOURS` = 25h). Result: posted exactly once per session, even
  across Home Assistant restarts.
- Wired into `__slice_recent_data_for_transmission` as a new
  `__setTempTarget(recent_data, tz)` step (guarded like the others), which loads
  the session state before and saves it after.

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
