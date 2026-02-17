#!/usr/bin/env python3
"""
HA Backup Copy Script — Copies the newest backup to /config/www/ for download.

Usage (from shell_command):
    python3 /homeassistant/scripts/ha_backup.py

The backup file is then downloadable at:
    http://homeassistant.local:8123/local/ha_backup_latest.tar

NOTE: Backup creation is triggered externally via hassio.backup_full service.
This script only handles the copy step (fast, no timeout issues).
"""

import shutil
import sys
from pathlib import Path

BACKUP_DIR = Path("/backup")
WWW_DIR = Path("/config/www")
LATEST_NAME = "ha_backup_latest.tar"


def main():
    WWW_DIR.mkdir(parents=True, exist_ok=True)

    # Find the newest .tar file in /backup/
    backups = sorted(BACKUP_DIR.glob("*.tar"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not backups:
        print("ERROR: No backup files found in /backup/", file=sys.stderr)
        sys.exit(1)

    src = backups[0]
    dst = WWW_DIR / LATEST_NAME

    shutil.copy2(src, dst)
    size_mb = dst.stat().st_size / (1024 * 1024)
    print(f"Copied {src.name} to {dst} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
