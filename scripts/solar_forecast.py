#!/usr/bin/env python3
"""Solar production forecast + supply planner for HA energy optimization.

Subcommands:
  init_db    - Create database tables (run once)
  forecast   - Generate 48-hour solar forecast (15-min intervals)
  actual     - Log current SolarEdge production (15-min intervals)
  compare    - Compare forecasts against actuals, compute errors
  calibrate  - Weekly auto-calibration from clear-sky days (per-array)
  banking    - Compute optimal jacuzzi thermal banking target
  plan       - Generate 48-hour cost-optimal supply plan

Called via shell_command from HA automations.
System: 23kWp split 50:50 on east/west slopes at ~35 deg tilt.
"""

import sys
import os
import json
import math
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    import mysql.connector
except ImportError:
    import subprocess
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "mysql-connector-python", "-q"]
    )
    import mysql.connector


# =============================================================================
# Configuration
# =============================================================================

DB = {
    "host": "core-mariadb",
    "port": 3306,
    "user": "homeassistant",
    "password": "Yuriandyogi001!",
    "database": "ha_analytics",
}

# Array specifications
EAST_KWP = 11.5
WEST_KWP = 11.5
TILT_DEG = 35.0
EAST_AZIMUTH = 90.0    # degrees from North
WEST_AZIMUTH = 270.0   # degrees from North
ALBEDO = 0.2
SOLAR_CONSTANT = 1361.0  # W/m^2

# Forecast intervals
INTERVAL_MIN = 15
SLOTS_48H = 192  # 48 * 4

# Tariff rates (CHF/kWh)
RATE_HIGH = 0.38
RATE_LOW = 0.26
RATE_SOLAR = 0.06  # solar opportunity cost

# Defaults
DEFAULT_CALIBRATION_EAST = 0.75
DEFAULT_CALIBRATION_WEST = 0.75

# Jacuzzi thermal parameters (read from HA where possible)
JAC_HEATER_KW = 6.0
JAC_DEFAULT_P_NET = 5.7  # effective after losses
JAC_DEFAULT_VOLUME_L = 3200
JAC_MAX_TEMP = 40.0
JAC_DEFAULT_STANDBY = 20.0

# EV parameters
EV_BATTERY_KWH = 75  # Tesla Model 3/Y
EV_MIN_AMPS = 5
EV_MAX_AMPS = 16
EV_VOLTAGE = 230
EV_PHASES = 3


# =============================================================================
# Database
# =============================================================================

def conn():
    return mysql.connector.connect(**DB)


# =============================================================================
# HA API
# =============================================================================

def get_token():
    """Get HA API token."""
    try:
        with open("/config/python_scripts/.ha_token", "r") as f:
            return f.read().strip()
    except Exception:
        return os.environ.get("SUPERVISOR_TOKEN", "")


def ha_get(entity_id, token):
    """Get full entity data from HA API."""
    url = f"http://supervisor/core/api/states/{entity_id}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    resp = urllib.request.urlopen(req, timeout=5)
    return json.loads(resp.read().decode())


def ha_state(entity_id, token):
    """Get entity state string."""
    try:
        return ha_get(entity_id, token).get("state", "")
    except Exception:
        return ""


def ha_attr(entity_id, attr, token):
    """Get entity attribute."""
    try:
        return ha_get(entity_id, token).get("attributes", {}).get(attr, None)
    except Exception:
        return None


def ha_set(entity_id, value, token):
    """Set HA entity value via API."""
    try:
        if entity_id.startswith("input_number."):
            url = "http://supervisor/core/api/services/input_number/set_value"
            payload = {"entity_id": entity_id, "value": float(value)}
        elif entity_id.startswith("input_select."):
            url = "http://supervisor/core/api/services/input_select/set_options"
            payload = {"entity_id": entity_id, "options": [str(value)[:255]]}
        elif entity_id.startswith("input_boolean."):
            svc = "turn_on" if value else "turn_off"
            url = f"http://supervisor/core/api/services/input_boolean/{svc}"
            payload = {"entity_id": entity_id}
        else:
            return False
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False


def ha_select_option(entity_id, option, token):
    """Select an option on an input_select with predefined options."""
    try:
        url = "http://supervisor/core/api/services/input_select/select_option"
        payload = {"entity_id": entity_id, "option": str(option)}
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False


# =============================================================================
# Location and timezone helpers
# =============================================================================

def get_location(token):
    """Get home lat/lon from HA zone.home."""
    lat = ha_attr("zone.home", "latitude", token)
    lon = ha_attr("zone.home", "longitude", token)
    if lat is None or lon is None:
        raise ValueError("Cannot get home coordinates from zone.home")
    return float(lat), float(lon)


def get_calibrations(token):
    """Get per-array calibration factors from HA helpers.

    Returns (cal_east, cal_west).
    """
    east = ha_state("input_number.energy_solar_calibration_east", token)
    west = ha_state("input_number.energy_solar_calibration_west", token)
    if east and east not in ("unknown", "unavailable"):
        cal_east = float(east)
    else:
        cal_east = DEFAULT_CALIBRATION_EAST
    if west and west not in ("unknown", "unavailable"):
        cal_west = float(west)
    else:
        cal_west = DEFAULT_CALIBRATION_WEST
    return cal_east, cal_west


def get_calibration(token):
    """Get single (legacy) calibration factor — average of east/west."""
    cal_east, cal_west = get_calibrations(token)
    return (cal_east + cal_west) / 2.0


def get_cloud_bias(token):
    """Get cloud bias corrections per horizon bucket from HA helpers.

    Returns dict of {bucket: bias_pct}.
    """
    bias = {}
    for bucket in ["t0", "t6", "t12", "t24", "t36"]:
        val = ha_state(f"input_number.energy_cloud_bias_{bucket}", token)
        if val and val not in ("unknown", "unavailable"):
            bias[bucket] = float(val)
        else:
            bias[bucket] = 0.0
    return bias


def get_tz_offset(dt_utc):
    """Get CET/CEST offset for a UTC datetime. Switzerland: +1 winter, +2 summer."""
    year = dt_utc.year
    # Last Sunday of March at 01:00 UTC
    march_last_sun = 31 - (datetime(year, 3, 31).weekday() + 1) % 7
    dst_start = datetime(year, 3, march_last_sun, 1, tzinfo=timezone.utc)
    # Last Sunday of October at 01:00 UTC
    oct_last_sun = 31 - (datetime(year, 10, 31).weekday() + 1) % 7
    dst_end = datetime(year, 10, oct_last_sun, 1, tzinfo=timezone.utc)
    return 2 if dst_start <= dt_utc < dst_end else 1


def utc_to_local(dt_utc):
    """Convert UTC datetime to local Swiss time."""
    offset = get_tz_offset(dt_utc)
    return dt_utc + timedelta(hours=offset)


# =============================================================================
# Sun Position (NOAA equations)
# =============================================================================

def _julian_day(dt):
    """Convert datetime to Julian day number."""
    y = dt.year
    m = dt.month
    d = (dt.day + dt.hour / 24.0 + dt.minute / 1440.0
         + dt.second / 86400.0)
    if m <= 2:
        y -= 1
        m += 12
    a = int(y / 100)
    b = 2 - a + int(a / 4)
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def sun_position(dt_utc, lat, lon):
    """Calculate solar altitude and azimuth for a UTC datetime and location.

    Returns (altitude_deg, azimuth_deg) where azimuth is 0=North, clockwise.
    """
    jd = _julian_day(dt_utc)
    jc = (jd - 2451545.0) / 36525.0  # Julian century

    # Geometric mean longitude and anomaly of sun
    geom_mean_lon = (280.46646 + jc * (36000.76983 + 0.0003032 * jc)) % 360
    geom_mean_anom = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    eccent = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)

    # Equation of center
    anom_rad = math.radians(geom_mean_anom)
    eq_center = (
        math.sin(anom_rad) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
        + math.sin(2 * anom_rad) * (0.019993 - 0.000101 * jc)
        + math.sin(3 * anom_rad) * 0.000289
    )

    # Sun true and apparent longitude
    sun_true_lon = geom_mean_lon + eq_center
    sun_app_lon = (
        sun_true_lon
        - 0.00569
        - 0.00478 * math.sin(math.radians(125.04 - 1934.136 * jc))
    )

    # Obliquity of ecliptic
    obliq_inner = 21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))
    mean_obliq = 23.0 + (26.0 + obliq_inner / 60.0) / 60.0
    obliq_corr = mean_obliq + 0.00256 * math.cos(
        math.radians(125.04 - 1934.136 * jc)
    )
    obliq_rad = math.radians(obliq_corr)

    # Declination
    sin_decl = math.sin(obliq_rad) * math.sin(math.radians(sun_app_lon))
    declination = math.degrees(math.asin(max(-1, min(1, sin_decl))))
    decl_rad = math.radians(declination)

    # Equation of time (minutes)
    y = math.tan(obliq_rad / 2) ** 2
    lon_rad = math.radians(geom_mean_lon)
    eot = 4 * math.degrees(
        y * math.sin(2 * lon_rad)
        - 2 * eccent * math.sin(anom_rad)
        + 4 * eccent * y * math.sin(anom_rad) * math.cos(2 * lon_rad)
        - 0.5 * y * y * math.sin(4 * lon_rad)
        - 1.25 * eccent * eccent * math.sin(2 * anom_rad)
    )

    # True solar time (minutes from midnight UTC, adjusted for longitude)
    minutes_utc = dt_utc.hour * 60 + dt_utc.minute + dt_utc.second / 60.0
    true_solar_time = (minutes_utc + eot + 4 * lon) % 1440

    # Hour angle
    hour_angle = true_solar_time / 4 - 180 if true_solar_time >= 0 else true_solar_time / 4 + 180
    ha_rad = math.radians(hour_angle)

    # Solar altitude
    lat_rad = math.radians(lat)
    sin_alt = (
        math.sin(lat_rad) * math.sin(decl_rad)
        + math.cos(lat_rad) * math.cos(decl_rad) * math.cos(ha_rad)
    )
    sin_alt = max(-1, min(1, sin_alt))
    altitude = math.degrees(math.asin(sin_alt))

    # Solar azimuth (0=N, clockwise)
    if altitude > -0.01:
        cos_alt = math.cos(math.radians(altitude))
        if cos_alt > 0.001:
            cos_az = (
                (math.sin(decl_rad) - math.sin(lat_rad) * sin_alt)
                / (math.cos(lat_rad) * cos_alt)
            )
            cos_az = max(-1, min(1, cos_az))
            azimuth = math.degrees(math.acos(cos_az))
            if hour_angle > 0:
                azimuth = 360 - azimuth
        else:
            azimuth = 180.0
    else:
        azimuth = 0.0

    return altitude, azimuth


# =============================================================================
# Clear-sky irradiance model (dual slopes)
# =============================================================================

def clear_sky_power(dt_utc, lat, lon):
    """Calculate clear-sky power output (W) for both arrays WITHOUT calibration.

    Returns (total_w, east_w, west_w, altitude, azimuth).
    """
    alt, az = sun_position(dt_utc, lat, lon)

    if alt <= 0:
        return 0.0, 0.0, 0.0, alt, az

    alt_rad = math.radians(alt)

    # Air mass (Kasten-Young formula)
    am = 1.0 / (math.sin(alt_rad) + 0.50572 * (alt + 6.07995) ** -1.6364)

    # Clear-sky DNI (Meinel model)
    dni = SOLAR_CONSTANT * 0.7 ** (am ** 0.678)

    # Global and diffuse horizontal irradiance
    ghi = dni * math.sin(alt_rad)
    dhi = 0.12 * ghi  # Clear-sky diffuse fraction ~12%

    east_w = 0.0
    west_w = 0.0

    for panel_az, kwp in [(EAST_AZIMUTH, EAST_KWP), (WEST_AZIMUTH, WEST_KWP)]:
        tilt_rad = math.radians(TILT_DEG)
        az_diff_rad = math.radians(az - panel_az)

        # Angle of incidence on tilted surface
        cos_aoi = (
            math.sin(alt_rad) * math.cos(tilt_rad)
            + math.cos(alt_rad) * math.sin(tilt_rad) * math.cos(az_diff_rad)
        )

        # Plane-of-array irradiance components
        poa_beam = dni * max(0, cos_aoi)
        poa_diffuse = dhi * (1 + math.cos(tilt_rad)) / 2
        poa_ground = ghi * ALBEDO * (1 - math.cos(tilt_rad)) / 2
        poa_total = poa_beam + poa_diffuse + poa_ground

        # Power from this array (W) — no calibration applied
        power = (poa_total / 1000.0) * kwp * 1000

        if panel_az == EAST_AZIMUTH:
            east_w = power
        else:
            west_w = power

    return east_w + west_w, east_w, west_w, alt, az


# =============================================================================
# Cloud scaling (Kasten-Czeplak model)
# =============================================================================

def cloud_scaling(cloud_pct):
    """Cloud attenuation factor. cloud_pct is 0-100, returns 0-1."""
    frac = max(0, min(100, cloud_pct)) / 100.0
    return 1.0 - 0.75 * (frac ** 3.4)


def invert_cloud_factor(factor):
    """Invert Kasten-Czeplak to get cloud_pct from factor. Returns 0-100."""
    if factor >= 1.0:
        return 0.0
    if factor <= 0.25:
        return 100.0
    frac = ((1.0 - factor) / 0.75) ** (1.0 / 3.4)
    return min(100, max(0, frac * 100))


def interpolate_cloud(target_utc, cloud_data):
    """Interpolate cloud % between hourly Met.no data points.

    cloud_data: dict of {datetime_utc_hour: cloud_pct}.
    Returns interpolated cloud % for target_utc.
    """
    hour_start = target_utc.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)

    cloud_start = cloud_data.get(hour_start, None)
    cloud_end = cloud_data.get(hour_end, None)

    if cloud_start is not None and cloud_end is not None:
        # Linear interpolation
        frac = (target_utc - hour_start).total_seconds() / 3600.0
        return cloud_start + frac * (cloud_end - cloud_start)
    elif cloud_start is not None:
        return cloud_start
    elif cloud_end is not None:
        return cloud_end
    else:
        return None


# =============================================================================
# Temperature derating
# =============================================================================

def estimate_panel_temp(ambient_c, irradiance_w_m2, wind_ms=2.0):
    """Estimate panel temperature from ambient + irradiance.

    Simplified Sandia model: T_panel = T_ambient + k * irradiance / (wind + 1)
    k ~ 0.035 C*m2/W for open-rack mounting.
    """
    return ambient_c + 0.035 * irradiance_w_m2 / (wind_ms + 1)


def temp_derating_factor(panel_temp_c):
    """Temperature derating factor for crystalline silicon PV.

    ~0.4%/C loss above 25C (standard temperature coefficient).
    """
    return max(0.5, 1.0 - 0.004 * max(0, panel_temp_c - 25))


# =============================================================================
# Met.no weather forecast
# =============================================================================

def fetch_metno_forecast(lat, lon):
    """Fetch hourly cloud forecast from Met.no API.

    Returns dict of {datetime_utc_hour: cloud_area_fraction_pct}.
    """
    url = (
        f"https://api.met.no/weatherapi/locationforecast/2.0/compact"
        f"?lat={lat:.4f}&lon={lon:.4f}"
    )
    req = urllib.request.Request(url)
    req.add_header(
        "User-Agent",
        "ha-energy-optimisation/1.0 github.com/FraserMacdonald"
    )
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read().decode())

    result = {}
    for entry in data.get("properties", {}).get("timeseries", []):
        time_str = entry["time"]
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        # Normalize to naive UTC for consistency
        dt_naive = dt.replace(tzinfo=None)
        hour_key = dt_naive.replace(minute=0, second=0, microsecond=0)
        details = entry.get("data", {}).get("instant", {}).get("details", {})
        cloud_pct = details.get("cloud_area_fraction", 50)
        result[hour_key] = cloud_pct

    return result


def fetch_metno_temps(lat, lon):
    """Fetch hourly temperature forecast from Met.no API.

    Returns dict of {datetime_utc_hour: air_temperature_c}.
    """
    url = (
        f"https://api.met.no/weatherapi/locationforecast/2.0/compact"
        f"?lat={lat:.4f}&lon={lon:.4f}"
    )
    req = urllib.request.Request(url)
    req.add_header(
        "User-Agent",
        "ha-energy-optimisation/1.0 github.com/FraserMacdonald"
    )
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read().decode())

    result = {}
    for entry in data.get("properties", {}).get("timeseries", []):
        time_str = entry["time"]
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        dt_naive = dt.replace(tzinfo=None)
        hour_key = dt_naive.replace(minute=0, second=0, microsecond=0)
        details = entry.get("data", {}).get("instant", {}).get("details", {})
        temp_c = details.get("air_temperature", None)
        if temp_c is not None:
            result[hour_key] = temp_c

    return result


def fetch_metno_wind(lat, lon):
    """Fetch hourly wind speed from Met.no API.

    Returns dict of {datetime_utc_hour: wind_speed_ms}.
    """
    url = (
        f"https://api.met.no/weatherapi/locationforecast/2.0/compact"
        f"?lat={lat:.4f}&lon={lon:.4f}"
    )
    req = urllib.request.Request(url)
    req.add_header(
        "User-Agent",
        "ha-energy-optimisation/1.0 github.com/FraserMacdonald"
    )
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read().decode())

    result = {}
    for entry in data.get("properties", {}).get("timeseries", []):
        time_str = entry["time"]
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        dt_naive = dt.replace(tzinfo=None)
        hour_key = dt_naive.replace(minute=0, second=0, microsecond=0)
        details = entry.get("data", {}).get("instant", {}).get("details", {})
        wind = details.get("wind_speed", None)
        if wind is not None:
            result[hour_key] = wind

    return result


def fetch_metno_all(lat, lon):
    """Fetch cloud, temperature, and wind from Met.no in a single API call.

    Returns (cloud_data, temp_data, wind_data) dicts.
    """
    url = (
        f"https://api.met.no/weatherapi/locationforecast/2.0/compact"
        f"?lat={lat:.4f}&lon={lon:.4f}"
    )
    req = urllib.request.Request(url)
    req.add_header(
        "User-Agent",
        "ha-energy-optimisation/1.0 github.com/FraserMacdonald"
    )
    resp = urllib.request.urlopen(req, timeout=15)
    data = json.loads(resp.read().decode())

    clouds = {}
    temps = {}
    winds = {}
    for entry in data.get("properties", {}).get("timeseries", []):
        time_str = entry["time"]
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        dt_naive = dt.replace(tzinfo=None)
        hour_key = dt_naive.replace(minute=0, second=0, microsecond=0)
        details = entry.get("data", {}).get("instant", {}).get("details", {})
        cloud_pct = details.get("cloud_area_fraction")
        if cloud_pct is not None:
            clouds[hour_key] = cloud_pct
        temp_c = details.get("air_temperature")
        if temp_c is not None:
            temps[hour_key] = temp_c
        wind = details.get("wind_speed")
        if wind is not None:
            winds[hour_key] = wind

    return clouds, temps, winds


def interpolate_hourly(target_utc, data_dict, default=None):
    """Interpolate between hourly data points for a sub-hourly target time."""
    hour_start = target_utc.replace(minute=0, second=0, microsecond=0)
    hour_end = hour_start + timedelta(hours=1)

    v_start = data_dict.get(hour_start, None)
    v_end = data_dict.get(hour_end, None)

    if v_start is not None and v_end is not None:
        frac = (target_utc - hour_start).total_seconds() / 3600.0
        return v_start + frac * (v_end - v_start)
    elif v_start is not None:
        return v_start
    elif v_end is not None:
        return v_end
    else:
        return default


# =============================================================================
# Tariff helpers
# =============================================================================

def _is_low_tariff_hour(local_dt):
    """Check if a local datetime falls in low tariff period.

    Schedule: Mon-Fri 17:00-22:00 = high; everything else = low.
    """
    dow = local_dt.weekday()
    hour = local_dt.hour
    is_high = dow in [0, 1, 2, 3, 4] and 17 <= hour < 22
    return not is_high


def _tariff_rate(local_dt):
    """Get tariff rate for a local datetime."""
    return RATE_LOW if _is_low_tariff_hour(local_dt) else RATE_HIGH


def _horizon_bucket(minutes):
    """Map horizon minutes to bucket label."""
    if minutes < 180:
        return "t0"
    elif minutes < 540:
        return "t6"
    elif minutes < 1080:
        return "t12"
    elif minutes < 1800:
        return "t24"
    else:
        return "t36"


# =============================================================================
# Confidence intervals
# =============================================================================

def _get_confidence_stats(cur):
    """Get rolling error statistics per horizon bucket (last 30 days).

    Returns dict of {bucket: (mean_error_pct, std_error_pct)}.
    """
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now_utc - timedelta(days=30)

    stats = {}
    for bucket in ["t0", "t6", "t12", "t24", "t36"]:
        cur.execute(
            """SELECT AVG(total_error_pct) as mean_err,
                      STDDEV(total_error_pct) as std_err,
                      COUNT(*) as cnt
               FROM solar_forecast_comparison
               WHERE horizon_bucket = %s
                 AND target_hour >= %s
                 AND actual_wh > 50""",
            (bucket, cutoff)
        )
        row = cur.fetchone()
        if row and row["cnt"] and row["cnt"] >= 5:
            mean = row["mean_err"] or 0
            std = row["std_err"] or 20
            stats[bucket] = (mean, std)
        else:
            stats[bucket] = (0, 30)  # default wide band
    return stats


# =============================================================================
# Database operations
# =============================================================================

def cmd_init_db():
    """Create all forecast and planner tables."""
    c = conn()
    cur = c.cursor()

    # Legacy hourly tables (kept for backward compat)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS solar_forecast_hourly (
            id INT AUTO_INCREMENT PRIMARY KEY,
            forecast_made_at DATETIME NOT NULL,
            target_hour DATETIME NOT NULL,
            horizon_minutes INT NOT NULL,
            solar_altitude FLOAT,
            solar_azimuth FLOAT,
            cloud_pct FLOAT,
            clear_sky_wh FLOAT NOT NULL,
            cloud_factor FLOAT,
            forecast_wh FLOAT NOT NULL,
            east_clear_sky_wh FLOAT,
            west_clear_sky_wh FLOAT,
            calibration_factor FLOAT NOT NULL,
            INDEX idx_target (target_hour),
            INDEX idx_made (forecast_made_at),
            INDEX idx_horizon (horizon_minutes)
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS solar_actual_hourly (
            hour_start DATETIME PRIMARY KEY,
            actual_wh FLOAT NOT NULL,
            avg_power_w FLOAT,
            sample_count INT DEFAULT 1,
            actual_cloud_pct FLOAT,
            la_dole_temp_c FLOAT,
            INDEX idx_date (hour_start)
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS solar_forecast_comparison (
            id INT AUTO_INCREMENT PRIMARY KEY,
            target_hour DATETIME NOT NULL,
            forecast_made_at DATETIME NOT NULL,
            horizon_minutes INT NOT NULL,
            horizon_bucket VARCHAR(10),
            forecast_wh FLOAT NOT NULL,
            actual_wh FLOAT NOT NULL,
            total_error_wh FLOAT,
            total_error_pct FLOAT,
            clear_sky_wh FLOAT,
            cloud_factor FLOAT,
            calibration_factor FLOAT,
            model_error_wh FLOAT,
            weather_error_wh FLOAT,
            INDEX idx_target (target_hour),
            INDEX idx_bucket (horizon_bucket),
            INDEX idx_made (forecast_made_at)
        ) ENGINE=InnoDB
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS solar_calibration_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            calibration_date DATETIME NOT NULL,
            old_factor FLOAT NOT NULL,
            new_factor FLOAT NOT NULL,
            clear_days_used INT,
            avg_ratio FLOAT,
            INDEX idx_date (calibration_date)
        ) ENGINE=InnoDB
    """)

    # New 15-min forecast table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS solar_forecast_15min (
            id INT AUTO_INCREMENT PRIMARY KEY,
            forecast_made_at DATETIME NOT NULL,
            target_slot DATETIME NOT NULL,
            horizon_minutes INT NOT NULL,
            solar_altitude FLOAT,
            solar_azimuth FLOAT,
            east_clear_sky_wh FLOAT,
            west_clear_sky_wh FLOAT,
            cloud_pct_raw FLOAT,
            cloud_pct_corrected FLOAT,
            cloud_factor FLOAT,
            temp_ambient_forecast FLOAT,
            panel_temp_estimate FLOAT,
            temp_derating_factor FLOAT,
            calibration_east FLOAT,
            calibration_west FLOAT,
            clear_sky_wh FLOAT NOT NULL,
            forecast_wh FLOAT NOT NULL,
            confidence_low_wh FLOAT,
            confidence_high_wh FLOAT,
            INDEX idx_slot (target_slot),
            INDEX idx_made (forecast_made_at)
        ) ENGINE=InnoDB
    """)

    # New 15-min actual table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS solar_actual_15min (
            slot_start DATETIME PRIMARY KEY,
            actual_wh FLOAT NOT NULL,
            avg_power_w FLOAT,
            actual_cloud_pct FLOAT,
            la_dole_temp_c FLOAT,
            base_load_w FLOAT,
            INDEX idx_date (slot_start)
        ) ENGINE=InnoDB
    """)

    # Component-level accuracy tracking
    cur.execute("""
        CREATE TABLE IF NOT EXISTS forecast_component_accuracy (
            id INT AUTO_INCREMENT PRIMARY KEY,
            target_slot DATETIME NOT NULL,
            cloud_forecast_pct FLOAT,
            cloud_actual_pct FLOAT,
            cloud_error_pct FLOAT,
            temp_forecast_c FLOAT,
            temp_actual_c FLOAT,
            temp_error_c FLOAT,
            east_forecast_wh FLOAT,
            east_actual_wh FLOAT,
            west_forecast_wh FLOAT,
            west_actual_wh FLOAT,
            horizon_bucket VARCHAR(10),
            total_forecast_wh FLOAT,
            total_actual_wh FLOAT,
            INDEX idx_slot (target_slot),
            INDEX idx_bucket (horizon_bucket)
        ) ENGINE=InnoDB
    """)

    # Supply plan schedule
    cur.execute("""
        CREATE TABLE IF NOT EXISTS supply_plan_schedule (
            id INT AUTO_INCREMENT PRIMARY KEY,
            plan_made_at DATETIME NOT NULL,
            slot_start DATETIME NOT NULL,
            slot_index INT NOT NULL,
            solar_forecast_w FLOAT,
            tariff_rate FLOAT,
            ambient_temp_c FLOAT,
            base_load_w FLOAT,
            jacuzzi_action VARCHAR(10),
            ev_action VARCHAR(10),
            ev_car VARCHAR(20),
            ev_amps INT,
            jacuzzi_temp_expected FLOAT,
            ev_soc_expected FLOAT,
            grid_draw_w FLOAT,
            solar_used_w FLOAT,
            solar_exported_w FLOAT,
            slot_cost_chf FLOAT,
            cumulative_cost_chf FLOAT,
            cumulative_self_consumption_pct FLOAT,
            INDEX idx_plan (plan_made_at),
            INDEX idx_slot (slot_start)
        ) ENGINE=InnoDB
    """)

    # Per-array calibration log
    cur.execute("""
        CREATE TABLE IF NOT EXISTS solar_calibration_log_v2 (
            id INT AUTO_INCREMENT PRIMARY KEY,
            calibration_date DATETIME NOT NULL,
            old_east FLOAT NOT NULL,
            new_east FLOAT NOT NULL,
            old_west FLOAT NOT NULL,
            new_west FLOAT NOT NULL,
            clear_days_used INT,
            avg_ratio_east FLOAT,
            avg_ratio_west FLOAT,
            INDEX idx_date (calibration_date)
        ) ENGINE=InnoDB
    """)

    c.commit()
    c.close()
    print("All forecast and planner tables created.")


# =============================================================================
# Subcommand: forecast (15-min intervals with per-component tracking)
# =============================================================================

def cmd_forecast(token):
    """Generate 48-hour forecast at 15-min resolution, store in DB, update HA helpers."""
    lat, lon = get_location(token)
    cal_east, cal_west = get_calibrations(token)
    cloud_bias = get_cloud_bias(token)

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    # Align to 15-min boundary
    minute_aligned = (now_utc.minute // INTERVAL_MIN) * INTERVAL_MIN
    current_slot = now_utc.replace(minute=minute_aligned, second=0, microsecond=0)
    forecast_made_at = current_slot

    # Fetch weather from Met.no (single call for all data)
    cloud_data = {}
    temp_data = {}
    wind_data = {}
    try:
        cloud_data, temp_data, wind_data = fetch_metno_all(lat, lon)
    except Exception as e:
        print(f"WARNING: Met.no fetch failed ({e}), using clear-sky only")

    # Get confidence stats from DB
    c = conn()
    cur = c.cursor(dictionary=True)
    try:
        conf_stats = _get_confidence_stats(cur)
    except Exception:
        conf_stats = {b: (0, 30) for b in ["t0", "t6", "t12", "t24", "t36"]}

    # Timezone for day boundaries
    tz_offset = get_tz_offset(now_utc.replace(tzinfo=timezone.utc))
    local_now = now_utc + timedelta(hours=tz_offset)
    today_date = local_now.date()
    tomorrow_date = today_date + timedelta(days=1)

    today_kwh = 0.0
    tomorrow_kwh = 0.0
    clear_sky_today_kwh = 0.0
    current_slot_w = 0.0
    next_slot_w = 0.0
    peak_w = 0.0
    peak_hour = 0
    current_cloud_pct = 0.0
    hourly_accum = {}  # For backward-compat hourly table

    cur_write = c.cursor()

    for slot in range(SLOTS_48H):
        target_utc = current_slot + timedelta(minutes=slot * INTERVAL_MIN)
        mid_slot = target_utc + timedelta(minutes=INTERVAL_MIN / 2)
        target_local = target_utc + timedelta(hours=tz_offset)
        horizon_min = slot * INTERVAL_MIN

        # Clear-sky at mid-slot
        total_w, east_w, west_w, alt, az = clear_sky_power(mid_slot, lat, lon)

        # Energy for 15-min slot (W at mid-point * 0.25h = Wh)
        east_clear_wh = east_w * (INTERVAL_MIN / 60)
        west_clear_wh = west_w * (INTERVAL_MIN / 60)
        clear_sky_wh = east_clear_wh + west_clear_wh

        # Cloud: interpolate between hourly Met.no data points
        cloud_raw = interpolate_cloud(target_utc, cloud_data)
        if cloud_raw is None:
            cloud_raw = 0.0

        # Cloud bias correction per horizon bucket
        bucket = _horizon_bucket(horizon_min)
        bias = cloud_bias.get(bucket, 0.0)
        cloud_corrected = max(0, min(100, cloud_raw - bias))

        cf = cloud_scaling(cloud_corrected)

        # Temperature derating
        ambient = interpolate_hourly(target_utc, temp_data, default=10.0)
        wind = interpolate_hourly(target_utc, wind_data, default=2.0)
        # Estimate irradiance on panel plane (simplified: use total clear-sky W / area)
        irradiance_est = total_w / max(EAST_KWP + WEST_KWP, 1) * 1000 / 1.0  # W/m2 approx
        irradiance_est = irradiance_est * cf  # Cloud-adjusted
        panel_temp = estimate_panel_temp(ambient, irradiance_est, wind)
        temp_factor = temp_derating_factor(panel_temp)

        # Per-array calibration with blending
        east_share = east_clear_wh / (east_clear_wh + west_clear_wh + 0.001)
        west_share = 1 - east_share

        # Apply all factors
        east_forecast_wh = east_clear_wh * cf * temp_factor * cal_east
        west_forecast_wh = west_clear_wh * cf * temp_factor * cal_west
        forecast_wh = east_forecast_wh + west_forecast_wh

        # Confidence intervals
        mean_err, std_err = conf_stats.get(bucket, (0, 30))
        conf_low = max(0, forecast_wh * (1 + (mean_err - 1.28 * std_err) / 100))
        conf_high = forecast_wh * (1 + (mean_err + 1.28 * std_err) / 100)

        # Insert into 15-min table
        cur_write.execute(
            """INSERT INTO solar_forecast_15min
               (forecast_made_at, target_slot, horizon_minutes,
                solar_altitude, solar_azimuth,
                east_clear_sky_wh, west_clear_sky_wh,
                cloud_pct_raw, cloud_pct_corrected, cloud_factor,
                temp_ambient_forecast, panel_temp_estimate, temp_derating_factor,
                calibration_east, calibration_west,
                clear_sky_wh, forecast_wh,
                confidence_low_wh, confidence_high_wh)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (forecast_made_at, target_utc, horizon_min,
             round(alt, 2), round(az, 2),
             round(east_clear_wh, 1), round(west_clear_wh, 1),
             round(cloud_raw, 1), round(cloud_corrected, 1), round(cf, 4),
             round(ambient, 1), round(panel_temp, 1), round(temp_factor, 4),
             cal_east, cal_west,
             round(clear_sky_wh, 1), round(forecast_wh, 1),
             round(conf_low, 1), round(conf_high, 1))
        )

        # Accumulate for hourly backward-compat table
        hour_key = target_utc.replace(minute=0, second=0, microsecond=0)
        if hour_key not in hourly_accum:
            hourly_accum[hour_key] = {
                "clear_sky_wh": 0, "forecast_wh": 0,
                "east_clear_wh": 0, "west_clear_wh": 0,
                "alt": alt, "az": az, "cloud_pct": cloud_raw,
                "cf": cf, "horizon_min": horizon_min,
            }
        hourly_accum[hour_key]["clear_sky_wh"] += clear_sky_wh
        hourly_accum[hour_key]["forecast_wh"] += forecast_wh
        hourly_accum[hour_key]["east_clear_wh"] += east_clear_wh
        hourly_accum[hour_key]["west_clear_wh"] += west_clear_wh

        # Aggregate for helpers
        target_date = target_local.date()
        if target_date == today_date:
            today_kwh += forecast_wh / 1000.0
            clear_sky_today_kwh += (clear_sky_wh * (cal_east * east_share + cal_west * west_share)) / 1000.0
        elif target_date == tomorrow_date:
            tomorrow_kwh += forecast_wh / 1000.0

        # Forecast power (W) for current and next slots
        forecast_w = forecast_wh * (60 / INTERVAL_MIN)  # Wh * 4 = W avg
        if slot == 0:
            current_slot_w = forecast_w
            current_cloud_pct = cloud_corrected
        elif slot == 1:
            next_slot_w = forecast_w

        # Track peak for today
        if target_date == today_date and forecast_w > peak_w:
            peak_w = forecast_w
            peak_hour = target_local.hour

    # Write hourly backward-compat rows
    blended_cal = (cal_east + cal_west) / 2.0
    for hour_key, acc in hourly_accum.items():
        cur_write.execute(
            """INSERT INTO solar_forecast_hourly
               (forecast_made_at, target_hour, horizon_minutes,
                solar_altitude, solar_azimuth, cloud_pct,
                clear_sky_wh, cloud_factor, forecast_wh,
                east_clear_sky_wh, west_clear_sky_wh, calibration_factor)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (forecast_made_at, hour_key, acc["horizon_min"],
             round(acc["alt"], 2), round(acc["az"], 2),
             round(acc["cloud_pct"], 1),
             round(acc["clear_sky_wh"], 1), round(acc["cf"], 4),
             round(acc["forecast_wh"], 1),
             round(acc["east_clear_wh"], 1), round(acc["west_clear_wh"], 1),
             blended_cal)
        )

    c.commit()
    c.close()

    # Update HA helpers
    ha_set("input_number.energy_solar_forecast_today_kwh",
           round(today_kwh, 2), token)
    ha_set("input_number.energy_solar_forecast_tomorrow_kwh",
           round(tomorrow_kwh, 2), token)
    ha_set("input_number.energy_solar_forecast_current_hour_w",
           round(current_slot_w, 0), token)
    ha_set("input_number.energy_solar_forecast_next_hour_w",
           round(next_slot_w, 0), token)
    ha_set("input_number.energy_solar_forecast_peak_hour_w",
           round(peak_w, 0), token)
    ha_set("input_number.energy_solar_forecast_peak_hour",
           peak_hour, token)
    ha_set("input_number.energy_solar_forecast_clear_sky_today_kwh",
           round(clear_sky_today_kwh, 2), token)
    ha_set("input_number.energy_solar_forecast_cloud_pct",
           round(current_cloud_pct, 0), token)

    timestamp = local_now.strftime("%H:%M %d/%m")
    status = f"OK {timestamp} ({len(cloud_data)}h weather, 15min)"
    ha_set("input_select.energy_solar_forecast_last_run", status, token)

    print(f"Forecast: today={today_kwh:.1f}kWh, tomorrow={tomorrow_kwh:.1f}kWh, "
          f"peak={peak_w:.0f}W@{peak_hour}h, cloud={current_cloud_pct:.0f}%, "
          f"cal_e={cal_east:.3f}, cal_w={cal_west:.3f}")


# =============================================================================
# Subcommand: actual (15-min logging)
# =============================================================================

def cmd_actual(token):
    """Log current SolarEdge production for the current 15-min slot."""
    lat, lon = get_location(token)
    cal_east, cal_west = get_calibrations(token)
    calibration = (cal_east + cal_west) / 2.0

    # Read SolarEdge power (normalize to W)
    power_str = ha_state("sensor.solaredge_current_power", token)
    unit = ha_attr("sensor.solaredge_current_power",
                   "unit_of_measurement", token)
    try:
        power_w = float(power_str)
    except (ValueError, TypeError):
        power_w = 0.0
    if unit == "kW":
        power_w *= 1000

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    # Align to 15-min slot boundary
    minute_aligned = (now_utc.minute // INTERVAL_MIN) * INTERVAL_MIN
    slot_start = now_utc.replace(minute=minute_aligned, second=0, microsecond=0)

    # Also compute hourly boundary for backward-compat
    hour_start = now_utc.replace(minute=0, second=0, microsecond=0)

    # Infer cloud percentage from production vs clear-sky
    mid_slot = slot_start + timedelta(minutes=INTERVAL_MIN / 2)
    clear_w, _, _, alt, _ = clear_sky_power(mid_slot, lat, lon)
    expected_w = clear_w * calibration

    actual_cloud_pct = None
    if expected_w > 50 and alt > 2:
        ratio = max(0, min(1, power_w / expected_w))
        actual_cloud_pct = round(invert_cloud_factor(ratio), 1)

    # Temperature
    temp_str = ha_state("sensor.la_dole_temperature", token)
    try:
        temp_c = float(temp_str)
    except (ValueError, TypeError):
        temp_c = None

    # Base load (home consumption minus solar self-consumption)
    cons_str = ha_state("sensor.solaredge_power_consumption", token)
    cons_unit = ha_attr("sensor.solaredge_power_consumption",
                        "unit_of_measurement", token)
    try:
        cons_w = float(cons_str)
    except (ValueError, TypeError):
        cons_w = 0.0
    if cons_unit == "kW":
        cons_w *= 1000
    base_load_w = cons_w

    # Energy for this 15-min sample
    energy_wh = power_w * (INTERVAL_MIN / 60)

    c = conn()
    cur = c.cursor()

    # Write to 15-min table
    cur.execute(
        """INSERT INTO solar_actual_15min
           (slot_start, actual_wh, avg_power_w, actual_cloud_pct,
            la_dole_temp_c, base_load_w)
           VALUES (%s, %s, %s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE
             actual_wh = %s,
             avg_power_w = %s,
             actual_cloud_pct = COALESCE(%s, actual_cloud_pct),
             la_dole_temp_c = COALESCE(%s, la_dole_temp_c),
             base_load_w = COALESCE(%s, base_load_w)""",
        (slot_start, energy_wh, power_w, actual_cloud_pct, temp_c, base_load_w,
         energy_wh, power_w, actual_cloud_pct, temp_c, base_load_w)
    )

    # Also write to hourly backward-compat table (accumulate)
    energy_wh_hourly = power_w * 0.25  # 15 min = 0.25h
    cur.execute(
        """INSERT INTO solar_actual_hourly
           (hour_start, actual_wh, avg_power_w, sample_count,
            actual_cloud_pct, la_dole_temp_c)
           VALUES (%s, %s, %s, 1, %s, %s)
           ON DUPLICATE KEY UPDATE
             actual_wh = actual_wh + %s,
             avg_power_w = (avg_power_w * sample_count + %s)
                           / (sample_count + 1),
             sample_count = sample_count + 1,
             actual_cloud_pct = COALESCE(%s, actual_cloud_pct),
             la_dole_temp_c = COALESCE(%s, la_dole_temp_c)""",
        (hour_start, energy_wh_hourly, power_w, actual_cloud_pct, temp_c,
         energy_wh_hourly, power_w, actual_cloud_pct, temp_c)
    )

    c.commit()
    c.close()

    # Update today's actual total
    tz_offset = get_tz_offset(now_utc.replace(tzinfo=timezone.utc))
    local_now = now_utc + timedelta(hours=tz_offset)
    today_start_local = local_now.replace(hour=0, minute=0, second=0,
                                          microsecond=0)
    today_start_utc = today_start_local - timedelta(hours=tz_offset)

    c = conn()
    cur = c.cursor()
    cur.execute(
        """SELECT COALESCE(SUM(actual_wh), 0) FROM solar_actual_15min
           WHERE slot_start >= %s AND slot_start < %s""",
        (today_start_utc, today_start_utc + timedelta(days=1))
    )
    today_wh = cur.fetchone()[0]
    c.close()

    ha_set("input_number.energy_solar_actual_today_kwh",
           round(today_wh / 1000, 2), token)

    print(f"Actual: {power_w:.0f}W, +{energy_wh:.0f}Wh (15min), "
          f"today={today_wh / 1000:.2f}kWh, base={base_load_w:.0f}W")


# =============================================================================
# Subcommand: compare (per-component comparison + bias correction)
# =============================================================================

def cmd_compare(token):
    """Compare forecast vintages against actuals at component level."""
    c = conn()
    cur = c.cursor(dictionary=True)

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now_utc - timedelta(hours=48)

    # Find 15-min actual slots not yet compared
    cur.execute(
        """SELECT a.slot_start, a.actual_wh, a.actual_cloud_pct, a.la_dole_temp_c
           FROM solar_actual_15min a
           WHERE a.slot_start >= %s
             AND a.slot_start < %s
             AND a.actual_wh > 0
             AND NOT EXISTS (
               SELECT 1 FROM forecast_component_accuracy fc
               WHERE fc.target_slot = a.slot_start
               LIMIT 1
             )
           ORDER BY a.slot_start""",
        (cutoff, now_utc)
    )
    actuals = cur.fetchall()

    if not actuals:
        print("No new slots to compare.")
        # Still update error helpers from existing data
        _update_error_helpers(cur, token)
        c.close()
        return

    insert_count = 0
    for actual in actuals:
        slot_start = actual["slot_start"]
        actual_wh = actual["actual_wh"]
        actual_cloud = actual["actual_cloud_pct"]
        actual_temp = actual["la_dole_temp_c"]

        # Find the latest forecast vintage for this slot
        cur.execute(
            """SELECT forecast_made_at, horizon_minutes, forecast_wh,
                      clear_sky_wh, cloud_factor, cloud_pct_raw,
                      cloud_pct_corrected, temp_ambient_forecast,
                      calibration_east, calibration_west,
                      east_clear_sky_wh, west_clear_sky_wh
               FROM solar_forecast_15min
               WHERE target_slot = %s
               ORDER BY forecast_made_at DESC
               LIMIT 1""",
            (slot_start,)
        )
        fc = cur.fetchone()
        if not fc:
            continue

        horizon = fc["horizon_minutes"]
        bucket = _horizon_bucket(horizon)

        # Estimate east/west actuals from time-of-day
        # Morning (before solar noon ~12:00 UTC) → more east
        # Afternoon (after solar noon) → more west
        hour_utc = slot_start.hour
        if fc["east_clear_sky_wh"] + fc["west_clear_sky_wh"] > 0:
            east_frac = fc["east_clear_sky_wh"] / (fc["east_clear_sky_wh"] + fc["west_clear_sky_wh"])
        else:
            east_frac = 0.5
        east_actual_wh = actual_wh * east_frac
        west_actual_wh = actual_wh * (1 - east_frac)

        # Component accuracy
        cloud_error = None
        if actual_cloud is not None and fc["cloud_pct_corrected"] is not None:
            cloud_error = fc["cloud_pct_corrected"] - actual_cloud

        temp_error = None
        if actual_temp is not None and fc["temp_ambient_forecast"] is not None:
            temp_error = fc["temp_ambient_forecast"] - actual_temp

        east_fc_wh = fc["east_clear_sky_wh"] * fc["cloud_factor"] * fc["calibration_east"]
        west_fc_wh = fc["west_clear_sky_wh"] * fc["cloud_factor"] * fc["calibration_west"]

        cur.execute(
            """INSERT INTO forecast_component_accuracy
               (target_slot, cloud_forecast_pct, cloud_actual_pct, cloud_error_pct,
                temp_forecast_c, temp_actual_c, temp_error_c,
                east_forecast_wh, east_actual_wh, west_forecast_wh, west_actual_wh,
                horizon_bucket, total_forecast_wh, total_actual_wh)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (slot_start,
             fc["cloud_pct_corrected"], actual_cloud, cloud_error,
             fc["temp_ambient_forecast"], actual_temp, temp_error,
             round(east_fc_wh, 1), round(east_actual_wh, 1),
             round(west_fc_wh, 1), round(west_actual_wh, 1),
             bucket,
             round(fc["forecast_wh"], 1), round(actual_wh, 1))
        )
        insert_count += 1

    # Also write to legacy comparison table (hourly)
    _legacy_compare(cur, cutoff, now_utc, token)

    c.commit()

    # Update error helpers and bias correction
    _update_error_helpers(cur, token)
    _update_cloud_bias(cur, token)

    c.close()
    print(f"Compared {len(actuals)} slots, {insert_count} component rows inserted.")


def _legacy_compare(cur, cutoff, now_utc, token):
    """Write to legacy solar_forecast_comparison table (hourly)."""
    cur.execute(
        """SELECT a.hour_start, a.actual_wh, a.actual_cloud_pct
           FROM solar_actual_hourly a
           WHERE a.hour_start >= %s
             AND a.hour_start < %s
             AND a.actual_wh > 0
             AND NOT EXISTS (
               SELECT 1 FROM solar_forecast_comparison c
               WHERE c.target_hour = a.hour_start
               LIMIT 1
             )
           ORDER BY a.hour_start""",
        (cutoff, now_utc)
    )
    actuals = cur.fetchall()

    for actual in actuals:
        hour_start = actual["hour_start"]
        actual_wh = actual["actual_wh"]
        actual_cloud = actual["actual_cloud_pct"]

        cur.execute(
            """SELECT forecast_made_at, horizon_minutes, forecast_wh,
                      clear_sky_wh, cloud_factor, calibration_factor, cloud_pct
               FROM solar_forecast_hourly
               WHERE target_hour = %s
               ORDER BY forecast_made_at""",
            (hour_start,)
        )
        forecasts = cur.fetchall()

        for fc in forecasts:
            horizon = fc["horizon_minutes"]
            bucket = _horizon_bucket(horizon)
            forecast_wh = fc["forecast_wh"]
            clear_sky_wh = fc["clear_sky_wh"]
            cal = fc["calibration_factor"]
            fc_cloud_factor = fc["cloud_factor"]

            total_error = actual_wh - forecast_wh
            total_error_pct = (
                (total_error / forecast_wh * 100) if forecast_wh > 10 else 0
            )

            model_error = None
            weather_error = None
            if actual_cloud is not None and clear_sky_wh > 10:
                actual_cf = cloud_scaling(actual_cloud)
                expected_with_actual_cloud = clear_sky_wh * actual_cf * cal
                model_error = actual_wh - expected_with_actual_cloud
                weather_error = total_error - model_error

            cur.execute(
                """INSERT INTO solar_forecast_comparison
                   (target_hour, forecast_made_at, horizon_minutes,
                    horizon_bucket, forecast_wh, actual_wh,
                    total_error_wh, total_error_pct,
                    clear_sky_wh, cloud_factor, calibration_factor,
                    model_error_wh, weather_error_wh)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                           %s, %s, %s, %s, %s)""",
                (hour_start, fc["forecast_made_at"], horizon, bucket,
                 round(forecast_wh, 1), round(actual_wh, 1),
                 round(total_error, 1),
                 round(total_error_pct, 1) if total_error_pct else 0,
                 round(clear_sky_wh, 1), fc_cloud_factor, cal,
                 round(model_error, 1) if model_error is not None else None,
                 round(weather_error, 1) if weather_error is not None else None)
            )


def _update_error_helpers(cur, token):
    """Update HA helpers with recent forecast error metrics."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    recent = now_utc - timedelta(hours=72)

    # Nowcast error (t0 bucket, last 72h)
    cur.execute(
        """SELECT AVG(ABS(total_error_pct)) AS avg_err
           FROM solar_forecast_comparison
           WHERE horizon_bucket = 't0'
             AND target_hour >= %s
             AND actual_wh > 50""",
        (recent,)
    )
    row = cur.fetchone()
    t0_err = row["avg_err"] if row and row["avg_err"] is not None else None
    if t0_err is not None:
        ha_set("input_number.energy_solar_forecast_error_pct_t0",
               round(t0_err, 1), token)

    # 24h-ahead error (t24 bucket, last 72h)
    cur.execute(
        """SELECT AVG(ABS(total_error_pct)) AS avg_err
           FROM solar_forecast_comparison
           WHERE horizon_bucket = 't24'
             AND target_hour >= %s
             AND actual_wh > 50""",
        (recent,)
    )
    row = cur.fetchone()
    t24_err = row["avg_err"] if row and row["avg_err"] is not None else None
    if t24_err is not None:
        ha_set("input_number.energy_solar_forecast_error_pct_t24",
               round(t24_err, 1), token)

    # Quality score (0-100, based on t0 error)
    if t0_err is not None:
        score = max(0, min(100, 100 - t0_err * 2))
        ha_set("input_number.energy_solar_forecast_quality_score",
               round(score, 0), token)

        if score >= 80:
            rating = "Excellent"
        elif score >= 60:
            rating = "Good"
        elif score >= 40:
            rating = "Fair"
        else:
            rating = "Poor"
        ha_set("input_select.energy_solar_forecast_quality_rating",
               rating, token)


def _update_cloud_bias(cur, token):
    """Update per-horizon cloud bias corrections from recent component accuracy."""
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now_utc - timedelta(days=30)

    for bucket in ["t0", "t6", "t12", "t24", "t36"]:
        cur.execute(
            """SELECT AVG(cloud_error_pct) as avg_bias
               FROM forecast_component_accuracy
               WHERE horizon_bucket = %s
                 AND target_slot >= %s
                 AND cloud_error_pct IS NOT NULL""",
            (bucket, cutoff)
        )
        row = cur.fetchone()
        if row and row["avg_bias"] is not None:
            ha_set(f"input_number.energy_cloud_bias_{bucket}",
                   round(row["avg_bias"], 1), token)


# =============================================================================
# Subcommand: calibrate (per-array east/west split)
# =============================================================================

def cmd_calibrate(token):
    """Weekly auto-calibration from clear-sky days, per-array."""
    lat, lon = get_location(token)
    cal_east, cal_west = get_calibrations(token)

    c = conn()
    cur = c.cursor(dictionary=True)

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now_utc - timedelta(days=90)

    # Find clear-sky days: avg cloud < 20% during daylight hours
    # Use 15-min data if available, fall back to hourly
    cur.execute(
        """SELECT DATE(slot_start) as day,
                  SUM(actual_wh) as daily_wh,
                  AVG(actual_cloud_pct) as avg_cloud,
                  COUNT(*) as slots
           FROM solar_actual_15min
           WHERE slot_start >= %s
             AND actual_wh > 10
             AND actual_cloud_pct IS NOT NULL
           GROUP BY DATE(slot_start)
           HAVING avg_cloud < 20 AND slots >= 20
           ORDER BY day""",
        (cutoff,)
    )
    clear_days = cur.fetchall()

    if len(clear_days) < 3:
        # Fall back to hourly data
        cur.execute(
            """SELECT DATE(hour_start) as day,
                      SUM(actual_wh) as daily_wh,
                      AVG(actual_cloud_pct) as avg_cloud,
                      COUNT(*) as hours
               FROM solar_actual_hourly
               WHERE hour_start >= %s
                 AND actual_wh > 50
                 AND actual_cloud_pct IS NOT NULL
               GROUP BY DATE(hour_start)
               HAVING avg_cloud < 20 AND hours >= 6
               ORDER BY day""",
            (cutoff,)
        )
        clear_days = cur.fetchall()

    if len(clear_days) < 3:
        print(f"Only {len(clear_days)} clear days found (need >= 3). "
              "Skipping calibration.")
        c.close()
        return

    east_ratios = []
    west_ratios = []

    for day_row in clear_days:
        day = day_row["day"]

        tz_offset = get_tz_offset(
            datetime.combine(day, datetime.min.time()).replace(
                tzinfo=timezone.utc
            )
        )
        day_start_local = datetime.combine(day, datetime.min.time())
        day_start_utc = day_start_local - timedelta(hours=tz_offset)

        # Calculate solar noon (roughly when sun is highest)
        noon_utc = day_start_utc + timedelta(hours=12 - tz_offset)

        # Split actual production into morning (east-dominated) and afternoon (west-dominated)
        morning_actual = 0
        afternoon_actual = 0
        morning_clear_east = 0
        morning_clear_west = 0
        afternoon_clear_east = 0
        afternoon_clear_west = 0

        # Use 15-min data if available
        cur.execute(
            """SELECT slot_start, actual_wh FROM solar_actual_15min
               WHERE DATE(slot_start) = %s AND actual_wh > 0
               ORDER BY slot_start""",
            (day,)
        )
        slots = cur.fetchall()

        if not slots:
            # Fall back to hourly
            for h in range(24):
                hour_utc = day_start_utc + timedelta(hours=h)
                mid = hour_utc + timedelta(minutes=30)
                _, east_cs, west_cs, alt_val, _ = clear_sky_power(mid, lat, lon)
                if alt_val > 0:
                    if hour_utc < noon_utc:
                        morning_clear_east += east_cs
                        morning_clear_west += west_cs
                    else:
                        afternoon_clear_east += east_cs
                        afternoon_clear_west += west_cs

            cur.execute(
                """SELECT hour_start, actual_wh FROM solar_actual_hourly
                   WHERE DATE(hour_start) = %s AND actual_wh > 0
                   ORDER BY hour_start""",
                (day,)
            )
            hours = cur.fetchall()
            for h in hours:
                if h["hour_start"] < noon_utc:
                    morning_actual += h["actual_wh"]
                else:
                    afternoon_actual += h["actual_wh"]
        else:
            for s in slots:
                mid = s["slot_start"] + timedelta(minutes=INTERVAL_MIN / 2)
                _, east_cs, west_cs, alt_val, _ = clear_sky_power(mid, lat, lon)
                wh_frac = INTERVAL_MIN / 60
                if alt_val > 0:
                    if s["slot_start"] < noon_utc:
                        morning_actual += s["actual_wh"]
                        morning_clear_east += east_cs * wh_frac
                        morning_clear_west += west_cs * wh_frac
                    else:
                        afternoon_actual += s["actual_wh"]
                        afternoon_clear_east += east_cs * wh_frac
                        afternoon_clear_west += west_cs * wh_frac

        # Morning: mostly east array, afternoon: mostly west
        # East ratio = morning_actual / morning_clear_total (east-dominated)
        if morning_clear_east > 50:
            # Simplified: attribute morning production proportionally
            total_morning_clear = morning_clear_east + morning_clear_west
            if total_morning_clear > 0:
                east_ratios.append(morning_actual / total_morning_clear)

        if afternoon_clear_west > 50:
            total_afternoon_clear = afternoon_clear_east + afternoon_clear_west
            if total_afternoon_clear > 0:
                west_ratios.append(afternoon_actual / total_afternoon_clear)

    if not east_ratios:
        east_ratios = [(cal_east)]
    if not west_ratios:
        west_ratios = [(cal_west)]

    # Exponentially weighted mean (alpha=0.1, more weight to recent)
    alpha = 0.1
    ewm_east = east_ratios[0]
    for r in east_ratios[1:]:
        ewm_east = alpha * r + (1 - alpha) * ewm_east
    new_east = round(max(0.3, min(1.2, ewm_east)), 4)

    ewm_west = west_ratios[0]
    for r in west_ratios[1:]:
        ewm_west = alpha * r + (1 - alpha) * ewm_west
    new_west = round(max(0.3, min(1.2, ewm_west)), 4)

    # Log the change
    cur.execute(
        """INSERT INTO solar_calibration_log_v2
           (calibration_date, old_east, new_east, old_west, new_west,
            clear_days_used, avg_ratio_east, avg_ratio_west)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (now_utc, cal_east, new_east, cal_west, new_west,
         len(clear_days),
         round(sum(east_ratios) / len(east_ratios), 4),
         round(sum(west_ratios) / len(west_ratios), 4))
    )

    # Also write legacy log
    avg_new = (new_east + new_west) / 2
    avg_old = (cal_east + cal_west) / 2
    cur.execute(
        """INSERT INTO solar_calibration_log
           (calibration_date, old_factor, new_factor,
            clear_days_used, avg_ratio)
           VALUES (%s, %s, %s, %s, %s)""",
        (now_utc, avg_old, avg_new, len(clear_days),
         round((sum(east_ratios) / len(east_ratios) + sum(west_ratios) / len(west_ratios)) / 2, 4))
    )

    c.commit()
    c.close()

    # Update HA helpers
    ha_set("input_number.energy_solar_calibration_east", new_east, token)
    ha_set("input_number.energy_solar_calibration_west", new_west, token)
    ha_set("input_number.energy_solar_calibration_factor", avg_new, token)

    print(f"Calibration: east {cal_east:.4f} -> {new_east:.4f} "
          f"({len(east_ratios)} samples), "
          f"west {cal_west:.4f} -> {new_west:.4f} "
          f"({len(west_ratios)} samples), "
          f"{len(clear_days)} clear days")


# =============================================================================
# Subcommand: banking (thermal banking calculator)
# =============================================================================

def _fetch_calendar_events(entity_id, start_utc, end_utc, token):
    """Fetch events from HA calendar API within time range.

    Returns list of dicts with 'start' (naive UTC datetime) and 'summary'.
    """
    start_iso = start_utc.strftime("%Y-%m-%dT%H:%M:%S")
    end_iso = end_utc.strftime("%Y-%m-%dT%H:%M:%S")
    url = (
        f"http://supervisor/core/api/calendars/{entity_id}"
        f"?start={start_iso}&end={end_iso}"
    )
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read().decode())

    events = []
    for e in data:
        start = e.get("start", {})
        if isinstance(start, dict):
            dt_str = start.get("dateTime", start.get("date", ""))
        else:
            dt_str = str(start)
        try:
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            # Convert to naive UTC
            if dt.tzinfo is not None:
                dt = dt - dt.utcoffset()
                dt = dt.replace(tzinfo=None)
            events.append({
                "start": dt,
                "summary": e.get("summary", ""),
            })
        except (ValueError, TypeError):
            continue

    events.sort(key=lambda x: x["start"])
    return events


def _fetch_solar_forecast_db(start_utc, end_utc):
    """Read latest solar forecast vintage from DB (15-min).

    Returns dict of {datetime_utc_slot: forecast_wh}.
    Falls back to hourly if 15-min data unavailable.
    """
    c = conn()
    cur = c.cursor(dictionary=True)

    # Try 15-min first
    cur.execute(
        """SELECT target_slot, forecast_wh
           FROM solar_forecast_15min
           WHERE forecast_made_at = (
               SELECT MAX(forecast_made_at) FROM solar_forecast_15min
           )
           AND target_slot >= %s AND target_slot < %s""",
        (start_utc, end_utc)
    )
    rows = cur.fetchall()
    if rows:
        result = {row["target_slot"]: row["forecast_wh"] for row in rows}
        c.close()
        return result

    # Fall back to hourly
    cur.execute(
        """SELECT target_hour, forecast_wh
           FROM solar_forecast_hourly
           WHERE forecast_made_at = (
               SELECT MAX(forecast_made_at) FROM solar_forecast_hourly
           )
           AND target_hour >= %s AND target_hour < %s""",
        (start_utc, end_utc)
    )
    result = {}
    for row in cur.fetchall():
        result[row["target_hour"]] = row["forecast_wh"]
    c.close()
    return result


def _fetch_solar_forecast_15min(start_utc, end_utc):
    """Read latest 15-min solar forecast from DB.

    Returns list of dicts with slot details.
    """
    c = conn()
    cur = c.cursor(dictionary=True)
    cur.execute(
        """SELECT target_slot, forecast_wh, confidence_low_wh, confidence_high_wh,
                  temp_ambient_forecast
           FROM solar_forecast_15min
           WHERE forecast_made_at = (
               SELECT MAX(forecast_made_at) FROM solar_forecast_15min
           )
           AND target_slot >= %s AND target_slot < %s
           ORDER BY target_slot""",
        (start_utc, end_utc)
    )
    rows = cur.fetchall()
    c.close()
    return rows


def _clear_banking(token):
    """Reset all banking helpers to inactive state."""
    ha_set("input_number.jacuzzi_banking_target_temp", 0, token)
    ha_set("input_number.jacuzzi_expected_solar_hours", 0, token)
    ha_set("input_number.jacuzzi_expected_solar_gain_c", 0, token)
    ha_select_option("input_select.jacuzzi_banking_strategy", "none", token)


def _log_banking_decision(code, text, context, token):
    """Log a banking decision to the database."""
    from log_to_db import log_decision
    log_decision("jacuzzi", "solar_forecast.py", code, text,
                 json.dumps(context))


def cmd_banking(token):
    """Compute optimal thermal banking target for jacuzzi.

    Uses calendar events, solar forecast, tariff schedule, and Met.no
    ambient forecast to determine the best temperature to pre-heat to
    during cheap energy periods.

    NOTE: This command is superseded by cmd_plan() which provides more
    comprehensive cost-optimal scheduling. Kept for backward compat.
    """
    BANKING_CAP = 37.0
    SOLAR_THRESHOLD_W = 6000

    lat, lon = get_location(token)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)

    # --- Read current state from HA ---
    t_water = ha_attr("climate.jacuzzi", "current_temperature", token)
    t_water = float(t_water) if t_water is not None else 20.0

    standby = float(ha_state("input_number.jacuzzi_standby_temp", token) or 20)
    p_net = float(ha_state("input_number.jacuzzi_effective_power_kw", token) or 5.7)
    c_thermal = float(ha_state("sensor.jacuzzi_thermal_capacity", token) or 3.72)
    t_ambient = float(ha_state("sensor.la_dole_temperature", token) or 10)
    min_standby_str = ha_state("sensor.jacuzzi_minimum_standby_temp", token)
    min_standby = float(min_standby_str) if min_standby_str and min_standby_str not in (
        "unknown", "unavailable"
    ) else standby

    # Check if banking is currently active (for cleared logging)
    prev_target_str = ha_state("input_number.jacuzzi_banking_target_temp", token)
    banking_was_active = (
        prev_target_str is not None
        and float(prev_target_str or 0) > 0
    )

    # k values per ambient temperature band
    k_cold = float(ha_state("input_number.jacuzzi_k_cold", token) or 0.040)
    k_mild = float(ha_state("input_number.jacuzzi_k_mild", token) or 0.035)
    k_warm = float(ha_state("input_number.jacuzzi_k_warm", token) or 0.025)

    def k_for_ambient(amb):
        if amb < 5:
            return k_cold
        elif amb <= 15:
            return k_mild
        else:
            return k_warm

    # --- Fetch calendar events within 48h ---
    end_utc = now_utc + timedelta(hours=48)
    try:
        events = _fetch_calendar_events(
            "calendar.jacuzzi_schedule", now_utc, end_utc, token
        )
    except Exception as e:
        print(f"Banking: Calendar fetch failed ({e}). Clearing.")
        _clear_banking(token)
        return

    if not events:
        if banking_was_active:
            _log_banking_decision(
                "banking_cleared",
                "Banking cleared — no events within 48h",
                {"reason": "no_events", "water_temp": t_water},
                token,
            )
        _clear_banking(token)
        print("Banking: No events within 48h. Cleared.")
        return

    event = events[0]
    event_start = event["start"]
    hours_to_event = (event_start - now_utc).total_seconds() / 3600

    if hours_to_event < 1:
        if banking_was_active:
            _log_banking_decision(
                "banking_cleared",
                f"Banking cleared — event in <1h ({event['summary']})",
                {"reason": "event_imminent", "event": event["summary"],
                 "water_temp": t_water},
                token,
            )
        _clear_banking(token)
        print(f"Banking: Event in <1h ({event['summary']}). Cleared.")
        return

    # --- Fetch Met.no ambient temperature forecast ---
    try:
        metno_temps = fetch_metno_temps(lat, lon)
    except Exception as e:
        print(f"WARNING: Met.no temp fetch failed ({e}), using current ambient")
        metno_temps = {}

    # --- Fetch solar forecast from DB ---
    try:
        solar_fc = _fetch_solar_forecast_db(now_utc, event_start)
    except Exception as e:
        print(f"WARNING: Solar forecast DB read failed ({e})")
        solar_fc = {}

    # --- Build hourly timeline from now to event ---
    current_hour = now_utc.replace(minute=0, second=0, microsecond=0)
    timeline = []
    while current_hour < event_start:
        local = utc_to_local(current_hour.replace(tzinfo=timezone.utc))
        amb = metno_temps.get(current_hour, t_ambient)
        solar_w = solar_fc.get(current_hour, 0)
        # Convert 15-min Wh to hourly W equivalent
        if solar_w < 100:  # Likely Wh from 15-min slot, not W
            solar_w = solar_w * 4  # 15-min Wh -> hourly equivalent W
        is_solar = solar_w > SOLAR_THRESHOLD_W
        is_low = _is_low_tariff_hour(local)
        is_cheap = is_solar or is_low

        timeline.append({
            "utc": current_hour,
            "ambient": amb,
            "is_cheap": is_cheap,
            "is_solar": is_solar,
            "is_low_tariff": is_low,
            "solar_w": solar_w,
            "k": k_for_ambient(amb),
        })
        current_hour += timedelta(hours=1)

    if not timeline:
        if banking_was_active:
            _log_banking_decision(
                "banking_cleared",
                "Banking cleared — no hours to analyse",
                {"reason": "no_hours", "water_temp": t_water},
                token,
            )
        _clear_banking(token)
        print("Banking: No hours to analyse. Cleared.")
        return

    # --- Compute expected solar hours and gain ---
    solar_hours_list = [h for h in timeline if h["is_solar"]]
    expected_solar_hours = len(solar_hours_list)

    expected_solar_gain = 0.0
    if expected_solar_hours > 0:
        avg_amb_solar = sum(h["ambient"] for h in solar_hours_list) / expected_solar_hours
        avg_k_solar = sum(h["k"] for h in solar_hours_list) / expected_solar_hours
        delta = max(0, standby - avg_amb_solar)
        net_p = p_net - avg_k_solar * delta
        if net_p > 0:
            expected_solar_gain = (net_p / c_thermal) * expected_solar_hours

    # --- Build segments of consecutive cheap/expensive hours ---
    segments = []
    for h in timeline:
        if not segments or segments[-1][0] != h["is_cheap"]:
            segments.append((h["is_cheap"], [h]))
        else:
            segments[-1][1].append(h)

    # --- Backward induction: compute banking target ---
    t_required = min_standby
    target_per_cheap = {}

    for i in range(len(segments) - 1, -1, -1):
        is_cheap, hours = segments[i]
        if not is_cheap:
            for h in reversed(hours):
                amb = h["ambient"]
                k = h["k"]
                t_required = amb + (t_required - amb) * math.exp(k / c_thermal)
        else:
            target_per_cheap[i] = min(t_required, BANKING_CAP)
            t_required = standby

    banking_target = standby
    for i in range(len(segments)):
        if segments[i][0] and i in target_per_cheap:
            banking_target = target_per_cheap[i]
            break

    banking_target = min(BANKING_CAP, max(standby, banking_target))

    # --- Cost check ---
    if banking_target > standby + 0.5:
        first_cheap_idx = None
        for i in range(len(segments)):
            if segments[i][0]:
                first_cheap_idx = i
                break

        if first_cheap_idx is not None:
            expensive_hours = []
            for i in range(first_cheap_idx + 1, len(segments)):
                if not segments[i][0]:
                    expensive_hours = segments[i][1]
                    break

            if expensive_hours:
                gap_hours = len(expensive_hours)
                avg_amb = sum(h["ambient"] for h in expensive_hours) / gap_hours
                avg_k = sum(h["k"] for h in expensive_hours) / gap_hours

                cheap_hours = segments[first_cheap_idx][1]
                has_solar = any(h["is_solar"] for h in cheap_hours)
                cheap_rate = RATE_SOLAR if has_solar else RATE_LOW

                banking_energy = c_thermal * (banking_target - standby)
                banking_cost = banking_energy * cheap_rate

                decay = math.exp(-avg_k * gap_hours / c_thermal)
                t_end_bank = avg_amb + (banking_target - avg_amb) * decay
                t_end_standby = avg_amb + (standby - avg_amb) * decay
                preserved = max(0, t_end_bank - t_end_standby)

                alternative_cost = c_thermal * preserved * RATE_HIGH

                if banking_cost >= alternative_cost:
                    banking_target = standby
                    print(f"Banking: Cost check failed "
                          f"(bank={banking_cost:.2f} >= alt={alternative_cost:.2f} CHF). "
                          f"Skipping.")

    # --- Determine strategy ---
    if banking_target <= standby + 0.5:
        strategy = "none"
        banking_target = 0
    else:
        first_cheap_hours = []
        for is_cheap, hours in segments:
            if is_cheap:
                first_cheap_hours = hours
                break
        has_solar = any(h["is_solar"] for h in first_cheap_hours)
        has_low_tariff = any(h["is_low_tariff"] for h in first_cheap_hours)
        if has_solar and has_low_tariff:
            strategy = "combined"
        elif has_solar:
            strategy = "solar"
        else:
            strategy = "low_tariff"

    # --- Write results to HA ---
    ha_set("input_number.jacuzzi_banking_target_temp",
           round(banking_target, 1), token)
    ha_set("input_number.jacuzzi_expected_solar_hours",
           round(expected_solar_hours, 1), token)
    ha_set("input_number.jacuzzi_expected_solar_gain_c",
           round(expected_solar_gain, 1), token)
    ha_select_option("input_select.jacuzzi_banking_strategy",
                     strategy, token)

    tz_offset = get_tz_offset(now_utc.replace(tzinfo=timezone.utc))
    event_local = event_start + timedelta(hours=tz_offset)

    # --- Log banking decision ---
    if strategy != "none":
        code = f"banking_{strategy}"
        cheap_count = sum(1 for h in timeline if h["is_cheap"])
        expensive_count = len(timeline) - cheap_count
        _log_banking_decision(
            code,
            f"Banking target set to {banking_target:.1f}\u00b0C ({strategy})",
            {
                "event_time": event_local.strftime("%Y-%m-%d %H:%M"),
                "hours_to_event": round(hours_to_event, 1),
                "target_temp": round(banking_target, 1),
                "strategy": strategy,
                "water_temp": round(t_water, 1),
                "cheap_hours": cheap_count,
                "expensive_hours": expensive_count,
                "solar_hours": expected_solar_hours,
                "solar_gain_c": round(expected_solar_gain, 1),
            },
            token,
        )
    elif banking_was_active:
        _log_banking_decision(
            "banking_cleared",
            "Banking cleared \u2014 strategy is none",
            {"reason": "not_worthwhile", "water_temp": round(t_water, 1),
             "event_time": event_local.strftime("%Y-%m-%d %H:%M")},
            token,
        )

    print(f"Banking: target={banking_target:.1f}\u00b0C, strategy={strategy}, "
          f"solar={expected_solar_hours:.0f}h(+{expected_solar_gain:.1f}\u00b0C), "
          f"event={event_local.strftime('%a %H:%M')} ({hours_to_event:.1f}h), "
          f"water={t_water:.1f}\u00b0C, min_standby={min_standby:.1f}\u00b0C")


# =============================================================================
# Subcommand: plan (cost-optimal 48h supply planner)
# =============================================================================

def cmd_plan(token):
    """Generate 48-hour cost-optimal supply plan.

    Uses forward simulation with marginal cost comparison to schedule
    jacuzzi heating and EV charging across 192 slots (15-min each).
    """
    try:
        _cmd_plan_inner(token)
    except Exception as e:
        import traceback
        err = f"ERROR: {e}"
        print(err)
        traceback.print_exc()
        # Write error to HA so it's visible on dashboard
        ha_set("input_select.energy_plan_status", f"ERR: {str(e)[:200]}", token)


def _cmd_plan_inner(token):
    """Inner plan logic — wrapped by cmd_plan for error reporting."""
    lat, lon = get_location(token)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    tz_offset = get_tz_offset(now_utc.replace(tzinfo=timezone.utc))

    # Align to 15-min boundary
    minute_aligned = (now_utc.minute // INTERVAL_MIN) * INTERVAL_MIN
    plan_start = now_utc.replace(minute=minute_aligned, second=0, microsecond=0)
    plan_made_at = plan_start

    # --- Read current state from HA ---
    t_water = ha_attr("climate.jacuzzi", "current_temperature", token)
    t_water = float(t_water) if t_water is not None else 20.0

    # Use effective standby (solar-aware: 40°C during solar) not raw standby (20°C)
    standby = float(ha_state("sensor.jacuzzi_effective_standby_temp", token)
                    or ha_state("input_number.jacuzzi_standby_temp", token)
                    or JAC_DEFAULT_STANDBY)
    p_net = float(ha_state("input_number.jacuzzi_effective_power_kw", token) or JAC_DEFAULT_P_NET)
    c_thermal = float(ha_state("sensor.jacuzzi_thermal_capacity", token) or 3.72)
    t_ambient_now = float(ha_state("sensor.la_dole_temperature", token) or 10)

    # k values per ambient temperature band
    k_cold = float(ha_state("input_number.jacuzzi_k_cold", token) or 0.040)
    k_mild = float(ha_state("input_number.jacuzzi_k_mild", token) or 0.035)
    k_warm = float(ha_state("input_number.jacuzzi_k_warm", token) or 0.025)

    def k_for_ambient(amb):
        if amb < 5:
            return k_cold
        elif amb <= 15:
            return k_mild
        else:
            return k_warm

    # EV state
    horace_soc = float(ha_state("input_number.ev_horace_current_soc", token) or 50)
    horatio_soc = float(ha_state("input_number.ev_horatio_current_soc", token) or 50)
    horace_home = ha_state("device_tracker.horace_location", token) == "home"
    horatio_home = ha_state("device_tracker.horatio_location", token) == "home"
    horace_limit = float(ha_state("input_number.ev_horace_charge_limit", token) or 80)
    horatio_limit = float(ha_state("input_number.ev_horatio_charge_limit", token) or 80)
    plugged = ha_state("sensor.ev_plugged_vehicle", token)
    ev_min_soc = float(ha_state("input_number.ev_minimum_soc", token) or 50)
    buffer_target = float(ha_state("input_number.energy_ev_buffer_target_soc", token) or 80)

    ev_voltage = float(ha_state("input_number.ev_voltage", token) or EV_VOLTAGE)
    ev_phases = int(float(ha_state("input_number.ev_phases", token) or EV_PHASES))
    ev_min_amps = int(float(ha_state("input_number.ev_min_amps", token) or EV_MIN_AMPS))
    ev_max_amps = int(float(ha_state("input_number.ev_charger_max_amps", token) or EV_MAX_AMPS))

    # Determine which car to charge
    night_car = ha_state("input_select.ev_night_charge_car", token)
    charge_car = None
    charge_soc = 0
    charge_limit = 80
    if plugged in ("Horace", "Horatio"):
        charge_car = plugged
    elif horace_home and not horatio_home:
        charge_car = "Horace"
    elif horatio_home and not horace_home:
        charge_car = "Horatio"
    elif horace_home and horatio_home:
        # Prefer the car with lower SOC
        charge_car = "Horace" if horace_soc <= horatio_soc else "Horatio"
    if charge_car == "Horace":
        charge_soc = horace_soc
        charge_limit = min(horace_limit, buffer_target)
    elif charge_car == "Horatio":
        charge_soc = horatio_soc
        charge_limit = min(horatio_limit, buffer_target)

    # --- Fetch solar forecast (15-min) ---
    end_utc = plan_start + timedelta(hours=48)
    try:
        forecast_rows = _fetch_solar_forecast_15min(plan_start, end_utc)
    except Exception as e:
        print(f"WARNING: Solar forecast read failed ({e})")
        forecast_rows = []

    # Build forecast lookup: slot_start -> {forecast_wh, conf_low, ambient}
    forecast_lookup = {}
    for row in forecast_rows:
        forecast_lookup[row["target_slot"]] = {
            "forecast_wh": row["forecast_wh"],
            "conf_low": row.get("confidence_low_wh", row["forecast_wh"] * 0.7),
            "ambient": row.get("temp_ambient_forecast", 10),
        }

    # --- Fetch calendar events ---
    try:
        jac_events = _fetch_calendar_events(
            "calendar.jacuzzi_schedule", now_utc, end_utc, token
        )
    except Exception:
        jac_events = []

    # Map events to slot indices
    event_slots = set()
    for ev in jac_events:
        ev_start = ev["start"]
        # Mark the 6h window before event as "must be ready"
        for offset_min in range(0, 6 * 60, INTERVAL_MIN):
            slot_time = ev_start - timedelta(minutes=offset_min)
            if slot_time >= plan_start:
                idx = int((slot_time - plan_start).total_seconds() / (INTERVAL_MIN * 60))
                if 0 <= idx < SLOTS_48H:
                    event_slots.add(idx)

    # Event deadlines: latest slot by which jacuzzi must be at 40C
    event_deadlines = []
    for ev in jac_events:
        idx = int((ev["start"] - plan_start).total_seconds() / (INTERVAL_MIN * 60))
        if 0 <= idx < SLOTS_48H:
            event_deadlines.append(idx)

    # --- Fetch base load estimate ---
    base_load_w = 500  # default
    try:
        c = conn()
        cur = c.cursor()
        cur.execute(
            """SELECT AVG(base_load_w) FROM solar_actual_15min
               WHERE slot_start >= %s AND base_load_w > 0""",
            (now_utc - timedelta(hours=24),)
        )
        row = cur.fetchone()
        if row and row[0]:
            base_load_w = float(row[0])
        c.close()
    except Exception:
        pass

    # --- Build slot data ---
    slots = []
    for i in range(SLOTS_48H):
        slot_start = plan_start + timedelta(minutes=i * INTERVAL_MIN)
        slot_local = slot_start + timedelta(hours=tz_offset)

        fc = forecast_lookup.get(slot_start, {"forecast_wh": 0, "conf_low": 0, "ambient": 10})
        # Convert 15-min Wh to average W for the slot
        solar_w = fc["forecast_wh"] * (60 / INTERVAL_MIN)
        solar_conf_low_w = fc["conf_low"] * (60 / INTERVAL_MIN)
        ambient = fc["ambient"]
        tariff = _tariff_rate(slot_local)

        # Solar surplus = solar production - base load
        surplus_w = max(0, solar_w - base_load_w)

        slots.append({
            "start": slot_start,
            "local": slot_local,
            "solar_w": solar_w,
            "surplus_w": surplus_w,
            "solar_conf_low_w": solar_conf_low_w,
            "ambient": ambient,
            "tariff": tariff,
            "k": k_for_ambient(ambient),
            "is_high": tariff == RATE_HIGH,
        })

    # --- Precompute: cheapest future rate for each slot ---
    cheapest_future = [RATE_LOW] * SLOTS_48H
    min_future = RATE_LOW
    for i in range(SLOTS_48H - 1, -1, -1):
        min_future = min(min_future, slots[i]["tariff"])
        # Consider solar: if there's surplus, effective rate is RATE_SOLAR
        if slots[i]["surplus_w"] > 0:
            min_future = min(min_future, RATE_SOLAR)
        cheapest_future[i] = min_future

    # --- Forward simulation ---
    jac_temp = t_water
    ev_soc = charge_soc
    cost_total = 0.0
    total_solar_used = 0.0
    total_solar_produced = 0.0
    total_grid_draw = 0.0
    dt = INTERVAL_MIN / 60.0  # hours per slot (0.25)

    plan_rows = []

    for i in range(SLOTS_48H):
        s = slots[i]
        surplus = s["surplus_w"]
        tariff = s["tariff"]
        ambient = s["ambient"]
        k = s["k"]
        is_high = s["is_high"]

        # Determine if jacuzzi needs heating
        jac_needs_heat = False
        jac_must_heat = False

        # Check event deadlines
        nearest_deadline = None
        for d in event_deadlines:
            if d >= i:
                nearest_deadline = d
                break

        if nearest_deadline is not None:
            slots_to_deadline = nearest_deadline - i
            if jac_temp < 39.5:
                jac_needs_heat = True
                # Must heat if we can't defer
                if slots_to_deadline < 24:  # <6h to event
                    jac_must_heat = True

        # Jacuzzi below effective standby (40°C during solar, 20°C otherwise)
        if jac_temp < standby - 0.5:
            jac_needs_heat = True

        # SOLAR BANKING: Always heat with surplus — every kWh self-consumed
        # saves 0.20-0.32 CHF vs exporting and reimporting later.
        # The jacuzzi is a thermal battery.
        jac_can_bank = jac_temp < JAC_MAX_TEMP and surplus > 0

        if jac_can_bank:
            jac_needs_heat = True

        # EV needs charge — any plugged car below limit should charge with solar
        ev_needs_charge = (charge_car is not None
                           and ev_soc < charge_limit
                           and plugged in (charge_car, "Horace", "Horatio"))
        ev_must_charge = ev_soc < 10  # Safety: charge at any tariff

        # --- Evaluate 4 combinations ---
        combos = []
        # Allow heating whenever physically possible (below max temp)
        jac_kw = p_net if jac_temp < JAC_MAX_TEMP else 0

        for do_jac in [False, True]:
            if do_jac and jac_kw == 0:
                continue
            for do_ev in [False, True]:
                if do_ev and not ev_needs_charge:
                    continue

                # Calculate grid draw and cost for this combo
                load_w = 0
                ev_amps = 0
                if do_jac:
                    load_w += JAC_HEATER_KW * 1000

                if do_ev:
                    # Calculate EV amps based on remaining surplus
                    remaining_surplus = max(0, surplus - (JAC_HEATER_KW * 1000 if do_jac else 0))
                    # At least min_amps if charging
                    raw_amps = int(remaining_surplus / (ev_voltage * ev_phases))
                    ev_amps = max(ev_min_amps, min(ev_max_amps, raw_amps))
                    ev_charge_w = ev_amps * ev_voltage * ev_phases
                    load_w += ev_charge_w

                # Grid draw = load - available surplus (surplus already accounts for base load)
                solar_used = min(load_w, surplus)
                grid_draw = max(0, load_w - surplus)

                # Cost for this slot
                solar_cost = (solar_used / 1000) * RATE_SOLAR * dt
                grid_cost = (grid_draw / 1000) * tariff * dt
                slot_cost = solar_cost + grid_cost

                # Exported solar value (opportunity cost of not exporting)
                export_w = max(0, surplus - load_w)

                # Hard constraint checks
                valid = True

                # No voluntary pure-grid jacuzzi heating during peak
                # (unless solar blend >= 2250W or event within 2h)
                if do_jac and is_high and surplus < 2250:
                    if not jac_must_heat:
                        valid = False

                # EV min amps constraint
                if do_ev and ev_amps < ev_min_amps:
                    valid = False

                # Jacuzzi max temp
                if do_jac and jac_temp >= JAC_MAX_TEMP:
                    valid = False

                if not valid:
                    continue

                # Marginal value: self-consumption savings + deferred cost savings
                # Every kWh of solar used instead of exported saves
                # (future_import_rate - RATE_SOLAR) per kWh.
                marginal = 0

                # Self-consumption value: avoided export loss
                # Exporting 1 kWh earns RATE_SOLAR (0.06), but later we must
                # import at RATE_LOW (0.26+). Net loss = 0.20+ per kWh exported.
                self_consumption_value = (solar_used / 1000) * (RATE_LOW - RATE_SOLAR) * dt

                # Grid draw cost: any grid used now vs deferring to cheaper slot
                grid_penalty = 0
                if grid_draw > 0:
                    future_rate = cheapest_future[min(i + 1, SLOTS_48H - 1)]
                    grid_penalty = (grid_draw / 1000) * (tariff - future_rate) * dt

                marginal = self_consumption_value - grid_penalty

                # For event-critical loads, add urgency bonus
                if do_jac and jac_must_heat:
                    marginal += JAC_HEATER_KW * dt * 0.5  # strong preference

                if do_ev and ev_must_charge:
                    ev_kw = ev_amps * ev_voltage * ev_phases / 1000
                    marginal += ev_kw * dt * 0.5

                combos.append({
                    "do_jac": do_jac,
                    "do_ev": do_ev,
                    "ev_amps": ev_amps,
                    "slot_cost": slot_cost,
                    "grid_draw": grid_draw,
                    "solar_used": solar_used,
                    "export_w": export_w,
                    "marginal": marginal,
                })

        # If no valid combos, add "do nothing"
        if not combos:
            combos.append({
                "do_jac": False,
                "do_ev": False,
                "ev_amps": 0,
                "slot_cost": 0,
                "grid_draw": 0,
                "solar_used": 0,
                "export_w": surplus,
                "marginal": 0,
            })

        # Select best combination
        # Priority: must-heat constraints first, then minimize cost
        best = None
        if jac_must_heat:
            jac_combos = [c for c in combos if c["do_jac"]]
            if jac_combos:
                best = min(jac_combos, key=lambda c: c["slot_cost"])
        if ev_must_charge and best is None:
            ev_combos = [c for c in combos if c["do_ev"]]
            if ev_combos:
                best = min(ev_combos, key=lambda c: c["slot_cost"])

        if best is None:
            # Choose combo with highest marginal value (or lowest cost if all zero)
            positive_marginal = [c for c in combos if c["marginal"] > 0]
            if positive_marginal:
                best = max(positive_marginal, key=lambda c: c["marginal"])
            else:
                best = min(combos, key=lambda c: c["slot_cost"])

        # --- Update state ---
        if best["do_jac"]:
            # Newton's law heating
            T_eq = ambient + p_net / k
            jac_temp = T_eq - (T_eq - jac_temp) * math.exp(-k * dt / c_thermal)
            jac_temp = min(JAC_MAX_TEMP, jac_temp)
        else:
            # Newton's law cooling
            jac_temp = ambient + (jac_temp - ambient) * math.exp(-k * dt / c_thermal)

        if best["do_ev"] and best["ev_amps"] > 0:
            charge_kw = best["ev_amps"] * ev_voltage * ev_phases / 1000
            charge_kwh = charge_kw * dt
            soc_gain = charge_kwh / EV_BATTERY_KWH * 100
            ev_soc = min(charge_limit, ev_soc + soc_gain)

        cost_total += best["slot_cost"]
        total_solar_used += best["solar_used"] * dt / 1000  # kWh
        total_solar_produced += s["solar_w"] * dt / 1000
        total_grid_draw += best["grid_draw"] * dt / 1000

        self_consumption_pct = (
            (total_solar_used / total_solar_produced * 100)
            if total_solar_produced > 0 else 0
        )

        # Determine action label
        if best["do_jac"] and best["do_ev"]:
            action = "Jac+EV"
        elif best["do_jac"]:
            action = "Jac"
        elif best["do_ev"]:
            action = "EV"
        elif surplus > 0:
            action = "Export"
        else:
            action = "Idle"

        plan_rows.append({
            "slot_start": s["start"],
            "slot_index": i,
            "solar_forecast_w": round(s["solar_w"], 0),
            "tariff_rate": tariff,
            "ambient_temp_c": round(ambient, 1),
            "base_load_w": round(base_load_w, 0),
            "jacuzzi_action": "heat" if best["do_jac"] else "idle",
            "ev_action": "charge" if best["do_ev"] else "idle",
            "ev_car": charge_car if best["do_ev"] else None,
            "ev_amps": best["ev_amps"] if best["do_ev"] else 0,
            "jacuzzi_temp_expected": round(jac_temp, 1),
            "ev_soc_expected": round(ev_soc, 1),
            "grid_draw_w": round(best["grid_draw"], 0),
            "solar_used_w": round(best["solar_used"], 0),
            "solar_exported_w": round(best["export_w"], 0),
            "slot_cost_chf": round(best["slot_cost"], 4),
            "cumulative_cost_chf": round(cost_total, 4),
            "cumulative_self_consumption_pct": round(self_consumption_pct, 1),
            "action": action,
        })

    # --- Write plan to DB ---
    c = conn()
    cur = c.cursor()
    for row in plan_rows:
        cur.execute(
            """INSERT INTO supply_plan_schedule
               (plan_made_at, slot_start, slot_index,
                solar_forecast_w, tariff_rate, ambient_temp_c, base_load_w,
                jacuzzi_action, ev_action, ev_car, ev_amps,
                jacuzzi_temp_expected, ev_soc_expected,
                grid_draw_w, solar_used_w, solar_exported_w,
                slot_cost_chf, cumulative_cost_chf,
                cumulative_self_consumption_pct)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s, %s, %s)""",
            (plan_made_at, row["slot_start"], row["slot_index"],
             row["solar_forecast_w"], row["tariff_rate"],
             row["ambient_temp_c"], row["base_load_w"],
             row["jacuzzi_action"], row["ev_action"],
             row["ev_car"], row["ev_amps"],
             row["jacuzzi_temp_expected"], row["ev_soc_expected"],
             row["grid_draw_w"], row["solar_used_w"],
             row["solar_exported_w"],
             row["slot_cost_chf"], row["cumulative_cost_chf"],
             row["cumulative_self_consumption_pct"])
        )
    c.commit()
    c.close()

    # --- Write current slot action to HA helpers ---
    current = plan_rows[0] if plan_rows else None
    if current:
        ha_set("input_select.energy_plan_current_action",
               current["action"], token)
        ha_set("input_number.energy_plan_ev_amps",
               current["ev_amps"], token)
        ha_set("input_number.energy_plan_48h_cost_chf",
               round(cost_total, 2), token)

        # Self-consumption
        final_sc = plan_rows[-1]["cumulative_self_consumption_pct"] if plan_rows else 0
        ha_set("input_number.energy_plan_self_consumption",
               round(final_sc, 0), token)

        # Peak-tariff grid draw
        peak_grid_kwh = sum(
            r["grid_draw_w"] * dt / 1000
            for r in plan_rows if r["tariff_rate"] == RATE_HIGH
        )
        ha_set("input_number.energy_plan_grid_peak_kwh",
               round(peak_grid_kwh, 2), token)

        # Naive baseline cost (all at peak rate)
        total_load_kwh = sum(
            (r["solar_used_w"] + r["grid_draw_w"]) * dt / 1000
            for r in plan_rows
        )
        naive_cost = total_load_kwh * RATE_HIGH
        savings = max(0, naive_cost - cost_total)
        ha_set("input_number.energy_plan_48h_savings_chf",
               round(savings, 2), token)

        # Next change
        next_change = "No changes planned"
        for r in plan_rows[1:]:
            if r["action"] != current["action"]:
                delta_min = r["slot_index"] * INTERVAL_MIN
                local_time = r["slot_start"] + timedelta(hours=tz_offset)
                if delta_min <= 60:
                    next_change = f"{r['action']} in {delta_min}min"
                else:
                    next_change = f"{r['action']} at {local_time.strftime('%H:%M')}"
                break
        ha_set("input_select.energy_plan_next_change", next_change, token)

        # Status
        local_now = now_utc + timedelta(hours=tz_offset)
        timestamp = local_now.strftime("%H:%M %d/%m")
        status = f"OK {timestamp} ({SLOTS_48H} slots, {cost_total:.2f} CHF)"
        ha_set("input_select.energy_plan_status", status, token)

    # --- Log decision ---
    try:
        from log_to_db import log_decision
        jac_heat_slots = sum(1 for r in plan_rows if r["jacuzzi_action"] == "heat")
        ev_charge_slots = sum(1 for r in plan_rows if r["ev_action"] == "charge")
        log_decision("energy", "solar_forecast.py", "supply_plan",
                     f"Plan: {cost_total:.2f} CHF, jac={jac_heat_slots}x15min, "
                     f"ev={ev_charge_slots}x15min, sc={final_sc:.0f}%",
                     json.dumps({
                         "cost_chf": round(cost_total, 2),
                         "savings_chf": round(savings, 2),
                         "jac_heat_slots": jac_heat_slots,
                         "ev_charge_slots": ev_charge_slots,
                         "self_consumption_pct": round(final_sc, 0),
                         "peak_grid_kwh": round(peak_grid_kwh, 2),
                         "charge_car": charge_car,
                         "jac_final_temp": round(jac_temp, 1),
                         "ev_final_soc": round(ev_soc, 1),
                     }))
    except Exception:
        pass

    print(f"Plan: cost={cost_total:.2f}CHF, savings={savings:.2f}CHF, "
          f"sc={final_sc:.0f}%, peak_grid={peak_grid_kwh:.1f}kWh, "
          f"jac_final={jac_temp:.1f}\u00b0C, ev_final={ev_soc:.0f}%, "
          f"action={current['action'] if current else 'none'}")


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "forecast"

    if cmd == "init_db":
        cmd_init_db()
    else:
        token = get_token()
        if not token:
            print("ERROR: No HA API token available")
            sys.exit(1)

        if cmd == "forecast":
            cmd_forecast(token)
        elif cmd == "actual":
            cmd_actual(token)
        elif cmd == "compare":
            cmd_compare(token)
        elif cmd == "calibrate":
            cmd_calibrate(token)
        elif cmd == "banking":
            cmd_banking(token)
        elif cmd == "plan":
            cmd_plan(token)
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: solar_forecast.py [init_db|forecast|actual|compare|calibrate|banking|plan]")
            sys.exit(1)
