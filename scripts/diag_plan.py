#!/usr/bin/env python3
"""Diagnostic: test cmd_plan dependencies and report via HA state API."""
import json
import os
import sys
import traceback
import urllib.request

TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
API = "http://supervisor/core/api"


def set_state(entity_id, state, attrs=None):
    """Set an entity state directly via the REST API."""
    payload = {"state": str(state)[:255]}
    if attrs:
        payload["attributes"] = attrs
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{API}/states/{entity_id}",
        data=data, method="POST"
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"set_state failed: {e}")


def main():
    results = []

    # 0. Immediately report that we started
    set_state("sensor.plan_diag", "running", {"detail": "started"})

    # 1. Check token
    results.append(f"Token: {'yes' if TOKEN else 'NO TOKEN'}")

    # 2. Check solar_forecast.py exists and has cmd_plan
    try:
        path = "/config/scripts/solar_forecast.py"
        with open(path) as f:
            content = f.read()
        results.append(f"sf.py: {len(content)} chars")
        has_inner = "def _cmd_plan_inner" in content
        has_error_wrapper = "ERR:" in content
        results.append(f"inner: {has_inner}, errwrap: {has_error_wrapper}")
    except Exception as e:
        results.append(f"sf.py READ: {e}")

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
        results.append(f"tables: {len(tables)}")

        has_plan = "supply_plan_schedule" in tables
        has_fc = "solar_forecast_15min" in tables
        results.append(f"plan_tbl: {has_plan}, fc_tbl: {has_fc}")

        if has_fc:
            cur.execute("SELECT COUNT(*) FROM solar_forecast_15min")
            cnt = cur.fetchone()[0]
            results.append(f"fc_rows: {cnt}")

        c.close()
    except Exception as e:
        results.append(f"DB: {e}")

    # Report progress
    set_state("sensor.plan_diag", "db_done",
              {"detail": " | ".join(results)})

    # 4. Try running cmd_plan
    try:
        sys.path.insert(0, "/config/scripts")
        from solar_forecast import cmd_plan, get_token
        token = get_token()
        results.append(f"token: {'ok' if token else 'FAIL'}")
        if token:
            cmd_plan(token)
            results.append("plan: OK")
    except Exception as e:
        results.append(f"plan: {e}")
        tb = traceback.format_exc()
        results.append(tb[-300:])

    # 5. Check plan status after run
    try:
        req = urllib.request.Request(
            f"{API}/states/input_select.energy_plan_status"
        )
        req.add_header("Authorization", f"Bearer {TOKEN}")
        resp = urllib.request.urlopen(req, timeout=5)
        state = json.loads(resp.read())["state"]
        results.append(f"status: {state}")
    except Exception as e:
        results.append(f"status_read: {e}")

    msg = " | ".join(results)
    set_state("sensor.plan_diag", "done",
              {"detail": msg[:2000]})
    print(msg)


if __name__ == "__main__":
    main()
