"""Bug operations and durable recovery. No HTTP dependencies."""
import hashlib
import io
import json
import logging
import os
import shutil
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .bugs_coordinator import coordinated, root_operation, StateConflict, RecoveryPending
from .bugs_store import BugsStore

log = logging.getLogger(__name__)
RECOVERY_HANDLERS = {}
IMAGE_TYPES = {'PNG': ('image/png', '.png'), 'JPEG': ('image/jpeg', '.jpg'), 'WEBP': ('image/webp', '.webp')}


def register_recovery(kind, handler):
    RECOVERY_HANDLERS[kind] = handler


def recover_operations(root, store):
    with store.connect() as connection:
        operations = [dict(row) for row in connection.execute(
            "SELECT * FROM bug_operations WHERE phase!='done' ORDER BY created_at,operation_id")]
    for operation in operations:
        try:
            handler = RECOVERY_HANDLERS[operation['kind']]
            handler(root, store, operation)
        except Exception as error:
            log.error('bug recovery operation=%s kind=%s phase=%s',
                      operation['operation_id'], operation['kind'], operation['phase'])
            raise RecoveryPending(operation['operation_id']) from error


def _phase(store, operation_id, phase):
    from .storage import now
    with store.connect() as connection:
        connection.execute('UPDATE bug_operations SET phase=?,updated_at=? WHERE operation_id=?',
                           (phase, now(), operation_id))


def _intent(store, kind, payload):
    from .storage import now
    if kind not in RECOVERY_HANDLERS:
        raise ValueError('Operação sem recuperação registrada.')
    operation_id = uuid.uuid4().hex
    with store.connect() as connection:
        connection.execute('INSERT INTO bug_operations VALUES (?,?,?,?,?,?)',
                           (operation_id, kind, json.dumps(payload), 'intent', now(), now()))
    return operation_id


def _execute(root, store, operation_id):
    try:
        recover_operations(root, store)
    except RecoveryPending:
        # Retry a transient fault while still holding the root coordinator.
        # Persistent faults leave the intention durable and block new mutations.
        recover_operations(root, store)
    return operation_id


def _recover_link(root, store, operation):
    from .storage import db, find_directory, get_meta, now, reconcile_bug_status
    payload = json.loads(operation['payload'])
    directory = find_directory(root, payload['session_id'])
    if directory is None:
        raise StateConflict('Sessão da operação não encontrada.')
    # Validate all expected generations before applying either resource.
    with db(directory) as connection:
        if get_meta(connection).get('id') != payload['session_id']:
            raise StateConflict('Identidade da sessão inválida.')
        for item in payload['cases']:
            row = connection.execute('SELECT execution_generation FROM cases WHERE id=?', (item['id'],)).fetchone()
            if row is None or row[0] != item['generation']:
                raise StateConflict('Execução da operação mudou.')
    with store.connect() as connection:
        if connection.execute('SELECT status FROM bugs WHERE id=?', (payload['bug_id'],)).fetchone()[0] == 'finalizado':
            raise StateConflict('Bug finalizado durante recuperação.')
        for item in payload['cases']:
            connection.execute(
                'INSERT INTO bug_links VALUES (?,?,?,?,?,?) ON CONFLICT(bug_id,session_id,case_id) '
                'DO UPDATE SET active=1,linked_at=excluded.linked_at,previous_manual_status=excluded.previous_manual_status '
                'WHERE bug_links.active=0',
                (payload['bug_id'], payload['session_id'], item['id'], 1, payload['linked_at'], item['manual']))
    _phase(store, operation['operation_id'], 'links')
    with db(directory) as connection:
        connection.execute('BEGIN IMMEDIATE')
        for item in payload['cases']:
            connection.execute("UPDATE cases SET manual_status=?,status_revision=status_revision+1 "
                               "WHERE id=? AND manual_status<>?",
                               (item['status'], item['id'], item['status']))
        reconcile_bug_status(connection, {item['id'] for item in payload['cases']}, {item['id'] for item in payload['cases']})
        connection.commit()
    _phase(store, operation['operation_id'], 'done')


def _safe_session_path(root, relative, session_id, excluded=False):
    path = (root / relative).resolve()
    draft = (root / 'rascunhos').resolve()
    sessions = (root / 'sessoes').resolve()
    excluded_root = (root / 'excluidas').resolve()
    valid = path.parent == draft or path.parent.parent == sessions
    if excluded:
        valid = path.parent == excluded_root and path.name == session_id
    if not valid or path == root.resolve():
        raise ValueError('Pasta da operação fora da área de dados.')
    return path


def _recover_remove(root, store, operation):
    from .storage import db, get_meta
    payload = json.loads(operation['payload'])
    source = _safe_session_path(root, payload['source'], payload['session_id'])
    target = _safe_session_path(root, 'excluidas/' + payload['session_id'], payload['session_id'], True)
    if source.exists():
        if operation['phase'] not in ('removing', 'files'):
            with db(source) as connection:
                if get_meta(connection).get('id') != payload['session_id']:
                    raise StateConflict('Identidade da sessão inválida.')
            # A delete can remove its own SQLite file before the remaining tree.
            # Once authorized durably, recovery finishes the contained path.
            _phase(store, operation['operation_id'], 'removing')
        if payload['delete']:
            shutil.rmtree(source)
        else:
            source.rename(target)
    elif not payload['delete'] and not target.exists():
        raise StateConflict('Pasta da sessão movida não encontrada.')
    if not payload['delete']:
        with db(target) as connection:
            if get_meta(connection).get('id') != payload['session_id']:
                raise StateConflict('Destino da sessão inválido.')
    _phase(store, operation['operation_id'], 'files')
    with store.connect() as connection:
        if payload['delete']:
            connection.execute('DELETE FROM bug_links WHERE session_id=?', (payload['session_id'],))
        else:
            connection.execute('UPDATE bug_links SET active=0 WHERE session_id=?', (payload['session_id'],))
    _phase(store, operation['operation_id'], 'done')


register_recovery('link', _recover_link)
register_recovery('remove', _recover_remove)


class BugsService:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.store = BugsStore(self.root)
        with coordinated(self.root):
            self.cleanup_orphans()

    def cleanup_orphans(self):
        with self.store.connect() as connection:
            referenced = {row[0] for row in connection.execute(
                'SELECT relative_path FROM bug_evidence WHERE relative_path IS NOT NULL')}
        for path in (self.root / 'bugs').glob('*/evidencias/*'):
            if path.is_file() and path.relative_to(self.root / 'bugs').as_posix() not in referenced:
                path.unlink()

    def _bug(self, connection, bug_id):
        row = connection.execute('SELECT * FROM bugs WHERE id=?', (bug_id,)).fetchone()
        if row is None:
            raise LookupError('Bug não encontrado.')
        return dict(row)

    def get(self, bug_id):
        with coordinated(self.root), self.store.connect() as connection:
            bug = self._bug(connection, bug_id)
            bug['evidence'] = [dict(row) for row in connection.execute(
                'SELECT * FROM bug_evidence WHERE bug_id=? ORDER BY created_at,id', (bug_id,))]
            bug['links'] = [dict(row) for row in connection.execute(
                'SELECT * FROM bug_links WHERE bug_id=? ORDER BY linked_at,session_id,case_id', (bug_id,))]
            return bug

    def list(self, session_id=None):
        with coordinated(self.root), self.store.connect() as connection:
            if session_id:
                return [dict(row) for row in connection.execute(
                    'SELECT b.*,MAX(l.active) AS active FROM bugs b JOIN bug_links l ON b.id=l.bug_id '
                    'WHERE l.session_id=? GROUP BY b.id ORDER BY b.created_at DESC', (session_id,))]
            return [dict(row) for row in connection.execute('SELECT * FROM bugs ORDER BY created_at DESC')]

    def _fields(self, fields):
        clean = {}
        for key in ('title', 'severity', 'actual', 'expected'):
            value = fields.get(key)
            if not isinstance(value, str) or not value.strip() or len(value) > 20000:
                raise ValueError('Preencha nome, severidade, resultado obtido e esperado (até 20.000 caracteres).')
            clean[key] = value.strip()
        return clean

    def _image(self, content, original_name):
        if not content or len(content) > 10 * 1024 * 1024:
            raise ValueError('Imagem deve ter até 10 MiB.')
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in IMAGE_TYPES or image.width * image.height > 40_000_000:
                    raise ValueError('Use PNG, JPEG ou WebP com até 40 megapixels.')
                mime, extension = IMAGE_TYPES[image.format]
                image.verify()
        except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
            raise ValueError('Imagem inválida.') from error
        return dict(id=uuid.uuid4().hex, mime=mime, extension=extension, size=len(content),
                    sha256=hashlib.sha256(content).hexdigest(), original_name=Path(original_name).name[:255])

    def _publish_image(self, bug_id, content, metadata):
        relative = f"{bug_id}/evidencias/{metadata['id']}{metadata['extension']}"
        path = self.root / 'bugs' / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        try:
            temporary.write_bytes(content)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        metadata['relative_path'] = relative
        return path

    def _insert_image(self, connection, bug_id, metadata, kind, token=None, note=""):
        from .storage import now
        connection.execute('INSERT INTO bug_evidence '
                           '(id,bug_id,kind,retest_token,relative_path,mime,size,sha256,original_name,created_at,note) '
                           'VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (metadata['id'], bug_id, kind, token, metadata['relative_path'], metadata['mime'],
                            metadata['size'], metadata['sha256'], metadata['original_name'], now(), note.strip()))

    def _document(self, blocks, evidence_ids):
        from .storage import normalize_document
        document, plain = normalize_document(blocks, evidence_ids)
        used = {block['id'] for block in json.loads(document) if block['type'] == 'image'}
        if not plain.strip() or not used:
            raise ValueError('Descreva fluxo e passos e inclua ao menos uma imagem de abertura no documento.')
        return document

    def create(self, fields, files, session_id, origin_type='sessao', origin_case_id=None):
        from .storage import find_directory, read_session, now
        with coordinated(self.root):
            directory = find_directory(self.root, session_id)
            if directory is None:
                raise LookupError('Sessão de origem não encontrada.')
            if origin_type not in ('sessao', 'precondicao'):
                raise ValueError('Origem inválida.')
            if origin_type == 'precondicao' and origin_case_id not in {c['id'] for c in read_session(directory)['cases']}:
                raise ValueError('Pré-condição não pertence à sessão.')
            clean = self._fields(fields)
            if not files or len(files) > 12:
                raise ValueError('Inclua de 1 a 12 imagens de abertura.')
            bug_id = uuid.uuid4().hex
            images = {key: self._image(content, name) for key, (content, name) in files.items()}
            blocks = fields.get('blocks')
            if not isinstance(blocks, list):
                raise ValueError('Documento inválido.')
            blocks = [dict(b, id=images[b['id']]['id']) if isinstance(b, dict) and b.get('type') == 'image'
                      and b.get('id') in images else b for b in blocks]
            document = self._document(blocks, {m['id'] for m in images.values()})
            if {b['id'] for b in blocks if b.get('type') == 'image'} != {m['id'] for m in images.values()}:
                raise ValueError('Todas as imagens devem pertencer ao documento.')
            paths = []
            try:
                with self.store.connect() as connection:
                    connection.execute('INSERT INTO bugs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                       (bug_id, clean['title'], clean['severity'], 'aberto', origin_type, session_id,
                                        origin_case_id, document, clean['actual'], clean['expected'], None, now(), now()))
                    for key, metadata in images.items():
                        paths.append(self._publish_image(bug_id, files[key][0], metadata))
                        self._insert_image(connection, bug_id, metadata, 'abertura')
            except Exception:
                for path in paths:
                    path.unlink(missing_ok=True)
                raise
            return self.get(bug_id)

    def edit(self, bug_id, fields):
        with coordinated(self.root), self.store.connect() as connection:
            bug = self._bug(connection, bug_id)
            if bug['status'] == 'finalizado':
                raise StateConflict('Bug finalizado permite apenas consulta e exportação.')
            clean = self._fields(fields)
            ids = {row[0] for row in connection.execute(
                "SELECT id FROM bug_evidence WHERE bug_id=? AND kind='abertura'", (bug_id,))}
            document = self._document(fields.get('blocks'), ids)
            from .storage import now
            connection.execute('UPDATE bugs SET title=?,severity=?,actual=?,expected=?,description_doc=?,updated_at=? WHERE id=?',
                               (clean['title'], clean['severity'], clean['actual'], clean['expected'], document, now(), bug_id))
        return self.get(bug_id)

    def add_evidence(self, bug_id, kind, content=None, name='', note='', token=None):
        from .storage import now
        with coordinated(self.root):
            bug = self.get(bug_id)
            if bug['status'] == 'finalizado':
                raise StateConflict('Bug finalizado permite apenas consulta e exportação.')
            if kind not in ('abertura', 'reteste'):
                raise ValueError('Tipo de evidência inválido.')
            if kind == 'reteste' and (bug['status'] != 'em_reteste' or not token or token != bug['current_retest_token']):
                raise StateConflict('Reteste mudou. Recarregue o bug antes de anexar a prova.')
            if not isinstance(note, str) or len(note) > 20000 or (not content and not note.strip()):
                raise ValueError('Inclua uma nota ou imagem válida.')
            if kind == 'abertura' and token is not None:
                raise ValueError('Imagem de abertura não recebe token de reteste.')
            if kind == 'abertura' and not content:
                raise ValueError('Evidência de abertura deve ser uma imagem.')
            if sum(e['kind'] == kind and e['retest_token'] == token for e in bug['evidence']) >= 12:
                raise ValueError('Limite de 12 evidências por seção.')
            metadata = self._image(content, name) if content else None
            path = None
            try:
                with self.store.connect() as connection:
                    if metadata:
                        path = self._publish_image(bug_id, content, metadata)
                        self._insert_image(connection, bug_id, metadata, kind, token, note)
                    else:
                        metadata = {'id': uuid.uuid4().hex}
                        connection.execute('INSERT INTO bug_evidence(id,bug_id,kind,retest_token,note,created_at) VALUES (?,?,?,?,?,?)',
                                           (metadata['id'], bug_id, kind, token, note.strip(), now()))
            except Exception:
                if path:
                    path.unlink(missing_ok=True)
                raise
            return next(e for e in self.get(bug_id)['evidence'] if e['id'] == metadata['id'])

    def evidence_bytes(self, bug_id, evidence_id):
        with coordinated(self.root):
            evidence = next((e for e in self.get(bug_id)['evidence'] if e['id'] == evidence_id), None)
            if evidence is None or not evidence['relative_path']:
                raise LookupError('Imagem não encontrada neste bug.')
            base = (self.root / 'bugs' / bug_id / 'evidencias').resolve()
            path = (self.root / 'bugs' / evidence['relative_path']).resolve()
            if path.parent != base or path.is_symlink():
                raise ValueError('Caminho de evidência inválido.')
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != evidence['sha256'] or len(content) != evidence['size']:
                raise ValueError('Evidência ausente ou corrompida.')
            metadata = self._image(content, evidence['original_name'])
            if metadata['mime'] != evidence['mime']:
                raise ValueError('Tipo da evidência inconsistente.')
            return content, evidence['mime']

    def remove_evidence(self, bug_id, evidence_id):
        with coordinated(self.root):
            bug = self.get(bug_id)
            if bug['status'] == 'finalizado':
                raise StateConflict('Bug finalizado permite apenas consulta e exportação.')
            evidence = next((e for e in bug['evidence'] if e['id'] == evidence_id), None)
            if evidence is None:
                raise LookupError('Evidência não encontrada neste bug.')
            blocks = [b for b in json.loads(bug['description_doc']) if b.get('id') != evidence_id]
            if evidence['kind'] == 'abertura':
                fields = {k: bug[k] for k in ('title', 'severity', 'actual', 'expected')}
                self.edit(bug_id, dict(fields, blocks=blocks))
            with self.store.connect() as connection:
                connection.execute('DELETE FROM bug_evidence WHERE id=? AND bug_id=?', (evidence_id, bug_id))
            # Unreferenced files are collected only under the root coordinator.
            self.cleanup_orphans()

    def preview(self, bug_id, session_id):
        from .storage import find_directory, read_session
        with coordinated(self.root):
            bug = self.get(bug_id)
            directory = find_directory(self.root, session_id)
            if directory is None:
                raise LookupError('Sessão não encontrada.')
            record = read_session(directory)
            if record['meta']['state'] == 'concluida' or bug['status'] == 'finalizado':
                raise StateConflict('Sessão concluída ou bug finalizado não aceita vínculos novos.')
            active = {l['case_id'] for l in bug['links'] if l['session_id'] == session_id and l['active']}
            return [dict(id=c['id'], name=c['name'], folder=c['folder'], status=c['status'],
                         generation=c['execution_generation'], manual=c['manual_status'],
                         result='ja_vinculado' if c['id'] in active else 'recusado' if c['status'] == 'aprovado' else 'elegivel',
                         reason='Caso aprovado' if c['status'] == 'aprovado' and c['id'] not in active else '')
                    for c in record['cases']]

    def link(self, bug_id, session_id, case_ids):
        from .storage import now
        with coordinated(self.root):
            if (not isinstance(case_ids, list) or not case_ids or any(type(i) is not int for i in case_ids)
                    or len(set(case_ids)) != len(case_ids)):
                raise ValueError('Selecione casos válidos sem duplicação.')
            candidates = {c['id']: c for c in self.preview(bug_id, session_id)}
            if not set(case_ids).issubset(candidates):
                raise ValueError('Caso não pertence à sessão atual.')
            results = [candidates[i] for i in case_ids]
            eligible = [dict(c, status='reprovado' if c['status'] == 'reprovado' else 'bloqueado')
                        for c in results if c['result'] == 'elegivel']
            operation_id = None
            if eligible:
                operation_id = _intent(self.store, 'link', dict(bug_id=bug_id, session_id=session_id,
                                       cases=[{k: c[k] for k in ('id', 'generation', 'manual', 'status')} for c in eligible],
                                       linked_at=now()))
                _execute(self.root, self.store, operation_id)
            for item in results:
                if item['result'] == 'elegivel':
                    item['result'] = 'vinculado'
            return dict(operation_id=operation_id, results=results)

    def unlink(self, bug_id, session_id, case_id):
        with coordinated(self.root), self.store.connect() as connection:
            self._bug(connection, bug_id)
            connection.execute('UPDATE bug_links SET active=0 WHERE bug_id=? AND session_id=? AND case_id=?',
                               (bug_id, session_id, case_id))

    def transition(self, bug_id, target, expected_state, token=None):
        from .storage import now
        with coordinated(self.root), self.store.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            bug = self._bug(connection, bug_id)
            if target == bug['status'] == 'finalizado':
                return bug
            if bug['status'] != expected_state:
                raise StateConflict('Estado do bug mudou. Recarregue a página.')
            allowed = {'aberto': {'em_reteste'}, 'reaberto': {'em_reteste'},
                       'em_reteste': {'reaberto', 'finalizado'}, 'finalizado': set()}
            if target not in allowed[bug['status']]:
                raise StateConflict('Transição de bug inválida.')
            if bug['status'] == 'em_reteste' and token != bug['current_retest_token']:
                raise StateConflict('Prova pertence a outro reteste.')
            if target == 'finalizado':
                proof = connection.execute("SELECT 1 FROM bug_evidence WHERE bug_id=? AND kind='reteste' AND retest_token=?",
                                           (bug_id, token)).fetchone()
                if proof is None:
                    raise StateConflict('Inclua uma prova do reteste atual antes de finalizar.')
                connection.execute('UPDATE bug_links SET active=0 WHERE bug_id=?', (bug_id,))
            next_token = uuid.uuid4().hex if target == 'em_reteste' else bug['current_retest_token']
            connection.execute('UPDATE bugs SET status=?,current_retest_token=?,updated_at=? WHERE id=?',
                               (target, next_token, now(), bug_id))
        return self.get(bug_id)


@root_operation
def remove_session_recoverably(root, session_id, delete_files):
    from .storage import find_directory, db, get_meta
    store = BugsStore(root)
    directory = find_directory(root, session_id)
    if directory is None:
        raise LookupError('Sessão não encontrada.')
    source = _safe_session_path(root, directory.relative_to(root).as_posix(), session_id)
    with db(source) as connection:
        if get_meta(connection).get('id') != session_id:
            raise ValueError('Identidade da sessão inválida.')
    target = root / 'excluidas' / session_id
    if not delete_files and target.exists():
        raise FileExistsError('Já existe uma sessão com esse identificador em Excluídas.')
    operation_id = _intent(store, 'remove', dict(session_id=session_id, source=source.relative_to(root).as_posix(), delete=delete_files))
    _execute(root, store, operation_id)
    return None if delete_files else target
