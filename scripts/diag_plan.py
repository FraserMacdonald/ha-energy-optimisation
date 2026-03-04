#!/usr/bin/env python3
"""Diagnostic: test cmd_plan dependencies and report via HA notification."""
import json
import os
import sys
import traceback
import urllib.request

TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
API = "http://supervisor/core/api"


def notify(msg):
    """Send persistent notification to HA."""
    payload = {
        "title": "Plan Diagnostic",
        "message": msg[:2000],
        "notification_id": "plan_diag",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API}/services/persistent_notification/create",
        data=data, method="POST"
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Notification failed: {e}")


def main():
    results = []

    # 1. Check token
    results.append(f"Token: {'yes' if TOKEN else 'NO TOKEN'}")

    # 2. Check solar_forecast.py exists and has cmd_plan
    try:
        path = "/config/scripts/solar_forecast.py"
        with open(path) as f:
            content = f.read()
        results.append(f"solar_forecast.py: {len(content)} chars")
        has_cmd_plan = "def cmd_plan" in content
        has_inner = "def _cmd_plan_inner" in content
        has_error_wrapper = "ERR:" in content
        results.append(f"cmd_plan: {has_cmd_plan}, inner: {has_inner}, errwrap: {has_error_wrapper}")
    except Exception as e:
        results.append(f"solar_forecast.py READ FAILED: {e}")

    # 3. Check DB connection
    try:
        import mysql.connector
        c = mysql.connector.connect(
            host="core-mariadb", user="homeassistant",
            password="homeassistant", database="ha_analytics"
        )
        cur = c.cursor()
        cur.execute("SHOW TABLES")
        tables = [r[0] for r in cur.fetchall()]
        results.append(f"DB tables: {', '.join(tables)}")

        # Check if supply_plan_schedule exists
        if "supply_plan_schedule" in tables:
            cur.execute("SELECT COUNT(*) FROM supply_plan_schedule")
            cnt = cur.fetchone()[0]
            results.append(f"supply_plan_schedule: {cnt} rows")
        else:
            results.append("supply_plan_schedule: MISSING")

        # Check solar_forecast_15min
        if "solar_forecast_15min" in tables:
            cur.execute("SELECT COUNT(*) FROM solar_forecast_15min")
            cnt = cur.fetchone()[0]
            results.append(f"solar_forecast_15min: {cnt} rows")
        else:
            results.append("solar_forecast_15min: MISSING")

        c.close()
    except Exception as e:
        results.append(f"DB FAILED: {e}")

    # 4. Try running cmd_plan
    try:
        sys.path.insert(0, "/config/scripts")
        from solar_forecast import cmd_plan, get_token
        token = get_token()
        results.append(f"get_token: {'ok' if token else 'FAILED'}")
        if token:
            cmd_plan(token)
            results.append("cmd_plan: COMPLETED")
    except Exception as e:
        results.append(f"cmd_plan FAILED: {e}")
        results.append(traceback.format_exc()[-500:])

    # 5. Check plan status after run
    try:
        req = urllib.request.Request(
            f"{API}/states/input_select.energy_plan_status"
        )
        req.add_header("Authorization", f"Bearer {TOKEN}")
        resp = urllib.request.urlopen(req, timeout=5)
        state = json.loads(resp.read())["state"]
        results.append(f"plan_status after: {state}")
    except Exception as e:
        results.append(f"status read failed: {e}")

    msg = "\n".join(results)
    print(msg)
    notify(msg)


if __name__ == "__main__":
    main()
