"""
Tiny JSON settings store. Keeps the API key + chosen model on disk between
runs, in a per-user config folder (~/.companion_app/config.json).
"""

import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".companion_app")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "api_key": "",
    "model": "gemini-3.5-flash-lite",
    "accent_color": "#FF2E88",
    "theme": "dark",
    "approved_apps": [],      # list of {"name": str, "path": str}
    "approved_folders": [],  # list of str paths
    "google_calendar_connected": False,
}


def load() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(DEFAULTS)
        merged.update(data or {})
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)


def save(settings: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)
