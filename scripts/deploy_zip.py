#!/usr/bin/env python3
"""Deploy from GitHub ZIP archive - no CDN caching, single download."""
import io
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "FraserMacdonald/ha-energy-optimisation"
BRANCH = "main"
ZIP_URL = f"https://github.com/{REPO}/archive/refs/heads/{BRANCH}.zip"
PREFIX = f"ha-energy-optimisation-{BRANCH}/"
DEST = Path("/config")


def deploy():
    print("Downloading ZIP from GitHub...")
    req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "HA-Deploy"})
    resp = urllib.request.urlopen(req, timeout=30)
    data = resp.read()
    print(f"Downloaded {len(data)} bytes")

    z = zipfile.ZipFile(io.BytesIO(data))
    updated = 0
    for name in z.namelist():
        if name.endswith("/"):
            continue
        rel = name[len(PREFIX):]
        if rel.startswith("config/"):
            dest_path = DEST / rel[len("config/"):]
        elif rel.startswith("scripts/"):
            dest_path = DEST / rel
        else:
            continue

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(z.read(name))
        updated += 1

    print(f"Deploy complete: {updated} files updated")


if __name__ == "__main__":
    # Also delete stale .ha_token
    ha_token = Path("/config/python_scripts/.ha_token")
    if ha_token.exists():
        ha_token.unlink()
        print("Removed stale .ha_token")
    deploy()
