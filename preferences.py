"""
UI preferences store — deliberately separate from timetracker_core.

The core contract (specs/core-logic-contract.md) is about session/entry data only.
Things like "which tab was open last" or future UI toggles don't belong in
it — they're app-level settings, so they get their own small file next to
(not inside) the sessions folder.

Usage from main.py:
    prefs = PreferencesStore(path)
    prefs.get_all()          -> dict, always has every DEFAULT_PREFERENCES key
    prefs.set("key", value)  -> persists immediately, returns the full dict
"""
import json
import os

DEFAULT_PREFERENCES = {
    "activeTab": "tasks",
    "theme": "cute",
    "entrySaveLocation": None,
}

VALID_THEMES = ("cute", "cyber", "poolside", "evergreen", "citrus-pop")

class PreferencesStore:
    def __init__(self, path):
        self.path = path
        self._data = dict(DEFAULT_PREFERENCES)
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._data.update(loaded)
        except (OSError, json.JSONDecodeError):
            # Corrupt/unreadable prefs file: fall back to defaults rather
            # than crash the app over a setting. Never worth losing session
            # data over — but this isn't session data, so "just reset it" is
            # an acceptable failure mode here (unlike the core's session files).
            pass
        self._validate_theme()
        location = self._data.get("entrySaveLocation")
        if location is not None and (not isinstance(location, str) or not location.strip()):
            self._data["entrySaveLocation"] = None

    def get_all(self):
        return dict(self._data)

    def _validate_theme(self):
        theme = self._data.get("theme")
        if not isinstance(theme, str) or theme not in VALID_THEMES:
            self._data["theme"] = "cute"

    def set(self, key, value):
        if key not in DEFAULT_PREFERENCES:
            return dict(self._data)
        if key == "theme":
            if not isinstance(value, str) or value not in VALID_THEMES:
                value = "cute"
        if key == "entrySaveLocation" and (not isinstance(value, str) or not value.strip()):
            return dict(self._data)
        self._data[key] = value
        self._save()
        return dict(self._data)

    def _save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)
        os.replace(tmp, self.path)  # atomic write, same pattern the core uses for sessions
