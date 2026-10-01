from __future__ import annotations

import json
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from html.parser import HTMLParser
from pathlib import Path

import pymupdf

from testplayer.html_export import generate_html, render_report_html
from testplayer.pdf_export import _browser_path, generate_pdf
from testplayer.storage import (
    SCHEMA,
    db,
    delete_folder_link,
    migrate_sessions,
    read_session,
    save_folder_link,
)
from testplayer.web import create_app, folder_card_details, folder_groups


# Copied from HEAD:testplayer/storage.py, the complete schema immediately before folder_links.
LEGACY_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY, position INTEGER NOT NULL UNIQUE, sheet TEXT NOT NULL,
  source_row INTEGER NOT NULL, name TEXT NOT NULL, precondition TEXT NOT NULL,
  source_status TEXT NOT NULL, priority TEXT NOT NULL, folder TEXT NOT NULL,
  manual_status TEXT NOT NULL DEFAULT '', comment TEXT NOT NULL DEFAULT '',
  comment_doc TEXT, precondition_doc TEXT, precondition_note_mode INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS steps (
  id INTEGER PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),
  position INTEGER NOT NULL, action TEXT NOT NULL, test_data TEXT NOT NULL,
  expected TEXT NOT NULL, UNIQUE(case_id, position)
);
CREATE TABLE IF NOT EXISTS results (
  step_id INTEGER PRIMARY KEY REFERENCES steps(id), status TEXT NOT NULL DEFAULT 'nao_executado',
  actual TEXT NOT NULL DEFAULT '', comment TEXT NOT NULL DEFAULT '', updated_at TEXT,
  status_changed_at TEXT, actual_doc TEXT
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY, step_id INTEGER NOT NULL REFERENCES steps(id),
  relative_path TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL,
  mime TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_steps_case ON steps(case_id, position);
CREATE INDEX IF NOT EXISTS ix_evidence_step ON evidence(step_id);
CREATE TABLE IF NOT EXISTS step_attachments (
  id TEXT PRIMARY KEY, step_id INTEGER NOT NULL REFERENCES steps(id),
  relative_path TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL,
  extension TEXT NOT NULL, content_type TEXT NOT NULL,
  size INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_step_attachments_step ON step_attachments(step_id);
CREATE TABLE IF NOT EXISTS case_evidence (
  id TEXT PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id), scope TEXT NOT NULL,
  relative_path TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL,
  mime TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_case_evidence_case ON case_evidence(case_id,scope);
CREATE TABLE IF NOT EXISTS case_runs (
  case_id INTEGER NOT NULL REFERENCES cases(id), run_no INTEGER NOT NULL,
  captured_at TEXT NOT NULL, status TEXT NOT NULL, snapshot_json TEXT NOT NULL,
  PRIMARY KEY(case_id,run_no)
);
CREATE TABLE IF NOT EXISTS archived_evidence (
  id TEXT PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),
  run_no INTEGER NOT NULL, relative_path TEXT NOT NULL, mime TEXT NOT NULL,
  FOREIGN KEY(case_id,run_no) REFERENCES case_runs(case_id,run_no)
);
CREATE INDEX IF NOT EXISTS ix_archived_evidence_run ON archived_evidence(case_id,run_no);
CREATE TABLE IF NOT EXISTS archived_attachments (
  id TEXT PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),
  run_no INTEGER NOT NULL, relative_path TEXT NOT NULL, original_name TEXT NOT NULL,
  extension TEXT NOT NULL, content_type TEXT NOT NULL,
  size INTEGER NOT NULL, sha256 TEXT NOT NULL,
  FOREIGN KEY(case_id,run_no) REFERENCES case_runs(case_id,run_no)
);
CREATE INDEX IF NOT EXISTS ix_archived_attachments_run ON archived_attachments(case_id,run_no);
"""


class ReportPayloadParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_payload = False
        self.payload = ""

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "report-data":
            self.in_payload = True

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_payload = False

    def handle_data(self, data):
        if self.in_payload:
            self.payload += data


class FolderLinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.session_id = "abcdef0123456789abcdef0123456789"
        self.directory = self.root / "rascunhos" / self.session_id
        (self.directory / "relatorios").mkdir(parents=True)
        with closing(sqlite3.connect(self.directory / "sessao.sqlite")) as connection:
            connection.executescript(SCHEMA)
            connection.executemany("INSERT INTO meta(key,value) VALUES (?,?)", [
                ("id", self.session_id), ("state", "rascunho"),
                ("created_at", "2026-10-01T10:00:00+00:00"), ("source_name", "casos.csv"),
            ])
            for position, folder, name in (
                (1, "/Produto/Same", "Primeiro"),
                (2, "/Produto/Same", "Segundo"),
                (3, "/Outro/Same", "Terceiro"),
            ):
                connection.execute(
                    "INSERT INTO cases(id,position,sheet,source_row,name,precondition,source_status,priority,folder) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (position, position, "Planilha", position + 1, name, "", "Novo", "Alta", folder),
                )
                step_id = position * 10
                connection.execute(
                    "INSERT INTO steps(id,case_id,position,action,test_data,expected) VALUES (?,?,?,?,?,?)",
                    (step_id, position, 1, "Executar", "dados", "resultado"),
                )
                connection.execute("INSERT INTO results(step_id) VALUES (?)", (step_id,))
            connection.commit()

    def tearDown(self):
        self.temporary.cleanup()

    def test_schema_and_old_session_migration_are_idempotent(self):
        with db(self.directory) as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(folder_links)")]
        self.assertEqual(columns, ["folder_path", "card_url", "provider", "updated_at"])

        legacy_id = "11111111111111111111111111111111"
        legacy = self.root / "rascunhos" / legacy_id
        legacy.mkdir()
        with closing(sqlite3.connect(legacy / "sessao.sqlite")) as connection:
            connection.executescript(LEGACY_SCHEMA)
            objects = {
                row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
                )
            }
            self.assertEqual(objects, {
                "meta", "cases", "steps", "results", "evidence", "step_attachments",
                "case_evidence", "case_runs", "archived_evidence", "archived_attachments",
                "ix_steps_case", "ix_evidence_step", "ix_step_attachments_step",
                "ix_case_evidence_case", "ix_archived_evidence_run", "ix_archived_attachments_run",
            })
            self.assertNotIn("folder_links", objects)
            connection.executemany("INSERT INTO meta(key,value) VALUES (?,?)", [
                ("id", legacy_id), ("state", "rascunho"),
                ("created_at", "2025-01-01T10:00:00+00:00"), ("source_name", "legado.csv"),
            ])
            connection.execute(
                "INSERT INTO cases(id,position,sheet,source_row,name,precondition,source_status,priority,folder) "
                "VALUES (1,1,'Legado',2,'Caso legado','','Novo','Alta','/Legado/Pasta')"
            )
            connection.execute(
                "INSERT INTO steps(id,case_id,position,action,test_data,expected) "
                "VALUES (10,1,1,'Executar','dados','resultado')"
            )
            connection.execute("INSERT INTO results(step_id) VALUES (10)")
            connection.commit()

        migrate_sessions(self.root)
        migrate_sessions(self.root)

        with db(legacy) as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(folder_links)")]
        self.assertEqual(columns, ["folder_path", "card_url", "provider", "updated_at"])
        self.assertEqual(read_session(legacy)["cases"][0]["name"], "Caso legado")
        save_folder_link(legacy, "/Legado/Pasta", "https://empresa.atlassian.net/browse/LEGACY-1", "Link")
        self.assertEqual(read_session(legacy)["cases"][0]["folder_card_provider"], "Jira")
        save_folder_link(legacy, "/Legado/Pasta", "https://app.clickup.com/t/LEGACY-1", "Jira")
        linked = read_session(legacy)["cases"][0]
        self.assertEqual(linked["folder_card_provider"], "ClickUp")
        self.assertEqual(create_app(self.root).test_client().get(f"/sessao/{legacy_id}/abrir").status_code, 200)
        delete_folder_link(legacy, "/Legado/Pasta")
        self.assertIsNone(read_session(legacy)["cases"][0]["folder_card_url"])

    def test_crud_updates_one_exact_folder_without_copying_to_cases(self):
        save_folder_link(self.directory, "/Produto/Same", "https://empresa.atlassian.net/browse/QA-231?x=1#top", "Jira")
        save_folder_link(self.directory, "/Produto/Same", "https://app.clickup.com/t/86b2x9j", "ClickUp")
        record = read_session(self.directory)
        cases = {case["id"]: case for case in record["cases"]}

        self.assertEqual(cases[1]["folder_card_url"], "https://app.clickup.com/t/86b2x9j")
        self.assertEqual(cases[2]["folder_card_url"], "https://app.clickup.com/t/86b2x9j")
        self.assertIsNone(cases[3]["folder_card_url"])
        with db(self.directory) as connection:
            self.assertNotIn("card_url", [row[1] for row in connection.execute("PRAGMA table_info(cases)")])
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM folder_links").fetchone()[0], 1)

        delete_folder_link(self.directory, "/Produto/Same")
        self.assertIsNone(read_session(self.directory)["cases"][0]["folder_card_url"])

    def test_missing_folder_cannot_be_written_or_removed(self):
        with self.assertRaises(LookupError):
            save_folder_link(self.directory, "/Inexistente", "https://example.com/CARD-1", "Link")
        with self.assertRaises(LookupError):
            delete_folder_link(self.directory, "/Inexistente")

    def test_storage_rejects_invalid_url_and_derives_provider(self):
        for invalid in ("javascript:alert(1)", "data:text/html,x", "https:///sem-host"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                save_folder_link(self.directory, "/Produto/Same", invalid, "Jira")
        save_folder_link(self.directory, "/Produto/Same", "https://app.clickup.com/t/86b2x9j", "Jira")
        with db(self.directory) as connection:
            stored = connection.execute(
                "SELECT card_url,provider FROM folder_links WHERE folder_path='/Produto/Same'"
            ).fetchone()
        self.assertEqual(dict(stored), {
            "card_url": "https://app.clickup.com/t/86b2x9j", "provider": "ClickUp",
        })

    def test_corrupt_legacy_url_is_not_projected_or_rendered(self):
        with db(self.directory) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO folder_links(folder_path,card_url,provider,updated_at) VALUES (?,?,?,?)",
                    ("/Produto/Same", "javascript:alert(1)", "Jira", "2026-10-01T11:00:00+00:00"),
                )
        record = read_session(self.directory)
        self.assertIsNone(record["cases"][0]["folder_card_url"])
        self.assertNotIn("/Produto/Same", record["folder_links"])
        report = render_report_html(self.directory, {1})
        listing = create_app(self.root).test_client().get(
            f"/sessao/{self.session_id}/abrir"
        ).get_data(as_text=True)
        self.assertNotIn("javascript:alert(1)", report)
        self.assertNotIn("javascript:alert(1)", listing)

    def test_url_validation_preserves_value_and_infers_provider_and_label(self):
        value = "https://empresa.atlassian.net/browse/QA-231?expand=a%2Fb#comment-2"
        self.assertEqual(folder_card_details(value), {
            "url": value, "provider": "Jira", "label": "QA-231",
        })
        self.assertEqual(folder_card_details("https://app.clickup.com/t/86b2x9j")["provider"], "ClickUp")
        self.assertEqual(folder_card_details("https://cards.example.com/work/ABC-9")["provider"], "Link")
        for invalid in (
            "", "empresa.atlassian.net/browse/QA-1", "javascript:alert(1)",
            "data:text/html,x", "file:///tmp/card", "https:///sem-host",
            " https://example.com/card", "https://example.com/card\n",
            "https://exa mple.com/card", "https://./card", "https://example.com/\x00card",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                folder_card_details(invalid)

    def test_grouping_uses_full_path_for_same_short_name(self):
        save_folder_link(self.directory, "/Produto/Same", "https://example.com/CARD-A", "Link")
        with db(self.directory) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO folder_links(folder_path,card_url,provider,updated_at) VALUES (?,?,?,?)",
                    ("/Pasta/Orfa", "https://example.com/ORPHAN", "Link", "2026-10-01T11:00:00+00:00"),
                )
        groups = {group["name"]: group for group in folder_groups(read_session(self.directory)["cases"])}
        self.assertEqual(groups["/Produto/Same"]["card"]["label"], "CARD-A")
        self.assertIsNone(groups["/Outro/Same"]["card"])
        self.assertNotIn("/Pasta/Orfa", groups)

    def test_listing_player_report_and_csrf_contracts(self):
        app = create_app(self.root)
        app.testing = True
        client = app.test_client()

        listing = client.get(f"/sessao/{self.session_id}/abrir")
        self.assertEqual(listing.status_code, 200)
        self.assertIn(b">Progresso<", listing.data)
        self.assertIn(b"Vincular card", listing.data)
        self.assertNotIn(b'<a class="folder-row"', listing.data)
        open_links = re.findall(r'<a class="folder-row-end" href="([^"]+)"[^>]*>.*?</a>',
                                listing.get_data(as_text=True), re.DOTALL)
        self.assertEqual(open_links, [
            f"/sessao/{self.session_id}",
            f"/sessao/{self.session_id}?pasta=/Produto/Same",
            f"/sessao/{self.session_id}?pasta=/Outro/Same",
        ])
        self.assertNotIn("data-folder-card-edit", "".join(
            re.findall(r'<a class="folder-row-end"[^>]*>.*?</a>',
                       listing.get_data(as_text=True), re.DOTALL)
        ))

        endpoint = f"/api/sessao/{self.session_id}/pasta/vinculo"
        body = {"folder_path": "/Produto/Same", "card_url": "https://empresa.atlassian.net/browse/QA-231"}
        self.assertEqual(client.post(endpoint, json=body).status_code, 400)
        with client.session_transaction() as browser_session:
            token = browser_session["csrf_token"]
        headers = {"X-CSRF-Token": token}
        saved = client.post(endpoint, json=body, headers=headers)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.get_json()["card"]["label"], "QA-231")
        self.assertEqual(client.post(endpoint, json={"folder_path": "/Outro/Same", "card_url": "javascript:alert(1)"}, headers=headers).status_code, 422)
        self.assertEqual(client.post(endpoint, json={"folder_path": "/Ausente", "card_url": "https://example.com/x"}, headers=headers).status_code, 404)

        linked_listing = client.get(f"/sessao/{self.session_id}/abrir").get_data(as_text=True)
        self.assertIn("Card vinculado", linked_listing)
        self.assertIn("QA-231", linked_listing)
        self.assertIn("Editar vínculo", linked_listing)
        self.assertIn('target="_blank"', linked_listing)
        self.assertIn('rel="noopener noreferrer"', linked_listing)

        player = client.get(f"/sessao/{self.session_id}").get_data(as_text=True)
        self.assertIn("QA-231", player)
        self.assertIn("somente consulta", player)
        self.assertNotIn("data-folder-card-edit", player)
        self.assertNotIn("folder-card-modal", player)

        html = render_report_html(self.directory, {1, 2, 3})
        parser = ReportPayloadParser()
        parser.feed(html)
        payload = json.loads(parser.payload)
        self.assertEqual([item["folder_card_url"] for item in payload[:2]], [body["card_url"]] * 2)
        self.assertIsNone(payload[2]["folder_card_url"])
        self.assertIn("Card vinculado:", html)
        self.assertIn("noopener noreferrer", html)
        generated_html = generate_html(self.directory, {1, 2, 3})
        self.assertTrue(generated_html.is_file())
        self.assertIn(body["card_url"], generated_html.read_text(encoding="utf-8"))
        self.assertEqual(client.get(f"/sessao/{self.session_id}", query_string={"pasta": "/Produto/Same"}).status_code, 200)
        self.assertEqual(client.get(f"/sessao/{self.session_id}", query_string={"pasta": "/Ausente"}).status_code, 404)
        for scope in ("latest", "all"):
            response = client.post(
                f"/sessao/{self.session_id}/gerar-html",
                data={"csrf_token": token, "case_id": "1", "run_scope": scope},
            )
            self.assertEqual(response.status_code, 200)
            response.close()

        self.assertEqual(client.delete(endpoint, json={"folder_path": "/Produto/Same"}).status_code, 400)
        removed = client.delete(endpoint, json={"folder_path": "/Produto/Same"}, headers=headers)
        self.assertEqual(removed.status_code, 200)
        self.assertNotIn("somente consulta", client.get(f"/sessao/{self.session_id}").get_data(as_text=True))

    def test_pdf_keeps_clickable_folder_card_link_when_browser_is_available(self):
        try:
            _browser_path()
        except RuntimeError as exc:
            self.fail(f"Navegador obrigatório para validar o PDF neste ambiente: {exc}")
        card_url = "https://empresa.atlassian.net/browse/QA-231?from=pdf#details"
        save_folder_link(self.directory, "/Produto/Same", card_url, "Jira")

        report = generate_pdf(self.directory, {1, 3})

        with pymupdf.open(report) as document:
            links = [link.get("uri") for page in document for link in page.get_links()]
            text = "".join(page.get_text() for page in document)
        self.assertIn(card_url, links)
        self.assertEqual(text.count("Card vinculado:"), 1)

    def test_modal_and_theme_contract_is_structurally_present(self):
        root = Path(__file__).resolve().parent / "testplayer"
        template = (root / "templates" / "choose_folder.html").read_text(encoding="utf-8")
        javascript = (root / "static" / "app.js").read_text(encoding="utf-8")
        fixes = (root / "static" / "ui-fixes.css").read_text(encoding="utf-8")
        carbon = (root / "static" / "carbon.css").read_text(encoding="utf-8")

        for fragment in (
            '<dialog id="folder-card-modal"', 'aria-labelledby="folder-card-modal-title"',
            'id="folder-card-url"', 'id="folder-card-error" role="alert"',
            "Cancelar", "Salvar vínculo", "Remover vínculo desta pasta",
        ):
            self.assertIn(fragment, template)
        for fragment in (
            "folderCardModal.addEventListener('cancel'", "folderCardModal.addEventListener('close'",
            "returnFocus?.focus()", "urlInput.focus()",
        ):
            self.assertIn(fragment, javascript)
        for selector in (".folder-card-add", ".folder-card-edit", ".folder-card-modal", ".folder-card-field input"):
            self.assertIn(selector, fixes)
        self.assertIn(':root[data-theme="light"]', carbon)
        self.assertIn(':root[data-theme="dark"]', carbon)
        self.assertIn("background: var(--canvas)", fixes)
        self.assertIn("color: var(--ink)", fixes)


if __name__ == "__main__":
    unittest.main()
