"""Capture geometry, persistence, idempotency and the local authenticated channel."""

from __future__ import annotations

import base64
import io
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from capture_client.bitmap import stitch_bitmaps
from capture_client.chrome import decorate_crop
from capture_client.draft import Draft
from capture_client.geometry import Monitor, Rect, normalize_rect, resize_rect, stitch_origin, tool_side
from capture_client.overlay import escape_action, live_screen_during, show_capture_chrome
from capture_client.hotkey import (
    MOD_CONTROL,
    MOD_SHIFT,
    Hotkey,
    hotkey_label,
    load_hotkey,
    save_hotkey,
    try_register,
    try_unregister,
    valid_hotkey,
)
from capture_client.render import Annotation, render_capture
from testplayer.capture_service import (
    CaptureError,
    cleanup_capture_temporaries,
    commit_capture,
    replace_observed_text,
    save_observed_text,
)
from testplayer.html_export import render_report_html
from testplayer.storage import (
    SCHEMA,
    RevisionConflict,
    StaleExecution,
    migrate_sessions,
    read_session,
    start_case_run,
)
from testplayer.web import create_app


def _png(color: tuple[int, int, int], size: tuple[int, int] = (24, 16)) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class GeometryRenderTests(unittest.TestCase):
    def test_negative_monitor_origin_and_crop_resize_keep_annotations_in_bitmap_space(self):
        left = Monitor("left", -1920, 0, 1920, 1080, 1.0, dip_x=-1920, dip_y=0, dip_w=1920, dip_h=1080)
        right = Monitor("right", 0, 0, 1280, 800, 1.25, dip_x=0, dip_y=0, dip_w=1024, dip_h=640)
        self.assertEqual(stitch_origin([right, left]), (-1920, 0))
        base = stitch_bitmaps([
            (Image.new("RGBA", (left.width, left.height), (10, 10, 10, 255)), left),
            (Image.new("RGBA", (right.width, right.height), (240, 240, 240, 255)), right),
        ])
        crop = Rect(1900, 10, 80, 40)
        resized = resize_rect(crop, "e", 20, 0, base.width, base.height)
        self.assertEqual((resized.x, resized.y), (crop.x, crop.y))
        note = Annotation("arrow", "#E10600", [(1910, 20), (1960, 40)])
        rendered = render_capture(base, resized, [note])
        self.assertEqual(rendered.size, (resized.width, resized.height))
        self.assertIn((225, 6, 0, 255), rendered.get_flattened_data())
        decorated = decorate_crop(rendered)
        self.assertGreater(decorated.width, rendered.width)
        self.assertEqual(tool_side(Rect(0, 0, base.width - 10, 20), base.width, 150), "inside")

    def test_tools_wait_for_a_region_and_escape_walks_the_selection_back(self):
        self.assertFalse(show_capture_chrome(False))
        self.assertTrue(show_capture_chrome(True))
        self.assertTrue(live_screen_during("new"))
        self.assertTrue(live_screen_during("move"))
        self.assertTrue(live_screen_during("se"))
        self.assertFalse(live_screen_during("rect"))
        self.assertFalse(live_screen_during(None))
        self.assertEqual(escape_action(True, False), "clear_gesture")
        self.assertEqual(escape_action(False, True), "clear_region")
        self.assertEqual(escape_action(False, False), "leave")

    def test_empty_region_is_rejected_and_undo_restores_the_previous_drawing(self):
        self.assertIsNone(normalize_rect(0, 0, 1, 8))
        base = Image.new("RGBA", (40, 40), (255, 255, 255, 255))
        draft = Draft(base, Rect(2, 2, 30, 30))
        draft.add(Annotation("rect", "#0000FF", [(4, 4), (20, 20)]))
        draft.color = "#E10600"
        first = draft.png()
        draft.add(Annotation("text", "#111111", [(6, 8)], "ação"))
        self.assertNotEqual(draft.png(), first)
        self.assertTrue(draft.undo())
        self.assertEqual(draft.png(), first)
        self.assertEqual(draft.annotations[0].color, "#0000FF")
        blue = render_capture(base, draft.crop, draft.annotations)
        self.assertIn((0, 0, 255, 255), blue.get_flattened_data())

    def test_hotkey_conflict_does_not_claim_success(self):
        calls = []

        def register(hwnd, hotkey_id, modifiers, virtual_key):
            calls.append((hwnd, hotkey_id, modifiers, virtual_key))
            return 0

        ok, code = try_register(register, 7)
        self.assertFalse(ok)
        self.assertEqual(code, "HOTKEY_CONFLICT")
        self.assertEqual(calls[0], (7, 1, 0x4000, 0x2C))
        removed = []
        try_unregister(lambda hwnd, hotkey_id: removed.append((hwnd, hotkey_id)), 7)
        self.assertEqual(removed, [(7, 1)])
        calls.clear()

        def remember(hwnd, hotkey_id, modifiers, virtual_key):
            calls.append((hwnd, hotkey_id, modifiers, virtual_key))
            return 1

        page_up = Hotkey(0x21, MOD_SHIFT)
        ok, code = try_register(remember, 7, page_up)
        self.assertTrue(ok)
        self.assertEqual(code, "")
        self.assertEqual(calls[0], (7, 1, 0x4004, 0x21))
        self.assertEqual(hotkey_label(Hotkey(0x41, MOD_CONTROL | MOD_SHIFT)), "Ctrl + Shift + A")
        self.assertEqual(hotkey_label(Hotkey(0x2C, MOD_SHIFT)), "Shift + PrintScreen")
        self.assertFalse(valid_hotkey(Hotkey(0x11, 0)))

    def test_saved_shortcut_survives_and_invalid_file_keeps_print_screen(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            save_hotkey(root, Hotkey(0x21, 0))
            self.assertEqual(load_hotkey(root), Hotkey(0x21, 0))
            path = root / "config" / "atalho-captura.json"
            path.write_text("{", encoding="utf-8")
            self.assertEqual(load_hotkey(root), Hotkey(0x2C, 0))


class CapturePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.session_id = uuid.uuid4().hex
        self.directory = self.root / "rascunhos" / self.session_id
        (self.directory / "evidencias").mkdir(parents=True)
        (self.directory / "relatorios").mkdir()
        self.generation = uuid.uuid4().hex
        with closing(sqlite3.connect(self.directory / "sessao.sqlite")) as connection:
            connection.executescript(SCHEMA)
            connection.executemany("INSERT INTO meta(key,value) VALUES (?,?)", [
                ("id", self.session_id), ("state", "rascunho"),
                ("created_at", "2026-10-31T12:00:00-03:00"), ("source_name", "casos.csv"),
            ])
            connection.execute(
                "INSERT INTO cases(id,position,sheet,source_row,name,precondition,source_status,priority,folder,"
                "execution_generation) VALUES (1,1,'Planilha',2,'Login','','Novo','Alta','/Produto',?)",
                (self.generation,),
            )
            connection.execute(
                "INSERT INTO steps(id,case_id,position,action,test_data,expected) VALUES (10,1,1,'Realizar login','dados','esperado')"
            )
            connection.execute(
                "INSERT INTO results(step_id,status,actual,actual_doc) VALUES (10,'em_andamento','texto inicial','')"
            )
            connection.commit()

    def tearDown(self):
        self.temporary.cleanup()

    def _attach(self, command_id: str, content: bytes, generation: str | None = None, revision: int = 0):
        return commit_capture(
            self.directory, command_id=command_id, step_id=10, case_id=1,
            execution_generation=generation or self.generation, expected_revision=revision,
            render_revision="render-1", content=content,
        )

    def test_attach_is_idempotent_preserves_status_and_reappears_in_the_report(self):
        content = _png((20, 40, 60))
        first = self._attach("command-one-1", content)
        second = self._attach("command-one-1", content, revision=first["revision"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["evidence_id"], first["evidence_id"])
        self.assertEqual(first["status"], "em_andamento")
        record = read_session(self.directory)
        step = record["cases"][0]["steps"][0]
        self.assertEqual(len(step["evidence"]), 1)
        self.assertEqual(step["actual"], "texto inicial")
        self.assertIn(first["evidence_id"], [block["id"] for block in step["actual_blocks"] if block["type"] == "image"])
        html = render_report_html(self.directory, {1})
        self.assertIn("data:image/png;base64,", html)
        saved = save_observed_text(self.directory, 10, "viu a ação", first["revision"], self.generation)
        self.assertEqual(saved["status"], "em_andamento")
        blocks = json.loads(read_session(self.directory)["cases"][0]["steps"][0]["actual_doc"])
        self.assertIn(first["evidence_id"], [block["id"] for block in blocks if block["type"] == "image"])
        self.assertIn("viu a ação", [block["text"] for block in blocks if block["type"] == "text"])

    def test_same_command_with_other_bytes_does_not_overwrite(self):
        self._attach("command-two-2", _png((1, 2, 3)))
        with self.assertRaises(CaptureError) as caught:
            self._attach("command-two-2", _png((9, 9, 9)), revision=1)
        self.assertEqual(caught.exception.code, "IDEMPOTENCY_CONFLICT")
        self.assertEqual(len(read_session(self.directory)["cases"][0]["steps"][0]["evidence"]), 1)

    def test_stale_revision_keeps_the_previous_text(self):
        save_observed_text(self.directory, 10, "primeiro", 0, self.generation)
        with self.assertRaises(Exception):
            save_observed_text(self.directory, 10, "atrasado", 0, self.generation)
        self.assertEqual(read_session(self.directory)["cases"][0]["steps"][0]["actual"], "primeiro")

    def test_retest_invalidates_the_old_generation_and_keeps_history(self):
        saved = self._attach("command-run-03", _png((4, 5, 6)))
        evidence_id = saved["evidence_id"]
        start_case_run(self.directory, 1)
        with self.assertRaises(StaleExecution):
            self._attach("command-run-04", _png((7, 8, 9)), generation=self.generation, revision=0)
        current = read_session(self.directory)["cases"][0]
        self.assertNotEqual(current["execution_generation"], self.generation)
        self.assertEqual(current["steps"][0]["evidence"], [])
        self.assertEqual(current["previous_runs"][0]["snapshot"]["steps"][0]["evidence"][0]["id"], evidence_id)
        fresh = self._attach("command-run-05", _png((7, 8, 9)), generation=current["execution_generation"], revision=0)
        self.assertFalse(fresh["duplicate"])

    def test_concurrent_requests_stop_at_twelve_images(self):
        with closing(sqlite3.connect(self.directory / "sessao.sqlite")) as connection:
            for index in range(11):
                connection.execute(
                    "INSERT INTO evidence(id,step_id,relative_path,original_name,mime,size,sha256,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (f"existing-{index}", 10, f"evidencias/caso-1/passo-1/existing-{index}.png",
                     "antes.png", "image/png", 3, f"{index:064d}", f"2026-10-31T12:00:{index:02d}-03:00"),
                )
            connection.commit()
        barrier = threading.Barrier(2)
        results: list[BaseException | dict] = []

        def attempt(command_id: str):
            barrier.wait()
            try:
                results.append(self._attach(command_id, _png((8, 0, 0), (8, 8))))
            except (CaptureError, RevisionConflict) as exc:
                results.append(exc)

        threads = [
            threading.Thread(target=attempt, args=("command-limit-1",)),
            threading.Thread(target=attempt, args=("command-limit-2",)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(read_session(self.directory)["cases"][0]["steps"][0]["evidence"]), 12)
        self.assertEqual(len(results), 2)
        self.assertEqual(sum(isinstance(item, dict) for item in results), 1)
        self.assertTrue(any(
            isinstance(item, CaptureError) and item.code == "IMAGE_LIMIT"
            or isinstance(item, RevisionConflict)
            for item in results
        ))

    def test_text_replacement_keeps_image_order(self):
        blocks = replace_observed_text(
            [{"type": "text", "text": "antes"}, {"type": "image", "id": "img", "width": 80}, {"type": "text", "text": "depois"}],
            "linha 1\nlinha 2",
        )
        self.assertEqual([block["type"] for block in blocks], ["text", "image", "text"])
        self.assertEqual(blocks[1]["id"], "img")

    def test_repeated_migration_keeps_the_assigned_generation(self):
        legacy_id = uuid.uuid4().hex
        legacy = self.root / "rascunhos" / legacy_id
        legacy.mkdir()
        with closing(sqlite3.connect(legacy / "sessao.sqlite")) as connection:
            connection.executescript("""
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE cases (
                  id INTEGER PRIMARY KEY, position INTEGER NOT NULL UNIQUE, sheet TEXT NOT NULL,
                  source_row INTEGER NOT NULL, name TEXT NOT NULL, precondition TEXT NOT NULL,
                  source_status TEXT NOT NULL, priority TEXT NOT NULL, folder TEXT NOT NULL
                );
                CREATE TABLE steps (
                  id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL, position INTEGER NOT NULL,
                  action TEXT NOT NULL, test_data TEXT NOT NULL, expected TEXT NOT NULL
                );
                CREATE TABLE results (
                  step_id INTEGER PRIMARY KEY, status TEXT NOT NULL DEFAULT 'nao_executado',
                  actual TEXT NOT NULL DEFAULT '', comment TEXT NOT NULL DEFAULT '', updated_at TEXT
                );
                CREATE TABLE evidence (
                  id TEXT PRIMARY KEY, step_id INTEGER NOT NULL, relative_path TEXT NOT NULL UNIQUE,
                  original_name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL,
                  sha256 TEXT NOT NULL, created_at TEXT NOT NULL
                );
                INSERT INTO meta(key,value) VALUES ('id', 'legacy'), ('state','rascunho'),
                  ('created_at','2026-01-01T00:00:00-03:00'), ('source_name','legado.csv');
                INSERT INTO cases(id,position,sheet,source_row,name,precondition,source_status,priority,folder)
                  VALUES (1,1,'A',2,'Caso','','','','/Pasta');
                INSERT INTO steps(id,case_id,position,action,test_data,expected) VALUES (3,1,1,'Agir','','');
                INSERT INTO results(step_id) VALUES (3);
            """)
            connection.execute("UPDATE meta SET value=? WHERE key='id'", (legacy_id,))
            connection.commit()
        migrate_sessions(self.root)
        migrate_sessions(self.root)
        record = read_session(legacy)
        generation = record["cases"][0]["execution_generation"]
        self.assertTrue(generation)
        self.assertEqual(record["cases"][0]["steps"][0]["revision"], 0)
        self.assertEqual(read_session(legacy)["cases"][0]["execution_generation"], generation)
        leftover = self.directory / "evidencias" / "caso-1" / "orphan.tmp"
        leftover.parent.mkdir(parents=True, exist_ok=True)
        leftover.write_bytes(b"tmp")
        cleanup_capture_temporaries(self.directory)
        self.assertFalse(leftover.exists())


class CaptureRouteTests(unittest.TestCase):
    def setUp(self):
        self.persistence = CapturePersistenceTests()
        self.persistence.setUp()
        self.app = create_app(self.persistence.root)
        self.app.testing = True
        self.client = self.app.test_client()
        self.token = self.app.extensions["capture_broker"].token

    def tearDown(self):
        self.persistence.tearDown()

    def _csrf(self) -> str:
        self.client.get("/")
        with self.client.session_transaction() as browser_session:
            return browser_session["csrf_token"]

    def test_host_is_rejected_without_capability_and_web_keeps_csrf(self):
        self.assertEqual(self.client.post("/api/captura/host/ping", json={"hotkey": True}).status_code, 403)
        self.assertEqual(self.client.post("/api/captura/web/contexto", json={}).status_code, 400)
        csrf = self._csrf()
        session_id = self.persistence.session_id
        published = self.client.post("/api/captura/web/contexto", json={
            "session_id": session_id, "case_id": 1, "step_id": 10,
            "execution_generation": self.persistence.generation,
            "client_id": "player-test", "event_id": "event-player-01",
        }, headers={"X-CSRF-Token": csrf})
        self.assertEqual(published.status_code, 200)
        self.assertTrue(published.get_json()["valid"])
        context = self.client.get("/api/captura/host/contexto", headers={"X-Testaize-Capture": self.token})
        self.assertEqual(context.status_code, 200)
        self.assertEqual(context.get_json()["step_id"], 10)
        self.assertNotIn(self.token, json.dumps(context.get_json()))

    def test_attach_endpoint_confirms_only_after_persistence_and_retries(self):
        csrf = self._csrf()
        session_id = self.persistence.session_id
        self.client.post("/api/captura/web/contexto", json={
            "session_id": session_id, "case_id": 1, "step_id": 10,
            "execution_generation": self.persistence.generation,
            "client_id": "player-test", "event_id": "event-player-02",
        }, headers={"X-CSRF-Token": csrf})
        body = {
            "command_id": "command-route-1",
            "session_id": session_id,
            "case_id": 1,
            "step_id": 10,
            "execution_generation": self.persistence.generation,
            "expected_revision": 0,
            "render_revision": "7",
            "image_base64": base64.b64encode(_png((30, 30, 30))).decode("ascii"),
        }
        headers = {"X-Testaize-Capture": self.token}
        first = self.client.post("/api/captura/host/anexar", json=body, headers=headers)
        second = self.client.post("/api/captura/host/anexar", json=body, headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(first.get_json()["duplicate"])
        self.assertTrue(second.get_json()["duplicate"])
        self.assertEqual(first.get_json()["evidence_id"], second.get_json()["evidence_id"])
        self.assertEqual(first.get_json()["status"], "em_andamento")
        events = self.client.get("/api/captura/web/eventos?after=0&client_id=player-test", headers={"X-CSRF-Token": csrf})
        self.assertTrue(any(item["type"] == "evidence" for item in events.get_json()["events"]))
        operation = self.client.get(
            f"/api/captura/host/operacao/command-route-1?session_id={session_id}", headers=headers,
        )
        self.assertEqual(operation.get_json()["evidence_id"], first.get_json()["evidence_id"])

    def test_prepare_waits_for_the_open_player(self):
        headers = {"X-Testaize-Capture": self.token}
        csrf = self._csrf()
        self.client.get("/api/captura/web/eventos?after=0&client_id=player-open", headers={"X-CSRF-Token": csrf})
        prepared = self.client.post("/api/captura/host/preparar", json={}, headers=headers)
        request_id = prepared.get_json()["request_id"]
        waiting = self.client.get(f"/api/captura/host/preparar?request_id={request_id}", headers=headers)
        self.assertFalse(waiting.get_json()["ready"])
        self.client.post("/api/captura/web/preparado", json={"request_id": request_id, "client_id": "player-open"},
                         headers={"X-CSRF-Token": csrf})
        ready = self.client.get(f"/api/captura/host/preparar?request_id={request_id}", headers=headers)
        self.assertTrue(ready.get_json()["ready"])

    def test_tray_requests_a_shortcut_and_the_player_learns_its_name(self):
        headers = {"X-Testaize-Capture": self.token}
        self.assertEqual(self.client.get("/api/captura/host/atalho").status_code, 403)
        broker = self.app.extensions["capture_broker"]
        broker.request_hotkey_record()
        pending = self.client.get("/api/captura/host/atalho", headers=headers)
        self.assertTrue(pending.get_json()["record"])
        self.assertEqual(pending.get_json()["label"], "PrintScreen")
        accepted = self.client.post("/api/captura/host/atalho", headers=headers)
        self.assertEqual(accepted.status_code, 200)
        self.assertFalse(self.client.get("/api/captura/host/atalho", headers=headers).get_json()["record"])
        ping = self.client.post("/api/captura/host/ping", json={"hotkey": True, "label": "Ctrl + Shift + A"}, headers=headers)
        self.assertEqual(ping.status_code, 200)
        csrf = self._csrf()
        events = self.client.get("/api/captura/web/eventos?after=0&client_id=player-label", headers={"X-CSRF-Token": csrf})
        self.assertEqual(events.get_json()["hotkey_label"], "Ctrl + Shift + A")
        self.assertTrue(events.get_json()["hotkey"])


if __name__ == "__main__":
    unittest.main()
