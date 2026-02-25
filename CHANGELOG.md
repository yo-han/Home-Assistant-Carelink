# Changelog

All notable changes to the Tandem Source / Carelink integration will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.2] - 2026-02-25

### Security
- **Sanitise error messages**: Removed HTTP response bodies, server-side error details, and internal URLs from all `TandemAuthError` and `TandemApiError` exception messages — only HTTP status codes are included
- **SSRF protection**: Nightscout URL validation now resolves hostnames and rejects private, loopback, link-local, and reserved IP addresses to prevent Server-Side Request Forgery
- **Narrow JWT exception handling**: `_extract_jwt_claims()` now catches only `json.JSONDecodeError`, `UnicodeDecodeError`, and `ValueError` instead of bare `Exception`, and error messages no longer leak internal details
- **Expanded PII redaction**: Added `serialNumber`, `tconnectDeviceId`, `pumperId`, `accountId`, and `partNumber` to the `PII_FIELDS` set used by `sanitize_for_logging()`

### Added
- 25 new security tests (`test_security.py`) covering error message sanitisation, SSRF protection, JWT decode handling, and PII redaction

## [1.2.1] - 2026-02-14

### Added
- **Cartridge fill volume input**: New number entity (`number.carelink_cartridge_fill_volume`) allows users to manually set cartridge fill volume when changing cartridges, since the Tandem API does not report this value (#14)

### Fixed
- **Glucose timestamp showing future time**: Fixed two independent timezone bugs (#13)
  - `parse_dotnet_date()` now returns UTC-aware datetimes; therapy timeline timestamps use `.astimezone()` for correct UTC-to-local conversion
  - Binary event decoder timestamps are **local pump time**, not UTC — decoder now creates naive datetimes, callers use `.replace(tzinfo=tz)` to label them correctly (previously stamped UTC onto local values, shifting data by the UTC offset)
- **Cartridge insulin showing 0**: Sensor now shows "Unknown" instead of misleading "0" when the Tandem API returns 0.0 for insulin volume (#14)
- **Software version not populated**: Added fallback to `partNumber` metadata field and debug logging when `softwareVersion` is missing from the API response (#15)
- **Last carb entry high y-axis**: Removed `state_class=MEASUREMENT` from the "Last carb entry" sensor to prevent HA from tracking it as long-term statistics, which caused misleading y-axis scaling on graphs (#16)

### Changed
- Added `Platform.NUMBER` to integration platforms for the cartridge fill volume entity

## [1.2.0] - 2026-02-14

### Added
- **Expanded data sources**: Decode 10 new pump event types (15 total, up from 5)
  - Pump suspend/resume state, activity mode (Sleep/Exercise/Eating Soon), Control-IQ mode (Open/Closed Loop)
  - Cartridge, cannula (site), and tubing change timestamps for infusion set tracking
  - Carb entries, manual BG readings, extended bolus completion, cartridge insulin level
- **Computed CGM summary**: Average glucose, Time in Range (70-180), time below/above range, SD, CV, GMI, CGM usage %
  - Fixes the 3 sensors (avg glucose, TIR, CGM usage) that were permanently unavailable due to dashboard_summary API returning 404
  - All stats computed locally from CGM pump events
- **Computed insulin summary**: Total Daily Insulin (TDI), daily bolus/basal totals, basal/bolus split %, daily carbs, daily bolus count
- **Pump settings extraction**: 11 new sensors from pump metadata upload settings
  - Active basal profile name (with full schedule as attributes: rates, ISF, carb ratio, target BG per segment)
  - Control-IQ settings: enabled status, configured weight, configured TDI
  - Pump limits: max bolus, basal rate limit
  - CGM alert thresholds: high/low glucose alerts
  - BG alert thresholds: low/high BG alerts, low insulin alert
- 27 new sensors total (45 Tandem sensors, up from 18)
- 48 new unit tests (236 total, up from 188)

### Changed
- API now requests 15 event types instead of 5 (adds events 11, 12, 16, 21, 33, 48, 61, 63, 229, 230)
- Dashboard summary API call only used as fallback when pump events are unavailable
- Daily insulin/carb summaries now filter events to "today" in pump timezone (previously summed full 2-day fetch window)

### Fixed
- **CRITICAL**: Fixed `lastUpload` parsing bug — field is a dict `{uploadId, lastUploadedAt, settings}`, not a timestamp string
  - `sensor.last_pump_upload` and `sensor.last_update` now show real timestamps (were stuck on "unknown")
- **CRITICAL**: Fixed timestamp timezone handling — API returns UTC timestamps, not local time
  - `.replace(tzinfo=tz)` was stamping local timezone onto UTC clock values, shifting all data by the UTC offset (e.g. 10.5 hours for Adelaide)
  - Decoder now uses `fromtimestamp(tz=timezone.utc)`, coordinator uses `.astimezone(tz)` for all conversions
- **CRITICAL**: Fixed CARBS_ENTERED binary decoder — payload is float32, not uint16
  - Was reading IEEE 754 float bytes as raw integer (e.g. 16,800 instead of 20g)
  - Verified correct format via live API binary decode in browser
- Fixed statistics import "Invalid timestamp" error — HA requires timestamps at top of hour (minute=0)
  - Statistics now importing successfully (CGM, IOB, basal)
- Fixed site change sensor — CANNULA_FILLED (event 61) never returned by API
  - Now derives from CARTRIDGE_FILLED (event 33) as fallback
- Fixed manifest.json key ordering for hassfest validation (alphabetical after domain/name)

## [1.1.0] - 2026-02-14

### Added
- **Stale data detection** (#11): Sensors now report `unavailable` when pump data is older than 30 minutes
  - Prevents misleading flat lines in glucose history graphs when the pump hasn't uploaded recent data
  - Timestamp and diagnostic sensors (last glucose update, last upload, serial, model, etc.) remain available so users can see when data was last received
  - Pattern adapted from upstream yo-han/Home-Assistant-Carelink staleness system

### Changed
- **API optimisation**: Coordinator now checks `maxDateWithEvents` from lightweight metadata endpoint before fetching full pump events
  - If no new data since last poll, skips the expensive `pumpevents` API call entirely
  - Reduces unnecessary API traffic and auth token usage when pump hasn't uploaded
- Added `helpers.py` with `is_data_stale()` utility function
- Sensor entity now tracks `platform_type` to apply staleness checks only to Tandem sensors (Carelink behaviour unchanged)

## [1.0.0] - 2026-02-14

### Added
- **Historical data import**: Import ALL pump events between polls instead of only the latest reading
  - Long-term statistics: CGM, IOB, and basal rate imported via `async_import_statistics()` with correct timestamps
  - Entity attributes: Recent readings arrays (24 CGM, 10 bolus, 10 basal) available for custom cards (e.g., ApexCharts)
- **Carelink coordinator**: Process ALL valid SG readings from API polls, not just the latest two
  - Import correctly-timestamped long-term statistics for Statistics Graph cards
  - Store reading history in sensor attributes for custom cards
- Event sequence number tracking to deduplicate events across polls
- Compact attribute keys to stay within Home Assistant's 16KB attribute limit
- Added `recorder` to manifest `after_dependencies` (ensures recorder loads first for `async_import_statistics`)

### Changed
- `_parse_pump_events()` now processes ALL events in the fetch window, not just the latest of each type

### Fixed
- **CRITICAL**: Fixed glucose graph spikes caused by historical replay mechanism (#9)
  - `async_set_updated_data()` replaced entire coordinator data dict during replay, causing sensors to oscillate between real values and `None` when dashboard keys were missing
  - Removed replay infrastructure entirely; historical data now handled solely via long-term statistics import
- Fixed `sensor.py` `setdefault` → `.get()` to prevent mutation of coordinator.data during sensor reads
- Glucose history graphs no longer show staircase pattern between polls
- Intermediate CGM readings, boluses, and basal changes between syncs are no longer discarded

### Housekeeping
- Removed untested Medtronic token tools (carelink-token-generator/, token-tool/, utils/)
- Removed fork template boilerplate (.devcontainer.json, .prettierrc, dependabot.yml, repository.yaml)
- Removed diagnostic/troubleshooting docs and scripts from repository
- Fixed remaining yo-han repo references → jnctech
- Fixed CODEOWNERS: updated from upstream author to @jnctech
- Fixed HACS custom repository URL in README
- Added Tandem-tested disclaimer to README and info.md
- Updated info.md to reflect Tandem Source scope and proper attribution

## [0.1.4-beta] - 2026-02-13

### Fixed
- **Sensor update timing**: Improved data fetch performance and reliability
  - Parallelised independent API calls (metadata + pumper_info concurrent, ControlIQ fallback concurrent)
  - Added retry with exponential backoff (2s, 4s) for transient network errors (connection reset, timeout, DNS)
  - Wrapped errors with Home Assistant `UpdateFailed` for proper coordinator backoff and entity unavailable marking
  - Fixed timezone mismatch: API date range now uses pump timezone instead of server local time
  - Demoted per-cycle INFO logs to DEBUG to reduce log noise (~288 lines/day at 5-min intervals)
- **CRITICAL**: Fixed sensor population - all Tandem pump sensors stuck in "Unknown" state (#3)
  - ControlIQ API endpoints (`tdcservices.eu.tandemdiabetes.com`) return 404 errors
  - Switched to Source Reports pumpevents API as primary data source (same endpoint the Tandem Source web UI uses)
  - Implemented binary event decoder for Tandem's proprietary 26-byte record format (base64-encoded)
  - Sensors now populate: glucose (mg/dL & mmol/L), active insulin (IOB), basal rate, last bolus, meal bolus, Control-IQ status

### Added
- `decode_pump_events()` binary decoder for Tandem pump event records
  - Supports CGM readings (event 256), bolus completed (event 20), bolus delivery (event 280), basal rate change (event 3), basal delivery (event 279)
  - Tandem epoch (2008-01-01) timestamp conversion
- `get_pump_events()` method targeting Source Reports API (`/api/reports/reportsfacade/pumpevents/`)
- `_parse_pump_events()` coordinator method to extract sensor values from decoded binary events

### Changed
- `get_recent_data()` now uses pump_events as primary data source, falling back to ControlIQ endpoints only when unavailable
- `get_recent_data()` accepts `pump_timezone` parameter for timezone-aware date ranges
- `_api_get()` retries transient network errors up to 2 times with exponential backoff
- Data coordinator prioritises pump_events over therapy_timeline for sensor value extraction
- Data coordinator raises `UpdateFailed` on errors instead of returning empty dict

### Technical Notes
- Binary format reference: [tconnectsync](https://github.com/jwoglom/tconnectsync) event parser
- Each record: 2-byte header (4-bit source + 12-bit event ID), 4-byte timestamp, 4-byte sequence, 16-byte payload
- Dashboard-dependent sensors (average glucose, CGM usage, time in range) still require ControlIQ endpoints

## [0.1.3-beta] - 2026-02-11

### Fixed
- **CRITICAL**: Fixed blocking SSL call in TandemSourceClient that prevented integration from loading
  - Moved SSL context creation to executor using `asyncio.run_in_executor()`
  - Resolves "Detected blocking call to load_verify_locations" error
  - Integration now loads successfully in Home Assistant 2024.1+

### Added
- Comprehensive test suite with 143 new tests using pytest-homeassistant-custom-component
  - 31 tests for TandemSourceClient (PKCE flow, authentication, data parsing)
  - 11 tests for Tandem config flow (setup, validation, error handling)
  - 19 tests for data coordinator (sensor data parsing, dashboard integration)
- Added `certifi>=2023.0.0` to requirements for explicit SSL certificate management
- Improved logging for ControlIQ API availability (Source OIDC tokens may not work with ControlIQ endpoints)

### Changed
- Updated repository references from yo-han to jnctech organization
- Updated codeowner to @jnctech
- Migrated test infrastructure from sys.modules mocking to real HA runtime fixtures
- Updated pytest configuration with pytest-homeassistant-custom-component==0.13.80

### Technical Notes
- The v0.1.0.beta branch attempted to fix the SSL issue using `create_async_httpx_client` from Home Assistant, but this approach broke the integration with "Invalid handler specified" errors
- The proper fix uses the standard httpx.AsyncClient with SSL context creation offloaded to an executor

## [0.1.1-beta] - 2024-XX-XX

### Added
- Initial Tandem t:slim pump integration support
- Support for EU and US Tandem Source regions
- README documentation for Tandem setup and configuration

## [2024.1.0] - 2024-XX-XX

### Added
- Initial Medtronic Carelink integration
- Support for MiniMed 770G/780G pumps
- Support for Guardian Connect CGM
- Nightscout upload capability

[1.2.1]: https://github.com/jnctech/ha-tandem-pump/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/jnctech/ha-tandem-pump/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/jnctech/ha-tandem-pump/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jnctech/ha-tandem-pump/compare/v0.1.4-beta...v1.0.0
[0.1.4-beta]: https://github.com/jnctech/ha-tandem-pump/compare/v0.1.3-beta...v0.1.4-beta
[0.1.3-beta]: https://github.com/jnctech/ha-tandem-pump/compare/v0.1.1-beta...v0.1.3-beta
[0.1.1-beta]: https://github.com/jnctech/ha-tandem-pump/compare/2024.1.0...v0.1.1-beta
[2024.1.0]: https://github.com/jnctech/ha-tandem-pump/releases/tag/2024.1.0
