from homeassistant.util import dt as dt_util
from .const import SENSOR_KEY_UPDATE_TIMESTAMP, DATA_STALE_TIMEDELTA


def is_data_stale(coordinator_data: dict, sensor_key: str) -> bool:
    last_update = coordinator_data.get(SENSOR_KEY_UPDATE_TIMESTAMP)
    if last_update is None:
        return True

    now = dt_util.utcnow()
    time_diff = now - last_update

    return time_diff >= DATA_STALE_TIMEDELTA