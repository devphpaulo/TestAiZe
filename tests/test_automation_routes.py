import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from testplayer.web import create_app
from testplayer.automation_environment import AutomationRuntime


class AutomationRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch('testplayer.web.detect_automation_runtime', return_value=AutomationRuntime(True, 'node', 'playwright')):
            self.app = create_app(Path(self.temp.name))
        self.manager = Mock()
        self.manager.start.return_value = {"state": "ready", "url": "http://127.0.0.1:51234/?embedded=1"}
        self.manager.stop.return_value = {"state": "idle"}
        self.manager.status.return_value = {"state": "idle"}
        self.app.extensions["automation_recorder"] = self.manager
        self.client = self.app.test_client()
        self.client.get("/")
        with self.client.session_transaction() as session:
            self.headers = {"X-CSRF-Token": session["csrf_token"]}

    def test_automation_is_separate_and_page_does_not_spawn(self):
        home = self.client.get("/").get_data(as_text=True)
        self.assertIn('href="/iniciativas/automacao"', home)
        self.assertNotIn('id="automation-workspace"', home)
        page = self.client.get("/iniciativas/automacao")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Pastas de automação", page.get_data(as_text=True))
        self.assertNotIn('id="automation-workspace"', page.get_data(as_text=True))
        self.assertEqual(self.client.get('/iniciativas/automacao/gravacao').status_code, 200)
        self.manager.start.assert_not_called()

    def test_start_uses_host_origin_and_returns_worker_url(self):
        result = self.client.post("/api/iniciativas/automacao/recorder/start", headers=self.headers,
                                  json={"owner": "page-a", "parent_origin": "https://evil.test"})
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json["ok"])
        self.manager.start.assert_called_once_with("http://localhost", "page-a")

    def test_mutations_require_csrf_and_same_origin(self):
        for action in ("start", "stop"):
            path = f"/api/iniciativas/automacao/recorder/{action}"
            response = self.client.post(path)
            self.assertEqual(response.status_code, 400)
            self.assertIsNotNone(response.json)
            self.assertEqual(self.client.post(path, headers={**self.headers, "Origin": "http://evil.test"}).status_code, 403)
        self.manager.start.assert_not_called()
        self.manager.stop.assert_not_called()

    def test_stop_accepts_beacon_form_and_status_does_not_spawn(self):
        response = self.client.post("/api/iniciativas/automacao/recorder/stop",
                                    data={"csrf_token": self.headers["X-CSRF-Token"], "owner": "page-a"})
        self.assertEqual(response.json, {"ok": True, "state": "idle"})
        self.manager.stop.assert_called_once_with("page-a")
        self.assertEqual(self.client.get("/api/iniciativas/automacao/recorder/status?owner=page-a").json["state"], "idle")
        self.manager.start.assert_not_called()

    def test_unavailable_worker_has_safe_retryable_error(self):
        from testplayer.automation_recorder import RecorderError
        self.manager.start.side_effect = RecorderError("Instale Node.js para usar Automação.")
        response = self.client.post("/api/iniciativas/automacao/recorder/start", headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.json["ok"])
        self.assertNotIn("Traceback", response.json["error"])

    def test_vault_updates_reach_worker_without_returning_secret(self):
        path = '/api/iniciativas/automacao/cofre'
        self.assertEqual(self.client.post(path, json={'key': 'API_TOKEN', 'value': 'secret'}).status_code, 400)
        result = self.client.post(path, headers=self.headers, json={'key': 'PLAYWRIGHT_PASSWORD', 'value': 'canary-secret', 'secret': True})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('canary-secret', result.get_data(as_text=True))
        self.manager.update_vault.assert_called_with({'PLAYWRIGHT_EMAIL': '', 'PLAYWRIGHT_PASSWORD': 'canary-secret'})
        entries = self.client.get(path)
        self.assertNotIn('canary-secret', entries.get_data(as_text=True))
        self.assertEqual(entries.headers['Cache-Control'], 'no-store')

    def test_invalid_vault_keys_are_rejected_without_runtime_changes(self):
        response = self.client.post('/api/iniciativas/automacao/cofre', headers=self.headers, json={'key': 'NODE_OPTIONS', 'value': 'malicious', 'secret': True})
        self.assertEqual(response.status_code, 400)
        self.manager.update_vault.assert_not_called()

    def test_library_crud_and_spec_download_are_protected_and_persistent(self):
        api = '/api/iniciativas/automacao/'
        self.assertEqual(self.client.post(api + 'pastas', json={'name': 'Pasta'}).status_code, 400)
        folder = self.client.post(api + 'pastas', headers=self.headers, json={'name': 'Pasta'}).json['item']
        cycle = self.client.post(api + 'ciclos', headers=self.headers, json={'name': 'Smoke', 'folder_id': folder['id']}).json['item']
        code = "import { test } from '@playwright/test'; test('um', () => {});"
        script = self.client.post(api + 'scripts', headers=self.headers, json={'name': 'Teste', 'cycle_id': cycle['id'], 'code': code}).json['item']
        response = self.client.get(api + 'scripts/' + script['id'] + '/download')
        self.assertEqual(response.get_data(as_text=True), code)
        self.assertIn('Teste.spec.ts', response.headers['Content-Disposition'])
        self.assertEqual(self.client.get('/iniciativas/automacao/pastas/' + folder['id']).status_code, 200)
        self.assertEqual(self.client.get('/iniciativas/automacao/scripts/' + script['id']).status_code, 200)
        self.client.put(api + 'pastas/' + folder['id'], headers=self.headers, json={'name': 'Renomeada'})
        self.assertIn('Renomeada', self.client.get('/iniciativas/automacao').get_data(as_text=True))
        self.client.delete(api + 'scripts/' + script['id'], headers=self.headers)
        self.assertEqual(self.client.get(api + 'scripts/' + script['id'] + '/download').status_code, 404)
