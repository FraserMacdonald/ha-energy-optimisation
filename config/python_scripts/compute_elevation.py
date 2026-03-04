#!/usr/bin/env python3
"""Compute elevation-adjusted energy for all trip legs.
Reads all data from HA API, queries Google Elevation.
Writes results to /config/python_scripts/elevation_results.json"""
import json
import os
import urllib.request

def get_token():
    """Get HA API token."""
    try:
        with open('/config/python_scripts/.ha_token', 'r') as f:
            t = f.read().strip()
            if t:
                return t
    except Exception:
        pass
    return os.environ.get("SUPERVISOR_TOKEN", "")

def ha_state(entity_id, token):
    """Get entity state from HA API."""
    try:
        url = f"http://localhost:8123/api/states/{entity_id}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        return data.get("state", "")
    except:
        return ""

def ha_attr(entity_id, attr, token):
    """Get entity attribute from HA API."""
    try:
        url = f"http://localhost:8123/api/states/{entity_id}"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        return data.get("attributes", {}).get(attr, None)
    except:
        return None

def ha_set(entity_id, value, token):
    """Set HA entity value via API."""
    try:
        if entity_id.startswith("input_number."):
            url = "http://localhost:8123/api/services/input_number/set_value"
            payload = {"entity_id": entity_id, "value": float(value)}
        elif entity_id.startswith("input_select."):
            url = "http://localhost:8123/api/services/input_select/set_options"
            payload = {"entity_id": entity_id, "options": [str(value)[:255]]}
        else:
            return False
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, method='POST')
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        urllib.request.urlopen(req, timeout=5)
        return True
    except:
        return False

def get_api_key():
    """Read Google API key from secrets.yaml."""
    try:
        with open('/config/secrets.yaml', 'r') as f:
            for line in f:
                if line.strip().startswith('google_elevation_api_key:'):
                    return line.split(':', 1)[1].strip().strip('"').strip("'")
    except:
        pass
    return None

def geocode(address, api_key):
    """Convert address to lat,lon."""
    encoded = urllib.request.quote(address)
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded}&key={api_key}"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return f"{loc['lat']},{loc['lng']}"
    except:
        pass
    return None

def get_elevation(origin, destination, api_key):
    """Get elevation gain and loss between two points."""
    path = f"{origin}|{destination}"
    url = (
        f"https://maps.googleapis.com/maps/api/elevation/json"
        f"?path={path}&samples=20&key={api_key}"
    )
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read().decode())
        if data.get("status") != "OK" or len(data.get("results", [])) < 2:
            return 0, 0
        elevations = [r["elevation"] for r in data["results"]]
        gain = 0
        loss = 0
        for i in range(1, len(elevations)):
            diff = elevations[i] - elevations[i - 1]
            if diff > 0:
                gain += diff
            else:
                loss += abs(diff)
        return round(gain, 1), round(loss, 1)
    except:
        return 0, 0

def compute_energy(dist_km, elev_gain, elev_loss, temp_c, whkm_base, batt_kwh, correction_factor):
    """Compute total energy used for a leg in kWh."""
    base_kwh = dist_km * whkm_base / 1000
    car_mass_t = 2.1 if batt_kwh <= 75 else 2.4
    climb_kwh = elev_gain * 3.5 * car_mass_t / 1000
    regen_kwh = elev_loss * 3.5 * car_mass_t / 1000 * 0.25
    
    # Temperature factor based on real-world Tesla data
    # Includes cabin heating overhead for short trips (<30km)
    if temp_c >= 20:
        temp_factor = 1.0
    elif temp_c >= 10:
        temp_factor = 1.0 + (20 - temp_c) * 0.01      # 10C = 1.10
    elif temp_c >= 0:
        temp_factor = 1.10 + (10 - temp_c) * 0.015     # 0C = 1.25
    elif temp_c >= -10:
        temp_factor = 1.25 + abs(temp_c) * 0.025        # -10C = 1.50
    else:
        temp_factor = 1.50 + (abs(temp_c) - 10) * 0.02  # -20C = 1.70
    
    # Short trip penalty: cabin/battery heating is a fixed overhead
    # that hurts more on shorter trips
    if dist_km < 30:
        heating_kwh = max(0, (20 - temp_c) * 0.05)  # ~1kWh at 0C, ~2kWh at -20C
        base_kwh += heating_kwh
    
    energy_kwh = (base_kwh + climb_kwh - regen_kwh) * temp_factor * correction_factor
    energy_kwh = max(0, energy_kwh)
    soc_drop = energy_kwh / batt_kwh * 100
    
    return round(energy_kwh, 2), round(soc_drop, 1)

def parse_ha_json(raw):
    """Parse JSON that HA stores with single quotes."""
    if not raw or raw in ['', 'unknown', 'unavailable']:
        return []
    try:
        fixed = raw.replace("'", '"').replace("True", "true").replace("False", "false").replace("None", "null")
        return json.loads(fixed)
    except:
        return []

def main():
    token = get_token()
    api_key = get_api_key()
    
    if not api_key:
        print(json.dumps({"error": "No API key"}))
        return
    
    if not token:
        print(json.dumps({"error": "No HA token"}))
        return
    
    # Get home coordinates
    home_lat = ha_attr("zone.home", "latitude", token)
    home_lon = ha_attr("zone.home", "longitude", token)
    home_coords = f"{home_lat},{home_lon}" if home_lat and home_lon else None
    
    if not home_coords:
        print(json.dumps({"error": "No home coordinates"}))
        return
    
    # Get temperature
    temp_str = ha_state("sensor.horace_outside_temperature", token)
    try:
        temp_c = float(temp_str)
    except:
        temp_c = 10
    
    # Get car assignments
    fraser_car = ha_state("input_select.ev_fraser_assigned_car", token)
    heather_car = ha_state("input_select.ev_heather_assigned_car", token)
    
    # Get correction factors
    try:
        horace_factor = float(ha_state("input_number.ev_horace_consumption_factor", token))
    except:
        horace_factor = 1.0
    try:
        horatio_factor = float(ha_state("input_number.ev_horatio_consumption_factor", token))
    except:
        horatio_factor = 1.0
    
    # Battery specs
    specs = {
        "Horace": {"batt_kwh": 70, "whkm": 180, "factor": horace_factor},
        "Horatio": {"batt_kwh": 90, "whkm": 215, "factor": horatio_factor}
    }
    
    # Get trip data
    fraser_legs_raw = ha_state("input_select.ev_fraser_trip_legs_json", token)
    heather_legs_raw = ha_state("input_select.ev_heather_trip_legs_json", token)
    fraser_stops_raw = ha_state("input_select.ev_fraser_stops_json", token)
    heather_stops_raw = ha_state("input_select.ev_heather_stops_json", token)
    
    results = {"temp_c": temp_c, "home": home_coords}
    total_fraser_soc = 0
    total_heather_soc = 0
    
    for driver, car, legs_raw, stops_raw in [
        ("fraser", fraser_car, fraser_legs_raw, fraser_stops_raw),
        ("heather", heather_car, heather_legs_raw, heather_stops_raw)
    ]:
        if car not in specs:
            results[driver] = []
            continue
        
        legs = parse_ha_json(legs_raw)
        stops = parse_ha_json(stops_raw)
        
        if not legs:
            results[driver] = []
            continue
        
        spec = specs[car]
        
        # Build coordinate list: home, stop1, stop2, ..., home
        locations = [home_coords]
        for stop in stops:
            loc_str = stop.get("l", "")
            if loc_str:
                coords = geocode(loc_str, api_key)
                locations.append(coords if coords else None)
            else:
                locations.append(None)
        locations.append(home_coords)
        
        leg_results = []
        total_gain = 0
        total_loss = 0
        total_km = 0
        
        for i, leg in enumerate(legs):
            dist_km = float(leg.get("km", 0))
            
            if i < len(locations) - 1 and locations[i] and locations[i + 1]:
                gain, loss = get_elevation(locations[i], locations[i + 1], api_key)
            else:
                gain, loss = 0, 0
            
            total_gain += gain
            total_loss += loss
            total_km += dist_km
            
            leg_results.append({
                "leg": leg.get("l", i),
                "dist_km": dist_km,
                "elevation_gain": gain,
                "elevation_loss": loss
            })
        
        # Calculate SOC drop for BOTH cars
        soc_horace = compute_energy(total_km, total_gain, total_loss, temp_c, 180, 70, horace_factor)
        soc_horatio = compute_energy(total_km, total_gain, total_loss, temp_c, 215, 90, horatio_factor)
        
        results[driver] = {
            "legs": leg_results,
            "total_km": round(total_km, 1),
            "total_gain": round(total_gain, 1),
            "total_loss": round(total_loss, 1),
            "soc_drop_horace": soc_horace[1],
            "soc_drop_horatio": soc_horatio[1]
        }
    
    # Write results to file
    with open('/config/python_scripts/elevation_results.json', 'w') as f:
        json.dump(results, f, indent=2)
    
    # Write all SOC drop combinations to HA
    for driver in ["fraser", "heather"]:
        driver_data = results.get(driver, {})
        if isinstance(driver_data, dict) and driver_data:
            ha_set(f"input_number.ev_{driver}_soc_drop_horace", driver_data.get("soc_drop_horace", 0), token)
            ha_set(f"input_number.ev_{driver}_soc_drop_horatio", driver_data.get("soc_drop_horatio", 0), token)
            # Also set the assigned car value
            car_entity = fraser_car if driver == "fraser" else heather_car
            if car_entity == "Horace":
                soc = driver_data.get("soc_drop_horace", 0)
            elif car_entity == "Horatio":
                soc = driver_data.get("soc_drop_horatio", 0)
            else:
                soc = 0
            ha_set(f"input_number.ev_{driver}_elevation_soc_drop", soc, token)
    
    # Write summary
    fraser_data = results.get("fraser", {})
    heather_data = results.get("heather", {})
    f_soc = fraser_data.get(f"soc_drop_{fraser_car.lower()}", 0) if isinstance(fraser_data, dict) else 0
    h_soc = heather_data.get(f"soc_drop_{heather_car.lower()}", 0) if isinstance(heather_data, dict) else 0
    summary = f"Fraser:{f_soc}%({temp_c}C) Heather:{h_soc}%"
    ha_set("input_select.ev_elevation_summary", summary, token)
    
    # Write total SOC drops back to HA helpers
    ha_set("input_number.ev_fraser_elevation_soc_drop", total_fraser_soc, token)
    ha_set("input_number.ev_heather_elevation_soc_drop", total_heather_soc, token)
    
    # Write summary to HA
    summary = f"Fraser: {total_fraser_soc}% ({temp_c}C), Heather: {total_heather_soc}%"
    ha_set("input_select.ev_elevation_summary", summary, token)
    
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()