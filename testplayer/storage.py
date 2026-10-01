from __future__ import annotations

import json
import hashlib
import os
import shutil
import sqlite3
import unicodedata
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .attachments import attachment_content_type, attachment_extension
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
                connection.row_factory = sqlite3.Row
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
                                       "extension TEXT NOT NULL DEFAULT '', content_type TEXT NOT NULL DEFAULT 'application/octet-stream',"
                                       "size INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL)")
                    connection.execute("CREATE INDEX IF NOT EXISTS ix_step_attachments_step ON step_attachments(step_id)")
                    connection.execute("CREATE TABLE IF NOT EXISTS archived_attachments ("
                                       "id TEXT PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES cases(id),"
                                       "run_no INTEGER NOT NULL, relative_path TEXT NOT NULL, original_name TEXT NOT NULL,"
                                       "extension TEXT NOT NULL DEFAULT '', content_type TEXT NOT NULL DEFAULT 'application/octet-stream',"
                                       "size INTEGER NOT NULL DEFAULT 0, sha256 TEXT NOT NULL DEFAULT '',"
                                       "FOREIGN KEY(case_id,run_no) REFERENCES case_runs(case_id,run_no))")
                    connection.execute("CREATE INDEX IF NOT EXISTS ix_archived_attachments_run ON archived_attachments(case_id,run_no)")
                    step_columns = {row[1] for row in connection.execute("PRAGMA table_info(step_attachments)")}
                    if "extension" not in step_columns:
                        connection.execute("ALTER TABLE step_attachments ADD COLUMN extension TEXT NOT NULL DEFAULT ''")
                    if "content_type" not in step_columns:
                        connection.execute("ALTER TABLE step_attachments ADD COLUMN content_type TEXT NOT NULL DEFAULT 'application/octet-stream'")
                    archive_columns = {row[1] for row in connection.execute("PRAGMA table_info(archived_attachments)")}
                    for name, definition in (
                        ("extension", "TEXT NOT NULL DEFAULT ''"),
                        ("content_type", "TEXT NOT NULL DEFAULT 'application/octet-stream'"),
                        ("size", "INTEGER NOT NULL DEFAULT 0"),
                        ("sha256", "TEXT NOT NULL DEFAULT ''"),
                    ):
                        if name not in archive_columns:
                            connection.execute(f"ALTER TABLE archived_attachments ADD COLUMN {name} {definition}")
                    for row in connection.execute("SELECT id,original_name FROM step_attachments WHERE extension=''"):
                        connection.execute("UPDATE step_attachments SET extension=?,content_type=? WHERE id=?",
                                           (attachment_extension(row["original_name"]),
                                            attachment_content_type(row["original_name"]), row["id"]))
                    for row in connection.execute(
                        "SELECT case_id,run_no,snapshot_json FROM case_runs WHERE EXISTS ("
                        "SELECT 1 FROM archived_attachments WHERE archived_attachments.case_id=case_runs.case_id "
                        "AND archived_attachments.run_no=case_runs.run_no AND archived_attachments.sha256='')"
                    ):
                        snapshot = json.loads(row["snapshot_json"])
                        for step in snapshot.get("steps", []):
                            for item in step.get("attachments", []):
                                name = item["original_name"]
                                connection.execute(
                                    "UPDATE archived_attachments SET extension=?,content_type=?,size=?,sha256=? "
                                    "WHERE id=? AND sha256=''",
                                    (item.get("extension") or attachment_extension(name),
                                     item.get("content_type") or attachment_content_type(name),
                                     item.get("size", 0), item.get("sha256", ""), item["id"]),
                                )
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


def normalize_step_description(value: str) -> str:
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_diacritics = "".join(character for character in decomposed
                                  if unicodedata.category(character) != "Mn")
    return " ".join(unicodedata.normalize("NFC", without_diacritics).split())


def _verified_evidence_path(directory: Path, item: dict) -> Path:
    base = directory.resolve()
    path = (base / item["relative_path"]).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError(f"Evidência indisponível: {item['original_name']}")
    content = path.read_bytes()
    if len(content) != item["size"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
        raise ValueError(f"Integridade da evidência divergente: {item['original_name']}")
    return path


def _sync_context(connection: sqlite3.Connection, directory: Path, source_step_id: int) -> dict:
    meta = get_meta(connection)
    session_id = meta.get("id", "")
    if (meta.get("state") not in {"rascunho", "concluida"} or not session_id
            or (directory.name != session_id and not directory.name.endswith(f"-{session_id}"))):
        raise ValueError("Sessão indisponível para sincronização.")
    source = connection.execute(
        "SELECT s.id AS step_id,s.case_id,s.position AS step_position,s.action AS description,"
        "c.name AS case_name,c.folder,c.position AS case_position,r.status,r.status_changed_at,"
        "r.actual,r.actual_doc FROM steps s JOIN cases c ON c.id=s.case_id "
        "JOIN results r ON r.step_id=s.id WHERE s.id=?", (source_step_id,)
    ).fetchone()
    if source is None:
        raise LookupError("Passo de origem não encontrado.")
    source = dict(source)
    normalized = normalize_step_description(source["description"])
    if not normalized:
        raise ValueError("O passo de origem não possui descrição.")
    if source["status"] not in STATUSES or not source["status_changed_at"]:
        raise ValueError("Salve o status do passo de origem antes de sincronizar.")
    evidence = [dict(row) for row in connection.execute(
        "SELECT * FROM evidence WHERE step_id=? ORDER BY created_at,id", (source_step_id,)
    )]
    if not evidence:
        raise ValueError("O passo de origem não possui evidência persistida.")
    for item in evidence:
        _verified_evidence_path(directory, item)
    targets = []
    for row in connection.execute(
        "SELECT s.id AS step_id,s.case_id,s.position AS step_position,s.action AS description,"
        "c.name AS case_name,c.folder,c.position AS case_position,r.status,"
        "EXISTS(SELECT 1 FROM evidence e WHERE e.step_id=s.id) AS has_evidence "
        "FROM steps s JOIN cases c ON c.id=s.case_id JOIN results r ON r.step_id=s.id "
        "ORDER BY c.position,s.position"
    ):
        item = dict(row)
        item["has_evidence"] = bool(item["has_evidence"])
        if item["step_id"] != source_step_id and normalize_step_description(item["description"]) == normalized:
            targets.append(item)
    source_blocks = display_blocks(source["actual_doc"], source["actual"], evidence)
    widths = {block["id"]: block["width"] for block in source_blocks if block["type"] == "image"}
    source.update(evidence=evidence, evidence_count=len(evidence), evidence_widths=widths)
    return {"origin": source, "targets": targets}


def find_sync_targets(directory: Path, source_step_id: int) -> dict:
    with db(directory) as connection:
        context = _sync_context(connection, directory, source_step_id)
    origin = context["origin"]
    return {
        "origin": {
            key: origin[key] for key in (
                "step_id", "case_id", "step_position", "description", "case_name", "folder", "status",
                "evidence_count",
            )
        } | {"evidence": [{key: item[key] for key in ("id", "original_name", "mime", "size")}
                           for item in origin["evidence"]]},
        "targets": context["targets"],
    }


def _stored_document_blocks(raw: str | None, fallback: str, evidence: list[dict]) -> list[dict]:
    blocks = []
    for block in display_blocks(raw, fallback, evidence):
        if block["type"] == "text":
            blocks.append({"type": "text", "text": block["text"]})
        else:
            blocks.append({"type": "image", "id": block["id"], "width": block["width"]})
    return blocks


def sync_step_evidence(directory: Path, source_step_id: int, target_step_ids: list[int],
                       replicate_status: bool = False) -> dict:
    if (not isinstance(target_step_ids, list) or not target_step_ids
            or any(type(step_id) is not int for step_id in target_step_ids)):
        raise ValueError("Selecione ao menos um passo de destino válido.")
    if len(target_step_ids) != len(set(target_step_ids)):
        raise ValueError("A seleção contém passos duplicados.")
    temporary_files: list[Path] = []
    created_files: list[Path] = []
    target_case_ids: set[int] = set()
    with db(directory) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            context = _sync_context(connection, directory, source_step_id)
            valid_targets = {item["step_id"]: item for item in context["targets"]}
            if not set(target_step_ids).issubset(valid_targets):
                raise ValueError("Há passos inválidos ou não equivalentes na seleção.")
            source = context["origin"]
            copies: dict[int, list[tuple[dict, str, str]]] = {}
            for target_step_id in target_step_ids:
                target = valid_targets[target_step_id]
                current = connection.execute(
                    "SELECT COUNT(*) FROM evidence WHERE step_id=?", (target_step_id,)
                ).fetchone()[0]
                if current + len(source["evidence"]) > 12:
                    raise ValueError(f"O passo {target['step_position']} de {target['case_name']} excederia o limite de 12 imagens.")
                target_case_ids.add(target["case_id"])
                copies[target_step_id] = []
                target_time = datetime.now().astimezone()
                latest = connection.execute(
                    "SELECT MAX(created_at) FROM evidence WHERE step_id=?", (target_step_id,)
                ).fetchone()[0]
                if latest:
                    try:
                        latest_time = datetime.fromisoformat(latest)
                        if latest_time.tzinfo is None:
                            latest_time = latest_time.replace(tzinfo=target_time.tzinfo)
                        if latest_time >= target_time:
                            target_time = latest_time + timedelta(microseconds=1)
                    except ValueError:
                        pass
                for evidence_position, item in enumerate(source["evidence"]):
                    source_path = _verified_evidence_path(directory, item)
                    image_id = uuid.uuid4().hex
                    suffix = Path(item["relative_path"]).suffix
                    relative = (Path("evidencias") / f"caso-{target['case_id']}" /
                                f"passo-{target['step_position']}" / f"{image_id}{suffix}")
                    final_path = (directory / relative).resolve()
                    if not final_path.is_relative_to(directory.resolve()):
                        raise ValueError("Caminho de destino da evidência inválido.")
                    final_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = final_path.with_name(final_path.name + ".tmp")
                    temporary_files.append(temporary)
                    shutil.copy2(source_path, temporary)
                    copied = temporary.read_bytes()
                    if len(copied) != item["size"] or hashlib.sha256(copied).hexdigest() != item["sha256"]:
                        raise OSError(f"Falha ao validar a cópia de {item['original_name']}.")
                    os.replace(temporary, final_path)
                    temporary_files.remove(temporary)
                    created_files.append(final_path)
                    created_at = (target_time + timedelta(microseconds=evidence_position)).isoformat(timespec="microseconds")
                    connection.execute(
                        "INSERT INTO evidence(id,step_id,relative_path,original_name,mime,size,sha256,created_at) "
                        "VALUES (?,?,?,?,?,?,?,?)",
                        (image_id, target_step_id, relative.as_posix(), item["original_name"], item["mime"],
                         item["size"], item["sha256"], created_at),
                    )
                    copies[target_step_id].append((item, image_id, relative.as_posix()))
            for target_step_id in target_step_ids:
                row = connection.execute(
                    "SELECT actual,actual_doc FROM results WHERE step_id=?", (target_step_id,)
                ).fetchone()
                existing = [dict(item) for item in connection.execute(
                    "SELECT * FROM evidence WHERE step_id=? AND id NOT IN ({}) ORDER BY created_at,id".format(
                        ",".join("?" for _ in copies[target_step_id])),
                    (target_step_id, *(image_id for _, image_id, _ in copies[target_step_id])),
                )]
                blocks = _stored_document_blocks(row["actual_doc"], row["actual"], existing)
                blocks.extend({"type": "image", "id": image_id,
                               "width": source["evidence_widths"].get(item["id"], 100)}
                              for item, image_id, _ in copies[target_step_id])
                all_ids = {item[0] for item in connection.execute(
                    "SELECT id FROM evidence WHERE step_id=?", (target_step_id,)
                )}
                document, _ = normalize_document(blocks, all_ids)
                if replicate_status:
                    connection.execute(
                        "UPDATE results SET status=?,actual_doc=?,updated_at=?,status_changed_at=? WHERE step_id=?",
                        (source["status"], document, now(), now(), target_step_id),
                    )
                else:
                    connection.execute("UPDATE results SET actual_doc=? WHERE step_id=?", (document, target_step_id))
            connection.commit()
        except Exception:
            connection.rollback()
            for path in temporary_files + created_files:
                path.unlink(missing_ok=True)
            raise
    record = read_session(directory)
    statuses = {case["id"]: case["status"] for case in record["cases"] if case["id"] in target_case_ids}
    return {"ok": True, "synced": len(target_step_ids), "replicated_status": replicate_status,
            "case_statuses": statuses}


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
                "INSERT INTO archived_attachments(id,case_id,run_no,relative_path,original_name,extension,content_type,size,sha256) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                [(item["id"], case_id, run_no, item["relative_path"], item["original_name"],
                  item.get("extension") or attachment_extension(item["original_name"]),
                  item.get("content_type") or attachment_content_type(item["original_name"]),
                  item["size"], item["sha256"])
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
