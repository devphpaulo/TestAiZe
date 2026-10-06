import json
import sys
import tempfile
import unittest
import time
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from testplayer.automation_environment import AutomationRuntime
from testplayer.automation_environment import detect_automation_runtime
from testplayer.automation_library import AutomationLibrary
from testplayer.automation_suite import AutomationSuiteRunner


class AutomationSuiteTests(unittest.TestCase):
    def test_missing_playwright_support_files_are_reported_before_creating_an_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = AutomationLibrary(Path(temporary))
            folder = library.create_folder('Instalação')
            cycle = library.create_cycle(folder['id'], 'Ciclo')
            library.save_script(cycle['id'], 'Teste', "test('um', () => {});")
            runner = AutomationSuiteRunner(library, AutomationRuntime(True, 'node', 'playwright'))
            try:
                with patch('testplayer.automation_suite.recorder_root', return_value=Path(temporary) / 'missing-worker'):
                    with self.assertRaisesRegex(ValueError, 'suite-runtime.cjs'):
                        runner.start(folder['id'], cycle['id'], {}, [])
                self.assertEqual(library.runs(folder['id']), [])
            finally:
                runner.shutdown()

    def test_run_snapshots_scripts_and_vault_and_persists_metrics(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = AutomationLibrary(Path(temporary))
            folder = library.create_folder('Suite')
            cycle = library.create_cycle(folder['id'], 'Ciclo')
            library.save_script(cycle['id'], 'Teste', "test('first', () => {});")
            runtime = AutomationRuntime(True, sys.executable, 'C:/env/playwright/test.js')
            runner = AutomationSuiteRunner(library, runtime)
            report = {'state': 'completed', 'total': 2, 'passed': 1, 'failed': 1, 'skipped': 0,
                      'results': [{'title': 'falha', 'status': 'failed', 'error': 'Expected secret-canary'}]}
            def run_fake(run_id, scripts, environment, secrets):
                library.write_report(run_id, report, secrets)
            with patch.object(runner, '_execute', side_effect=run_fake):
                run = runner.start(folder['id'], cycle['id'], {'PLAYWRIGHT_PASSWORD': 'secret-canary'}, ['secret-canary'])
                runner.wait()
            saved = runner.status(run['id'])
            self.assertEqual(saved['passed'], 1)
            self.assertEqual(saved['failed'], 1)
            self.assertNotIn('secret-canary', json.dumps(saved))
            self.assertEqual(AutomationLibrary(Path(temporary)).runs(folder['id'])[0]['id'], run['id'])
            runner.shutdown()

    def test_empty_suite_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = AutomationLibrary(Path(temporary))
            folder = library.create_folder('Vazia')
            runner = AutomationSuiteRunner(library, AutomationRuntime(True, 'node', 'playwright'))
            with self.assertRaises(ValueError): runner.start(folder['id'], None, {}, [])

    def test_real_playwright_suite_reports_pass_failure_and_redacts_vault_secret(self):
        runtime = detect_automation_runtime()
        if not runtime.available: self.skipTest('Playwright do ambiente indisponível.')
        with tempfile.TemporaryDirectory() as temporary:
            library = AutomationLibrary(Path(temporary))
            folder = library.create_folder('Real')
            cycle = library.create_cycle(folder['id'], 'Smoke')
            library.save_script(cycle['id'], 'Sucesso', "import { test, expect } from '@playwright/test'; test('passa', async () => { expect(1).toBe(1); });")
            library.save_script(cycle['id'], 'Falha', "import { test, expect } from '@playwright/test'; test('falha', async () => { expect(process.env.PLAYWRIGHT_PASSWORD).toBe('outro'); });")
            runner = AutomationSuiteRunner(library, runtime, timeout=30)
            self.addCleanup(runner.shutdown)
            run = runner.start(folder['id'], cycle['id'], {'PLAYWRIGHT_PASSWORD': 'private-vault-canary'}, ['private-vault-canary'])
            runner.wait()
            report = runner.status(run['id'])
            self.assertEqual(report['state'], 'completed', report.get('errors'))
            self.assertEqual((report['total'], report['passed'], report['failed']), (2, 1, 1))
            self.assertNotIn('private-vault-canary', json.dumps(report))
            self.assertIn('[secret]', json.dumps(report))
            self.assertNotIn('private-vault-canary', (library.run_path(run['id']) / 'report.json').read_text())

    def test_startup_marks_an_unfinished_run_interrupted_and_keeps_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            library = AutomationLibrary(Path(temporary))
            folder = library.create_folder('Recuperação')
            cycle = library.create_cycle(folder['id'], 'Ciclo')
            script = library.save_script(cycle['id'], 'Snapshot', 'original')
            run = library.create_run(folder['id'], cycle['id'], [script])
            library.save_script(cycle['id'], 'Snapshot', 'alterado', script['id'])
            runner = AutomationSuiteRunner(library, AutomationRuntime())
            self.assertEqual(runner.status(run['id'])['state'], 'interrupted')
            self.assertEqual((library.run_path(run['id']) / 'scripts' / (script['id'] + '.spec.ts')).read_text(), 'original')
            runner.shutdown()

    def test_cancelling_real_runner_ends_only_its_owned_process(self):
        runtime = detect_automation_runtime()
        if not runtime.available: self.skipTest('Playwright do ambiente indisponível.')
        with tempfile.TemporaryDirectory() as temporary:
            library = AutomationLibrary(Path(temporary))
            folder = library.create_folder('Cancelamento')
            cycle = library.create_cycle(folder['id'], 'Ciclo')
            library.save_script(cycle['id'], 'Lento', "import { test } from '@playwright/test'; test('lento', async () => { await new Promise(resolve => setTimeout(resolve, 20000)); });")
            runner = AutomationSuiteRunner(library, runtime, timeout=30)
            self.addCleanup(runner.shutdown)
            run = runner.start(folder['id'], cycle['id'], {}, [])
            deadline = time.monotonic() + 5
            while runner._process is None and time.monotonic() < deadline: time.sleep(.02)
            self.assertIsNotNone(runner._process)
            process = runner._process
            runner.cancel(run['id'])
            runner.wait()
            self.assertEqual(runner.status(run['id'])['state'], 'cancelled')
            self.assertIsNotNone(process.poll())
