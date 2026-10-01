from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from testplayer.storage import (
    SCHEMA,
    db,
    find_sync_targets,
    normalize_step_description,
    read_session,
    sync_step_evidence,
)
try:
    from testplayer.web import create_app
except ModuleNotFoundError as import_error:
    create_app = None
    WEB_IMPORT_ERROR = str(import_error)
else:
    WEB_IMPORT_ERROR = ""


class SyncStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.session_id = "0123456789abcdef0123456789abcdef"
        self.directory = self.root / "rascunhos" / self.session_id
        (self.directory / "evidencias").mkdir(parents=True)
        with closing(sqlite3.connect(self.directory / "sessao.sqlite")) as connection:
            connection.executescript(SCHEMA)
            connection.executemany("INSERT INTO meta(key,value) VALUES (?,?)", [
                ("id", self.session_id), ("state", "rascunho"),
                ("created_at", "2026-09-30T10:00:00+00:00"), ("source_name", "casos.csv"),
            ])
            for position, folder, name, manual in (
                (1, "Ciclo A", "Origem", ""),
                (2, "Ciclo B", "Destino B", ""),
                (3, "Ciclo A", "Destino A", "bloqueado"),
            ):
                connection.execute(
                    "INSERT INTO cases(id,position,sheet,source_row,name,precondition,source_status,priority,folder,manual_status) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (position, position, "Planilha", position + 1, name, "", "", "", folder, manual),
                )
            steps = (
                (11, 1, 1, "Realizar login na aplicação"),
                (21, 2, 1, "Realizar login na aplicacao"),
                (22, 2, 2, "Outro passo"),
                (31, 3, 1, "  REALIZAR\tlogin na aplicação\n"),
            )
            for step_id, case_id, position, action in steps:
                connection.execute(
                    "INSERT INTO steps(id,case_id,position,action,test_data,expected) VALUES (?,?,?,?,?,?)",
                    (step_id, case_id, position, action, "dados", "esperado"),
                )
                status = "aprovado" if step_id == 11 else "nao_executado"
                changed = "2026-09-30T10:02:00+00:00" if step_id == 11 else None
                actual = "texto da origem" if step_id == 11 else "texto preservado"
                connection.execute(
                    "INSERT INTO results(step_id,status,actual,actual_doc,updated_at,status_changed_at) VALUES (?,?,?,?,?,?)",
                    (step_id, status, actual, None, changed, changed),
                )
            self._add_evidence(connection, "source-a", 11, b"imagem-a", ".png", "a.png",
                               "2026-09-30T10:03:00+00:00")
            self._add_evidence(connection, "source-b", 11, b"imagem-b", ".webp", "b.webp",
                               "2026-09-30T10:04:00+00:00")
            self._add_evidence(connection, "existing", 21, b"existente", ".jpg", "existente.jpg",
                               "2026-09-30T10:01:00+00:00")
            connection.execute(
                "UPDATE results SET actual_doc=? WHERE step_id=11",
                (json.dumps([
                    {"type": "text", "text": "texto da origem"},
                    {"type": "image", "id": "source-a", "width": 45},
                    {"type": "image", "id": "source-b", "width": 80},
                ]),),
            )
            connection.commit()

    def tearDown(self):
        self.temporary.cleanup()

    def _add_evidence(self, connection, evidence_id, step_id, content, suffix, name, created_at):
        case_id, position = connection.execute(
            "SELECT case_id,position FROM steps WHERE id=?", (step_id,)
        ).fetchone()
        relative = Path("evidencias") / f"caso-{case_id}" / f"passo-{position}" / f"{evidence_id}{suffix}"
        target = self.directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        connection.execute(
            "INSERT INTO evidence(id,step_id,relative_path,original_name,mime,size,sha256,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (evidence_id, step_id, relative.as_posix(), name, f"image/{suffix[1:]}", len(content),
             hashlib.sha256(content).hexdigest(), created_at),
        )

    def evidence(self, step_id):
        with db(self.directory) as connection:
            return [dict(row) for row in connection.execute(
                "SELECT * FROM evidence WHERE step_id=? ORDER BY created_at,id", (step_id,)
            )]

    def test_normalization_is_deterministic(self):
        expected = "realizar login na aplicacao!"
        for value in ("Realizar login na aplicação!", " realizar  LOGIN na aplicacao! ",
                      "REALIZAR\nlogin\tna aplicação!"):
            self.assertEqual(normalize_step_description(value), expected)
        self.assertEqual(normalize_step_description("  \n\t "), "")
        self.assertNotEqual(normalize_step_description("Realizar login?"),
                            normalize_step_description("Realizar login!"))

    def test_matching_crosses_folders_keeps_order_and_excludes_source(self):
        preview = find_sync_targets(self.directory, 11)
        self.assertEqual([item["step_id"] for item in preview["targets"]], [21, 31])
        self.assertEqual([item["folder"] for item in preview["targets"]], ["Ciclo B", "Ciclo A"])
        self.assertEqual([item["has_evidence"] for item in preview["targets"]], [True, False])
        self.assertEqual(preview["origin"]["evidence_count"], 2)

    def test_sync_appends_independent_images_in_order_without_status(self):
        result = sync_step_evidence(self.directory, 11, [21], replicate_status=False)
        self.assertEqual(result["synced"], 1)
        items = self.evidence(21)
        self.assertEqual([item["original_name"] for item in items], ["existente.jpg", "a.png", "b.webp"])
        self.assertEqual([Path(item["relative_path"]).suffix for item in items], [".jpg", ".png", ".webp"])
        self.assertEqual([(item["size"], item["sha256"]) for item in items[1:]],
                         [(len(b"imagem-a"), hashlib.sha256(b"imagem-a").hexdigest()),
                          (len(b"imagem-b"), hashlib.sha256(b"imagem-b").hexdigest())])
        self.assertNotEqual(items[1]["relative_path"], self.evidence(11)[0]["relative_path"])
        (self.directory / self.evidence(11)[0]["relative_path"]).write_bytes(b"alterada")
        self.assertEqual((self.directory / items[1]["relative_path"]).read_bytes(), b"imagem-a")
        with db(self.directory) as connection:
            row = connection.execute("SELECT status,actual,actual_doc FROM results WHERE step_id=21").fetchone()
        self.assertEqual(row["status"], "nao_executado")
        self.assertEqual(row["actual"], "texto preservado")
        blocks = json.loads(row["actual_doc"])
        self.assertEqual([block.get("text") for block in blocks if block["type"] == "text"], ["texto preservado", ""])
        self.assertEqual([block.get("width") for block in blocks if block["type"] == "image"][-2:], [45, 80])

    def test_sync_copies_one_evidence(self):
        source_b = self.directory / self.evidence(11)[1]["relative_path"]
        with db(self.directory) as connection:
            with connection:
                connection.execute("DELETE FROM evidence WHERE id='source-b'")
        source_b.unlink()
        sync_step_evidence(self.directory, 11, [31])
        copied = self.evidence(31)
        self.assertEqual(len(copied), 1)
        self.assertEqual(copied[0]["original_name"], "a.png")

    def test_optional_status_uses_aggregate_and_preserves_manual_override(self):
        sync_step_evidence(self.directory, 11, [21, 31], replicate_status=True)
        record = read_session(self.directory)
        cases = {case["id"]: case for case in record["cases"]}
        self.assertEqual(cases[2]["steps"][0]["status"], "aprovado")
        self.assertEqual(cases[2]["status"], "em_andamento")
        self.assertEqual(cases[3]["steps"][0]["status"], "aprovado")
        self.assertEqual(cases[3]["status"], "bloqueado")

    def test_invalid_source_destination_and_limit_do_not_write(self):
        with db(self.directory) as connection:
            with connection:
                connection.execute("UPDATE results SET status_changed_at=NULL WHERE step_id=11")
        with self.assertRaises(ValueError):
            find_sync_targets(self.directory, 11)
        with db(self.directory) as connection:
            with connection:
                connection.execute("UPDATE results SET status_changed_at=? WHERE step_id=11", ("2026-09-30",))
        for targets in ([], [11], [22], [21, 21], [999]):
            with self.assertRaises((ValueError, LookupError)):
                sync_step_evidence(self.directory, 11, targets)
        with db(self.directory) as connection:
            with connection:
                for index in range(10):
                    self._add_evidence(connection, f"extra-{index}", 21, str(index).encode(), ".png",
                                       f"extra-{index}.png", f"2026-09-30T11:{index:02d}:00+00:00")
        with self.assertRaises(ValueError):
            sync_step_evidence(self.directory, 11, [21])
        self.assertEqual(len(self.evidence(21)), 11)

    def test_missing_source_file_is_rejected(self):
        (self.directory / self.evidence(11)[0]["relative_path"]).unlink()
        with self.assertRaisesRegex(ValueError, "indisponível"):
            find_sync_targets(self.directory, 11)

    def test_copy_failure_rolls_back_database_and_files(self):
        before = {path.relative_to(self.directory) for path in self.directory.rglob("*") if path.is_file()}
        real_copy = shutil.copy2
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("falha simulada")
            return real_copy(source, target)

        with patch("testplayer.storage.shutil.copy2", side_effect=fail_second):
            with self.assertRaises(OSError):
                sync_step_evidence(self.directory, 11, [31])
        self.assertEqual(self.evidence(31), [])
        after = {path.relative_to(self.directory) for path in self.directory.rglob("*") if path.is_file()}
        self.assertEqual(after, before)

    @unittest.skipUnless(create_app, f"Dependências web indisponíveis: {WEB_IMPORT_ERROR}")
    def test_preview_and_confirmation_endpoints_require_csrf(self):
        app = create_app(self.root)
        app.testing = True
        client = app.test_client()
        self.assertEqual(client.get(f"/sessao/{self.session_id}").status_code, 200)
        preview = client.get(f"/api/sessao/{self.session_id}/passo/11/sincronizacao")
        self.assertEqual(preview.status_code, 200)
        self.assertEqual([item["step_id"] for item in preview.get_json()["targets"]], [21, 31])
        payload = {"target_step_ids": [31], "replicate_status": False}
        self.assertEqual(client.post(
            f"/api/sessao/{self.session_id}/passo/11/sincronizacao", json=payload
        ).status_code, 400)
        with client.session_transaction() as browser_session:
            token = browser_session["csrf_token"]
        invalid_endpoints = (
            f"/api/sessao/{self.session_id}/passo/11",
            f"/api/sessao/{self.session_id}/caso/1",
            f"/api/sessao/{self.session_id}/passo/11/sincronizacao",
        )
        for endpoint in invalid_endpoints:
            for invalid_body in ([], "destino", 31):
                invalid = client.post(endpoint, json=invalid_body, headers={"X-CSRF-Token": token})
                self.assertEqual(invalid.status_code, 400)
                self.assertEqual(invalid.get_json()["error"], "Envie um objeto JSON válido.")
        response = client.post(
            f"/api/sessao/{self.session_id}/passo/11/sincronizacao", json=payload,
            headers={"X-CSRF-Token": token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["synced"], 1)


if __name__ == "__main__":
    unittest.main()
