"""Records the next key combination. The hook exists only while this dialog is open."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

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
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        title = QLabel("Qual tecla abre a captura?")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)
        intro = QLabel(
            "Essa combinação funciona mesmo com outra janela na frente. "
            "Depois de salvar, use-a para escurecer a tela e selecionar a área."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        current_box = QFrame()
        current_box.setObjectName("currentBox")
        current_layout = QVBoxLayout(current_box)
        current_caption = QLabel("Atalho atual")
        current_caption.setObjectName("muted")
        self.current_value = QLabel(hotkey_label(current))
        value_font = QFont()
        value_font.setPointSize(16)
        value_font.setBold(True)
        self.current_value.setFont(value_font)
        current_layout.addWidget(current_caption)
        current_layout.addWidget(self.current_value)
        layout.addWidget(current_box)
        instruction = QLabel("Pressione agora a nova combinação. Não precisa clicar no campo.")
        instruction.setWordWrap(True)
        layout.addWidget(instruction)
        self.field = QLineEdit()
        self.field.setReadOnly(True)
        self.field.setPlaceholderText("Aguardando tecla…")
        self.field.setMinimumHeight(40)
        layout.addWidget(self.field)
        self.hint = QLabel("Esc fecha sem alterar. Se outro programa já usar a combinação, o TestAíZé avisa e mantém a atual.")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        tray = QLabel("Para abrir esta tela de novo: botão direito no ícone do TestAíZé, ao lado do relógio, e depois “Atalho da captura”.")
        tray.setObjectName("muted")
        tray.setWordWrap(True)
        layout.addWidget(tray)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        self.save_button = QPushButton("Salvar atalho")
        self.save_button.setDefault(True)
        self.save_button.setEnabled(False)
        self.save_button.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        self.setStyleSheet(
            "QDialog { background:#161616; color:#f5f5f5; }"
            "QLabel { color:#f5f5f5; }"
            "QLabel#muted { color:#bdbdbd; }"
            "QFrame#currentBox { background:#111; border:1px solid #333; border-radius:8px; padding:8px; }"
            "QLineEdit { background:#111; color:#f5f5f5; border:1px solid #555; border-radius:6px; padding:8px 10px; font-size:16px; }"
            "QPushButton { background:#2a2a2a; color:#f5f5f5; border:1px solid #444; border-radius:6px; padding:8px 16px; }"
            "QPushButton:disabled { color:#777; }"
            "QPushButton:default { background:#2F6FED; border-color:#2F6FED; }"
        )
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
        label = hotkey_label(spec)
        self.field.setText(label)
        self.save_button.setEnabled(True)
        self.hint.setText(f"Salve para passar a usar {label}. Esc ainda cancela e mantém {hotkey_label(self.current)}.")

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
