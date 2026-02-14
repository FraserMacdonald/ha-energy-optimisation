#!/usr/bin/env python3
import sys, os
from datetime import datetime, date

try:
    import mysql.connector
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "mysql-connector-python", "-q"])
    import mysql.connector

DB = {
    "host": "core-mariadb",
    "port": 3306,
    "user": "homeassistant",
    "password": "Yuriandyogi001!",
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

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "decision":
        log_decision(*sys.argv[2:7])
    elif cmd == "action":
        log_action(*sys.argv[2:6])
    elif cmd == "feedback":
        log_feedback(*sys.argv[2:7])
    elif cmd == "cost":
        log_cost(*sys.argv[2:6])
