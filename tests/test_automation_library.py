import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from testplayer.automation_library import AutomationLibrary
from testplayer.storage import ensure_root
from testplayer.backup import make_backup


class AutomationLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.library = AutomationLibrary(Path(self.temp.name))

    def test_folder_cycle_and_script_survive_reopening_and_live_in_data_directory(self):
        folder = self.library.create_folder('Checkout')
        cycle = self.library.create_cycle(folder['id'], 'Regressão')
        script = self.library.save_script(cycle['id'], 'Login', "import { test } from '@playwright/test'; test('login', async () => {});")
        reopened = AutomationLibrary(Path(self.temp.name))
        self.assertEqual(reopened.folders()[0]['script_count'], 1)
        self.assertEqual(reopened.script(script['id'])['name'], 'Login')
        self.assertTrue(reopened.script_path(script['id']).is_file())
        self.assertTrue(str(reopened.script_path(script['id'])).endswith('.spec.ts'))
        self.assertEqual(reopened.scripts(folder['id'], cycle['id'])[0]['code'], script['code'])

    def test_rename_move_update_and_delete_are_scoped_to_automation(self):
        folder = self.library.create_folder('A')
        cycle = self.library.create_cycle(folder['id'], 'C1')
        second = self.library.create_cycle(folder['id'], 'C2')
        script = self.library.save_script(cycle['id'], 'Original', 'original')
        self.library.rename('folders', folder['id'], 'B')
        self.library.rename('cycles', cycle['id'], 'Ciclo')
        self.library.save_script(second['id'], 'Novo', 'atualizado', script['id'])
        self.assertEqual(self.library.scripts(folder['id'], cycle['id']), [])
        self.assertEqual(self.library.script(script['id'])['code'], 'atualizado')
        manual = Path(self.temp.name) / 'manual.txt'
        manual.write_text('preservar')
        self.library.delete('folders', folder['id'])
        self.assertEqual(self.library.folders(), [])
        self.assertEqual(manual.read_text(), 'preservar')
        with self.assertRaises(LookupError): self.library.script(script['id'])

    def test_invalid_identifiers_and_names_never_escape_root(self):
        with self.assertRaises(ValueError): self.library.create_folder('../outside')
        with self.assertRaises(LookupError): self.library.folder('../outside')
        with self.assertRaises(ValueError): self.library.create_folder(' ')
        self.library.create_folder('Smoke')
        with self.assertRaises(ValueError): self.library.create_folder('Smoke')

    def test_application_backup_contains_automation_database_scripts_and_history(self):
        root = Path(self.temp.name)
        ensure_root(root)
        folder = self.library.create_folder('Backup')
        cycle = self.library.create_cycle(folder['id'], 'Ciclo')
        script = self.library.save_script(cycle['id'], 'Teste', 'codigo salvo')
        run = self.library.create_run(folder['id'], cycle['id'], [script])
        archive_path = make_backup(root)
        script_archive_path = f"automacao/pastas/{folder['id']}/ciclos/{cycle['id']}/{script['id']}.spec.ts"
        with zipfile.ZipFile(archive_path) as archive:
            self.assertIn('automacao/biblioteca.sqlite3', archive.namelist())
            self.assertEqual(archive.read(script_archive_path).decode(), 'codigo salvo')
            self.assertIn('automacao/execucoes/' + run['id'] + '/report.json', archive.namelist())
