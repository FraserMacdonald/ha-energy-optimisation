#!/usr/bin/env python3
"""
HA Backup Script — Creates a full backup and copies it to /config/www/
for external download. Cleans up old backups beyond retention count.

Usage (from shell_command):
    python3 /homeassistant/scripts/ha_backup.py

The backup file is then downloadable at:
    http://homeassistant.local:8123/local/ha_backup_latest.tar

Environment:
    SUPERVISOR_TOKEN — automatically set by HA when run via shell_command
"""

import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

SUPERVISOR_URL = "http://supervisor"
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
BACKUP_DIR = Path("/backup")
WWW_DIR = Path("/config/www")
LATEST_NAME = "ha_backup_latest.tar"
RETENTION = 5  # keep this many backups on HA


def supervisor_api(method, endpoint, data=None, timeout=300):
    """Call the Supervisor API."""
    url = f"{SUPERVISOR_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except URLError as e:
        print(f"ERROR: Supervisor API call failed: {endpoint} — {e}", file=sys.stderr)
        sys.exit(1)


def create_backup():
    """Create a full backup and return its slug."""
    name = f"auto_{datetime.now().strftime('%Y%m%d_%H%M')}"
    print(f"Creating backup '{name}'...")
    result = supervisor_api("POST", "/backups/new/full", {"name": name}, timeout=600)
    slug = result.get("data", {}).get("slug")
    if not slug:
        print(f"ERROR: No slug returned: {result}", file=sys.stderr)
        sys.exit(1)
    print(f"Backup created: {slug}")
    return slug


def copy_to_www(slug):
    """Copy the backup tar to /config/www/ for external download."""
    WWW_DIR.mkdir(parents=True, exist_ok=True)
    src = BACKUP_DIR / f"{slug}.tar"
    dst = WWW_DIR / LATEST_NAME

    # Wait for file to appear (backup creation is async)
    for _ in range(30):
        if src.exists():
            break
        time.sleep(2)
    else:
        print(f"ERROR: Backup file not found: {src}", file=sys.stderr)
        sys.exit(1)

    shutil.copy2(src, dst)
    size_mb = dst.stat().st_size / (1024 * 1024)
    print(f"Copied to {dst} ({size_mb:.1f} MB)")


def cleanup_old_backups():
    """Remove old backups beyond retention count."""
    result = supervisor_api("GET", "/backups")
    backups = result.get("data", {}).get("backups", [])

    # Sort by date descending
    backups.sort(key=lambda b: b.get("date", ""), reverse=True)

    # Only clean up auto-created backups
    auto_backups = [b for b in backups if b.get("name", "").startswith("auto_")]

    if len(auto_backups) <= RETENTION:
        print(f"Retention OK: {len(auto_backups)} auto backups (limit {RETENTION})")
        return

    to_delete = auto_backups[RETENTION:]
    for backup in to_delete:
        slug = backup["slug"]
        print(f"Deleting old backup: {backup['name']} ({slug})")
        supervisor_api("DELETE", f"/backups/{slug}")

    print(f"Cleaned up {len(to_delete)} old backups")


def main():
    if not TOKEN:
        print("ERROR: SUPERVISOR_TOKEN not set. Run via HA shell_command.", file=sys.stderr)
        sys.exit(1)

    slug = create_backup()
    copy_to_www(slug)
    cleanup_old_backups()
    print("Done.")


if __name__ == "__main__":
    main()
