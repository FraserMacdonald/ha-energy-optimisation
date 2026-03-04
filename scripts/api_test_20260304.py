#!/usr/bin/env python3
"""One-time API diagnostic - tests SUPERVISOR_TOKEN and API access."""
import json
import os
import urllib.request

results = []

# 1. Token
token = os.environ.get("SUPERVISOR_TOKEN", "")
results.append(f"token_len={len(token)}")
results.append(f"token_start={token[:10]}..." if token else "NO_TOKEN")

# 2. Check .ha_token file
try:
    with open("/config/python_scripts/.ha_token") as f:
        ha_token = f.read().strip()
    results.append(f"ha_token_exists=yes,len={len(ha_token)}")
except FileNotFoundError:
    results.append("ha_token_exists=no")
except Exception as e:
    results.append(f"ha_token_err={e}")

# 3. Try supervisor API with SUPERVISOR_TOKEN
if token:
    try:
        url = "http://supervisor/core/api/"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        resp = urllib.request.urlopen(req, timeout=5)
        data = resp.read().decode()
        results.append(f"supervisor_api=OK({resp.status})")
    except Exception as e:
        results.append(f"supervisor_api=FAIL({e})")

# 4. Try localhost API with SUPERVISOR_TOKEN
if token:
    try:
        url = "http://localhost:8123/api/"
        req = urllib.request.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        resp = urllib.request.urlopen(req, timeout=5)
        data = resp.read().decode()
        results.append(f"localhost_api=OK({resp.status})")
    except Exception as e:
        results.append(f"localhost_api=FAIL({e})")

# 5. Try to write a state using supervisor API
if token:
    try:
        payload = json.dumps({
            "state": "diag_ok",
            "attributes": {"detail": " | ".join(results)}
        }).encode()
        url = "http://supervisor/core/api/states/sensor.api_test"
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=5)
        results.append(f"write_state=OK({resp.status})")
    except Exception as e:
        results.append(f"write_state=FAIL({e})")

# 6. Try to write a state using localhost API
if token:
    try:
        payload = json.dumps({
            "state": "diag_ok",
            "attributes": {"detail": " | ".join(results), "via": "localhost"}
        }).encode()
        url = "http://localhost:8123/api/states/sensor.api_test_local"
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        resp = urllib.request.urlopen(req, timeout=5)
        results.append(f"write_local=OK({resp.status})")
    except Exception as e:
        results.append(f"write_local=FAIL({e})")

# Write output to a file as backup
output = "\n".join(results)
with open("/config/api_test_output.txt", "w") as f:
    f.write(output)

print(output)
