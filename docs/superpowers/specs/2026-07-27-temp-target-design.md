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

To avoid reporting `on` from a cached banner long after the target ended (which
would be a false negative for the reminder automation), the coordinator also
derives `off` once the banner's implied end has passed: `is_temp_target_expired`
returns `True` when `now > last_report (SENSOR_KEY_UPDATE_TIMESTAMP) +
time_remaining`. In the normal fresh case the implied end is in the future, so
this never turns an active target off early; it only fires on stale snapshots.

## Part B — Nightscout Temporary Target treatment

Upload a single Nightscout "Temporary Target" treatment per temp-target session.

The banner's `timeRemaining` decreases every poll, so a per-poll upload would
create overlapping, shrinking treatments. The session is identified by its
**implied end time, anchored to the pump's own report time**:
`banner_end = lastConduitDateTime + timeRemaining`. Unlike `now + timeRemaining`,
this value is stable across every poll of one session (report time and remaining
move together in the same pump snapshot), and it is already in the past when
CareLink returns a cached banner after the pump stopped reporting. This single
rule replaces the earlier ad-hoc mix of wall-clock end estimates, a reconcile
flag, and a time-based grace expiry.

- The uploader holds an active-session record
  `{"created_at", "dedup_key", "duration", "end"}`, persisted to
  `carelink_ns_temptarget_{entry_id}.json` (atomic write, mirroring the dedup
  state) so the guarantee survives restarts. `created_at` / `dedup_key` are
  anchored to the first poll that started the session; `duration` is the initial
  remaining minutes (fixed); `end` is `banner_end`.
- On each poll, read `recent_data["pumpBannerState"]` and compute `banner_end`
  (falling back to `now + timeRemaining` only if `lastConduitDateTime` is
  missing):
  - No `TEMP_TARGET` entry → clear the active session, upload nothing.
  - `banner_end` more than `TEMP_TARGET_STALE_GRACE` (10 min) in the past →
    stale/ended cached banner → clear the session, upload nothing.
  - No active session, or `|banner_end − stored end| > TEMP_TARGET_END_TOLERANCE`
    (2 min, absorbing integer-minute rounding) → start a new session. The end
    shift catches a cancel+restart even when it happens entirely between polls
    (no off edge observed).
  - Otherwise → reuse the stored record.
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
