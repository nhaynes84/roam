"""Action registry for Roam.

Maps action name strings to async HID key sequences. Each action sends
the appropriate keyboard or consumer report, waits briefly, then sends
a release. Some actions are multi-step (e.g., tmux prefix + key).
"""

import asyncio

from hid_report import (
    MOD_CTRL, MOD_SHIFT,
    KEY_B, KEY_C, KEY_D, KEY_O, KEY_Y,
    KEY_ENTER, KEY_ESCAPE, KEY_TAB,
    CONSUMER_DICTATION,
)


class ActionRegistry:
    """Executes named HID actions via the BLE HID service.

    Args:
        ble_hid: BleHID instance for sending reports.
        haptic: Haptic instance for feedback (optional).
        display: Display instance for showing action names (optional).
    """

    def __init__(self, ble_hid, haptic=None, display=None):
        self._ble = ble_hid
        self._haptic = haptic
        self._display = display

    async def execute(self, action_name):
        """Execute a named action.

        Args:
            action_name: Action string from config (e.g., 'dictation_toggle').

        Returns:
            True if the action was found and executed, False otherwise.
        """
        handler = self._actions.get(action_name)
        if handler is None:
            print("actions: unknown action:", action_name)
            return False

        if self._display:
            self._display.show_action(action_name)

        await handler(self)
        return True

    async def _dictation_toggle(self):
        """Send macOS dictation consumer key (0x00CF)."""
        await self._ble.send_consumer_report(CONSUMER_DICTATION)
        await asyncio.sleep_ms(50)
        await self._ble.send_consumer_report(0x0000)

    async def _dictation_shortcut(self):
        """Send Ctrl+Shift+D as a keyboard shortcut fallback for dictation."""
        await self._ble.send_keyboard_report(
            modifiers=MOD_CTRL | MOD_SHIFT,
            keys=[KEY_D],
        )
        await asyncio.sleep_ms(50)
        await self._ble.release_all()

    async def _tmux_next_pane(self):
        """Send tmux prefix (Ctrl+B) then 'o' to switch panes."""
        # Ctrl+B
        await self._ble.send_keyboard_report(modifiers=MOD_CTRL, keys=[KEY_B])
        await asyncio.sleep_ms(30)
        await self._ble.release_all()
        await asyncio.sleep_ms(50)
        # 'o'
        await self._ble.send_keyboard_report(keys=[KEY_O])
        await asyncio.sleep_ms(30)
        await self._ble.release_all()

    async def _cycle_mode(self):
        """Send Shift+Tab to cycle through modes."""
        await self._ble.send_keyboard_report(modifiers=MOD_SHIFT, keys=[KEY_TAB])
        await asyncio.sleep_ms(50)
        await self._ble.release_all()

    async def _ble_switch(self):
        """Disconnect BLE and re-advertise to switch to a different host."""
        await self._ble.disconnect()
        await asyncio.sleep_ms(200)
        await self._ble.start_advertising()

    async def _approve_yes(self):
        """Send 'y' then Enter — approve a prompt."""
        await self._ble.send_keyboard_report(keys=[KEY_Y])
        await asyncio.sleep_ms(30)
        await self._ble.release_all()
        await asyncio.sleep_ms(30)
        await self._ble.send_keyboard_report(keys=[KEY_ENTER])
        await asyncio.sleep_ms(30)
        await self._ble.release_all()

    async def _approve_always(self):
        """Send Tab then Enter — select 'Always allow' option."""
        await self._ble.send_keyboard_report(keys=[KEY_TAB])
        await asyncio.sleep_ms(30)
        await self._ble.release_all()
        await asyncio.sleep_ms(30)
        await self._ble.send_keyboard_report(keys=[KEY_ENTER])
        await asyncio.sleep_ms(30)
        await self._ble.release_all()

    async def _reject_escape(self):
        """Send Escape — dismiss/reject a prompt."""
        await self._ble.send_keyboard_report(keys=[KEY_ESCAPE])
        await asyncio.sleep_ms(50)
        await self._ble.release_all()

    async def _kill_process(self):
        """Send Ctrl+C — interrupt running process."""
        await self._ble.send_keyboard_report(modifiers=MOD_CTRL, keys=[KEY_C])
        await asyncio.sleep_ms(50)
        await self._ble.release_all()

    # Action lookup table — maps config strings to methods
    _actions = {
        "dictation_toggle": _dictation_toggle,
        "dictation_shortcut": _dictation_shortcut,
        "tmux_next_pane": _tmux_next_pane,
        "cycle_mode": _cycle_mode,
        "ble_switch": _ble_switch,
        "approve_yes": _approve_yes,
        "approve_always": _approve_always,
        "reject_escape": _reject_escape,
        "kill_process": _kill_process,
    }
