#!/usr/bin/env python3
"""Simple key-value text store for HA."""
import sys
import json

STORE = '/config/python_scripts/ev_text_store.json'

def load():
    try:
        with open(STORE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save(data):
    with open(STORE, 'w') as f:
        json.dump(data, f)

def main():
    data = load()
    if len(sys.argv) == 1:
        print(json.dumps(data))
    elif len(sys.argv) == 2:
        print(data.get(sys.argv[1], ''))
    elif len(sys.argv) >= 3:
        key = sys.argv[1]
        value = ' '.join(sys.argv[2:])
        data[key] = value
        save(data)
        print(json.dumps({"ok": True, "key": key}))

if __name__ == "__main__":
    main()
