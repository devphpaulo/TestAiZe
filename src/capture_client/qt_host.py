"""PySide6 capture host. The bitmap is taken before any overlay is shown."""

from __future__ import annotations

import base64
import ctypes
import logging
import os
import sys
import time
import uuid
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QAbstractNativeEventFilter, QEvent, QObject, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QImage,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .bitmap import stitch_bitmaps
from .draft import Draft
from .geometry import (
    Monitor,
    Rect,
    dip_global_to_physical,
    hit_crop_handle,
    move_rect,
    normalize_rect,
    physical_to_stitch,
    resize_rect,
    stitch_origin,
    tool_side,
)
from .hotkey import HOTKEY_ID, WM_HOTKEY, Hotkey, hotkey_label, load_hotkey, save_hotkey, try_register, try_unregister
from .icons import tool_icon
from .inline_text import InlineTextEdit
from .overlay import live_screen_during, show_capture_chrome
from .painting import paint_annotation
from .render import Annotation, DEFAULT_FONT_SIZE, font_path
from .transport import LocalApi

WDA_EXCLUDEFROMCAPTURE = 0x00000011
COLORS = ("#E10600", "#FFFFFF", "#111111", "#F5C518", "#1F8A4C", "#2F6FED")
TOOLS = (
    ("crop", "Seleção"),
    ("free", "Livre"),
    ("line", "Linha"),
    ("arrow", "Seta"),
    ("rect", "Retângulo"),
    ("circle", "Círculo"),
    ("text", "Texto"),
)


def _configure_log() -> None:
    root = os.environ.get("TESTAIZE_DATA_DIR")
    if not root:
        return
    folder = Path(root) / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(folder / "captura.log"),
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        force=True,
    )


def qimage_to_pil(image: QImage) -> Image.Image:
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    stride = image.bytesPerLine()
    bits = image.constBits()
    if hasattr(bits, "setsize"):
        bits.setsize(image.sizeInBytes())
    raw = bytes(bits)
    if stride == width * 4:
        return Image.frombytes("RGBA", (width, height), raw)
    rows = b"".join(raw[y * stride:y * stride + width * 4] for y in range(height))
    return Image.frombytes("RGBA", (width, height), rows)


def pil_to_qpixmap(image: Image.Image) -> QPixmap:
    rgba = image.convert("RGBA")
    qimage = QImage(rgba.tobytes(), rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


def _exclude(widget: QWidget) -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.SetWindowDisplayAffinity(int(widget.winId()), WDA_EXCLUDEFROMCAPTURE)
    except (OSError, ValueError):
        logging.info("captura exclusao da janela propria indisponivel")


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, host: "CaptureHost") -> None:
        super().__init__()
        self.host = host

    def nativeEventFilter(self, event_type, message) -> bool:
        if os.name != "nt" or "windows_generic_MSG" not in str(event_type):
            return False
        try:
            address = int(message)
            msg = ctypes.wintypes.MSG.from_address(address)
        except (TypeError, ValueError, OverflowError):
            return False
        if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
            self.host.begin()
            return True
        return False


class KeyFilter(QObject):
    def __init__(self, host: "CaptureHost") -> None:
        super().__init__()
        self.host = host

    def eventFilter(self, watched, event) -> bool:
        if event.type() != QEvent.Type.KeyPress or not self.host.layers:
            return False
        focus = QApplication.focusWidget()
        if event.key() == Qt.Key.Key_Escape:
            self.host.cancel()
            return True
        if event.matches(QKeySequence.StandardKey.Copy) and focus is not self.host.dock.observed:
            self.host.copy_image()
            return True
        if isinstance(focus, QPlainTextEdit):
            return False
        if event.matches(QKeySequence.StandardKey.Undo):
            self.host.undo()
            return True
        return False


class ScreenLayer(QWidget):
    def __init__(self, host: "CaptureHost", monitor: Monitor, pixmap: QPixmap) -> None:
        super().__init__()
        self.host = host
        self.monitor = monitor
        self.pixmap = pixmap
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setGeometry(monitor.dip_x, monitor.dip_y, monitor.dip_w, monitor.dip_h)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        crop = self.host.current_crop()
        if crop is not None:
            self._paint_crop(painter, crop)
        else:
            self._paint_hint(painter)
        painter.end()

    def _paint_hint(self, painter: QPainter) -> None:
        painter.setPen(QColor("#f5f5f5"))
        painter.setFont(QFont("Segoe UI", 16))
        painter.drawText(
            self.rect().adjusted(24, 48, -24, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "Arraste para selecionar a área.\nEsc ou botão direito cancela.",
        )

    def _paint_crop(self, painter: QPainter, crop: Rect) -> None:
        origin_x, origin_y = physical_to_stitch(self.host.monitors, self.monitor.origin_x, self.monitor.origin_y)
        left = max(crop.x, origin_x)
        top = max(crop.y, origin_y)
        right = min(crop.right, origin_x + self.monitor.width)
        bottom = min(crop.bottom, origin_y + self.monitor.height)
        if right <= left or bottom <= top:
            return
        scale = self.monitor.scale or 1
        dest = QRectF((left - origin_x) / scale, (top - origin_y) / scale, (right - left) / scale, (bottom - top) / scale)
        preview = self.host.preview
        if (
            preview is not None
            and not preview.isNull()
            and not live_screen_during(self.host.drag)
        ):
            source = QRect(left - crop.x, top - crop.y, right - left, bottom - top)
            painter.drawPixmap(dest, preview, source)
        else:
            source = QRect(left - origin_x, top - origin_y, right - left, bottom - top)
            painter.drawPixmap(dest, self.pixmap, source)
        full = QRectF((crop.x - origin_x) / scale, (crop.y - origin_y) / scale, crop.width / scale, crop.height / scale)
        painter.setPen(QPen(QColor("#f5f5f5"), 2))
        painter.drawRect(full)
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QPointF(full.left(), max(16, full.top() - 6)), f"{crop.width} × {crop.height}")
        painter.setBrush(QColor("#f5f5f5"))
        for name in ("nw", "n", "ne", "e", "se", "s", "sw", "w"):
            handle = self._handle_point(crop, name)
            if handle is None:
                continue
            local_x = (handle[0] - origin_x) / scale
            local_y = (handle[1] - origin_y) / scale
            painter.drawRect(QRectF(local_x - 4, local_y - 4, 8, 8))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rubber = self.host.rubber_points
        if rubber and len(rubber) >= 2:
            paint_annotation(painter, Annotation(self.host.drag, self.host.color, list(rubber)),
                             origin_x, origin_y, scale)

    def _handle_point(self, crop: Rect, name: str) -> tuple[float, float] | None:
        points = {
            "nw": (crop.x, crop.y), "n": (crop.x + crop.width / 2, crop.y), "ne": (crop.right, crop.y),
            "e": (crop.right, crop.y + crop.height / 2), "se": (crop.right, crop.bottom),
            "s": (crop.x + crop.width / 2, crop.bottom), "sw": (crop.x, crop.bottom), "w": (crop.x, crop.y + crop.height / 2),
        }
        return points.get(name)

    def _pointer(self, event) -> tuple[int, int]:
        point = event.globalPosition()
        absolute_x, absolute_y = dip_global_to_physical(self.host.monitors, point.x(), point.y())
        return physical_to_stitch(self.host.monitors, absolute_x, absolute_y)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.host.step_back()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self.host.step_back()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.host.press(self._pointer(event))
            if self.host.drag:
                self.grabMouse()

    def mouseMoveEvent(self, event) -> None:
        if self.host.drag:
            self.host.move_to(self._pointer(event))

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mouseGrabber() is self:
                self.releaseMouse()
            if self.host.drag:
                self.host.release(self._pointer(event))


class ToolPanel(QWidget):
    def __init__(self, host: "CaptureHost") -> None:
        super().__init__()
        self.host = host
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, (key, label) in enumerate(TOOLS):
            button = QPushButton()
            button.setIcon(tool_icon(key))
            button.setIconSize(QSize(24, 24))
            button.setFixedSize(36, 36)
            button.setAccessibleName(label)
            button.setCheckable(True)
            button.setToolTip(label)
            button.setProperty("tool", key)
            if key == "crop":
                button.setChecked(True)
            self.group.addButton(button, index)
            layout.addWidget(button)
        self.group.idClicked.connect(self._choose)
        undo = QPushButton()
        undo.setIcon(tool_icon("undo"))
        undo.setIconSize(QSize(24, 24))
        undo.setFixedSize(36, 36)
        undo.setAccessibleName("Desfazer")
        undo.setToolTip("Desfazer a última anotação (Ctrl+Z)")
        undo.clicked.connect(host.undo)
        layout.addWidget(undo)
        colors = QGridLayout()
        colors.setSpacing(4)
        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        for index, color in enumerate(COLORS):
            swatch = QPushButton()
            swatch.setFixedSize(16, 16)
            swatch.setCheckable(True)
            swatch.setToolTip(color)
            swatch.setAccessibleName(f"Cor {color}")
            swatch.setStyleSheet(
                f"QPushButton {{ background:{color}; border:1px solid #888; padding:0; }} "
                "QPushButton:checked { border:2px solid #2F6FED; }"
            )
            swatch.setProperty("color", color)
            if color == host.color:
                swatch.setChecked(True)
            self.color_group.addButton(swatch, index)
            colors.addWidget(swatch, index // 2, index % 2)
        self.color_group.idClicked.connect(self._color)
        layout.addLayout(colors)
        self.setStyleSheet(
            "QWidget { background:#161616; color:#f5f5f5; } "
            "QPushButton { background:#2a2a2a; color:#f5f5f5; border:1px solid #444; padding:0; } "
            "QPushButton:hover { background:#393939; } "
            "QPushButton:checked { background:#254c85; border:2px solid #78a9ff; } "
            "QPushButton:focus { border:2px solid #f5f5f5; } "
            "QToolTip { background:#262626; color:#f5f5f5; border:1px solid #666; padding:4px; }"
        )

    def _choose(self, button_id: int) -> None:
        button = self.group.button(button_id)
        if button is not None:
            self.host.finish_text()
            self.host.tool = button.property("tool")

    def _color(self, button_id: int) -> None:
        button = self.color_group.button(button_id)
        if button is None:
            return
        self.host.color = button.property("color")
        if self.host.draft is not None:
            self.host.draft.color = self.host.color


class DockPanel(QWidget):
    def __init__(self, host: "CaptureHost") -> None:
        super().__init__()
        self.host = host
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint)
        self.setFixedWidth(320)
        layout = QVBoxLayout(self)
        self.case_label = QLabel("Nenhum caso aberto")
        self.case_label.setWordWrap(True)
        layout.addWidget(self.case_label)
        self.steps = QListWidget()
        self.steps.setFixedHeight(140)
        self.steps.itemClicked.connect(self._click_step)
        layout.addWidget(self.steps)
        layout.addWidget(QLabel("Resultado observado"))
        self.observed = QPlainTextEdit()
        self.observed.setFixedHeight(72)
        self.observed.setPlaceholderText("Texto do passo, separado do texto desenhado na imagem")
        self.observed.textChanged.connect(host.observed_changed)
        layout.addWidget(self.observed)
        actions = QHBoxLayout()
        self.attach = QPushButton("Anexar")
        self.attach.clicked.connect(host.attach)
        copy = QPushButton("Copiar")
        copy.clicked.connect(host.copy_image)
        save = QPushButton("Salvar")
        save.clicked.connect(host.save_image)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(host.cancel)
        for button in (self.attach, copy, save, cancel):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.status = QLabel("Ctrl+C copia e fecha. Anexar mantém aberto. Esc sai sem confirmação.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.setStyleSheet(
            "QWidget { background:#161616; color:#f5f5f5; } "
            "QPushButton { background:#2a2a2a; color:#f5f5f5; border:1px solid #444; padding:6px; } "
            "QListWidget, QPlainTextEdit { background:#111; color:#f5f5f5; border:1px solid #333; }"
        )

    def _click_step(self, item: QListWidgetItem) -> None:
        self.host.select_step(int(item.data(Qt.ItemDataRole.UserRole)))


class CaptureHost(QObject):
    def __init__(self, base_url: str, token: str) -> None:
        super().__init__()
        # The offscreen Qt platform does not enumerate Windows fonts. Register
        # the same local font used by export so inline text stays readable there.
        if "Segoe UI" not in QFontDatabase.families():
            path = font_path()
            if path is not None:
                font_id = QFontDatabase.addApplicationFont(str(path))
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    QApplication.instance().setFont(QFont(families[0]))
        self.api = LocalApi(base_url, token)
        self.monitors: list[Monitor] = []
        self.layers: list[ScreenLayer] = []
        self.base: Image.Image | None = None
        self.draft: Draft | None = None
        self.preview: QPixmap | None = None
        self.tool = "crop"
        self.color = "#E10600"
        self.drag: str | None = None
        self.anchor: tuple[int, int] | None = None
        self.rubber: Rect | None = None
        self.rubber_points: list[tuple[int, int]] = []
        self.context: dict | None = None
        self.hotkey = Hotkey(0x2C, 0)
        self.hotkey_ok = False
        self._busy = False
        self._attaching = False
        self._silence = False
        self._text_blocked = False
        self.pending_observed: dict | None = None
        self.text_editor: InlineTextEdit | None = None
        self.text_point: tuple[int, int] | None = None
        self.text_color = self.color
        self._recording = False
        self._hwnd = 0
        self.tools = ToolPanel(self)
        self.dock = DockPanel(self)
        self.text_timer = QTimer(self)
        self.text_timer.setSingleShot(True)
        self.text_timer.timeout.connect(self.send_observed)
        self.context_timer = QTimer(self)
        self.context_timer.timeout.connect(self.refresh_context)
        self._install_hotkey()
        self.key_filter = KeyFilter(self)
        QApplication.instance().installEventFilter(self.key_filter)
        QTimer.singleShot(300, self, self._ping)

    def _install_hotkey(self) -> None:
        self.hotkey_window = QWidget()
        self.hotkey_window.setWindowFlag(Qt.WindowType.Tool)
        self._hwnd = int(self.hotkey_window.winId())
        if os.name != "nt":
            logging.info("atalho global indisponivel fora do Windows")
            return
        user32 = ctypes.windll.user32
        directory = os.environ.get("TESTAIZE_DATA_DIR")
        if directory:
            self.hotkey = load_hotkey(Path(directory))
        ok, code = try_register(user32.RegisterHotKey, self._hwnd, self.hotkey)
        self.hotkey_ok = ok
        if ok:
            logging.info("atalho de captura registrado")
        else:
            logging.info("atalho de captura indisponivel code=%s", code)
        self.hotkey_filter = HotkeyFilter(self)
        QApplication.instance().installNativeEventFilter(self.hotkey_filter)
        self.poll = QTimer(self)
        self.poll.timeout.connect(self._peek_hotkey)
        self.poll.start(80)
        self.hotkey_timer = QTimer(self)
        self.hotkey_timer.timeout.connect(self._poll_hotkey_request)
        self.hotkey_timer.start(500)

    def _peek_hotkey(self) -> None:
        if os.name != "nt" or not self._hwnd:
            return
        msg = ctypes.wintypes.MSG()
        user32 = ctypes.windll.user32
        while user32.PeekMessageW(ctypes.byref(msg), self._hwnd, WM_HOTKEY, WM_HOTKEY, 1):
            if msg.wParam == HOTKEY_ID:
                self.begin()

    def _ping(self) -> None:
        self.api.post("/api/captura/host/ping", {"hotkey": self.hotkey_ok, "label": hotkey_label(self.hotkey)})

    def _poll_hotkey_request(self) -> None:
        if self._recording or self.layers or self._busy:
            return
        payload, status = self.api.get("/api/captura/host/atalho")
        if status != 200 or not payload.get("record"):
            return
        self.api.post("/api/captura/host/atalho", {})
        self._recording = True
        chosen = None
        restored = False
        try:
            from .shortcut_dialog import record_hotkey
            chosen, restored = record_hotkey(self.hotkey, self._hwnd)
        except Exception:
            logging.exception("falha ao abrir a gravacao do atalho")
            user32 = ctypes.windll.user32
            restored, _code = try_register(user32.RegisterHotKey, self._hwnd, self.hotkey)
        finally:
            self._recording = False
        if chosen is None:
            self.hotkey_ok = restored
            self._ping()
            return
        directory = os.environ.get("TESTAIZE_DATA_DIR")
        if directory:
            try:
                save_hotkey(Path(directory), chosen)
            except OSError:
                logging.exception("nao foi possivel gravar o atalho")
                user32 = ctypes.windll.user32
                try_unregister(user32.UnregisterHotKey, self._hwnd)
                restored, _code = try_register(user32.RegisterHotKey, self._hwnd, self.hotkey)
                self.hotkey_ok = restored
                self._ping()
                return
        self.hotkey = chosen
        self.hotkey_ok = True
        logging.info("atalho de captura atualizado")
        self._ping()

    def begin(self) -> None:
        if self._busy or self.layers or self._recording:
            return
        self._busy = True
        try:
            if not self._wait_clear():
                QMessageBox.warning(
                    None, "TestAíZé",
                    "Não foi possível ocultar o Mini Player. A captura foi cancelada para não gravar o painel.",
                )
                logging.info("captura exclusao falhou")
                return
            time.sleep(0.2)
            self._open_editor()
        finally:
            self._busy = False

    def _wait_clear(self) -> bool:
        payload, status = self.api.post("/api/captura/host/preparar", {})
        if status == 0:
            return True
        request_id = payload.get("request_id", "")
        for _ in range(25):
            state, _ = self.api.get(f"/api/captura/host/preparar?request_id={request_id}")
            if state.get("ready"):
                return True
            time.sleep(0.1)
        return False

    def _open_editor(self) -> None:
        parts: list[tuple[Image.Image, Monitor]] = []
        pixmaps: list[tuple[Monitor, QPixmap]] = []
        for index, screen in enumerate(QGuiApplication.screens()):
            geo = screen.geometry()
            scale = float(screen.devicePixelRatio() or 1)
            pixmap = screen.grabWindow(0)
            image = qimage_to_pil(pixmap.toImage())
            monitor = Monitor(
                f"screen-{index}",
                geo.x() if os.name == "nt" else int(round(geo.x() * scale)),
                geo.y() if os.name == "nt" else int(round(geo.y() * scale)),
                image.width,
                image.height,
                scale,
                dip_x=geo.x(),
                dip_y=geo.y(),
                dip_w=geo.width(),
                dip_h=geo.height(),
            )
            parts.append((image, monitor))
            pixmaps.append((monitor, pixmap))
        if not parts:
            QMessageBox.warning(None, "TestAíZé", "Não foi possível ler a tela.")
            return
        self.base = stitch_bitmaps(parts)
        self.monitors = [monitor for _, monitor in parts]
        self.layers = [ScreenLayer(self, monitor, pixmap) for monitor, pixmap in pixmaps]
        for layer in self.layers:
            layer.show()
            _exclude(layer)
        self._set_chrome_visible(False)
        if self.layers:
            self.layers[0].activateWindow()
            self.layers[0].setFocus(Qt.FocusReason.OtherFocusReason)
        self.context_timer.start(1000)
        self.refresh_context()
        logging.info("captura iniciada")

    def current_crop(self) -> Rect | None:
        if self.draft is not None:
            return self.draft.crop
        return self.rubber

    def press(self, point: tuple[int, int]) -> None:
        self.finish_text()
        self.anchor = point
        self.rubber_points = [point]
        if self.draft is None:
            self.drag = "new"
            return
        if self.tool == "text":
            self._add_text(point)
            self.drag = None
            self.anchor = None
            self.rubber_points = []
            return
        radius = int(10 * (self.monitors[0].scale if self.monitors else 1))
        handle = hit_crop_handle(point[0], point[1], self.draft.crop, radius)
        if self.tool == "crop" and handle:
            self.drag = handle
        elif self.tool == "crop" and self._inside(point, self.draft.crop):
            self.drag = "move"
        elif self.tool == "crop":
            self.drag = None
            return
        else:
            self.drag = self.tool
        self._raise_chrome()

    def move_to(self, point: tuple[int, int]) -> None:
        if not self.drag or self.anchor is None or self.base is None:
            return
        if self.drag == "new":
            self.rubber = normalize_rect(
                self.anchor[0], self.anchor[1], point[0] - self.anchor[0], point[1] - self.anchor[1],
            )
        elif self.draft is not None and self.drag == "move" and self.rubber_points:
            previous = self.rubber_points[-1]
            moved = move_rect(
                self.draft.crop, point[0] - previous[0], point[1] - previous[1],
                self.base.width, self.base.height,
            )
            if moved is not None:
                self.draft.crop = moved
            self.rubber_points.append(point)
        elif self.draft is not None and self.drag in {"nw", "n", "ne", "e", "se", "s", "sw", "w"} and self.rubber_points:
            previous = self.rubber_points[-1]
            resized = resize_rect(
                self.draft.crop, self.drag, point[0] - previous[0], point[1] - previous[1],
                self.base.width, self.base.height,
            )
            if resized is not None:
                self.draft.crop = resized
            self.rubber_points.append(point)
        elif self.drag == "free":
            self.rubber_points.append(point)
        elif self.anchor is not None:
            self.rubber_points = [self.anchor, point]
        self._refresh()

    def release(self, point: tuple[int, int]) -> None:
        drag = self.drag
        anchor = self.anchor
        self.drag = None
        if drag == "new" and anchor is not None:
            rect = normalize_rect(anchor[0], anchor[1], point[0] - anchor[0], point[1] - anchor[1])
            if rect is not None and self.base is not None:
                self.draft = Draft(self.base, rect)
                self.draft.color = self.color
        elif drag in {"move", "nw", "n", "ne", "e", "se", "s", "sw", "w"} and self.draft is not None:
            self.draft.touch()
        elif drag in {"rect", "line", "arrow", "circle", "free"} and self.draft is not None and anchor is not None:
            points = list(self.rubber_points)
            if drag != "free":
                points = [anchor, point]
            if len(points) >= 2:
                self.draft.add(Annotation(drag, self.color, points))
        self.rubber = None
        self.rubber_points = []
        self.anchor = None
        self._update_preview()
        self._set_chrome_visible(show_capture_chrome(self.draft is not None))

    def _add_text(self, point: tuple[int, int]) -> None:
        self.finish_text()
        if self.draft is None or not self._inside(point, self.draft.crop):
            return
        for layer in self.layers:
            origin_x, origin_y = physical_to_stitch(self.monitors, layer.monitor.origin_x, layer.monitor.origin_y)
            if not (origin_x <= point[0] < origin_x + layer.monitor.width
                    and origin_y <= point[1] < origin_y + layer.monitor.height):
                continue
            self.text_point = point
            self.text_color = self.color
            self.text_editor = InlineTextEdit(self, layer)
            scale = layer.monitor.scale or 1
            font = QFont("Segoe UI")
            font.setPixelSize(max(1, round(DEFAULT_FONT_SIZE / scale)))
            self.text_editor.setFont(font)
            self.text_editor.setStyleSheet(
                f"QPlainTextEdit {{ background:transparent; color:{self.text_color}; "
                f"border:1px dashed {self.text_color}; padding:0; }}"
            )
            self.text_editor.move(round((point[0] - origin_x) / scale),
                                  round((point[1] - origin_y) / scale))
            self.text_editor.textChanged.connect(self._resize_text_editor)
            self._resize_text_editor()
            self.text_editor.show()
            self.text_editor.raise_()
            layer.activateWindow()
            self.text_editor.setFocus(Qt.FocusReason.OtherFocusReason)
            return

    def _resize_text_editor(self) -> None:
        editor = self.text_editor
        if editor is None:
            return
        metrics = editor.fontMetrics()
        lines = editor.toPlainText().split("\n")
        width = max(80, max(metrics.horizontalAdvance(line) for line in lines) + 10)
        height = metrics.lineSpacing() * len(lines) + 8
        parent = editor.parentWidget()
        scale = parent.monitor.scale or 1
        crop = self.draft.crop
        origin_x, origin_y = physical_to_stitch(self.monitors, parent.monitor.origin_x, parent.monitor.origin_y)
        right = min(parent.width(), (crop.right - origin_x) / scale)
        bottom = min(parent.height(), (crop.bottom - origin_y) / scale)
        editor.resize(max(2, min(width, round(right - editor.x()))),
                      max(2, min(height, round(bottom - editor.y()))))

    def finish_text(self, editor: InlineTextEdit | None = None) -> None:
        current = self.text_editor
        if current is None or (editor is not None and current is not editor):
            return
        text = current.toPlainText()
        point = self.text_point
        self.text_editor = None
        self.text_point = None
        current.hide()
        current.deleteLater()
        if text.strip() and point is not None and self.draft is not None:
            self.draft.add(Annotation("text", self.text_color, [point], text))
            self._update_preview()

    def _inside(self, point: tuple[int, int], rect: Rect) -> bool:
        return rect.x <= point[0] < rect.right and rect.y <= point[1] < rect.bottom

    def undo(self) -> None:
        if self.draft and self.draft.undo():
            self._update_preview()

    def observed_changed(self) -> None:
        if self._silence:
            return
        if self.pending_observed is None:
            if not self.context or not self.context.get("valid"):
                return
            self.pending_observed = {
                key: self.context[key] for key in
                ("session_id", "case_id", "step_id", "execution_generation")
            }
            self.pending_observed["expected_revision"] = self.context["result_revision"]
        self.pending_observed["text"] = self.dock.observed.toPlainText()
        self.text_timer.start(650)

    def send_observed(self) -> bool:
        self.text_timer.stop()
        if self.pending_observed is None:
            return True
        payload, status = self.api.post("/api/captura/host/resultado", self.pending_observed)
        if status == 200 and payload.get("ok"):
            if self._context_key(self.context) == self._context_key(self.pending_observed):
                self.context["result_revision"] = payload["revision"]
                self.context["observed"] = payload.get("actual", "")
            self.pending_observed = None
            self._text_blocked = False
            self.dock.status.setText("Resultado observado sincronizado. A imagem ainda não foi anexada.")
            return True
        self._text_blocked = True
        self.dock.status.setText(payload.get("error") or "Texto não sincronizado.")
        return False

    @staticmethod
    def _context_key(context: dict | None) -> tuple:
        return tuple((context or {}).get(key) for key in
                     ("session_id", "case_id", "step_id", "execution_generation"))

    def select_step(self, step_id: int) -> None:
        if not self.context or not self.context.get("session_id"):
            return
        if not self.send_observed():
            return
        payload, status = self.api.post("/api/captura/host/selecao", {
            "session_id": self.context["session_id"],
            "case_id": self.context.get("case_id"),
            "step_id": step_id,
            "execution_generation": self.context.get("execution_generation", ""),
            "event_id": uuid.uuid4().hex,
        })
        if status == 200:
            self._apply_context(payload, force_text=not self.dock.observed.hasFocus())

    def refresh_context(self) -> None:
        if not self.layers:
            return
        payload, status = self.api.get("/api/captura/host/contexto")
        if status == 0:
            self.dock.status.setText("TestAíZé indisponível. Copiar e salvar continuam disponíveis.")
            self.dock.attach.setEnabled(False)
            return
        if status == 200:
            typing = self.dock.observed.hasFocus() or self.pending_observed is not None
            self._apply_context(payload, force_text=not typing)

    def _apply_context(self, payload: dict, force_text: bool) -> None:
        changed = self._context_key(payload) != self._context_key(self.context)
        if changed and not self.send_observed():
            self.dock.attach.setEnabled(False)
            return
        self.context = payload
        if payload.get("case_name"):
            self.dock.case_label.setText(str(payload.get("case_name")))
        elif payload.get("message"):
            self.dock.case_label.setText(str(payload.get("message")))
        self.dock.steps.blockSignals(True)
        self.dock.steps.clear()
        for step in payload.get("steps") or []:
            item = QListWidgetItem(f"{int(step['position']):02d}  {step.get('action') or 'Passo'}")
            item.setData(Qt.ItemDataRole.UserRole, int(step["id"]))
            self.dock.steps.addItem(item)
            if step.get("selected"):
                self.dock.steps.setCurrentItem(item)
        self.dock.steps.blockSignals(False)
        if (force_text or changed) and self.pending_observed is None:
            observed = payload.get("observed") or ""
            if self.dock.observed.toPlainText() != observed:
                self._silence = True
                self.dock.observed.setPlainText(observed)
                self._silence = False
        valid = bool(payload.get("valid")) and self.draft is not None and not self._attaching
        self.dock.attach.setEnabled(valid)
        self.dock.attach.setText(payload.get("attach_label") or "Anexar")
        if not payload.get("valid"):
            self.dock.attach.setToolTip(payload.get("message") or "Anexar indisponível")
        else:
            self.dock.attach.setToolTip("Anexar a imagem ao passo selecionado")

    def copy_image(self) -> None:
        self.finish_text()
        if self.draft is None:
            return
        QApplication.clipboard().setImage(pil_to_qpixmap(self.draft.image()).toImage())
        self._close_editor()

    def save_image(self) -> None:
        self.finish_text()
        if self.draft is None:
            return
        path, _selected = QFileDialog.getSaveFileName(self.dock, "Salvar captura", "captura.png", "PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        self.draft.image().save(path, "PNG")
        self.dock.status.setText("Imagem salva neste computador. Nada foi anexado ao teste.")

    def attach(self) -> None:
        self.finish_text()
        if self._attaching or self.draft is None or not self.context or not self.context.get("valid"):
            self.dock.status.setText(self.context.get("message") if self.context else "Escolha um passo antes de anexar.")
            return
        if not self.send_observed():
            return
        self._attaching = True
        self.dock.attach.setEnabled(False)
        frozen = self.draft.freeze(self.context)
        body = {
            "command_id": frozen["command_id"],
            "render_revision": frozen["render_revision"],
            "session_id": frozen["session_id"],
            "case_id": frozen["case_id"],
            "step_id": frozen["step_id"],
            "execution_generation": frozen["execution_generation"],
            "expected_revision": frozen["expected_revision"],
            "image_base64": base64.b64encode(frozen["png"]).decode("ascii"),
        }
        payload, status = self.api.post("/api/captura/host/anexar", body)
        self._attaching = False
        if status == 200 and payload.get("ok"):
            self.draft.finish_command()
            self.dock.status.setText(
                f"Anexado ao passo {payload.get('step_position')}. Continuar editando não altera essa evidência."
            )
            self.refresh_context()
            logging.info("captura anexada command=%s", body["command_id"])
            return
        self.dock.attach.setEnabled(True)
        if status == 409 and payload.get("code") == "REVISION_CONFLICT":
            # The server explicitly rejected this command; a new click can use the new revision.
            self.draft.finish_command()
            self.context["result_revision"] = payload["revision"]
        self.dock.status.setText(payload.get("error") or "Não foi possível anexar. A captura continua aqui.")
        logging.info("captura anexo falhou code=%s", payload.get("code", ""))

    def cancel(self) -> None:
        self._close_editor()

    def step_back(self) -> None:
        self.cancel()

    def _close_editor(self) -> None:
        self.context_timer.stop()
        self.text_timer.stop()
        editor = self.text_editor
        self.text_editor = None
        self.text_point = None
        if editor is not None:
            editor.hide()
            editor.deleteLater()
        for panel in (self.tools, self.dock):
            panel.hide()
            if panel.windowHandle() is not None:
                panel.windowHandle().setTransientParent(None)
        for layer in self.layers:
            if layer.mouseGrabber() is layer:
                layer.releaseMouse()
            layer.close()
            layer.deleteLater()
        self.layers = []
        old_panels = (self.tools, self.dock)
        self.draft = None
        self.preview = None
        self.base = None
        self.rubber = None
        self.drag = None
        self.anchor = None
        self.rubber_points = []
        self.tool = "crop"
        self.pending_observed = None
        self.context = None
        self._text_blocked = False
        # Each capture gets its own native tool windows. Reusing HWNDs whose
        # previous screen owner was destroyed leaves them hidden on Windows.
        for panel in old_panels:
            panel.close()
            panel.deleteLater()
        self.tools = ToolPanel(self)
        self.dock = DockPanel(self)
        logging.info("captura cancelada")

    def _update_preview(self) -> None:
        if self.draft is None:
            self.preview = None
        else:
            self.preview = pil_to_qpixmap(self.draft.image())
        self._refresh()

    def _refresh(self) -> None:
        live = live_screen_during(self.drag)
        for layer in self.layers:
            if live:
                layer.repaint()
            else:
                layer.update()
        if not live:
            self._place()
        self._raise_chrome()

    def _set_chrome_visible(self, visible: bool) -> None:
        if not visible:
            self.tools.hide()
            self.dock.hide()
            return
        owner = self.layers[0].windowHandle() if self.layers else None
        for panel in (self.tools, self.dock):
            # Changing a visible tool window's owner can hide its native HWND
            # while QWidget still reports it visible. Bind before showing it.
            panel.winId()
            panel.windowHandle().setTransientParent(owner)
            panel.show()
        _exclude(self.tools)
        _exclude(self.dock)
        self._place()
        self._raise_chrome()

    def _raise_chrome(self) -> None:
        if self.draft is None or not self.layers:
            return
        for panel in (self.tools, self.dock):
            panel.raise_()
        if self.text_editor is not None:
            self.text_editor.raise_()

    def _place(self) -> None:
        if self.draft is None or not self.monitors or self.base is None:
            return
        crop = self.draft.crop
        side = tool_side(crop, self.base.width, self.tools.width())
        min_x, min_y = stitch_origin(self.monitors)
        if side == "left":
            tool_x, tool_y = self._dip(min_x + crop.x - 8, min_y + crop.y)
            self.tools.move(int(tool_x) - self.tools.width() - 8, int(tool_y))
        else:
            tool_x, tool_y = self._dip(min_x + crop.right + 8, min_y + crop.y)
            self.tools.move(int(tool_x), int(tool_y))
        dock_x, dock_y = self._dip(min_x + crop.x, min_y + crop.bottom + 12)
        if dock_y + self.dock.height() > self._bottom():
            dock_x, dock_y = self._dip(min_x + crop.x, min_y + crop.y - self.dock.height() - 12)
        self.dock.move(int(dock_x), int(dock_y))
        anchor_x, anchor_y = self._dip(min_x + crop.x, min_y + crop.y)
        screen = QGuiApplication.screenAt(QPoint(int(anchor_x), int(anchor_y))) or QGuiApplication.primaryScreen()
        if screen is not None:
            bounds = screen.availableGeometry()
            for panel in (self.tools, self.dock):
                panel.move(
                    max(bounds.left(), min(panel.x(), bounds.right() + 1 - panel.width())),
                    max(bounds.top(), min(panel.y(), bounds.bottom() + 1 - panel.height())),
                )
        self.dock.attach.setEnabled(bool(self.context and self.context.get("valid")) and not self._attaching)

    def _dip(self, absolute_x: int, absolute_y: int) -> tuple[float, float]:
        from .geometry import physical_to_dip
        return physical_to_dip(self.monitors, absolute_x, absolute_y)

    def _bottom(self) -> int:
        return max(item.dip_y + item.dip_h for item in self.monitors)

    def shutdown(self) -> None:
        self._close_editor()
        if os.name == "nt" and self._hwnd:
            try_unregister(ctypes.windll.user32.UnregisterHotKey, self._hwnd)
        logging.info("host de captura encerrado")


def main() -> int:
    url = os.environ.get("TESTAIZE_CAPTURE_URL", "")
    token = os.environ.get("TESTAIZE_CAPTURE_TOKEN", "")
    if not url or not token:
        return 2
    _configure_log()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    host = CaptureHost(url, token)
    app.aboutToQuit.connect(host.shutdown)
    logging.info("host de captura pronto")
    return app.exec()
