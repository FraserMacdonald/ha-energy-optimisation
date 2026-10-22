#!/usr/bin/env python3
"""Diagnostic: test cmd_plan dependencies and report via HA state API.

Read-only by default. cmd_plan() starts a planning cycle, so it only runs when
--run-plan is passed explicitly. Previously it ran on every invocation, which
meant a "diagnostic" could silently re-plan the house.
"""
import json
import os
import sys
import traceback
import urllib.request

TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
API = "http://localhost:8123/api"


def _secret(name):
    """Read a secret from the Home Assistant secrets.yaml.

    Credentials live in secrets.yaml, which is git-ignored, so they are never
    committed or published. A flat "key: value" parse is used so the script
    needs no YAML dependency.
    """
    import re
    for base in ("/config", "/homeassistant"):
        try:
            with open(os.path.join(base, "secrets.yaml")) as fh:
                for line in fh:
                    m = re.match(r"^\s*%s\s*:\s*(.+?)\s*$" % re.escape(name), line)
                    if not m:
                        continue
                    val = m.group(1).strip()
                    if len(val) > 1 and val[0] == val[-1] and val[0] in "'\"":
                        val = val[1:-1]
                    if val:
                        return val
        except OSError:
            continue
    raise SystemExit(
        "FATAL: secret '%s' not found (checked /config/secrets.yaml and "
        "/homeassistant/secrets.yaml)" % name
    )


DB = {
    "host": "core-mariadb",
    "port": 3306,
    "user": "homeassistant",
    "password": _secret("mariadb_password"),
    "database": "ha_analytics",
}


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
        with mysql.connector.connect(**DB) as c:
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
    except Exception as e:
        results.append(f"DB: {e}")

    # Report progress
    set_state("sensor.plan_diag", "db_done",
              {"detail": " | ".join(results)})

    # 4. Optionally run cmd_plan (side-effecting, opt-in only)
    if "--run-plan" not in sys.argv[1:]:
        results.append("plan: skipped (pass --run-plan to execute)")
    else:
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
