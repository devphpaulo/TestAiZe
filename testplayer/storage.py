from __future__ import annotations

import json
import os
import shutil
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

from .bug_prompt import DEFAULT_PROMPT, PROMPT_FILENAME


SCHEMA = """
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
  FOREIGN KEY(case_id,run_no) REFERENCES case_runs(case_id,run_no)
);
CREATE INDEX IF NOT EXISTS ix_archived_attachments_run ON archived_attachments(case_id,run_no);
"""
STATUSES = {"nao_executado", "em_andamento", "aprovado", "reprovado", "bloqueado"}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_root(root: Path) -> None:
    for name in ("rascunhos", "sessoes", "excluidas", "temporarios", "backups", "logs", "config"):
        (root / name).mkdir(parents=True, exist_ok=True)
    prompt_path = root / PROMPT_FILENAME
    if not prompt_path.exists():
        prompt_path.write_text(DEFAULT_PROMPT, encoding="utf-8")


def migrate_sessions(root: Path) -> None:
    """Add columns and case evidence to sessions created by earlier versions."""
    paths = list((root / "rascunhos").glob("*/sessao.sqlite"))
    paths += list((root / "sessoes").glob("*/*/sessao.sqlite"))
    for path in paths:
        try:
            with closing(sqlite3.connect(path)) as connection:
                with connection:
                    columns = {row[1] for row in connection.execute("PRAGMA table_info(cases)")}
                    if "manual_status" not in columns:
                        connection.execute("ALTER TABLE cases ADD COLUMN manual_status TEXT NOT NULL DEFAULT ''")
                    if "comment" not in columns:
                        connection.execute("ALTER TABLE cases ADD COLUMN comment TEXT NOT NULL DEFAULT ''")
                    if "comment_doc" not in columns:
                        connection.execute("ALTER TABLE cases ADD COLUMN comment_doc TEXT")
                    if "precondition_doc" not in columns:
                        connection.execute("ALTER TABLE cases ADD COLUMN precondition_doc TEXT")
                    if "precondition_note_mode" not in columns:
                        connection.execute("ALTER TABLE cases ADD COLUMN precondition_note_mode INTEGER NOT NULL DEFAULT 0")
                    result_columns = {row[1] for row in connection.execute("PRAGMA table_info(results)")}
                    if "status_changed_at" not in result_columns:
                        connection.execute("ALTER TABLE results ADD COLUMN status_changed_at TEXT")
                        connection.execute("UPDATE results SET status_changed_at=updated_at WHERE status!='nao_executado'")
                    if "actual_doc" not in result_columns:
                        connection.execute("ALTER TABLE results ADD COLUMN actual_doc TEXT")
                    connection.execute("CREATE TABLE IF NOT EXISTS case_evidence ("
                                       "id TEXT PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),"
                                       "scope TEXT NOT NULL, relative_path TEXT NOT NULL UNIQUE,"
                                       "original_name TEXT NOT NULL, mime TEXT NOT NULL, size INTEGER NOT NULL,"
                                       "sha256 TEXT NOT NULL, created_at TEXT NOT NULL)")
                    connection.execute("CREATE INDEX IF NOT EXISTS ix_case_evidence_case ON case_evidence(case_id,scope)")
                    connection.execute("CREATE TABLE IF NOT EXISTS case_runs ("
                                       "case_id INTEGER NOT NULL REFERENCES cases(id), run_no INTEGER NOT NULL,"
                                       "captured_at TEXT NOT NULL, status TEXT NOT NULL, snapshot_json TEXT NOT NULL,"
                                       "PRIMARY KEY(case_id,run_no))")
                    connection.execute("CREATE TABLE IF NOT EXISTS archived_evidence ("
                                       "id TEXT PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),"
                                       "run_no INTEGER NOT NULL, relative_path TEXT NOT NULL, mime TEXT NOT NULL,"
                                       "FOREIGN KEY(case_id,run_no) REFERENCES case_runs(case_id,run_no))")
                    connection.execute("CREATE INDEX IF NOT EXISTS ix_archived_evidence_run ON archived_evidence(case_id,run_no)")
                    connection.execute("CREATE TABLE IF NOT EXISTS step_attachments ("
                                       "id TEXT PRIMARY KEY, step_id INTEGER NOT NULL REFERENCES steps(id),"
                                       "relative_path TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL,"
                                       "size INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL)")
                    connection.execute("CREATE INDEX IF NOT EXISTS ix_step_attachments_step ON step_attachments(step_id)")
                    connection.execute("CREATE TABLE IF NOT EXISTS archived_attachments ("
                                       "id TEXT PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),"
                                       "run_no INTEGER NOT NULL, relative_path TEXT NOT NULL, original_name TEXT NOT NULL,"
                                       "FOREIGN KEY(case_id,run_no) REFERENCES case_runs(case_id,run_no))")
                    connection.execute("CREATE INDEX IF NOT EXISTS ix_archived_attachments_run ON archived_attachments(case_id,run_no)")
        except (OSError, sqlite3.DatabaseError):
            continue


@contextmanager
def db(directory: Path):
    connection = sqlite3.connect(directory / "sessao.sqlite", timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
    finally:
        connection.close()


def set_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute("INSERT OR REPLACE INTO meta(key,value) VALUES (?,?)", (key, value))


def get_meta(connection: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in connection.execute("SELECT key,value FROM meta")}


def _write_manifest(directory: Path) -> None:
    with db(directory) as connection:
        meta = get_meta(connection)
        cases = connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
        steps = connection.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
    manifest = {
        "id": meta["id"], "state": meta["state"], "created_at": meta["created_at"],
        "finalized_at": meta.get("finalized_at", ""), "source_name": meta.get("source_name", ""),
        "parent_id": meta.get("parent_id", ""), "cases": cases, "steps": steps,
    }
    temporary = directory / "manifesto.json.tmp"
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, directory / "manifesto.json")


def create_draft(root: Path, parsed: dict, source_path: Path, selected: set[str], display_name: str | None = None) -> str:
    session_id = uuid.uuid4().hex
    directory = root / "rascunhos" / session_id
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "origem").mkdir()
    (directory / "evidencias").mkdir()
    (directory / "relatorios").mkdir()
    try:
        stored_name = f"entrada{source_path.suffix.lower()}"
        shutil.copy2(source_path, directory / "origem" / stored_name)
        with db(directory) as connection:
            connection.executescript(SCHEMA)
            with connection:
                for key, value in {
                    "id": session_id,
                    "state": "rascunho",
                    "created_at": now(),
                    "source_name": display_name or source_path.name,
                    "source_file": stored_name,
                    "source_sha256": parsed["sha256"],
                    "sheets": json.dumps(sorted(selected), ensure_ascii=False),
                    "parent_id": "",
                }.items():
                    set_meta(connection, key, value)
                case_position = 0
                for sheet in parsed["sheets"]:
                    if sheet["name"] not in selected:
                        continue
                    for case in sheet["cases"]:
                        case_position += 1
                        cursor = connection.execute(
                            "INSERT INTO cases(position,sheet,source_row,name,precondition,source_status,priority,folder) "
                            "VALUES (?,?,?,?,?,?,?,?)",
                            (case_position, case["sheet"], case["row"], case["name"], case["precondition"],
                             case["source_status"], case["priority"], case["folder"]),
                        )
                        case_id = cursor.lastrowid
                        for position, step in enumerate(case["steps"], start=1):
                            cursor = connection.execute(
                                "INSERT INTO steps(case_id,position,action,test_data,expected) VALUES (?,?,?,?,?)",
                                (case_id, position, step["action"], step["test_data"], step["expected"]),
                            )
                            connection.execute("INSERT INTO results(step_id) VALUES (?)", (cursor.lastrowid,))
        _write_manifest(directory)
        return session_id
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def find_directory(root: Path, session_id: str) -> Path | None:
    try:
        uuid.UUID(hex=session_id)
    except (ValueError, AttributeError):
        return None
    draft = root / "rascunhos" / session_id
    if (draft / "sessao.sqlite").is_file():
        return draft
    for day in (root / "sessoes").iterdir():
        if not day.is_dir():
            continue
        for directory in day.glob(f"execucao-*-{session_id}"):
            if (directory / "sessao.sqlite").is_file():
                return directory
    return None


def remove_session(root: Path, session_id: str, delete_files: bool) -> Path | None:
    """Hide an active session by moving it to excluidas, or delete its verified directory."""
    directory = find_directory(root, session_id)
    if directory is None:
        raise LookupError("Sessão não encontrada.")
    source = directory.resolve()
    draft_root = (root / "rascunhos").resolve()
    completed_root = (root / "sessoes").resolve()
    if directory.is_symlink() or not (source.parent == draft_root or source.parent.parent == completed_root):
        raise ValueError("Pasta da sessão fora da área de dados.")
    with db(source) as connection:
        if get_meta(connection).get("id") != session_id:
            raise ValueError("Identidade da sessão inválida.")
    if delete_files:
        shutil.rmtree(source)
        return None
    excluded_root = (root / "excluidas").resolve()
    excluded_root.mkdir(parents=True, exist_ok=True)
    target = (excluded_root / session_id).resolve()
    if not target.is_relative_to(excluded_root) or target == excluded_root or target.exists():
        raise FileExistsError("Já existe uma sessão com esse identificador em Excluídas.")
    source.rename(target)
    return target


def normalize_document(blocks: object, evidence_ids: set[str]) -> tuple[str, str]:
    """Store editor content as text and references to images owned by this field."""
    if not isinstance(blocks, list) or len(blocks) > 150:
        raise ValueError("Conteúdo da evidência inválido.")
    clean = []
    seen = set()
    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("Bloco de evidência inválido.")
        if block.get("type") == "text":
            value = block.get("text")
            if not isinstance(value, str):
                raise ValueError("Texto de evidência inválido.")
            clean.append({"type": "text", "text": value})
        elif block.get("type") == "image":
            image_id = block.get("id")
            width = block.get("width", 100)
            if image_id not in evidence_ids or image_id in seen or type(width) not in (int, float):
                raise ValueError("Imagem não pertence a este campo.")
            seen.add(image_id)
            clean.append({"type": "image", "id": image_id, "width": max(20, min(100, round(width)))})
        else:
            raise ValueError("Tipo de bloco de evidência inválido.")
    plain = "\n".join(block["text"] for block in clean if block["type"] == "text")
    if len(plain) > 20_000:
        raise ValueError("Texto excede 20.000 caracteres.")
    return json.dumps(clean, ensure_ascii=False), plain


def display_blocks(raw: str | None, fallback: str, evidence: list[dict]) -> list[dict]:
    images = {item["id"]: item for item in evidence}
    try:
        blocks = json.loads(raw) if raw is not None else None
    except (TypeError, json.JSONDecodeError):
        blocks = None
    if not isinstance(blocks, list):
        blocks = [{"type": "text", "text": fallback}]
    shown = []
    seen = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            shown.append({"type": "text", "text": block["text"]})
        elif block.get("type") == "image" and block.get("id") in images:
            item = images[block["id"]]
            shown.append({"type": "image", "id": item["id"], "width": max(20, min(100, int(block.get("width", 100)))), "item": item})
            seen.add(item["id"])
    for item in evidence:
        if item["id"] not in seen:
            shown.append({"type": "image", "id": item["id"], "width": 100, "item": item})
    if shown and shown[-1]["type"] == "image":
        shown.append({"type": "text", "text": ""})
    return shown or [{"type": "text", "text": ""}]


def precondition_notes(blocks: list[dict], source: str, note_mode: int) -> list[dict]:
    """Separate the immutable spreadsheet value from older mixed editor documents."""
    if note_mode or not source or not blocks or blocks[0]["type"] != "text":
        return blocks
    first = blocks[0]["text"]
    if first == source:
        return blocks[1:] or [{"type": "text", "text": ""}]
    if first.startswith(source + "\n"):
        return [{"type": "text", "text": first[len(source) + 1:]}] + blocks[1:]
    return blocks


def _hydrate_case(connection: sqlite3.Connection, case: dict) -> dict:
    steps = [dict(row) for row in connection.execute(
        "SELECT s.*,r.status,r.actual,r.actual_doc,r.comment,r.updated_at,r.status_changed_at FROM steps s "
        "JOIN results r ON r.step_id=s.id WHERE s.case_id=? ORDER BY s.position", (case["id"],)
    )]
    for step in steps:
        step["evidence"] = [dict(row) for row in connection.execute(
            "SELECT * FROM evidence WHERE step_id=? ORDER BY created_at,id", (step["id"],)
        )]
        step["attachments"] = [dict(row) for row in connection.execute(
            "SELECT * FROM step_attachments WHERE step_id=? ORDER BY created_at,id", (step["id"],)
        )]
        step["actual_blocks"] = display_blocks(step["actual_doc"], step["actual"], step["evidence"])
    case["steps"] = steps
    case["precondition_evidence"] = [dict(row) for row in connection.execute(
        "SELECT * FROM case_evidence WHERE case_id=? AND scope='precondition' ORDER BY created_at,id", (case["id"],)
    )]
    case["precondition_blocks"] = display_blocks(case["precondition_doc"], "",
                                                  case["precondition_evidence"])
    case["precondition_notes_blocks"] = precondition_notes(
        case["precondition_blocks"], case["precondition"], case["precondition_note_mode"])
    case["comment_evidence"] = [dict(row) for row in connection.execute(
        "SELECT * FROM case_evidence WHERE case_id=? AND scope='comment' ORDER BY created_at,id", (case["id"],)
    )]
    case["comment_blocks"] = display_blocks(case["comment_doc"], case["comment"], case["comment_evidence"])
    case["status"] = case["manual_status"] or aggregate([s["status"] for s in steps])
    return case


def read_session(directory: Path) -> dict:
    with db(directory) as connection:
        meta = get_meta(connection)
        cases = [_hydrate_case(connection, dict(row)) for row in connection.execute("SELECT * FROM cases ORDER BY position")]
        for case in cases:
            case["previous_runs"] = [
                {"run_no": row["run_no"], "captured_at": row["captured_at"], "status": row["status"],
                 "snapshot": json.loads(row["snapshot_json"])}
                for row in connection.execute(
                    "SELECT run_no,captured_at,status,snapshot_json FROM case_runs WHERE case_id=? ORDER BY run_no DESC",
                    (case["id"],))
            ]
        counts = {key: 0 for key in ("nao_executado", "em_andamento", "aprovado", "reprovado", "bloqueado")}
        for case in cases:
            counts[case["status"]] += 1
        return {"meta": meta, "cases": cases, "counts": counts, "steps_total": sum(len(c["steps"]) for c in cases)}


def aggregate(statuses: list[str]) -> str:
    if not statuses or all(s == "nao_executado" for s in statuses):
        return "nao_executado"
    if "reprovado" in statuses:
        return "reprovado"
    if "bloqueado" in statuses:
        return "bloqueado"
    if all(s == "aprovado" for s in statuses):
        return "aprovado"
    return "em_andamento"


def list_sessions(root: Path) -> list[dict]:
    found = []
    directories = list((root / "rascunhos").glob("*/sessao.sqlite"))
    directories += list((root / "sessoes").glob("*/*/sessao.sqlite"))
    for db_path in directories:
        directory = db_path.parent
        try:
            manifest_path = directory / "manifesto.json"
            if not manifest_path.is_file():
                _write_manifest(directory)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            found.append(manifest)
        except (OSError, json.JSONDecodeError, sqlite3.DatabaseError, KeyError):
            continue
    return sorted(found, key=lambda item: item.get("finalized_at") or item.get("created_at", ""), reverse=True)


def save_result(directory: Path, step_id: int, status: str, actual: str, comment: str | None = None,
                status_action: bool = False, actual_doc: object | None = None) -> str | None:
    if status not in STATUSES:
        raise ValueError("Status de passo inválido.")
    if len(actual) > 20_000 or (comment is not None and len(comment) > 20_000):
        raise ValueError("Resultado ou comentário excede 20.000 caracteres.")
    with db(directory) as connection:
        with connection:
            normalized_doc = None
            if actual_doc is not None:
                ids = {row[0] for row in connection.execute("SELECT id FROM evidence WHERE step_id=?", (step_id,))}
                normalized_doc, actual = normalize_document(actual_doc, ids)
            if comment is None:
                cursor = connection.execute(
                    "UPDATE results SET status=?,actual=?,actual_doc=COALESCE(?,actual_doc),updated_at=?,"
                    "status_changed_at=CASE WHEN ? OR status<>? THEN ? ELSE status_changed_at END WHERE step_id=?",
                    (status, actual, normalized_doc, now(), status_action, status, now(), step_id),
                )
            else:
                cursor = connection.execute(
                    "UPDATE results SET status=?,actual=?,actual_doc=COALESCE(?,actual_doc),comment=?,updated_at=?,"
                    "status_changed_at=CASE WHEN ? OR status<>? THEN ? ELSE status_changed_at END WHERE step_id=?",
                    (status, actual, normalized_doc, comment, now(), status_action, status, now(), step_id),
                )
            if cursor.rowcount != 1:
                raise LookupError("Passo não encontrado.")
            return connection.execute("SELECT status_changed_at FROM results WHERE step_id=?", (step_id,)).fetchone()[0]


def save_case(directory: Path, case_id: int, status: str, comment: str, comment_doc: object | None = None,
              precondition_doc: object | None = None) -> None:
    if status not in STATUSES | {""}:
        raise ValueError("Status de caso inválido.")
    if len(comment) > 20_000:
        raise ValueError("Comentário excede 20.000 caracteres.")
    with db(directory) as connection:
        with connection:
            normalized_doc = None
            if comment_doc is not None:
                ids = {row[0] for row in connection.execute(
                    "SELECT id FROM case_evidence WHERE case_id=? AND scope='comment'", (case_id,))}
                normalized_doc, comment = normalize_document(comment_doc, ids)
            normalized_precondition = None
            if precondition_doc is not None:
                ids = {row[0] for row in connection.execute(
                    "SELECT id FROM case_evidence WHERE case_id=? AND scope='precondition'", (case_id,))}
                normalized_precondition, _ = normalize_document(precondition_doc, ids)
            cursor = connection.execute(
                "UPDATE cases SET manual_status=?,comment=?,comment_doc=COALESCE(?,comment_doc),"
                "precondition_doc=COALESCE(?,precondition_doc),"
                "precondition_note_mode=CASE WHEN ? IS NOT NULL THEN 1 ELSE precondition_note_mode END WHERE id=?",
                (status, comment, normalized_doc, normalized_precondition, normalized_precondition, case_id),
            )
            if cursor.rowcount != 1:
                raise LookupError("Caso não encontrado.")


def start_case_run(directory: Path, case_id: int) -> int:
    """Archive one case's current execution and reset only that case in the same session."""
    with db(directory) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if row is None:
                raise LookupError("Caso não encontrado.")
            snapshot = _hydrate_case(connection, dict(row))
            run_no = connection.execute(
                "SELECT COALESCE(MAX(run_no),0)+1 FROM case_runs WHERE case_id=?", (case_id,)
            ).fetchone()[0]
            captured_at = now()
            connection.execute(
                "INSERT INTO case_runs(case_id,run_no,captured_at,status,snapshot_json) VALUES (?,?,?,?,?)",
                (case_id, run_no, captured_at, snapshot["status"], json.dumps(snapshot, ensure_ascii=False)),
            )
            images = snapshot["precondition_evidence"] + snapshot["comment_evidence"]
            images += [item for step in snapshot["steps"] for item in step["evidence"]]
            connection.executemany(
                "INSERT INTO archived_evidence(id,case_id,run_no,relative_path,mime) VALUES (?,?,?,?,?)",
                [(item["id"], case_id, run_no, item["relative_path"], item["mime"]) for item in images],
            )
            attachments = [item for step in snapshot["steps"] for item in step["attachments"]]
            connection.executemany(
                "INSERT INTO archived_attachments(id,case_id,run_no,relative_path,original_name) VALUES (?,?,?,?,?)",
                [(item["id"], case_id, run_no, item["relative_path"], item["original_name"])
                 for item in attachments],
            )
            connection.execute("DELETE FROM evidence WHERE step_id IN (SELECT id FROM steps WHERE case_id=?)", (case_id,))
            connection.execute("DELETE FROM step_attachments WHERE step_id IN (SELECT id FROM steps WHERE case_id=?)", (case_id,))
            connection.execute("DELETE FROM case_evidence WHERE case_id=?", (case_id,))
            connection.execute(
                "UPDATE results SET status='nao_executado',actual='',actual_doc=NULL,comment='',"
                "updated_at=NULL,status_changed_at=NULL WHERE step_id IN (SELECT id FROM steps WHERE case_id=?)",
                (case_id,),
            )
            connection.execute(
                "UPDATE cases SET manual_status='',comment='',comment_doc=NULL,precondition_doc=NULL,"
                "precondition_note_mode=1 WHERE id=?",
                (case_id,),
            )
            connection.commit()
            return run_no
        except Exception:
            connection.rollback()
            raise


def finalize(root: Path, directory: Path) -> Path:
    with db(directory) as connection:
        with connection:
            meta = get_meta(connection)
            if meta.get("state") != "rascunho":
                raise ValueError("Esta sessão já foi concluída.")
            total_steps = connection.execute("SELECT COUNT(*) FROM steps").fetchone()[0]
            if not total_steps:
                raise ValueError("A sessão não possui passos.")
            set_meta(connection, "state", "concluida")
            set_meta(connection, "finalized_at", now())
    return promote(root, directory)


def promote(root: Path, directory: Path) -> Path:
    with db(directory) as connection:
        meta = get_meta(connection)
    finalized = datetime.fromisoformat(meta["finalized_at"])
    day = root / "sessoes" / finalized.strftime("%Y-%m-%d")
    day.mkdir(parents=True, exist_ok=True)
    target = day / f"execucao-{finalized.strftime('%H%M%S')}-{meta['id']}"
    if directory.resolve() != target.resolve():
        if target.exists():
            raise FileExistsError("Destino da sessão já existe.")
        directory.rename(target)
    _write_manifest(target)
    return target


def recover_promotions(root: Path) -> None:
    for db_path in (root / "rascunhos").glob("*/sessao.sqlite"):
        directory = db_path.parent
        try:
            with db(directory) as connection:
                state = get_meta(connection).get("state")
            if state == "concluida":
                promote(root, directory)
        except (OSError, sqlite3.DatabaseError, KeyError, ValueError):
            continue


def rerun(root: Path, source_dir: Path) -> str:
    with db(source_dir) as source:
        source_meta = get_meta(source)
        if source_meta.get("state") != "concluida":
            raise ValueError("Conclua a sessão antes de iniciar outra execução a partir dela.")
        original_cases = [dict(row) for row in source.execute("SELECT * FROM cases ORDER BY position")]
        original_steps = [dict(row) for row in source.execute("SELECT * FROM steps ORDER BY case_id,position")]
    session_id = uuid.uuid4().hex
    directory = root / "rascunhos" / session_id
    directory.mkdir(parents=True, exist_ok=False)
    try:
        (directory / "origem").mkdir()
        (directory / "evidencias").mkdir()
        (directory / "relatorios").mkdir()
        source_file = source_dir / "origem" / source_meta["source_file"]
        shutil.copy2(source_file, directory / "origem" / source_file.name)
        with db(directory) as connection:
            connection.executescript(SCHEMA)
            with connection:
                for key, value in {
                    "id": session_id, "state": "rascunho", "created_at": now(),
                    "source_name": source_meta["source_name"],
                    "source_file": source_meta["source_file"],
                    "source_sha256": source_meta.get("source_sha256", ""),
                    "sheets": source_meta.get("sheets", "[]"),
                    "parent_id": source_meta["id"],
                }.items():
                    set_meta(connection, key, value)
                ids = {}
                for case in original_cases:
                    cursor = connection.execute(
                        "INSERT INTO cases(position,sheet,source_row,name,precondition,source_status,priority,folder) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (case["position"], case["sheet"], case["source_row"], case["name"],
                         case["precondition"], case["source_status"], case["priority"], case["folder"]),
                    )
                    ids[case["id"]] = cursor.lastrowid
                for step in original_steps:
                    cursor = connection.execute(
                        "INSERT INTO steps(case_id,position,action,test_data,expected) VALUES (?,?,?,?,?)",
                        (ids[step["case_id"]], step["position"], step["action"], step["test_data"], step["expected"]),
                    )
                    connection.execute("INSERT INTO results(step_id) VALUES (?)", (cursor.lastrowid,))
        _write_manifest(directory)
        return session_id
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
