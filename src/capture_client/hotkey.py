"""Global PrintScreen registration. A failure is reported; other apps are left alone."""

from __future__ import annotations

VK_SNAPSHOT = 0x2C
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
HOTKEY_ID = 1


def try_register(register, hwnd=None) -> tuple[bool, str]:
    """register(hwnd, id, modifiers, vk) -> nonzero on success, matching RegisterHotKey."""
    if register(hwnd, HOTKEY_ID, MOD_NOREPEAT, VK_SNAPSHOT):
        return True, ""
    return False, "HOTKEY_CONFLICT"


def try_unregister(unregister, hwnd=None) -> None:
    unregister(hwnd, HOTKEY_ID)
