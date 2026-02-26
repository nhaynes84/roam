"""Configuration manager for Roam.

Loads and saves button mappings and device settings from /config.json
on the Pico's filesystem.
"""

import json

_DEFAULT_CONFIG = {
    "buttons": [
        {"short": "dictation_toggle", "long": "tmux_next_pane"},
        {"short": "cycle_mode", "long": "ble_switch"},
        {"short": "approve_yes", "long": "approve_always"},
        {"short": "reject_escape", "long": "kill_process"},
    ],
    "long_press_ms": 600,
    "dictation_method": "consumer_key",
}

CONFIG_PATH = "/config.json"


class Config:
    """Manages persistent configuration stored as JSON on flash."""

    def __init__(self):
        self.data = {}
        self.load()

    def load(self):
        """Load config from flash, falling back to defaults on any error."""
        try:
            with open(CONFIG_PATH, "r") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = dict(_DEFAULT_CONFIG)
            self.save()

    def save(self):
        """Persist current config to flash."""
        try:
            with open(CONFIG_PATH, "w") as f:
                json.dump(self.data, f)
        except OSError as e:
            print("config: save failed:", e)

    @property
    def buttons(self):
        """Return the list of button mapping dicts."""
        return self.data.get("buttons", _DEFAULT_CONFIG["buttons"])

    @property
    def long_press_ms(self):
        """Long press threshold in milliseconds."""
        return self.data.get("long_press_ms", 600)

    @property
    def dictation_method(self):
        """Dictation method: 'consumer_key' or 'shortcut'."""
        return self.data.get("dictation_method", "consumer_key")

    def get_button_action(self, index, press_type):
        """Get the action name for a button press.

        Args:
            index: Button index (0-3).
            press_type: 'short' or 'long'.

        Returns:
            Action name string, or None if not mapped.
        """
        buttons = self.buttons
        if 0 <= index < len(buttons):
            return buttons[index].get(press_type)
        return None
