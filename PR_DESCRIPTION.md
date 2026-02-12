# Improve Sensor Names and Add Data Staleness Detection

## What's the problem?

### Generic sensor names
The current sensor names like `sensor.last_alarm` and `sensor.last_update` are pretty generic. This causes a few issues:
- It's not clear which device they belong to
- Users with multiple Carelink accounts run into naming collisions
- Doesn't follow Home Assistant's naming best practices

### Showing stale data
Right now, sensors keep displaying old values even if the last update was days ago. This means:
- Automations might trigger based on outdated information
- It's hard to tell if there's a connectivity problem
- Users can get confused about the actual current state

## What this PR does

### Device names in sensor names
All sensors now include the patient/device name from the Carelink API as part of the prefix.

**Before:** sensor.carelink_last_alarm → "Carelink Last alarm"  
**After:** sensor.carelink_lucy_huish_last_alarm → "Carelink Lucy Huish Last alarm"

### Availability based on update time
Sensors now mark themselves as unavailable when the data gets too old.

**Before:** Glucose reading shows "120 mg/dL" even if it's 3 days old  
**After:** Sensor shows "Unavailable" after 2 hours without an update (timestamp sensors stay visible so you can see when the last update was)

## Technical changes

### Sensor naming (sensor.py, binary_sensor.py)
- Both sensor files now pull the device name from coordinator data and use it as a prefix
- This applies to all 38 regular sensors and 5 binary sensors
- Falls back to "Carelink" if no device name is available

### Availability watchdog (const.py, sensor.py, binary_sensor.py)
- Added a `DATA_STALE_TIMEOUT_HOURS` constant set to 2 hours by default
- Added an `available` property to both sensor classes that checks the last update timestamp
- The timestamp sensors themselves (`Last update`, `Last glucose update`) always stay available for troubleshooting
- Uses Home Assistant's datetime utilities for proper timezone handling

## Why this is useful

### Better sensor names
- You can immediately tell which device each sensor belongs to
- Works out of the box if you have multiple pumps or accounts
- Makes organizing automations and dashboards much easier

### Data freshness
- Automations won't trigger on old data anymore
- You'll know right away if there's a connectivity issue
- Timestamp sensors stay visible so you can always check when the last update happened
- The timeout is configurable if 2 hours doesn't work for your setup  

## Migration
What to expect after upgrading

### Sensor names
- The friendly names will update automatically when you restart Home Assistant
- Entity IDs won't change unless you manually recreate them using Home Assistant's "Recreate entity IDs" option
- All your history and automations will keep working

### Availability
- No breaking changes here
- If your sensors have stale data (over 2 hours old), they'll show as "Unavailable" right after the upgrade
- Once fresh data comes in, they'll become available again automatically
- You can change the timeout by editing `DATA_STALE_TIMEOUT_HOURS` in const.py

## Testing checklist

1. Check that sensor names now include the device/patient name
2. Wait over 2 hours without a data update and verify sensors show "Unavailable"
3. Confirm timestamp sensors stay visible even when other sensors are unavailable
4. If you have multiple Carelink accounts, test that everything works properly
5. Make sure your automations correctly handle th