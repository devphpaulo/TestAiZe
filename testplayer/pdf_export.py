from __future__ import annotations

import os
import logging
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

import pymupdf

from .html_export import render_report_html
from .storage import read_session


logger = logging.getLogger(__name__)


def _browser_path() -> Path:
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError("Microsoft Edge ou Google Chrome não foi encontrado para gerar o PDF.")


def _render_html_with_browser(html: str, target: Path) -> None:
    browser = _browser_path()
    _clean_stale_browser_dirs()
    temp_dir = Path(tempfile.mkdtemp(prefix="testaize-pdf-"))
    try:
        source = temp_dir / "relatorio.html"
        source.write_text(html, encoding="utf-8")
        failures = []
        for attempt, headless in enumerate(("--headless=new", "--headless"), start=1):
            profile = temp_dir / f"browser-profile-{attempt}"
            rendered = temp_dir / f"relatorio-{attempt}.pdf"
            command = [
                str(browser), headless, "--no-sandbox", "--disable-gpu", "--disable-gpu-sandbox",
                "--disable-dev-shm-usage", "--disable-features=SkiaGraphite,Vulkan", "--no-first-run",
                "--no-default-browser-check", "--disable-extensions", "--allow-file-access-from-files",
                "--disable-breakpad", "--disable-crash-reporter", "--disable-crashpad-for-testing",
                "--disable-sync", "--disable-background-networking", "--metrics-recording-only",
                "--password-store=basic", "--run-all-compositor-stages-before-draw",
                "--virtual-time-budget=10000", "--no-pdf-header-footer", "--print-to-pdf-no-header",
                f"--user-data-dir={profile}", f"--print-to-pdf={rendered}", source.as_uri(),
            ]
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            try:
                result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        timeout=90, creationflags=flags, check=False)
                returncode = result.returncode
                output = (result.stdout + b"\n" + result.stderr).decode("utf-8", errors="replace")[-700:]
            except subprocess.TimeoutExpired as exc:
                returncode = "timeout"
                output = str(exc)
            if _wait_for_valid_pdf(rendered, seconds=12):
                shutil.copyfile(rendered, target)
                if returncode != 0:
                    logger.warning("PDF gerado apesar do código de saída %s do navegador.", returncode)
                return
            size = rendered.stat().st_size if rendered.exists() else 0
            failure = f"tentativa {attempt}: saída={returncode}, PDF={size} bytes, detalhes={output!r}"
            failures.append(failure)
            logger.warning("Falha na conversão HTML→PDF: %s", failure)
        raise RuntimeError("Falha ao converter o relatório HTML em PDF. " + " | ".join(failures))
    finally:
        _remove_tree_when_released(temp_dir)


def _wait_for_valid_pdf(path: Path, seconds: int) -> bool:
    deadline = time.monotonic() + seconds
    while True:
        try:
            if path.stat().st_size > 1000:
                with pymupdf.open(path) as document:
                    if document.page_count > 0:
                        return True
        except (FileNotFoundError, OSError, ValueError, pymupdf.FileDataError):
            pass
        if time.monotonic() >= deadline:
            return False
        time.sleep(.25)


def _clean_stale_browser_dirs() -> None:
    cutoff = time.time() - 600
    for candidate in Path(tempfile.gettempdir()).glob("testaize-pdf-*"):
        try:
            if candidate.is_dir() and candidate.stat().st_mtime < cutoff:
                shutil.rmtree(candidate)
        except OSError:
            continue


def _remove_tree_when_released(path: Path) -> None:
    for delay in (0, .05, .1, .2, .4, .8):
        if delay:
            time.sleep(delay)
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            continue

    def finish_cleanup() -> None:
        for _ in range(30):
            time.sleep(1)
            try:
                shutil.rmtree(path)
                return
            except FileNotFoundError:
                return
            except OSError:
                continue

    threading.Thread(target=finish_cleanup, name="testaize-pdf-cleanup", daemon=True).start()


def _safe_unlink(path: Path) -> None:
    for delay in (0, .05, .1, .2, .4):
        if delay:
            time.sleep(delay)
        try:
            path.unlink(missing_ok=True)
            return
        except OSError:
            continue


def generate_pdf(directory: Path, selected_case_ids: set[int] | None = None,
                 include_history: bool = False, output_name: str = "relatorio.pdf",
                 report_kind: str = "execution") -> Path:
    session = read_session(directory)
    valid_ids = {case["id"] for case in session["cases"]}
    selected = valid_ids if selected_case_ids is None else set(selected_case_ids)
    if not selected or not selected.issubset(valid_ids):
        raise ValueError("Selecione ao menos um caso válido para o PDF.")
    if Path(output_name).name != output_name or not output_name.lower().endswith(".pdf"):
        raise ValueError("Nome do relatório inválido.")

    html = render_report_html(directory, selected, include_history, report_kind=report_kind,
                              print_all=True, pdf_mode=True)
    report = directory / "relatorios" / output_name
    report.parent.mkdir(parents=True, exist_ok=True)
    # Remove temporary files left by releases that used fixed intermediate names.
    _safe_unlink(report.with_suffix(".rendered.pdf.tmp"))
    token = uuid.uuid4().hex
    rendered = report.parent / f".{report.stem}-{token}.rendered.pdf.tmp"
    try:
        _render_html_with_browser(html, rendered)
        os.replace(rendered, report)
    finally:
        _safe_unlink(rendered)
    return report
