"""Desktop regressions without browsers, hotkeys or access to the real screen."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QKeyEvent, QPixmap
from PySide6.QtTest import QTest

from capture_client.draft import Draft
from capture_client.geometry import Monitor, Rect
from capture_client.qt_host import CaptureHost, KeyFilter, ScreenLayer, TOOLS
from capture_client.render import Annotation, render_capture


def context(step=10, revision=0):
    return {
        "valid": True, "session_id": "session", "case_id": 1, "step_id": step,
        "execution_generation": "generation", "result_revision": revision,
        "observed": f"Passo {step}", "steps": [], "case_name": "Login",
    }


class CaptureUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        with patch.object(CaptureHost, "_install_hotkey", new=lambda self: None):
            self.host = CaptureHost("http://127.0.0.1:1", "test-token")
        self.host.api = Mock()
        self.host.api.post.return_value = ({"error": "Serviço indisponível"}, 0)
        self.host.api.get.return_value = (context(), 200)
        self.host._apply_context(context(), force_text=True)

    def tearDown(self):
        self.host._close_editor()
        self.host.tools.close()
        self.host.dock.close()
        self.host.tools.deleteLater()
        self.host.dock.deleteLater()
        self.app.removeEventFilter(self.host.key_filter)
        self.host.deleteLater()
        self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def test_tools_have_icons_accessible_names_and_hover_labels_without_button_text(self):
        for index, (_key, label) in enumerate(TOOLS):
            button = self.host.tools.group.button(index)
            with self.subTest(label=label):
                self.assertEqual(button.text(), "")
                self.assertFalse(button.icon().isNull())
                self.assertEqual(button.accessibleName(), label)
                self.assertEqual(button.toolTip(), label)

    def test_selection_flushes_text_to_original_step_before_changing_target(self):
        self.host.dock.observed.setPlainText("Resultado do passo 10")
        self.host.api.post.side_effect = [
            ({"ok": True, "revision": 1, "actual": "Resultado do passo 10"}, 200),
            (context(11), 200),
        ]
        self.host.select_step(11)
        calls = self.host.api.post.call_args_list
        self.assertEqual(calls[0].args[0], "/api/captura/host/resultado")
        self.assertEqual(calls[0].args[1]["step_id"], 10)
        self.assertEqual(calls[0].args[1]["text"], "Resultado do passo 10")
        self.assertEqual(self.host.context["step_id"], 11)
        self.assertEqual(self.host.dock.observed.toPlainText(), "Passo 11")

    def test_remote_selection_does_not_retarget_pending_text_when_save_fails(self):
        self.host.dock.observed.setPlainText("Texto ainda local")
        self.host._apply_context(context(11), force_text=False)
        self.assertEqual(self.host.context["step_id"], 10)
        self.assertEqual(self.host.dock.observed.toPlainText(), "Texto ainda local")
        self.host.send_observed()
        self.assertEqual(self.host.api.post.call_args.args[1]["step_id"], 10)

    def test_pending_text_keeps_its_revision_when_remote_result_arrives(self):
        self.host.dock.observed.setPlainText("Minha edição")
        self.host._apply_context(context(revision=2), force_text=False)
        self.host.send_observed()
        self.assertEqual(self.host.api.post.call_args.args[1]["expected_revision"], 0)

    def test_cancel_closes_without_confirmation_or_waiting_for_the_service(self):
        self.host.dock.observed.setPlainText("Não perder")
        with patch("capture_client.qt_host.QMessageBox.question") as question:
            self.host.cancel()
        question.assert_not_called()
        self.host.api.post.assert_not_called()
        self.assertIsNone(self.host.context)

    def open_selection(self):
        self.host.base = Image.new("RGBA", (700, 550), "white")
        self.host.monitors = [Monitor("screen", 0, 0, 700, 550, 1, 0, 0, 700, 550)]
        pixmap = QPixmap(700, 550)
        pixmap.fill()
        layer = ScreenLayer(self.host, self.host.monitors[0], pixmap)
        self.host.layers = [layer]
        layer.show()
        self.host.draft = Draft(self.host.base, Rect(50, 50, 350, 280))
        self.host._set_chrome_visible(True)
        return layer

    def test_tools_stay_visible_during_drawing(self):
        self.open_selection()
        for tool in ("arrow", "rect", "circle", "free"):
            with self.subTest(tool=tool):
                self.host.tool = tool
                self.host.press((100, 100))
                self.host.move_to((170, 160))
                self.assertTrue(self.host.tools.isVisible())
                self.assertTrue(self.host.dock.isVisible())
                self.host.release((170, 160))
                self.assertTrue(self.host.tools.isVisible())
                self.assertTrue(self.host.dock.isVisible())

    def test_panels_hide_during_crop_adjustment_and_reappear_at_new_position(self):
        self.open_selection()
        for start, end in (((400, 330), (450, 350)), ((150, 150), (170, 170))):
            with self.subTest(start=start):
                previous = self.host.tools.pos()
                self.host.press(start)
                self.assertFalse(self.host.tools.isVisible())
                self.assertFalse(self.host.dock.isVisible())
                self.host.move_to(end)
                self.app.processEvents()
                self.assertFalse(self.host.tools.isVisible())
                self.assertFalse(self.host.dock.isVisible())
                self.host.release(end)
                self.app.processEvents()
                self.assertTrue(self.host.tools.isVisible())
                self.assertTrue(self.host.dock.isVisible())
                self.assertNotEqual(self.host.tools.pos(), previous)

    def test_attachment_highlights_only_the_confirmed_step_even_if_refresh_fails(self):
        self.open_selection()
        payload = context()
        payload["steps"] = [
            {"id": 10, "position": 1, "action": "Login", "selected": True},
            {"id": 11, "position": 2, "action": "Consulta", "selected": False},
        ]
        self.host._apply_context(payload, force_text=True)
        self.host.api.get.return_value = ({}, 0)
        self.host.attach()
        self.assertEqual(self.host.dock.steps.item(0).background().style(), Qt.BrushStyle.NoBrush)
        self.host.api.post.return_value = ({"ok": True, "step_position": 1}, 200)
        self.host.attach()
        self.assertNotEqual(self.host.dock.steps.item(0).background().style(), Qt.BrushStyle.NoBrush)
        self.assertEqual(self.host.dock.steps.item(1).background().style(), Qt.BrushStyle.NoBrush)
        self.assertIs(self.host.dock.steps.currentItem(), self.host.dock.steps.item(0))

    def test_copy_exports_final_image_then_closes_and_can_start_another_selection(self):
        self.open_selection()
        draft = self.host.draft
        draft.add(Annotation("arrow", "#E10600", [(100, 100), (220, 180)]))
        with patch("capture_client.qt_host.QApplication.clipboard") as clipboard:
            self.host.copy_image()
        exported = clipboard.return_value.setImage.call_args.args[0]
        self.assertEqual((exported.width(), exported.height()), (350, 280))
        self.assertEqual(self.host.layers, [])
        self.assertIsNone(self.host.draft)
        self.assertFalse(self.host.tools.isVisible())
        self.open_selection()
        self.assertTrue(self.host.tools.isVisible())

    def test_repeated_capture_after_copy_processes_window_destruction_and_keeps_every_tool_available(self):
        screen = Mock()
        screen.geometry.return_value = QRect(0, 0, 700, 550)
        screen.devicePixelRatio.return_value = 1
        pixmap = QPixmap(700, 550)
        pixmap.fill()
        screen.grabWindow.return_value = pixmap
        with patch("capture_client.qt_host.QGuiApplication.screens", return_value=[screen]), \
             patch("capture_client.qt_host._exclude", new=lambda widget: None), \
             patch.object(self.host, "_wait_clear", new=lambda: True), \
             patch("capture_client.qt_host.time.sleep"), \
             patch("capture_client.qt_host.QApplication.clipboard"):
            for cycle in range(20):
                with self.subTest(cycle=cycle):
                    self.host.begin()
                    self.app.processEvents()
                    self.host.press((50, 50))
                    self.host.move_to((400, 330))
                    self.host.release((400, 330))
                    self.app.processEvents()
                    self.host.press((400, 330))
                    self.host.move_to((420, 340))
                    self.assertFalse(self.host.tools.isVisible())
                    self.assertFalse(self.host.dock.isVisible())
                    self.host.release((420, 340))
                    self.app.processEvents()
                    for panel in (self.host.tools, self.host.dock):
                        self.assertTrue(panel.isVisible())
                        self.assertTrue(panel.isEnabled())
                        self.assertIs(panel.windowHandle().transientParent(), self.host.layers[0].windowHandle())
                        if os.name == "nt" and os.environ.get("QT_QPA_PLATFORM") == "windows":
                            import ctypes
                            from ctypes import wintypes
                            user32 = ctypes.windll.user32
                            user32.IsWindowVisible.argtypes = [wintypes.HWND]
                            self.assertTrue(user32.IsWindowVisible(int(panel.winId())))
                            user32.WindowFromPoint.argtypes = [wintypes.POINT]
                            user32.WindowFromPoint.restype = wintypes.HWND
                            user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
                            user32.GetAncestor.restype = wintypes.HWND
                            user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
                            bounds = wintypes.RECT()
                            self.assertTrue(user32.GetWindowRect(int(panel.winId()), ctypes.byref(bounds)))
                            center = wintypes.POINT((bounds.left + bounds.right) // 2,
                                                   (bounds.top + bounds.bottom) // 2)
                            top = user32.GetAncestor(user32.WindowFromPoint(center), 2)
                            self.assertEqual(int(top or 0), int(panel.winId()))
                    for index, (key, _label) in enumerate(TOOLS):
                        button = self.host.tools.group.button(index)
                        self.assertTrue(button.isEnabled())
                        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
                        self.assertEqual(self.host.tool, key)
                    selected_color = self.host.tools.color_group.checkedButton()
                    self.assertEqual(selected_color.property("color"), self.host.color)
                    QTest.mouseClick(self.host.tools.color_group.button(cycle % 6), Qt.MouseButton.LeftButton)
                    self.host.tool = "arrow"
                    self.host.press((100, 100))
                    self.host.move_to((220, 180))
                    self.host.release((220, 180))
                    if cycle % 2:
                        QTest.keyClick(self.host.layers[0], Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
                    else:
                        self.host.copy_image()
                    self.app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                    self.app.processEvents()
                    self.assertEqual(self.host.layers, [])

    def test_escape_closes_even_while_typing_without_a_question(self):
        self.open_selection()
        self.host.dock.observed.setFocus()
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        with patch("capture_client.qt_host.QMessageBox.question") as question:
            self.assertTrue(KeyFilter(self.host).eventFilter(self.host.dock.observed, event))
        question.assert_not_called()
        self.assertEqual(self.host.layers, [])

    def test_ctrl_c_copies_the_capture_and_closes(self):
        layer = self.open_selection()
        layer.setFocus()
        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
        with patch("capture_client.qt_host.QApplication.clipboard") as clipboard:
            self.assertTrue(KeyFilter(self.host).eventFilter(layer, event))
        clipboard.return_value.setImage.assert_called_once()
        self.assertEqual(self.host.layers, [])

    def test_text_is_typed_in_the_selection_and_included_by_copy_without_a_modal(self):
        self.open_selection()
        self.host.tool = "text"
        with patch("PySide6.QtWidgets.QInputDialog.getMultiLineText", return_value=("modal", False)) as modal:
            self.host.press((110, 100))
            modal.assert_not_called()
        editor = self.host.text_editor
        self.assertIsNotNone(editor)
        self.assertIs(editor.parentWidget(), self.host.layers[0])
        self.assertTrue(editor.fontMetrics().inFontUcs4(ord("ç")))
        editor.setPlainText("ação na imagem")
        self.app.processEvents()
        self.assertIs(self.host.text_editor, editor)
        draft = self.host.draft
        with patch("capture_client.qt_host.QApplication.clipboard"):
            self.host.copy_image()
        self.assertEqual(draft.annotations[-1].text, "ação na imagem")
        self.assertEqual(draft.annotations[-1].points, [(110, 100)])
        self.assertEqual(self.host.layers, [])

    def test_attach_commits_inline_text_and_keeps_editor_and_tools_open(self):
        self.open_selection()
        self.host._add_text((110, 100))
        self.host.text_editor.setPlainText("evidência")
        self.host.api.post.return_value = ({"ok": True, "step_position": 1}, 200)
        self.host.attach()
        self.assertIsNotNone(self.host.draft)
        self.assertEqual(self.host.draft.annotations[-1].text, "evidência")
        self.assertTrue(self.host.tools.isVisible())
        self.assertTrue(self.host.dock.isVisible())

    def test_enter_commits_inline_text_and_clicking_another_tool_keeps_it(self):
        self.open_selection()
        self.host._add_text((110, 100))
        self.host.text_editor.setPlainText("Primeiro")
        QTest.keyClick(self.host.text_editor, Qt.Key.Key_Return)
        self.assertIsNone(self.host.text_editor)
        self.host._add_text((110, 140))
        self.host.text_editor.setPlainText("Segundo")
        self.host.tools._choose(3)
        self.assertEqual([note.text for note in self.host.draft.annotations], ["Primeiro", "Segundo"])
        self.assertEqual(self.host.tool, "arrow")

    def test_panels_stay_on_screen_for_full_screen_crop(self):
        screen = self.app.primaryScreen().availableGeometry()
        width, height = screen.width(), screen.height()
        self.host.base = Image.new("RGBA", (width, height), "white")
        self.host.monitors = [Monitor("screen", 0, 0, width, height, 1,
                                      screen.x(), screen.y(), width, height)]
        self.host.draft = Draft(self.host.base, Rect(0, 0, width, height))
        self.host.tools.adjustSize()
        self.host.dock.adjustSize()
        self.host._place()
        self.assertTrue(screen.contains(self.host.tools.geometry()))
        self.assertTrue(screen.contains(self.host.dock.geometry()))

    @unittest.skipUnless(os.name == "nt", "Windows keeps native screen origins")
    def test_scaled_monitor_keeps_its_native_origin(self):
        screen = Mock()
        screen.geometry.return_value = QRect(-1920, 0, 1536, 864)
        screen.devicePixelRatio.return_value = 1.25
        pixmap = QPixmap(1920, 1080)
        pixmap.fill()
        screen.grabWindow.return_value = pixmap
        with patch("capture_client.qt_host.QGuiApplication.screens", return_value=[screen]), \
             patch("capture_client.qt_host._exclude", new=lambda widget: None):
            self.host._open_editor()
        self.assertEqual(self.host.monitors[0].origin_x, -1920)

    def test_rectangle_renders_in_every_drag_direction(self):
        base = Image.new("RGBA", (40, 40), "white")
        for start, end in [((4, 4), (30, 30)), ((30, 30), (4, 4)),
                           ((30, 4), (4, 30)), ((4, 30), (30, 4))]:
            with self.subTest(start=start, end=end):
                image = render_capture(base, Rect(0, 0, 40, 40),
                                       [Annotation("rect", "#E10600", [start, end])])
                self.assertEqual(image.getpixel((4, 12)), (225, 6, 0, 255))


if __name__ == "__main__":
    unittest.main()
