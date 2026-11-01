"""Records the next key combination. The hook exists only while this dialog is open."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from .hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    MOD_WIN,
    MODIFIER_KEYS,
    Hotkey,
    hotkey_label,
    try_register,
    try_unregister,
    valid_hotkey,
)

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_SHIFT = 0x10
VK_LWIN = 0x5B
VK_RWIN = 0x5C

_LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
_HOOKPROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class _KeyboardHook(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


def _key_down(user32, virtual_key: int) -> bool:
    user32.GetAsyncKeyState.restype = ctypes.c_short
    return user32.GetAsyncKeyState(virtual_key) < 0


def _pressed_modifiers(user32) -> int:
    modifiers = 0
    if _key_down(user32, VK_CONTROL):
        modifiers |= MOD_CONTROL
    if _key_down(user32, VK_SHIFT):
        modifiers |= MOD_SHIFT
    if _key_down(user32, VK_MENU):
        modifiers |= MOD_ALT
    if _key_down(user32, VK_LWIN) or _key_down(user32, VK_RWIN):
        modifiers |= MOD_WIN
    return modifiers


class HotkeyDialog(QDialog):
    _captured = Signal(int, int)
    _cancel_requested = Signal()

    def __init__(self, current: Hotkey, hwnd: int) -> None:
        super().__init__()
        self.current = current
        self.hwnd = hwnd
        self.chosen: Hotkey | None = None
        self.saved = False
        self._hook = None
        self._callback = None
        self.setWindowTitle("Atalho da captura")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Pressione a combinação que vai abrir a captura."))
        layout.addWidget(QLabel(f"Atalho atual: {hotkey_label(current)}"))
        self.field = QLineEdit()
        self.field.setReadOnly(True)
        self.field.setPlaceholderText("Aguardando tecla…")
        layout.addWidget(self.field)
        actions = QHBoxLayout()
        self.save_button = QPushButton("Salvar")
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        actions.addWidget(self.save_button)
        actions.addWidget(cancel)
        layout.addLayout(actions)
        self._captured.connect(self._apply_capture, Qt.ConnectionType.QueuedConnection)
        self._cancel_requested.connect(self.reject, Qt.ConnectionType.QueuedConnection)
        self._install_hook()

    def _user32(self):
        user32 = ctypes.windll.user32
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = _LRESULT
        user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        return user32

    def _install_hook(self) -> None:
        if self._hook:
            return
        user32 = self._user32()
        self._callback = _HOOKPROC(self._on_key)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._callback, None, 0)

    def _remove_hook(self) -> None:
        if not self._hook:
            return
        self._user32().UnhookWindowsHookEx(self._hook)
        self._hook = None
        self._callback = None

    def _on_key(self, code, wparam, lparam):
        user32 = self._user32()
        if code >= 0 and wparam in (WM_KEYDOWN, WM_SYSKEYDOWN) and self._hook:
            event = ctypes.cast(lparam, ctypes.POINTER(_KeyboardHook)).contents
            virtual_key = int(event.vkCode)
            modifiers = _pressed_modifiers(user32)
            if virtual_key == VK_ESCAPE and modifiers == 0:
                self._cancel_requested.emit()
                return 1
            if virtual_key not in MODIFIER_KEYS:
                spec = Hotkey(virtual_key, modifiers)
                if valid_hotkey(spec):
                    self._captured.emit(virtual_key, modifiers)
                    return 1
        return user32.CallNextHookEx(self._hook, code, wparam, lparam)

    def _apply_capture(self, virtual_key: int, modifiers: int) -> None:
        spec = Hotkey(virtual_key, modifiers)
        if not valid_hotkey(spec):
            return
        self.chosen = spec
        self.field.setText(hotkey_label(spec))
        self.save_button.setEnabled(True)

    def keyPressEvent(self, event) -> None:
        if self._hook or event.isAutoRepeat():
            return
        virtual_key = int(event.nativeVirtualKey() or 0)
        modifiers = 0
        flags = event.modifiers()
        if flags & Qt.KeyboardModifier.ControlModifier:
            modifiers |= MOD_CONTROL
        if flags & Qt.KeyboardModifier.ShiftModifier:
            modifiers |= MOD_SHIFT
        if flags & Qt.KeyboardModifier.AltModifier:
            modifiers |= MOD_ALT
        if flags & Qt.KeyboardModifier.MetaModifier:
            modifiers |= MOD_WIN
        if virtual_key == VK_ESCAPE and modifiers == 0:
            self.reject()
            return
        self._apply_capture(virtual_key, modifiers)

    def _save(self) -> None:
        if self.chosen is None or not valid_hotkey(self.chosen):
            return
        self._remove_hook()
        user32 = ctypes.windll.user32
        try_unregister(user32.UnregisterHotKey, self.hwnd)
        ok, _code = try_register(user32.RegisterHotKey, self.hwnd, self.chosen)
        if not ok:
            QMessageBox.warning(
                self, "TestAíZé",
                "Esse atalho já está em uso por outro programa. Escolha outro.",
            )
            self._install_hook()
            return
        self.saved = True
        self.accept()

    def done(self, code: int) -> None:
        self._remove_hook()
        super().done(code)


def record_hotkey(current: Hotkey, hwnd: int) -> tuple[Hotkey | None, bool]:
    """Unregister the active shortcut, let the person press a new one, then restore on cancel."""
    user32 = ctypes.windll.user32
    try_unregister(user32.UnregisterHotKey, hwnd)
    dialog = HotkeyDialog(current, hwnd)
    try:
        dialog.exec()
    finally:
        dialog._remove_hook()
    if dialog.saved and dialog.chosen is not None:
        return dialog.chosen, True
    ok, _code = try_register(user32.RegisterHotKey, hwnd, current)
    return None, ok
