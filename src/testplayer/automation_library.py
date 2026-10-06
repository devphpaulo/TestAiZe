"""Persistent automation folders, cycles, scripts and immutable suite snapshots."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def name_value(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 120 or any(char in '/\\' or ord(char) < 32 for char in value):
        raise ValueError('Informe um nome de até 120 caracteres, sem barras.')
    return value.strip()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise LookupError('Item de automação não encontrado.')
    return value


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def redact(value, secrets):
    if isinstance(value, str):
        for secret in sorted((item for item in secrets if item), key=len, reverse=True):
            value = value.replace(secret, '[secret]')
        return re.sub(r'\x1b\[[0-9;]*m', '', value)
    if isinstance(value, list): return [redact(item, secrets) for item in value]
    if isinstance(value, dict): return {key: redact(item, secrets) for key, item in value.items()}
    return value


class AutomationLibrary:
    def __init__(self, data_root: Path):
        self.root = data_root.resolve() / 'automacao'
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'pastas').mkdir(exist_ok=True)
        (self.root / 'execucoes').mkdir(exist_ok=True)
        with self._db() as connection:
            connection.executescript('''
                CREATE TABLE IF NOT EXISTS folders(id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS cycles(id TEXT PRIMARY KEY, folder_id TEXT NOT NULL REFERENCES folders(id) ON DELETE CASCADE, name TEXT NOT NULL COLLATE NOCASE, created_at TEXT NOT NULL, UNIQUE(folder_id, name));
                CREATE TABLE IF NOT EXISTS scripts(id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL REFERENCES cycles(id) ON DELETE CASCADE, name TEXT NOT NULL COLLATE NOCASE, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(cycle_id, name));
                CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, folder_id TEXT NOT NULL, cycle_id TEXT, created_at TEXT NOT NULL);
            ''')

    @contextmanager
    def _db(self):
        connection = sqlite3.connect(self.root / 'biblioteca.sqlite3', timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection: yield connection
        except sqlite3.IntegrityError:
            raise ValueError('Já existe um item com esse nome nesta organização.') from None
        finally:
            connection.close()

    def folders(self):
        with self._db() as connection:
            return [dict(row) for row in connection.execute('''SELECT f.*,
                (SELECT count(*) FROM cycles c WHERE c.folder_id=f.id) AS cycle_count,
                (SELECT count(*) FROM scripts s JOIN cycles c ON s.cycle_id=c.id WHERE c.folder_id=f.id) AS script_count
                FROM folders f ORDER BY f.name''')]

    def _item(self, table, item_id):
        identifier(item_id)
        with self._db() as connection:
            row = connection.execute(f'SELECT * FROM {table} WHERE id=?', (item_id,)).fetchone()
        if row is None: raise LookupError('Item de automação não encontrado.')
        return dict(row)

    def folder(self, item_id): return self._item('folders', item_id)
    def cycle(self, item_id): return self._item('cycles', item_id)

    def cycles(self, folder_id):
        self.folder(folder_id)
        with self._db() as connection:
            return [dict(row) for row in connection.execute('''SELECT c.*, (SELECT count(*) FROM scripts s WHERE s.cycle_id=c.id) AS script_count
                FROM cycles c WHERE c.folder_id=? ORDER BY c.name''', (folder_id,))]

    def create_folder(self, name):
        item_id = uuid.uuid4().hex
        with self._db() as connection:
            connection.execute('INSERT INTO folders VALUES(?,?,?)', (item_id, name_value(name), timestamp()))
        self.folder_path(item_id).mkdir(parents=True)
        return self.folder(item_id)

    def create_cycle(self, folder_id, name):
        self.folder(folder_id)
        item_id = uuid.uuid4().hex
        with self._db() as connection:
            connection.execute('INSERT INTO cycles VALUES(?,?,?,?)', (item_id, folder_id, name_value(name), timestamp()))
        self.cycle_path(item_id).mkdir(parents=True)
        return self.cycle(item_id)

    def rename(self, table, item_id, name):
        if table not in ('folders', 'cycles'): raise ValueError('Tipo inválido.')
        self._item(table, item_id)
        with self._db() as connection:
            connection.execute(f'UPDATE {table} SET name=? WHERE id=?', (name_value(name), item_id))
        return self._item(table, item_id)

    def folder_path(self, folder_id):
        return self.root / 'pastas' / identifier(folder_id)

    def cycle_path(self, cycle_id):
        cycle = self.cycle(cycle_id)
        return self.folder_path(cycle['folder_id']) / 'ciclos' / cycle['id']

    def script_path(self, script_id):
        script = self._item('scripts', script_id)
        return self.cycle_path(script['cycle_id']) / (script['id'] + '.spec.ts')

    def script(self, script_id):
        script = self._item('scripts', script_id)
        cycle = self.cycle(script['cycle_id'])
        script.update(folder_id=cycle['folder_id'], cycle_name=cycle['name'], code=self.script_path(script_id).read_text(encoding='utf-8'))
        return script

    def scripts(self, folder_id, cycle_id=None):
        self.folder(folder_id)
        if cycle_id and self.cycle(cycle_id)['folder_id'] != folder_id: raise LookupError('Ciclo não pertence à pasta.')
        with self._db() as connection:
            rows = connection.execute('''SELECT s.id FROM scripts s JOIN cycles c ON c.id=s.cycle_id
                WHERE c.folder_id=? AND (? IS NULL OR c.id=?) ORDER BY c.name, s.name''', (folder_id, cycle_id, cycle_id)).fetchall()
        return [self.script(row['id']) for row in rows]

    def save_script(self, cycle_id, name, code, script_id=None):
        self.cycle(cycle_id)
        name = name_value(name)
        if not isinstance(code, str) or not code.strip() or len(code.encode('utf-8')) > 512 * 1024:
            raise ValueError('Informe código de teste de até 512 KB.')
        old_path = self.script_path(script_id) if script_id else None
        item_id = script_id or uuid.uuid4().hex
        created_at = self._item('scripts', item_id)['created_at'] if script_id else timestamp()
        target = self.cycle_path(cycle_id) / (item_id + '.spec.ts')
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as connection:
            connection.execute('''INSERT INTO scripts VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE
                SET cycle_id=excluded.cycle_id, name=excluded.name, updated_at=excluded.updated_at''', (item_id, cycle_id, name, created_at, timestamp()))
            temporary = target.with_suffix('.tmp')
            temporary.write_text(code, encoding='utf-8')
            temporary.replace(target)
        if old_path and old_path != target: old_path.unlink(missing_ok=True)
        return self.script(item_id)

    def delete(self, table, item_id):
        if table not in ('folders', 'cycles', 'scripts'): raise ValueError('Tipo inválido.')
        self._item(table, item_id)
        path = self.folder_path(item_id) if table == 'folders' else self.cycle_path(item_id) if table == 'cycles' else self.script_path(item_id)
        path.resolve().relative_to(self.root.resolve())
        if table == 'scripts': path.unlink(missing_ok=True)
        elif path.exists(): shutil.rmtree(path)
        with self._db() as connection:
            connection.execute(f'DELETE FROM {table} WHERE id=?', (item_id,))

    def run_path(self, run_id):
        return self.root / 'execucoes' / identifier(run_id)

    def create_run(self, folder_id, cycle_id, scripts):
        run_id = uuid.uuid4().hex
        path = self.run_path(run_id)
        (path / 'scripts').mkdir(parents=True)
        manifest = []
        for script in scripts:
            (path / 'scripts' / (script['id'] + '.spec.ts')).write_text(script['code'], encoding='utf-8')
            manifest.append({'id': script['id'], 'name': script['name']})
        atomic_json(path / 'manifest.json', manifest)
        self.write_report(run_id, {'state': 'running', 'total': 0, 'passed': 0, 'failed': 0, 'skipped': 0, 'results': [], 'errors': []})
        with self._db() as connection:
            connection.execute('INSERT INTO runs VALUES(?,?,?,?)', (run_id, folder_id, cycle_id, timestamp()))
        return self.run(run_id)

    def write_report(self, run_id, report, secrets=()):
        atomic_json(self.run_path(run_id) / 'report.json', redact(report, secrets))

    def run(self, run_id):
        run = self._item('runs', run_id)
        path = self.run_path(run_id)
        report = json.loads((path / 'report.json').read_text(encoding='utf-8'))
        names = {item['id']: item['name'] for item in json.loads((path / 'manifest.json').read_text(encoding='utf-8'))}
        for result in report.get('results', []): result['script_name'] = names.get(result.get('script_id'), 'Teste')
        return {**run, **report}

    def runs(self, folder_id, cycle_id=None):
        with self._db() as connection:
            rows = connection.execute('SELECT id FROM runs WHERE folder_id=? AND (? IS NULL OR cycle_id=?) ORDER BY created_at DESC, rowid DESC', (folder_id, cycle_id, cycle_id)).fetchall()
        return [self.run(row['id']) for row in rows]
