"""Global shortcut for the capture. A failure is reported; other apps are left alone."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

VK_SNAPSHOT = 0x2C
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
HOTKEY_ID = 1
_MODIFIER_MASK = MOD_ALT | MOD_CONTROL | MOD_SHIFT | MOD_WIN
MODIFIER_KEYS = frozenset({
    0x10, 0x11, 0x12, 0x5B, 0x5C,
    0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5,
})

_KEY_NAMES = {
    0x08: "Backspace", 0x09: "Tab", 0x0D: "Enter", 0x13: "Pause",
    0x14: "Caps Lock", 0x1B: "Esc", 0x20: "Espaço",
    0x21: "Page Up", 0x22: "Page Down", 0x23: "End", 0x24: "Home",
    0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓",
    0x2C: "PrintScreen", 0x2D: "Insert", 0x2E: "Delete",
    0x5D: "Menu", 0x90: "Num Lock", 0x91: "Scroll Lock",
    0x6A: "Num *", 0x6B: "Num +", 0x6D: "Num -", 0x6E: "Num .", 0x6F: "Num /",
}
_KEY_NAMES.update({0x6F + number: f"F{number}" for number in range(1, 25)})
_KEY_NAMES.update({code: chr(code) for code in range(0x30, 0x3A)})
_KEY_NAMES.update({code: chr(code) for code in range(0x41, 0x5B)})
_KEY_NAMES.update({0x60 + number: f"Num {number}" for number in range(10)})


@dataclass(frozen=True)
class Hotkey:
    virtual_key: int
    modifiers: int = 0

    def register_modifiers(self) -> int:
        return (self.modifiers & _MODIFIER_MASK) | MOD_NOREPEAT


DEFAULT_HOTKEY = Hotkey(VK_SNAPSHOT, 0)


def valid_hotkey(spec: Hotkey) -> bool:
    if not isinstance(spec.virtual_key, int) or not isinstance(spec.modifiers, int):
        return False
    if spec.virtual_key < 1 or spec.virtual_key > 254 or spec.virtual_key in MODIFIER_KEYS:
        return False
    if spec.modifiers < 0 or spec.modifiers & ~_MODIFIER_MASK:
        return False
    return True


def hotkey_label(spec: Hotkey) -> str:
    parts = []
    if spec.modifiers & MOD_CONTROL:
        parts.append("Ctrl")
    if spec.modifiers & MOD_SHIFT:
        parts.append("Shift")
    if spec.modifiers & MOD_ALT:
        parts.append("Alt")
    if spec.modifiers & MOD_WIN:
        parts.append("Win")
    parts.append(_KEY_NAMES.get(spec.virtual_key, f"Tecla {spec.virtual_key}"))
    return " + ".join(parts)


def try_register(register, hwnd=None, spec: Hotkey | None = None) -> tuple[bool, str]:
    """register(hwnd, id, modifiers, vk) -> nonzero on success, matching RegisterHotKey."""
    chosen = spec or DEFAULT_HOTKEY
    if not valid_hotkey(chosen):
        return False, "HOTKEY_INVALID"
    if register(hwnd, HOTKEY_ID, chosen.register_modifiers(), chosen.virtual_key):
        return True, ""
    return False, "HOTKEY_CONFLICT"


def try_unregister(unregister, hwnd=None) -> None:
    unregister(hwnd, HOTKEY_ID)


def hotkey_path(directory: Path) -> Path:
    return directory / "config" / "atalho-captura.json"


def load_hotkey(directory: Path) -> Hotkey:
    try:
        payload = json.loads(hotkey_path(directory).read_text(encoding="utf-8"))
        spec = Hotkey(int(payload["virtual_key"]), int(payload["modifiers"]))
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return DEFAULT_HOTKEY
    return spec if valid_hotkey(spec) else DEFAULT_HOTKEY


def save_hotkey(directory: Path, spec: Hotkey) -> None:
    if not valid_hotkey(spec):
        raise ValueError("Atalho inválido.")
    path = hotkey_path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"virtual_key": spec.virtual_key, "modifiers": spec.modifiers}),
        encoding="utf-8",
    )
    os.replace(temporary, path)
