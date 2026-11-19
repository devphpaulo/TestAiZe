import hashlib
import unittest

from test_bugs_flow import BugsFixture
from testplayer import storage
from testplayer.web import create_app


class SessionBoardTests(BugsFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        with storage.db(self.directory) as connection, connection:
            connection.execute("UPDATE cases SET manual_status=''")
        self.app = create_app(self.root)
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["csrf_token"] = "test-token"
        self.headers = {"X-CSRF-Token": "test-token"}
        self.board_url = f"/api/sessao/{self.sid}/quadro"

    def move(self, destination, **options):
        snapshot = self.client.get(self.board_url).json
        return self.client.post(self.board_url, headers=self.headers, json={
            "destination": destination, "version": snapshot["version"], **options
        })

    def test_review_block_close_edit_copy_and_permanent_removal(self):
        for destination in ("todo", "doing", "review"):
            self.assertEqual(self.move(destination).status_code, 200)
        self.assertEqual(self.move("blocked").status_code, 422)
        self.assertEqual(self.move("blocked", reason="Ambiente indisponível").status_code, 200)
        self.assertEqual(self.move("doing").status_code, 422)
        self.assertEqual(self.move("review").status_code, 200)
        self.assertEqual(self.move("done").status_code, 422)
        stale = self.client.get(self.board_url).json["version"]
        storage.save_result(self.directory, 1, "aprovado", "Resultado registrado")
        self.assertEqual(self.move("done", confirmed=True, version=stale).status_code, 409)
        self.assertEqual(self.move("done", confirmed=True).status_code, 200)
        completed = storage.find_directory(self.root, self.sid)
        self.assertIsNotNone(completed)
        player_url = f"/sessao/{self.sid}"
        self.assertIn(b'data-writable="false"', self.client.get(player_url).data)
        step_url = f"/api/sessao/{self.sid}/passo/1"
        body = {"status": "reprovado", "actual": "Editado"}
        self.assertEqual(self.client.post(step_url, headers=self.headers, json=body).status_code, 409)
        native_url = "/api/captura/host/resultado"
        native_headers = {"X-Testaize-Capture": self.app.extensions["capture_broker"].token}
        native_body = {"session_id": self.sid, "case_id": 1, "step_id": 1,
                       "text": "Edição pela captura", "expected_revision": 1, "execution_generation": "generation"}
        self.assertEqual(self.client.post(native_url, headers=native_headers, json=native_body).status_code, 409)
        edit = self.client.post(player_url + "/editar", headers=self.headers, json={"confirmed": True})
        self.assertEqual(edit.status_code, 200)
        grant = edit.json["grant"]
        edit_headers = {**self.headers, "X-Session-Edit": grant}
        context = self.client.post("/api/captura/web/contexto", headers=edit_headers,
                                   json={**native_body, "event_id": "select-after-edit"})
        native_body["context_revision"] = context.json["context_revision"]
        self.assertEqual(self.client.post(native_url, headers=native_headers, json=native_body).status_code, 200)
        self.assertEqual(self.client.post(step_url, headers=edit_headers, json=body).status_code, 200)
        self.client.post(player_url + "/encerrar-edicao", headers=edit_headers, json={})
        self.assertEqual(self.client.post(step_url, headers=edit_headers, json=body).status_code, 409)
        self.assertEqual(self.client.post(native_url, headers=native_headers, json=native_body).status_code, 409)
        self.client.post(player_url + "/nova-execucao", headers=self.headers)
        cards = storage.board_sessions(self.root)
        copied = next(card for card in cards if card["id"] != self.sid)
        self.assertEqual((copied["phase"], copied["parent_id"], copied["counts"]["aprovado"]), ("backlog", self.sid, 0))
        self.assertEqual(self.client.get(self.board_url).json["phase"], "done")
        self.client.post(player_url + "/excluir", headers=self.headers, data={"action": "delete"})
        self.assertFalse(completed.exists())
        self.assertIsNone(storage.find_directory(self.root, self.sid))

    def test_indirect_status_promotes_backlog_and_migration_is_repeatable(self):
        storage.save_result(self.directory, 1, "nao_executado", "Só texto")
        self.assertEqual(self.client.get(self.board_url).json["phase"], "backlog")
        bug = self.create_bug()
        self.service.link(bug["id"], self.sid, [1])
        self.assertEqual(self.client.get(self.board_url).json["phase"], "todo")
        self.assertEqual(self.move("doing").status_code, 200)
        storage.migrate_sessions(self.root)
        self.assertEqual(self.client.get(self.board_url).json["phase"], "doing")

    def test_status_replication_only_moves_when_a_target_status_changes(self):
        image = self.directory / "evidencias" / "source.png"
        image.parent.mkdir(exist_ok=True)
        image.write_bytes(self.image)
        with storage.db(self.directory) as connection, connection:
            connection.execute("UPDATE results SET status='aprovado',status_changed_at=? WHERE step_id IN (1,2)",
                               (storage.now(),))
            connection.execute("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?)",
                               ("source", 1, "evidencias/source.png", "source.png", "image/png", len(self.image),
                                hashlib.sha256(self.image).hexdigest(), storage.now()))
        storage.sync_step_evidence(self.directory, 1, [2], replicate_status=True)
        storage.sync_step_evidence(self.directory, 1, [3], replicate_status=False)
        self.assertEqual(storage.read_board_card(self.directory)["phase"], "backlog")
        storage.sync_step_evidence(self.directory, 1, [3], replicate_status=True)
        self.assertEqual(storage.read_board_card(self.directory)["phase"], "todo")

    def test_legacy_results_and_manual_approval_use_player_status(self):
        with storage.db(self.directory) as connection, connection:
            connection.execute("DELETE FROM meta WHERE key='board_phase'")
            connection.execute("UPDATE results SET actual='Resultado legado' WHERE step_id=1")
        storage.migrate_sessions(self.root)
        self.assertEqual(storage.read_board_card(self.directory)["phase"], "todo")
        storage.set_case_status(self.directory, 1, "aprovado", 0, "generation")
        self.assertEqual(storage.read_board_card(self.directory)["counts"]["aprovado"], 1)
        for case_id in (2, 3):
            storage.set_case_status(self.directory, case_id, "aprovado", 0, "generation")
        self.assertEqual(self.move("doing").status_code, 200)
        self.assertEqual(self.move("review").status_code, 200)
        self.assertEqual(self.move("done").status_code, 422)
        self.assertEqual(self.move("done", confirmed=True).json["counts"]["aprovado"], 3)
