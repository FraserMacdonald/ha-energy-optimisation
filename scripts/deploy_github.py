#!/usr/bin/env python3
"""Deploy config and scripts from GitHub without git.

Downloads files from the GitHub API (public repo) using urllib,
then copies them to /homeassistant/. Fallback for environments
where git binary is not available (e.g., HA Core container).

Usage: python3 deploy_github.py
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

REPO = "FraserMacdonald/ha-energy-optimisation"
BRANCH = "main"
BASE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
RAW_URL = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}"
DEST = Path("/homeassistant")


def fetch_tree():
    """Fetch the full file tree from GitHub API."""
    req = urllib.request.Request(BASE_URL, headers={"User-Agent": "HA-Deploy"})
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read())
    return [
        entry["path"]
        for entry in data.get("tree", [])
        if entry["type"] == "blob"
    ]


def download_file(path):
    """Download a single file from GitHub raw."""
    url = f"{RAW_URL}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "HA-Deploy"})
    resp = urllib.request.urlopen(req, timeout=30)
    return resp.read()


def deploy():
    """Download and deploy config/ and scripts/ from GitHub."""
    print("Fetching file tree from GitHub...")
    all_files = fetch_tree()

    # Filter to config/ and scripts/ directories
    deploy_files = [
        f for f in all_files
        if f.startswith("config/") or f.startswith("scripts/")
    ]
    print(f"Found {len(deploy_files)} files to deploy.")

    updated = 0
    errors = 0
    for rel_path in deploy_files:
        if rel_path.startswith("config/"):
            # config/foo -> /homeassistant/foo
            dest_path = DEST / rel_path[len("config/"):]
        elif rel_path.startswith("scripts/"):
            # scripts/foo -> /homeassistant/scripts/foo
            dest_path = DEST / rel_path
        else:
            continue

        try:
            content = download_file(rel_path)
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
