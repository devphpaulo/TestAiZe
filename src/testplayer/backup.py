from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path


def make_backup(root: Path) -> Path:
    """Create a portable archive while the application holds its exclusive lock."""
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    destination = root / "backups" / f"backup-{timestamp}.zip"
    if destination.exists():
        raise FileExistsError("Já existe um backup com este horário. Tente novamente.")
    sources = []
    for folder in (root / "rascunhos", root / "sessoes", root / "excluidas"):
        if folder.exists():
            sources.extend(path for path in folder.rglob("*") if path.is_file())
    prompt = root / "prompt-report-bug.txt"
    if prompt.is_file():
        sources.append(prompt)
    checksums = {}
    with tempfile.TemporaryDirectory(dir=root / "temporarios") as scratch, zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as archive:
        scratch_dir = Path(scratch)
        for source in sources:
            relative = source.relative_to(root).as_posix()
            if source.name == "sessao.sqlite":
                snapshot = scratch_dir / f"{len(checksums)}.sqlite"
                original_db = sqlite3.connect(source)
                backup_db = sqlite3.connect(snapshot)
                try:
                    original_db.backup(backup_db)
                finally:
                    backup_db.close()
                    original_db.close()
                content = snapshot.read_bytes()
            else:
                content = source.read_bytes()
            checksums[relative] = hashlib.sha256(content).hexdigest()
            archive.writestr(relative, content)
        archive.writestr("integridade.json", json.dumps({"created_at": timestamp, "sha256": checksums}, indent=2))
    with zipfile.ZipFile(destination) as archive:
        damaged = archive.testzip()
        if damaged:
            destination.unlink(missing_ok=True)
            raise IOError(f"Falha ao validar o backup: {damaged}")
    return destination
