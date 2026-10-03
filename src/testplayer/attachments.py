from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path, PureWindowsPath


MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_STEP_ATTACHMENTS = 5


def safe_attachment_name(value: str) -> str:
    """Keep a download-safe basename, including its original extension."""
    name = PureWindowsPath((value or "").replace("/", "\\")).name
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"/\\|?*\x7f')
    name = name.strip(" .")[:180].rstrip(" .")
    if not name or name.split(".", 1)[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        raise ValueError("Nome de arquivo inválido.")
    return name


def attachment_extension(name: str) -> str:
    return Path(name).suffix.lower()


def attachment_content_type(name: str, declared: str | None = None) -> str:
    # Metadata only. Downloads and HTML blobs are always application/octet-stream.
    if declared and len(declared) <= 120 and all(ch.isalnum() or ch in "/.+-" for ch in declared):
        return declared.lower()
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def verified_attachment_bytes(directory: Path, item: dict) -> bytes:
    base = directory.resolve()
    path = (base / item["relative_path"]).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError(f"Arquivo anexado indisponível: {item['original_name']}")
    content = path.read_bytes()
    recorded_size = item.get("size")
    if recorded_size is not None and int(recorded_size) != len(content):
        raise ValueError(f"Tamanho do anexo diverge do registro: {item['original_name']}")
    checksum = item.get("sha256")
    if checksum and hashlib.sha256(content).hexdigest() != checksum:
        raise ValueError(f"Integridade do anexo comprometida: {item['original_name']}")
    return content
