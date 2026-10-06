import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from testplayer.automation_environment import AutomationRuntime, detect_automation_runtime
from testplayer.web import create_app
import tempfile


class AutomationEnvironmentTests(unittest.TestCase):
    def test_missing_node_disables_automation_without_installing_anything(self):
        with patch('testplayer.automation_environment.shutil.which', return_value=None), patch('testplayer.automation_environment.subprocess.run') as run:
            runtime = detect_automation_runtime()
        self.assertFalse(runtime.available)
        self.assertIn('Node.js', runtime.message)
        run.assert_not_called()

    def test_installed_codegen_enables_automation_from_environment(self):
        result = Mock(returncode=0, stdout=json.dumps({'available': True, 'entry': 'C:/tools/playwright/test.js', 'version': '1.62.1'}))
        with patch('testplayer.automation_environment.shutil.which', return_value='C:/tools/node.exe'), patch('testplayer.automation_environment.subprocess.run', return_value=result) as run:
            runtime = detect_automation_runtime()
        self.assertTrue(runtime.available)
        self.assertEqual(runtime.node, 'C:/tools/node.exe')
        self.assertEqual(runtime.playwright_entry, 'C:/tools/playwright/test.js')
        self.assertNotIn('npx', str(run.call_args))

    def test_missing_codegen_and_failed_probe_are_nonfatal(self):
        for result in [Mock(returncode=0, stdout=json.dumps({'available': False, 'message': 'Playwright Codegen não encontrado.'})), Mock(returncode=1, stdout='')]:
            with patch('testplayer.automation_environment.shutil.which', return_value='node'), patch('testplayer.automation_environment.subprocess.run', return_value=result):
                runtime = detect_automation_runtime()
                self.assertFalse(runtime.available)
                self.assertTrue(runtime.message)

    def test_every_app_start_detects_again_and_hides_disabled_navigation(self):
        with tempfile.TemporaryDirectory() as directory, patch('testplayer.web.detect_automation_runtime', return_value=AutomationRuntime(message='Node.js não encontrado.')) as detect:
            for _ in range(2):
                app = create_app(Path(directory))
                client = app.test_client()
                page = client.get('/').get_data(as_text=True)
                self.assertNotIn('class="automation-nav"', page)
                self.assertIn('Node.js não encontrado.', page)
                self.assertEqual(client.get('/iniciativas/automacao').status_code, 503)
                with client.session_transaction() as session:
                    csrf = session['csrf_token']
                result = client.post('/api/iniciativas/automacao/recorder/start', headers={'X-CSRF-Token': csrf})
                self.assertEqual(result.status_code, 503)
            self.assertEqual(detect.call_count, 2)
