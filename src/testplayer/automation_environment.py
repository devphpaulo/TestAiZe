"""Detect installed tools once per application startup; never install or bundle them."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AutomationRuntime:
    available: bool = False
    node: str = ""
    playwright_entry: str = ""
    version: str = ""
    message: str = ""


def recorder_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "playwright-recorder"
    return Path(__file__).resolve().parents[1] / "playwright-recorder"


def detect_automation_runtime() -> AutomationRuntime:
    node = shutil.which("node")
    if not node:
        return AutomationRuntime(message="Node.js não encontrado. O aplicativo iniciou com Automação oculta.")
    try:
        result = subprocess.run([node, str(recorder_root() / "environment.cjs")],
                                capture_output=True, text=True, encoding="utf-8", timeout=8,
                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        payload = json.loads(result.stdout) if result.returncode == 0 else {}
        if not isinstance(payload, dict):
            payload = {}
        if payload.get("available") is True and isinstance(payload.get("entry"), str):
            return AutomationRuntime(True, node, payload["entry"], payload.get("version", ""))
        return AutomationRuntime(message=payload.get("message") or "Não foi possível verificar o Playwright Codegen. Automação está oculta.")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return AutomationRuntime(message="Não foi possível verificar Node.js e Playwright Codegen. O restante do aplicativo está disponível.")
