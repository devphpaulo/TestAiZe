import hashlib
import io
import json
import sys
import tempfile
import threading
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from PIL import Image
from testplayer import storage
from testplayer.backup import make_backup
from testplayer.bugs_service import BugsService
from testplayer.bugs_store import BugsStore
from testplayer.bugs_coordinator import coordinated, StateConflict, RecoveryPending


class BugsFixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        storage.ensure_root(self.root)
        self.sid = uuid.uuid4().hex
        self.directory = self.root / 'rascunhos' / self.sid
        self.directory.mkdir()
        (self.directory / 'origem').mkdir()
        (self.directory / 'origem' / 'cases.csv').write_text('case')
        with storage.db(self.directory) as db:
            db.executescript(storage.SCHEMA)
            with db:
                for key, value in {'id': self.sid, 'state': 'rascunho', 'created_at': storage.now(),
                                   'source_name': 'cases.csv', 'source_file': 'cases.csv'}.items():
                    storage.set_meta(db, key, value)
                for i, manual in enumerate(('', 'aprovado', 'reprovado'), 1):
                    db.execute('INSERT INTO cases(id,position,sheet,source_row,name,precondition,source_status,priority,folder,manual_status,execution_generation) '
                               'VALUES (?,?,?,?,?,?,?,?,?,?,?)', (i, i, 'Planilha', i, f'Caso {i}', '', '', '', 'Pasta', manual, 'generation'))
                    db.execute('INSERT INTO steps(id,case_id,position,action,test_data,expected) VALUES (?,?,1,?,?,?)',
                               (i, i, 'Ação', '', 'Esperado'))
                    db.execute('INSERT INTO results(step_id) VALUES (?)', (i,))
        stream = io.BytesIO()
        Image.new('RGB', (30, 20), 'red').save(stream, 'PNG')
        self.image = stream.getvalue()
        self.service = BugsService(self.root)

    def create_bug(self):
        return self.service.create(dict(title='Falha <script>', severity='Alta', actual='Obtido', expected='Esperado',
                                        blocks=[{'type': 'text', 'text': 'Fluxo\nPassos'},
                                                {'type': 'image', 'id': 'upload', 'width': 65}]),
                                   {'upload': (self.image, 'evidence.png')}, self.sid)

    def state(self, case_id=1):
        return storage.case_state(self.directory, case_id)

    def finish_bug(self, bug_id):
        bug = self.service.get(bug_id)
        bug = self.service.transition(bug_id, 'em_reteste', bug['status'])
        self.service.add_evidence(bug_id, 'reteste', note='Verificado', token=bug['current_retest_token'])
        return self.service.transition(bug_id, 'finalizado', 'em_reteste', bug['current_retest_token'])


class BugsFlowTests(BugsFixture, unittest.TestCase):
    def test_creation_validation_and_ownership(self):
        with self.assertRaises(ValueError):
            self.service.create({}, {}, self.sid)
        self.assertEqual(self.service.list(), [])
        bug = self.create_bug()
        other = self.create_bug()
        self.assertEqual(self.state()['status'], 'nao_executado')
        self.assertEqual(json.loads(bug['description_doc'])[1]['width'], 65)
        with self.assertRaises(ValueError):
            self.service.edit(bug['id'], dict(bug, blocks=[{'type': 'text', 'text': 'x'},
                                                          {'type': 'image', 'id': other['evidence'][0]['id']}]))
        with self.assertRaises(LookupError):
            self.service.evidence_bytes(bug['id'], other['evidence'][0]['id'])
        with self.assertRaises(ValueError):
            self.service.remove_evidence(bug['id'], bug['evidence'][0]['id'])
        with self.service.store.connect() as db:
            db.execute("UPDATE bug_evidence SET relative_path='../escape.png' WHERE id=?", (bug['evidence'][0]['id'],))
        with self.assertRaises(ValueError):
            self.service.evidence_bytes(bug['id'], bug['evidence'][0]['id'])

    def test_batch_status_autosave_retest_and_two_bugs(self):
        bug = self.create_bug()
        result = self.service.link(bug['id'], self.sid, [1, 2, 3])
        self.assertEqual([r['result'] for r in result['results']], ['vinculado', 'recusado', 'vinculado'])
        self.assertEqual(self.state()['status'], 'bloqueado')
        self.assertEqual(self.state(3)['status'], 'reprovado')
        with self.assertRaises(StateConflict):
            storage.save_case(self.directory, 1, '', 'old autosave')
        self.assertEqual(storage.read_session(self.directory)['cases'][0]['comment'], 'old autosave')
        self.assertEqual(self.state()['manual_status'], 'bloqueado')
        storage.save_case(self.directory, 1, None, 'new autosave')
        state = self.state()
        with self.assertRaises(StateConflict):
            storage.set_case_status(self.directory, 1, 'aprovado', state['status_revision'], state['execution_generation'])
        storage.save_result(self.directory, 1, 'reprovado', 'Falhou')
        self.assertEqual(self.state()['status'], 'reprovado')
        storage.start_case_run(self.directory, 1)
        self.assertNotEqual(self.state()['execution_generation'], 'generation')
        self.assertEqual(self.state()['status'], 'bloqueado')
        storage.save_result(self.directory, 1, 'aprovado', 'Corrigido')
        self.assertEqual(self.state()['status'], 'bloqueado')
        other = self.create_bug()
        self.service.link(other['id'], self.sid, [1])
        self.finish_bug(bug['id'])
        self.assertEqual(self.state()['status'], 'bloqueado')
        self.assertIn(1, storage.active_bug_cases(self.directory))
        self.finish_bug(other['id'])
        self.assertEqual(self.state()['status'], 'bloqueado')
        state = self.state()
        storage.set_case_status(self.directory, 1, '', state['status_revision'], state['execution_generation'])
        self.assertEqual(self.state()['status'], 'aprovado')
        with self.assertRaises(StateConflict):
            storage.set_case_status(self.directory, 1, '', state['status_revision'], state['execution_generation'])

    def test_current_token_and_idempotent_unlink(self):
        bug = self.create_bug()
        self.service.link(bug['id'], self.sid, [1])
        metadata = self.service.get(bug['id'])['links'][0]
        self.service.link(bug['id'], self.sid, [1])
        self.assertEqual(self.service.get(bug['id'])['links'][0], metadata)
        bug = self.service.transition(bug['id'], 'em_reteste', 'aberto')
        old_token = bug['current_retest_token']
        self.service.add_evidence(bug['id'], 'reteste', note='Primeiro teste', token=old_token)
        self.service.transition(bug['id'], 'reaberto', 'em_reteste', old_token)
        bug = self.service.transition(bug['id'], 'em_reteste', 'reaberto')
        self.assertNotEqual(old_token, bug['current_retest_token'])
        with self.assertRaises(StateConflict):
            self.service.add_evidence(bug['id'], 'reteste', note='Prova atrasada', token=old_token)
        with self.assertRaises(StateConflict):
            self.service.transition(bug['id'], 'finalizado', 'em_reteste', bug['current_retest_token'])
        self.service.unlink(bug['id'], self.sid, 1)
        self.service.unlink(bug['id'], self.sid, 1)
        self.assertEqual(self.state()['status'], 'bloqueado')
        self.assertEqual(len(self.service.get(bug['id'])['links']), 1)

    def test_link_reconciles_existing_failed_steps_and_proof_keeps_image_and_note(self):
        with storage.db(self.directory) as db:
            with db:
                db.execute("UPDATE cases SET manual_status='bloqueado' WHERE id=1")
                db.execute("UPDATE results SET status='reprovado' WHERE step_id=1")
        bug = self.create_bug()
        self.service.link(bug['id'], self.sid, [1])
        self.assertEqual(self.state()['status'], 'reprovado')
        bug = self.service.transition(bug['id'], 'em_reteste', 'aberto')
        proof = self.service.add_evidence(bug['id'], 'reteste', self.image, 'proof.png',
                                          note='A imagem confirma a correção', token=bug['current_retest_token'])
        self.assertEqual(proof['note'], 'A imagem confirma a correção')
        self.assertEqual(self.service.evidence_bytes(bug['id'], proof['id'])[0], self.image)

    def test_recovery_between_commits_and_backup_restore(self):
        bug = self.create_bug()
        with patch('testplayer.bugs_service._phase', side_effect=OSError('crash')):
            with self.assertRaises(RecoveryPending):
                self.service.link(bug['id'], self.sid, [1])
            with self.assertRaises(RecoveryPending):
                storage.save_case(self.directory, 1, None, 'must wait')
        restarted = BugsService(self.root)
        self.assertEqual(self.state()['status'], 'bloqueado')
        self.assertEqual(len(restarted.get(bug['id'])['links']), 1)
        retest = restarted.transition(bug['id'], 'em_reteste', 'aberto')
        restarted.add_evidence(bug['id'], 'reteste', note='Prova atual', token=retest['current_retest_token'])
        backup = make_backup(self.root)
        restored = self.root / 'restored'
        with zipfile.ZipFile(backup) as archive:
            archive.extractall(restored)
            checksums = json.loads(archive.read('integridade.json'))['sha256']
        for path, expected in checksums.items():
            self.assertEqual(hashlib.sha256((restored / path).read_bytes()).hexdigest(), expected)
        service = BugsService(restored)
        self.assertEqual(service.get(bug['id'])['current_retest_token'], retest['current_retest_token'])
        self.assertEqual(service.evidence_bytes(bug['id'], bug['evidence'][0]['id'])[0], self.image)
        self.assertEqual(len(service.get(bug['id'])['links']), 1)

    def test_remove_recovery_preserves_bug_and_images(self):
        bug = self.create_bug()
        self.service.link(bug['id'], self.sid, [1])
        with patch('testplayer.bugs_service._phase', side_effect=OSError('crash')):
            with self.assertRaises(RecoveryPending):
                storage.remove_session(self.root, self.sid, True)
        restarted = BugsService(self.root)
        self.assertFalse(self.directory.exists())
        self.assertEqual(restarted.get(bug['id'])['links'], [])
        self.assertEqual(restarted.evidence_bytes(bug['id'], bug['evidence'][0]['id'])[0], self.image)

    def test_move_and_rerun_do_not_transfer_active_links(self):
        bug = self.create_bug()
        self.service.link(bug['id'], self.sid, [1])
        directory = storage.finalize(self.root, self.directory)
        with self.assertRaises(StateConflict):
            self.service.link(bug['id'], self.sid, [3])
        new_id = storage.rerun(self.root, directory)
        self.assertEqual(storage.active_bug_cases(storage.find_directory(self.root, new_id)), set())
        target = storage.remove_session(self.root, self.sid, False)
        self.assertTrue(target.exists())
        self.assertEqual(self.service.get(bug['id'])['links'][0]['active'], 0)

    def test_delete_recovery_finishes_after_database_was_already_deleted(self):
        bug = self.create_bug()
        self.service.link(bug['id'], self.sid, [1])
        def partial_delete(source):
            (source / 'sessao.sqlite').unlink()
            raise OSError('crash after deleting database, before other files')
        with patch('testplayer.bugs_service.shutil.rmtree', side_effect=partial_delete):
            with self.assertRaises(RecoveryPending):
                storage.remove_session(self.root, self.sid, True)
        self.assertTrue(self.directory.exists())
        BugsService(self.root)
        self.assertFalse(self.directory.exists())
        self.assertEqual(self.service.get(bug['id'])['links'], [])

    def test_concurrent_link_and_autosave_preserve_restriction(self):
        bug = self.create_bug()
        barrier = threading.Barrier(2)
        errors = []
        def run(action):
            try:
                barrier.wait()
                action()
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=run, args=(action,)) for action in (
            lambda: self.service.link(bug['id'], self.sid, [1]),
            lambda: storage.save_case(self.directory, 1, None, 'Concorrente'))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.state()['status'], 'bloqueado')

    def test_move_recovers_after_rename_before_links_commit(self):
        bug = self.create_bug()
        self.service.link(bug['id'], self.sid, [1])
        from testplayer.bugs_service import _phase
        def fail_after_files(store, operation_id, phase):
            if phase == 'files':
                raise OSError('crash after rename')
            return _phase(store, operation_id, phase)
        with patch('testplayer.bugs_service._phase', side_effect=fail_after_files):
            with self.assertRaises(RecoveryPending):
                storage.remove_session(self.root, self.sid, False)
        self.assertFalse(self.directory.exists())
        restarted = BugsService(self.root)
        self.assertEqual(restarted.get(bug['id'])['links'][0]['active'], 0)
        self.assertTrue((self.root / 'excluidas' / self.sid / 'sessao.sqlite').is_file())

    def test_status_replication_materializes_failure_under_active_link(self):
        bug = self.create_bug()
        self.service.link(bug['id'], self.sid, [1])
        storage.save_result(self.directory, 3, 'reprovado', 'Falha reproduzida')
        image = self.directory / 'evidencias' / 'source.png'
        image.parent.mkdir(exist_ok=True)
        image.write_bytes(self.image)
        with storage.db(self.directory) as db:
            with db:
                db.execute('INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?)',
                           ('source', 3, 'evidencias/source.png', 'source.png', 'image/png', len(self.image),
                            hashlib.sha256(self.image).hexdigest(), storage.now()))
        result = storage.sync_step_evidence(self.directory, 3, [1], True)
        self.assertEqual(result['case_states'][1]['manual_status'], 'reprovado')
        storage.start_case_run(self.directory, 1)
        storage.save_result(self.directory, 3, 'aprovado', 'Corrigido')
        result = storage.sync_step_evidence(self.directory, 3, [1], True)
        self.assertEqual(result['case_states'][1]['status'], 'bloqueado')

    def test_concurrent_backup_and_upload_restore_without_broken_references(self):
        bug = self.create_bug()
        barrier = threading.Barrier(2)
        results, errors = [], []
        def execute(action):
            try:
                barrier.wait()
                results.append(action())
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=execute, args=(action,)) for action in (
            lambda: self.service.add_evidence(bug['id'], 'abertura', self.image, 'extra.png'),
            lambda: make_backup(self.root))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        archive = next(result for result in results if isinstance(result, Path))
        restored = self.root / 'backup-restore'
        with zipfile.ZipFile(archive) as backup:
            backup.extractall(restored)
        service = BugsService(restored)
        for item in service.get(bug['id'])['evidence']:
            self.assertEqual(service.evidence_bytes(bug['id'], item['id'])[0], self.image)
