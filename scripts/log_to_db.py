#!/usr/bin/env python3
import sys, os
from datetime import datetime, date

# Fail loudly rather than at runtime. The previous version attempted a runtime
# `pip install mysql-connector-python` on ImportError; when that failed it died
# with no traceback, which surfaced in Home Assistant as
# "return code: 1 / NoneType: None" and made the fault undiagnosable.
import mysql.connector

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

def conn():
    return mysql.connector.connect(**DB)

def log_decision(system, aid, code, text, ctx):
    c = conn()
    cur = c.cursor()
    cur.execute(
        "INSERT INTO log_decisions (system,automation_id,decision_code,decision_text,context) VALUES (%s,%s,%s,%s,%s)",
        (system, aid, code, text, ctx)
    )
    c.commit()
    c.close()

def log_action(system, atype, target, params):
    c = conn()
    cur = c.cursor()
    cur.execute(
        "INSERT INTO log_actions (system,action_type,target_entity,parameters) VALUES (%s,%s,%s,%s)",
        (system, atype, target, params)
    )
    c.commit()
    c.close()

def log_feedback(system, metric, predicted, actual, ctx):
    p = float(predicted or 0)
    a = float(actual or 0)
    err = ((a - p) / p * 100) if p != 0 else 0
    c = conn()
    cur = c.cursor()
    cur.execute(
        "INSERT INTO log_feedback (system,metric,predicted,actual,error_pct,context) VALUES (%s,%s,%s,%s,%s,%s)",
        (system, metric, p, a, round(err, 2), ctx)
    )
    c.commit()
    c.close()

def log_cost(system, s, gl, gh):
    s = float(s or 0)
    gl = float(gl or 0)
    gh = float(gh or 0)
    cost = gl * 0.22 + gh * 0.49
    base = (s + gl + gh) * 0.49
    save = base - cost
    c = conn()
    cur = c.cursor()
    cur.execute(
        "INSERT INTO log_costs (date,system,kwh_solar,kwh_grid_low,kwh_grid_high,"
        "cost_actual_chf,cost_baseline_chf,saving_chf) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
        "ON DUPLICATE KEY UPDATE kwh_solar=%s,kwh_grid_low=%s,kwh_grid_high=%s,"
        "cost_actual_chf=%s,cost_baseline_chf=%s,saving_chf=%s",
        (date.today(), system, s, gl, gh, round(cost, 2), round(base, 2), round(save, 2),
         s, gl, gh, round(cost, 2), round(base, 2), round(save, 2))
    )
    c.commit()
    c.close()

def query_decisions_today(to_file=False):
    import json as _json
    c = conn()
    cur = c.cursor()
    cur.execute(
        "SELECT ts, system, automation_id, decision_code, decision_text, context "
        "FROM log_decisions WHERE DATE(ts) = CURDATE() ORDER BY ts"
    )
    rows = cur.fetchall()
    c.close()
    if to_file:
        out = []
        for r in rows:
            out.append({
                "time": r[0].strftime("%H:%M:%S") if r[0] else "?",
                "system": r[1], "automation_id": r[2],
                "code": r[3], "text": r[4], "context": r[5],
            })
        os.makedirs("/config/data", exist_ok=True)
        with open("/config/data/decisions.json", "w") as f:
            _json.dump({"count": len(out), "decisions": out}, f, indent=2)
        print(f"Wrote {len(out)} decisions to /config/data/decisions.json")
        return
    if not rows:
        print("No decisions logged today.")
        return
    for r in rows:
        ts = r[0].strftime("%H:%M:%S") if r[0] else "?"
        print(f"[{ts}] {r[1]}/{r[2]} {r[3]}: {r[4]}")
        if r[5]:
            print(f"  ctx: {r[5]}")


def main(argv):
    if len(argv) < 2:
        print("usage: log_to_db.py <decision|action|feedback|cost|query_today|query_today_file> ...",
              file=sys.stderr)
        return 2
    cmd = argv[1]
    if cmd == "decision":
        log_decision(*argv[2:7])
    elif cmd == "action":
        log_action(*argv[2:6])
    elif cmd == "feedback":
        log_feedback(*argv[2:7])
    elif cmd == "cost":
        log_cost(*argv[2:6])
    elif cmd == "query_today":
        query_decisions_today()
    elif cmd == "query_today_file":
        query_decisions_today(to_file=True)
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    # Print a real traceback so failures are visible in the HA log instead of
    # the opaque "return code: 1 / NoneType: None".
    import traceback
    try:
        sys.exit(main(sys.argv))
    except Exception:
        traceback.print_exc()
        sys.exit(1)
