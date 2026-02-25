#!/usr/bin/env python3
"""Solar production forecast engine for HA energy optimization.

Subcommands:
  init_db    - Create database tables (run once)
  forecast   - Generate 48-hour solar forecast
  actual     - Log current SolarEdge production for the hour
  compare    - Compare forecasts against actuals, compute errors
  calibrate  - Weekly auto-calibration from clear-sky days
  banking    - Compute optimal jacuzzi thermal banking target

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

DEFAULT_CALIBRATION = 0.75


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


def get_calibration(token):
    """Get calibration factor from HA helper."""
    val = ha_state("input_number.energy_solar_calibration_factor", token)
    if val and val not in ("unknown", "unavailable"):
        return float(val)
    return DEFAULT_CALIBRATION


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


# =============================================================================
# Database operations
# =============================================================================

def cmd_init_db():
    """Create all forecast tables."""
    c = conn()
    cur = c.cursor()

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

    c.commit()
    c.close()
    print("Solar forecast tables created.")


# =============================================================================
# Subcommand: forecast
# =============================================================================

def cmd_forecast(token):
    """Generate 48-hour forecast, store in DB, update HA helpers."""
    lat, lon = get_location(token)
    calibration = get_calibration(token)

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    forecast_made_at = now_utc.replace(second=0, microsecond=0)

    # Fetch cloud forecast from Met.no
    cloud_data = {}
    try:
        cloud_data = fetch_metno_forecast(lat, lon)
    except Exception as e:
        print(f"WARNING: Met.no fetch failed ({e}), using clear-sky only")

    # Timezone for day boundaries
    tz_offset = get_tz_offset(now_utc.replace(tzinfo=timezone.utc))
    local_now = now_utc + timedelta(hours=tz_offset)
    today_date = local_now.date()
    tomorrow_date = today_date + timedelta(days=1)

    c = conn()
    cur = c.cursor()

    today_kwh = 0.0
    tomorrow_kwh = 0.0
    clear_sky_today_kwh = 0.0
    current_hour_w = 0.0
    next_hour_w = 0.0
    peak_w = 0.0
    peak_hour = 0
    current_cloud_pct = 0.0
    current_hour_utc = now_utc.replace(minute=0, second=0, microsecond=0)

    for h in range(48):
        target_hour_utc = current_hour_utc + timedelta(hours=h)
        target_local = target_hour_utc + timedelta(hours=tz_offset)

        # Calculate clear-sky at mid-hour
        mid_hour = target_hour_utc + timedelta(minutes=30)
        total_w, east_w, west_w, alt, az = clear_sky_power(mid_hour, lat, lon)

        clear_sky_wh = total_w  # W at mid-hour ~ average Wh for the hour
        east_clear_wh = east_w
        west_clear_wh = west_w

        # Cloud scaling
        cloud_pct = cloud_data.get(target_hour_utc, None)
        if cloud_pct is not None:
            cf = cloud_scaling(cloud_pct)
        else:
            cf = 1.0  # Clear-sky if no weather data
            cloud_pct = 0.0

        forecast_wh = clear_sky_wh * cf * calibration
        horizon_min = h * 60

        # Insert into DB
        cur.execute(
            """INSERT INTO solar_forecast_hourly
               (forecast_made_at, target_hour, horizon_minutes,
                solar_altitude, solar_azimuth, cloud_pct,
                clear_sky_wh, cloud_factor, forecast_wh,
                east_clear_sky_wh, west_clear_sky_wh, calibration_factor)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (forecast_made_at, target_hour_utc, horizon_min,
             round(alt, 2), round(az, 2), round(cloud_pct, 1),
             round(clear_sky_wh, 1), round(cf, 4), round(forecast_wh, 1),
             round(east_clear_wh, 1), round(west_clear_wh, 1), calibration)
        )

        # Aggregate for helpers
        target_date = target_local.date()
        if target_date == today_date:
            today_kwh += forecast_wh / 1000.0
            clear_sky_today_kwh += (clear_sky_wh * calibration) / 1000.0
        elif target_date == tomorrow_date:
            tomorrow_kwh += forecast_wh / 1000.0

        if h == 0:
            current_hour_w = forecast_wh
            current_cloud_pct = cloud_pct
        elif h == 1:
            next_hour_w = forecast_wh

        # Track peak for today
        if target_date == today_date and forecast_wh > peak_w:
            peak_w = forecast_wh
            peak_hour = target_local.hour

    c.commit()
    c.close()

    # Update HA helpers
    ha_set("input_number.energy_solar_forecast_today_kwh",
           round(today_kwh, 2), token)
    ha_set("input_number.energy_solar_forecast_tomorrow_kwh",
           round(tomorrow_kwh, 2), token)
    ha_set("input_number.energy_solar_forecast_current_hour_w",
           round(current_hour_w, 0), token)
    ha_set("input_number.energy_solar_forecast_next_hour_w",
           round(next_hour_w, 0), token)
    ha_set("input_number.energy_solar_forecast_peak_hour_w",
           round(peak_w, 0), token)
    ha_set("input_number.energy_solar_forecast_peak_hour",
           peak_hour, token)
    ha_set("input_number.energy_solar_forecast_clear_sky_today_kwh",
           round(clear_sky_today_kwh, 2), token)
    ha_set("input_number.energy_solar_forecast_cloud_pct",
           round(current_cloud_pct, 0), token)

    timestamp = local_now.strftime("%H:%M %d/%m")
    status = f"OK {timestamp} ({len(cloud_data)}h weather)"
    ha_set("input_select.energy_solar_forecast_last_run", status, token)

    print(f"Forecast: today={today_kwh:.1f}kWh, tomorrow={tomorrow_kwh:.1f}kWh, "
          f"peak={peak_w:.0f}W@{peak_hour}h, cloud={current_cloud_pct:.0f}%")


# =============================================================================
# Subcommand: actual
# =============================================================================

def cmd_actual(token):
    """Log current SolarEdge production for the current hour."""
    lat, lon = get_location(token)
    calibration = get_calibration(token)

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
    hour_start = now_utc.replace(minute=0, second=0, microsecond=0)

    # Infer cloud percentage from production vs clear-sky
    mid_hour = hour_start + timedelta(minutes=30)
    clear_w, _, _, alt, _ = clear_sky_power(mid_hour, lat, lon)
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

    # Energy for this 30-min sample
    energy_wh = power_w * 0.5

    c = conn()
    cur = c.cursor()
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
        (hour_start, energy_wh, power_w, actual_cloud_pct, temp_c,
         energy_wh, power_w, actual_cloud_pct, temp_c)
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
        """SELECT COALESCE(SUM(actual_wh), 0) FROM solar_actual_hourly
           WHERE hour_start >= %s AND hour_start < %s""",
        (today_start_utc, today_start_utc + timedelta(days=1))
    )
    today_wh = cur.fetchone()[0]
    c.close()

    ha_set("input_number.energy_solar_actual_today_kwh",
           round(today_wh / 1000, 2), token)

    print(f"Actual: {power_w:.0f}W, +{energy_wh:.0f}Wh, "
          f"today={today_wh / 1000:.2f}kWh")


# =============================================================================
# Subcommand: compare
# =============================================================================

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


def cmd_compare(token):
    """Compare forecast vintages against actuals, compute errors."""
    c = conn()
    cur = c.cursor(dictionary=True)

    # Find actual hours not yet compared (last 48 hours)
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now_utc - timedelta(hours=48)

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

    if not actuals:
        print("No new hours to compare.")
        c.close()
        return

    insert_count = 0
    for actual in actuals:
        hour_start = actual["hour_start"]
        actual_wh = actual["actual_wh"]
        actual_cloud = actual["actual_cloud_pct"]

        # Find all forecast vintages for this hour
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

            # Variance decomposition
            model_error = None
            weather_error = None
            if actual_cloud is not None and clear_sky_wh > 10:
                # What model predicts with actual cloud conditions
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
            insert_count += 1

    c.commit()

    # Update error helpers from recent comparisons
    _update_error_helpers(cur, token)

    c.close()
    print(f"Compared {len(actuals)} hours, {insert_count} rows inserted.")


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
        # 0% error = 100 score, 50%+ error = 0 score
        score = max(0, min(100, 100 - t0_err * 2))
        ha_set("input_number.energy_solar_forecast_quality_score",
               round(score, 0), token)

        # Quality rating
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


# =============================================================================
# Subcommand: calibrate
# =============================================================================

def cmd_calibrate(token):
    """Weekly auto-calibration from clear-sky days (last 90 days)."""
    lat, lon = get_location(token)
    calibration = get_calibration(token)

    c = conn()
    cur = c.cursor(dictionary=True)

    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now_utc - timedelta(days=90)

    # Find clear-sky days: avg cloud < 20% during daylight hours
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

    # For each clear day, compute ratio = actual / clear_sky_theoretical
    ratios = []
    for day_row in clear_days:
        day = day_row["day"]
        daily_actual_wh = day_row["daily_wh"]

        # Calculate clear-sky total for this day (theoretical, uncalibrated)
        tz_offset = get_tz_offset(
            datetime.combine(day, datetime.min.time()).replace(
                tzinfo=timezone.utc
            )
        )
        day_start_local = datetime.combine(day, datetime.min.time())
        day_start_utc = day_start_local - timedelta(hours=tz_offset)

        daily_clear_wh = 0
        for h in range(24):
            hour_utc = day_start_utc + timedelta(hours=h)
            mid = hour_utc + timedelta(minutes=30)
            cs_w, _, _, alt, _ = clear_sky_power(mid, lat, lon)
            if alt > 0:
                daily_clear_wh += cs_w

        if daily_clear_wh < 100:
            continue

        ratio = daily_actual_wh / daily_clear_wh
        ratios.append(ratio)

    if not ratios:
        print("No valid ratios computed. Skipping calibration.")
        c.close()
        return

    # Exponentially weighted mean (alpha=0.1, more weight to recent)
    alpha = 0.1
    ewm = ratios[0]
    for r in ratios[1:]:
        ewm = alpha * r + (1 - alpha) * ewm
    new_calibration = round(ewm, 4)

    # Clamp to reasonable range
    new_calibration = max(0.3, min(1.2, new_calibration))

    # Log the change
    cur.execute(
        """INSERT INTO solar_calibration_log
           (calibration_date, old_factor, new_factor,
            clear_days_used, avg_ratio)
           VALUES (%s, %s, %s, %s, %s)""",
        (now_utc, calibration, new_calibration,
         len(ratios), round(sum(ratios) / len(ratios), 4))
    )
    c.commit()
    c.close()

    # Update HA helper
    ha_set("input_number.energy_solar_calibration_factor",
           new_calibration, token)

    print(f"Calibration: {calibration:.4f} -> {new_calibration:.4f} "
          f"({len(ratios)} clear days, avg ratio={sum(ratios)/len(ratios):.4f})")


# =============================================================================
# Subcommand: banking
# =============================================================================

def _is_low_tariff_hour(local_dt):
    """Check if a local datetime falls in low tariff period.

    Schedule: Mon-Fri 17:00-22:00 = high; everything else = low.
    """
    dow = local_dt.weekday()
    hour = local_dt.hour
    is_high = dow in [0, 1, 2, 3, 4] and 17 <= hour < 22
    return not is_high


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
    """Read latest solar forecast vintage from DB.

    Returns dict of {datetime_utc_hour: forecast_wh}.
    """
    c = conn()
    cur = c.cursor(dictionary=True)
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


def _clear_banking(token):
    """Reset all banking helpers to inactive state."""
    ha_set("input_number.jacuzzi_banking_target_temp", 0, token)
    ha_set("input_number.jacuzzi_expected_solar_hours", 0, token)
    ha_set("input_number.jacuzzi_expected_solar_gain_c", 0, token)
    ha_select_option("input_select.jacuzzi_banking_strategy", "none", token)


def cmd_banking(token):
    """Compute optimal thermal banking target for jacuzzi.

    Uses calendar events, solar forecast, tariff schedule, and Met.no
    ambient forecast to determine the best temperature to pre-heat to
    during cheap energy periods.
    """
    BANKING_CAP = 37.0
    SOLAR_THRESHOLD_W = 6000
    RATE_HIGH = 0.38
    RATE_LOW = 0.26
    RATE_SOLAR = 0.06

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
        _clear_banking(token)
        print("Banking: No events within 48h. Cleared.")
        return

    event = events[0]
    event_start = event["start"]
    hours_to_event = (event_start - now_utc).total_seconds() / 3600

    if hours_to_event < 1:
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
    # Walk backward from event. For expensive hours, invert cooling to find
    # needed start temperature. For cheap segments, record the target and
    # reset (the cheap window can reheat).
    t_required = min_standby
    target_per_cheap = {}  # segment_index -> target_temp

    for i in range(len(segments) - 1, -1, -1):
        is_cheap, hours = segments[i]
        if not is_cheap:
            # Expensive: invert cooling for each hour (backward)
            for h in reversed(hours):
                amb = h["ambient"]
                k = h["k"]
                # T_start = T_amb + (T_end - T_amb) * e^(k/C)
                t_required = amb + (t_required - amb) * math.exp(k / c_thermal)
        else:
            # Cheap: this segment can heat to t_required
            target_per_cheap[i] = min(t_required, BANKING_CAP)
            # Earlier segments only need to deliver standby
            t_required = standby

    # Find the first (current or next) cheap segment's target
    banking_target = standby
    for i in range(len(segments)):
        if segments[i][0] and i in target_per_cheap:
            banking_target = target_per_cheap[i]
            break

    # Floor at standby, cap at BANKING_CAP
    banking_target = min(BANKING_CAP, max(standby, banking_target))

    # --- Cost check: is banking worth it? ---
    if banking_target > standby + 0.5:
        # Find the expensive gap after the first cheap segment
        first_cheap_idx = None
        for i in range(len(segments)):
            if segments[i][0]:
                first_cheap_idx = i
                break

        if first_cheap_idx is not None:
            # Find the following expensive gap
            expensive_hours = []
            for i in range(first_cheap_idx + 1, len(segments)):
                if not segments[i][0]:
                    expensive_hours = segments[i][1]
                    break

            if expensive_hours:
                gap_hours = len(expensive_hours)
                avg_amb = sum(h["ambient"] for h in expensive_hours) / gap_hours
                avg_k = sum(h["k"] for h in expensive_hours) / gap_hours

                # Cheapest rate in current cheap window
                cheap_hours = segments[first_cheap_idx][1]
                has_solar = any(h["is_solar"] for h in cheap_hours)
                cheap_rate = RATE_SOLAR if has_solar else RATE_LOW

                # Cost of banking energy
                banking_energy = c_thermal * (banking_target - standby)
                banking_cost = banking_energy * cheap_rate

                # Temperature preserved after cooling through expensive gap
                decay = math.exp(-avg_k * gap_hours / c_thermal)
                t_end_bank = avg_amb + (banking_target - avg_amb) * decay
                t_end_standby = avg_amb + (standby - avg_amb) * decay
                preserved = max(0, t_end_bank - t_end_standby)

                # Value of preserved temp at high tariff
                alternative_cost = c_thermal * preserved * RATE_HIGH

                if banking_cost >= alternative_cost:
                    banking_target = standby
                    print(f"Banking: Cost check failed "
                          f"(bank={banking_cost:.2f} >= alt={alternative_cost:.2f} CHF). "
                          f"Skipping.")

    # --- Determine strategy ---
    if banking_target <= standby + 0.5:
        strategy = "none"
        banking_target = 0  # Signal no active banking
    else:
        # Determine from what's available in the current cheap window
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

    print(f"Banking: target={banking_target:.1f}°C, strategy={strategy}, "
          f"solar={expected_solar_hours:.0f}h(+{expected_solar_gain:.1f}°C), "
          f"event={event_local.strftime('%a %H:%M')} ({hours_to_event:.1f}h), "
          f"water={t_water:.1f}°C, min_standby={min_standby:.1f}°C")


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
        else:
            print(f"Unknown command: {cmd}")
            print("Usage: solar_forecast.py [init_db|forecast|actual|compare|calibrate|banking]")
            sys.exit(1)
