#!/usr/bin/env python3
"""Deploy config and scripts from GitHub without git.

Downloads files from the GitHub API (public repo) using urllib,
then copies them to /config/ and /homeassistant/.

Uses GitHub API blob endpoint (not raw.githubusercontent.com) to avoid
CDN caching issues that can serve stale files for minutes.

Usage: python3 deploy_github.py
"""

import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO = "FraserMacdonald/ha-energy-optimisation"
BRANCH = "main"
API_BASE = f"https://api.github.com/repos/{REPO}"
TREE_URL = f"{API_BASE}/git/trees/{BRANCH}?recursive=1"

# HA Core container: /config is the config dir.
# /homeassistant may be a symlink or legacy path — deploy to both.
DEST_PRIMARY = Path("/config")
DEST_FALLBACK = Path("/homeassistant")

HEADERS = {
    "User-Agent": "HA-Deploy",
    "Accept": "application/vnd.github.v3+json",
}


def fetch_tree():
    """Fetch the full file tree with blob SHAs from GitHub API."""
    req = urllib.request.Request(TREE_URL, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read())
    return [
        {"path": entry["path"], "sha": entry["sha"]}
        for entry in data.get("tree", [])
        if entry["type"] == "blob"
    ]


def download_blob(sha):
    """Download file content via GitHub blob API (no CDN caching)."""
    url = f"{API_BASE}/git/blobs/{sha}"
    req = urllib.request.Request(url, headers=HEADERS)
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read())
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"])
    return data["content"].encode()


def deploy():
    """Download and deploy config/ and scripts/ from GitHub."""
    print("Fetching file tree from GitHub...")
    all_files = fetch_tree()

    # Filter to config/ and scripts/ directories
    deploy_files = [
        f for f in all_files
        if f["path"].startswith("config/") or f["path"].startswith("scripts/")
    ]
    print(f"Found {len(deploy_files)} files to deploy.")

    updated = 0
    errors = 0
    for entry in deploy_files:
        rel_path = entry["path"]
        if rel_path.startswith("config/"):
            sub = rel_path[len("config/"):]
        elif rel_path.startswith("scripts/"):
            sub = rel_path
        else:
            continue

        try:
            content = download_blob(entry["sha"])
            for dest in (DEST_PRIMARY, DEST_FALLBACK):
                dest_path = dest / sub
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(content)
            updated += 1
        except Exception as e:
            print(f"  ERROR: {rel_path} -> {e}")
            errors += 1

    print(f"Deploy complete: {updated} files updated, {errors} errors.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    deploy()
