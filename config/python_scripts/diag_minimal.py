#!/usr/bin/env python3
"""Minimal diagnostic - writes to file and tries to set HA state."""
import json
import os
import urllib.request

results = []

# 1. Token check
token = os.environ.get("SUPERVISOR_TOKEN", "")
results.append(f"token_len={len(token)}")

# 2. Check if scripts/ directory was deployed
scripts_dir = "/config/scripts"
try:
    files = os.listdir(scripts_dir)
    results.append(f"scripts_dir={len(files)} files")
    sf = os.path.getsize(f"{scripts_dir}/solar_forecast.py")
    results.append(f"solar_forecast.py={sf} bytes")
except Exception as e:
    results.append(f"scripts_dir=ERR:{e}")

# 3. Check deploy_zip.py exists
try:
    sz = os.path.getsize("/config/python_scripts/deploy_zip.py")
    results.append(f"deploy_zip.py={sz} bytes")
except Exception as e:
    results.append(f"deploy_zip.py=ERR:{e}")

# 4. Try supervisor API
if token:
    try:
        req = urllib.request.Request("http://localhost:8123/api/")
        req.add_header("Authorization", f"Bearer {token}")
        resp = urllib.request.urlopen(req, timeout=5)
        results.append(f"supervisor_api=OK({resp.status})")
    except Exception as e:
        results.append(f"supervisor_api=FAIL({e})")

    # 5. Try localhost API
    try:
        req = urllib.request.Request("http://localhost:8123/api/")
        req.add_header("Authorization", f"Bearer {token}")
        resp = urllib.request.urlopen(req, timeout=5)
        results.append(f"localhost_api=OK({resp.status})")
    except Exception as e:
        results.append(f"localhost_api=FAIL({e})")

    # 6. Try to write a state via supervisor
    try:
        payload = json.dumps({
            "state": "diag_ok",
            "attributes": {"detail": " | ".join(results)}
        }).encode()
        req = urllib.request.Request(
            "http://localhost:8123/api/states/sensor.diag_minimal",
            data=payload, method="POST"
        )
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=5)
        results.append(f"set_state=OK({resp.status})")
    except Exception as e:
        results.append(f"set_state=FAIL({e})")

# 7. Write to file as backup
output = "\n".join(results)
with open("/config/diag_output.txt", "w") as f:
    f.write(output)
print(output)
