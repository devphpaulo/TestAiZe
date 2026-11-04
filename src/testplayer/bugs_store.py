"""Global bug database. Session IDs are references, never cross-database foreign keys."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


class MigrationError(RuntimeError):
    pass


SCHEMA = (
    "CREATE TABLE bugs (id TEXT PRIMARY KEY,title TEXT NOT NULL,severity TEXT NOT NULL,"
    "status TEXT NOT NULL CHECK(status IN ('aberto','em_reteste','reaberto','finalizado')),"
    "origin_type TEXT NOT NULL CHECK(origin_type IN ('sessao','precondicao')),origin_session_id TEXT NOT NULL,"
    "origin_case_id INTEGER,description_doc TEXT NOT NULL,actual TEXT NOT NULL,expected TEXT NOT NULL,"
    "current_retest_token TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",
    "CREATE TABLE bug_evidence (id TEXT PRIMARY KEY,bug_id TEXT NOT NULL REFERENCES bugs(id),"
    "kind TEXT NOT NULL CHECK(kind IN ('abertura','reteste')),retest_token TEXT,note TEXT NOT NULL DEFAULT '',"
    "relative_path TEXT UNIQUE,mime TEXT,size INTEGER,sha256 TEXT,original_name TEXT,created_at TEXT NOT NULL,"
    "CHECK(length(trim(note))>0 OR relative_path IS NOT NULL),"
    "CHECK((kind='abertura' AND retest_token IS NULL) OR (kind='reteste' AND retest_token IS NOT NULL)))",
    "CREATE TABLE bug_links (bug_id TEXT NOT NULL REFERENCES bugs(id),session_id TEXT NOT NULL,case_id INTEGER NOT NULL,"
    "active INTEGER NOT NULL CHECK(active IN (0,1)),linked_at TEXT NOT NULL,previous_manual_status TEXT,"
    "PRIMARY KEY(bug_id,session_id,case_id))",
    "CREATE INDEX ix_bug_links_case ON bug_links(session_id,case_id,active)",
    "CREATE INDEX ix_bug_evidence_bug ON bug_evidence(bug_id,kind,retest_token)",
    "CREATE TABLE bug_operations (operation_id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,"
    "phase TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)",
)


class BugsStore:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.path = self.root / 'bugs' / 'bugs.sqlite'

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.connect() as connection:
                connection.execute('BEGIN IMMEDIATE')
                version = connection.execute('PRAGMA user_version').fetchone()[0]
                if version == 0:
                    for statement in SCHEMA:
                        connection.execute(statement)
                    connection.execute('PRAGMA user_version=1')
                elif version != 1:
                    raise MigrationError('Versão do banco de bugs incompatível.')
                for table in ('bugs', 'bug_evidence', 'bug_links', 'bug_operations'):
                    connection.execute(f'SELECT * FROM {table} LIMIT 0')
        except sqlite3.DatabaseError as error:
            raise MigrationError('Falha na migração do banco de bugs.') from error

    def active_cases(self, session_id):
        with self.connect() as connection:
            return {row[0] for row in connection.execute(
                'SELECT case_id FROM bug_links WHERE session_id=? AND active=1', (session_id,))}
