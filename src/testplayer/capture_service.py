"""Commit of a capture and observed text. The desktop host never writes SQLite itself."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .storage import (
    RevisionConflict,
    StaleExecution,
    db,
    display_blocks,
    normalize_document,
    now,
)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_IMAGES = 12
_COMMAND_ID = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
_IMAGE_TYPES = {"PNG": ("image/png", ".png"), "JPEG": ("image/jpeg", ".jpg"), "WEBP": ("image/webp", ".webp")}


class CaptureError(Exception):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def replace_observed_text(blocks: list[dict], text: str) -> list[dict]:
    """Replace text blocks and keep image blocks where they already are."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines:
        lines = [""]
    result: list[dict] = []
    line_index = 0
    for block in blocks:
        if block.get("type") == "image" and isinstance(block.get("id"), str):
            width = block.get("width", 100)
            result.append({"type": "image", "id": block["id"], "width": width})
            continue
        if block.get("type") != "text":
            continue
        if line_index < len(lines):
            result.append({"type": "text", "text": lines[line_index]})
            line_index += 1
    while line_index < len(lines):
        result.append({"type": "text", "text": lines[line_index]})
        line_index += 1
    if not any(block.get("type") == "text" for block in result):
        result.append({"type": "text", "text": ""})
    return result or [{"type": "text", "text": ""}]


def _stored_blocks(actual: str, actual_doc: str | None) -> list[dict]:
    try:
        blocks = json.loads(actual_doc) if actual_doc else None
    except (TypeError, json.JSONDecodeError):
        blocks = None
    if not isinstance(blocks, list):
        return [{"type": "text", "text": actual or ""}]
    return blocks


def load_case_context(directory: Path, case_id: int, step_id: int) -> dict:
    with db(directory) as connection:
        case = connection.execute(
            "SELECT id,name,execution_generation FROM cases WHERE id=?", (case_id,)
        ).fetchone()
        if case is None:
            raise CaptureError("INVALID_TARGET", "Caso não encontrado.", 404)
        steps = [dict(row) for row in connection.execute(
            "SELECT s.id,s.position,s.action,EXISTS("
            "SELECT 1 FROM capture_commands c JOIN evidence e ON e.id=c.evidence_id "
            "WHERE c.step_id=s.id AND c.execution_generation=?"
            ") AS capture_sent FROM steps s WHERE s.case_id=? ORDER BY s.position",
            (case["execution_generation"], case_id),
        )]
        selected = next((item for item in steps if item["id"] == step_id), None)
        if selected is None:
            raise CaptureError("INVALID_TARGET", "O passo não pertence a este caso.", 404)
        result = connection.execute(
            "SELECT revision,actual,status FROM results WHERE step_id=?", (step_id,)
        ).fetchone()
        if result is None:
            raise CaptureError("INVALID_TARGET", "Passo não encontrado.", 404)
    return {
        "case_id": case["id"],
        "case_name": case["name"],
        "execution_generation": case["execution_generation"],
        "step_id": selected["id"],
        "step_position": selected["position"],
        "step_action": selected["action"],
        "result_revision": int(result["revision"]),
        "observed": result["actual"],
        "status": result["status"],
        "steps": [
            {"id": item["id"], "position": item["position"], "action": item["action"],
             "selected": item["id"] == step_id, "capture_sent": bool(item["capture_sent"])}
            for item in steps
        ],
    }


def save_observed_text(directory: Path, step_id: int, text: str, expected_revision: int,
                       execution_generation: str) -> dict:
    if type(step_id) is not int or type(expected_revision) is not int or expected_revision < 0:
        raise CaptureError("REVISION_CONFLICT", "Revisão do resultado inválida.", 422)
    if not isinstance(text, str):
        raise CaptureError("INVALID_TARGET", "Texto observado inválido.", 422)
    with db(directory) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                "SELECT s.case_id,c.execution_generation,r.revision,r.actual,r.actual_doc,r.status "
                "FROM steps s JOIN cases c ON c.id=s.case_id JOIN results r ON r.step_id=s.id "
                "WHERE s.id=?",
                (step_id,),
            ).fetchone()
            if row is None:
                raise CaptureError("INVALID_TARGET", "Passo não encontrado.", 404)
            if row["execution_generation"] != execution_generation:
                raise StaleExecution()
            if int(row["revision"]) != expected_revision:
                raise RevisionConflict(int(row["revision"]), row["actual"], row["actual_doc"])
            ids = {item[0] for item in connection.execute("SELECT id FROM evidence WHERE step_id=?", (step_id,))}
            blocks = replace_observed_text(_stored_blocks(row["actual"], row["actual_doc"]), text)
            document, plain = normalize_document(blocks, ids)
            cursor = connection.execute(
                "UPDATE results SET actual=?,actual_doc=?,revision=revision+1,updated_at=? "
                "WHERE step_id=? AND revision=?",
                (plain, document, now(), step_id, expected_revision),
            )
            if cursor.rowcount != 1:
                current = connection.execute(
                    "SELECT revision,actual,actual_doc FROM results WHERE step_id=?", (step_id,)
                ).fetchone()
                raise RevisionConflict(int(current["revision"]), current["actual"], current["actual_doc"])
            saved = connection.execute(
                "SELECT revision,actual,status FROM results WHERE step_id=?", (step_id,)
            ).fetchone()
            connection.commit()
            return {
                "revision": int(saved["revision"]),
                "actual": saved["actual"],
                "status": saved["status"],
                "case_id": row["case_id"],
                "execution_generation": row["execution_generation"],
            }
        except Exception:
            connection.rollback()
            raise


def inspect_image(content: bytes) -> tuple[str, str]:
    if len(content) > MAX_IMAGE_BYTES:
        raise CaptureError("IMAGE_TOO_LARGE", "Imagem maior que 10 MB.", 413)
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            kind = image.format
            width, height = image.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise CaptureError("INVALID_IMAGE", "Imagem inválida.", 415) from exc
    if kind not in _IMAGE_TYPES or width * height > MAX_PIXELS or width < 2 or height < 2:
        raise CaptureError("INVALID_IMAGE", "Use PNG, JPEG ou WebP com até 40 megapixels.", 415)
    mime, extension = _IMAGE_TYPES[kind]
    return mime, extension


def _evidence_payload(connection, evidence_id: str) -> dict | None:
    row = connection.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone()
    if row is None:
        return None
    return dict(row)


def commit_capture(directory: Path, *, command_id: str, step_id: int, case_id: int,
                   execution_generation: str, expected_revision: int, render_revision: str,
                   content: bytes) -> dict:
    if type(step_id) is not int or type(case_id) is not int:
        raise CaptureError("INVALID_TARGET", "Destino inválido.", 422)
    if not _COMMAND_ID.fullmatch(command_id or ""):
        raise CaptureError("IDEMPOTENCY_CONFLICT", "Comando de anexação inválido.", 422)
    if not isinstance(render_revision, str) or not render_revision or len(render_revision) > 40:
        raise CaptureError("INVALID_IMAGE", "Revisão da imagem inválida.", 422)
    if type(expected_revision) is not int or expected_revision < 0:
        raise CaptureError("REVISION_CONFLICT", "Revisão do resultado inválida.", 422)
    mime, extension = inspect_image(content)
    digest = hashlib.sha256(content).hexdigest()
    target: Path | None = None
    temporary: Path | None = None
    committed = False
    with db(directory) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            row = connection.execute(
                "SELECT s.position,s.action,s.case_id,c.execution_generation,c.name,"
                "r.revision,r.actual,r.actual_doc,r.status "
                "FROM steps s JOIN cases c ON c.id=s.case_id JOIN results r ON r.step_id=s.id WHERE s.id=?",
                (step_id,),
            ).fetchone()
            if row is None or row["case_id"] != case_id:
                raise CaptureError("INVALID_TARGET", "O destino não pertence a esta sessão.", 404)
            existing = connection.execute(
                "SELECT * FROM capture_commands WHERE command_id=?", (command_id,)
            ).fetchone()
            if existing is not None:
                same = (
                    existing["step_id"] == step_id
                    and existing["execution_generation"] == execution_generation
                    and existing["render_revision"] == render_revision
                    and existing["content_hash"] == digest
                )
                if not same:
                    raise CaptureError(
                        "IDEMPOTENCY_CONFLICT",
                        "Este comando já foi usado com outro conteúdo. Anexe de novo se quiser outra evidência.",
                        409,
                    )
                evidence = _evidence_payload(connection, existing["evidence_id"])
                if evidence is None:
                    raise CaptureError(
                        "IDEMPOTENCY_CONFLICT",
                        "Este comando já foi processado e a evidência não está mais no passo.",
                        409,
                    )
                saved = connection.execute(
                    "SELECT revision,status FROM results WHERE step_id=?", (step_id,)
                ).fetchone()
                connection.commit()
                committed = True
                return {
                    "duplicate": True,
                    "evidence_id": evidence["id"],
                    "mime": evidence["mime"],
                    "name": evidence["original_name"],
                    "revision": int(saved["revision"]),
                    "status": saved["status"],
                    "step_id": step_id,
                    "case_id": case_id,
                    "execution_generation": row["execution_generation"],
                    "step_position": row["position"],
                    "step_action": row["action"],
                }
            if row["execution_generation"] != execution_generation:
                raise StaleExecution()
            if int(row["revision"]) != expected_revision:
                raise RevisionConflict(int(row["revision"]), row["actual"], row["actual_doc"])
            count = connection.execute(
                "SELECT COUNT(*) FROM evidence WHERE step_id=?", (step_id,)
            ).fetchone()[0]
            if count >= MAX_IMAGES:
                raise CaptureError("IMAGE_LIMIT", "Limite de 12 imagens por passo.", 413)
            image_id = uuid.uuid4().hex
            relative = Path("evidencias") / f"caso-{case_id}" / f"passo-{row['position']}" / f"{image_id}{extension}"
            target = directory / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(content)
            os.replace(temporary, target)
            temporary = None
            connection.execute(
                "INSERT INTO evidence(id,step_id,relative_path,original_name,mime,size,sha256,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (image_id, step_id, relative.as_posix(), "captura.png", mime, len(content), digest, now()),
            )
            ids = {item[0] for item in connection.execute("SELECT id FROM evidence WHERE step_id=?", (step_id,))}
            blocks = _stored_blocks(row["actual"], row["actual_doc"])
            blocks.append({"type": "image", "id": image_id, "width": 100})
            document, plain = normalize_document(blocks, ids)
            updated = connection.execute(
                "UPDATE results SET actual=?,actual_doc=?,revision=revision+1,updated_at=? "
                "WHERE step_id=? AND revision=?",
                (plain, document, now(), step_id, expected_revision),
            )
            if updated.rowcount != 1:
                raise CaptureError("REVISION_CONFLICT", "O resultado mudou durante a anexação.", 409)
            connection.execute(
                "INSERT INTO capture_commands(command_id,step_id,execution_generation,render_revision,"
                "content_hash,evidence_id,created_at) VALUES (?,?,?,?,?,?,?)",
                (command_id, step_id, execution_generation, render_revision, digest, image_id, now()),
            )
            saved = connection.execute(
                "SELECT revision,status FROM results WHERE step_id=?", (step_id,)
            ).fetchone()
            connection.commit()
            committed = True
            return {
                "duplicate": False,
                "evidence_id": image_id,
                "mime": mime,
                "name": "captura.png",
                "revision": int(saved["revision"]),
                "status": saved["status"],
                "step_id": step_id,
                "case_id": case_id,
                "execution_generation": execution_generation,
                "step_position": row["position"],
                "step_action": row["action"],
            }
        except Exception:
            if not committed:
                connection.rollback()
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
                if target is not None:
                    target.unlink(missing_ok=True)
            raise


def cleanup_capture_temporaries(directory: Path) -> None:
    root = directory / "evidencias"
    if not root.is_dir():
        return
    for path in root.rglob("*.tmp"):
        path.unlink(missing_ok=True)


def attached_blocks(directory: Path, step_id: int) -> list[dict]:
    """Read path used by history and reports. Missing document references are recovered."""
    from .storage import read_session

    record = read_session(directory)
    for case in record["cases"]:
        for step in case["steps"]:
            if step["id"] == step_id:
                return display_blocks(step["actual_doc"], step["actual"], step["evidence"])
    return []
