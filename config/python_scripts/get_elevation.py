#!/usr/bin/env python3
"""Get elevation data between two points.
Reads origin/destination from /config/scripts/elevation_query.json
Results written to /config/scripts/elevation_result.json

Can also be called with command line args for testing:
  python3 get_elevation.py lat1,lon1 lat2,lon2 api_key
"""
import sys
import json
import urllib.request

def main():
    if len(sys.argv) == 4:
        origin = sys.argv[1]
        destination = sys.argv[2]
        api_key = sys.argv[3]
    else:
        try:
            with open('/config/scripts/elevation_query.json', 'r') as f:
                query = json.load(f)
            origin = query['origin']
            destination = query['destination']
            api_key = query['key']
        except Exception as e:
            print(json.dumps({"elevation_gain": 0, "elevation_loss": 0, "error": str(e)}))
            sys.exit(1)

    path = f"{origin}|{destination}"
    samples = 20
    url = (
        f"https://maps.googleapis.com/maps/api/elevation/json"
        f"?path={path}&samples={samples}&key={api_key}"
    )

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "OK" or len(data.get("results", [])) < 2:
            result = {
                "elevation_gain": 0,
                "elevation_loss": 0,
                "error": data.get("status", "unknown")
            }
        else:
            elevations = [r["elevation"] for r in data["results"]]
            total_gain = 0
            total_loss = 0

            for i in range(1, len(elevations)):
                diff = elevations[i] - elevations[i - 1]
                if diff > 0:
                    total_gain += diff
                else:
                    total_loss += abs(diff)

            result = {
                "elevation_start": round(elevations[0], 1),
                "elevation_end": round(elevations[-1], 1),
                "elevation_gain": round(total_gain, 1),
                "elevation_loss": round(total_loss, 1),
                "samples": len(elevations)
            }

        with open('/config/scripts/elevation_result.json', 'w') as f:
            json.dump(result, f)
        print(json.dumps(result))

    except Exception as e:
        result = {"elevation_gain": 0, "elevation_loss": 0, "error": str(e)}
        with open('/config/scripts/elevation_result.json', 'w') as f:
            json.dump(result, f)
        print(json.dumps(result))

if __name__ == "__main__":
    main()