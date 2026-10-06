"""Ownership of the ephemeral local recorder process; no browser or storage logic."""
from __future__ import annotations

import atexit
import os
import queue
import json
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import urlopen
from .automation_environment import AutomationRuntime, detect_automation_runtime, recorder_root


class RecorderError(RuntimeError):
    """An actionable message safe to show in the host UI."""


class RecorderManager:
    def __init__(self, root: Path | None = None, *, runtime: AutomationRuntime | None = None, start_timeout=15, idle_timeout=180):
        self.root = (root or recorder_root()).resolve()
        self.runtime = runtime if runtime is not None else detect_automation_runtime()
        self.start_timeout = start_timeout
        self.idle_timeout = idle_timeout
        self._lock = threading.RLock()
        self._process = None
        self._url = None
        self._owner = None
        self._parent_origin = None
        self._last_seen = 0
        self._watchdog_stop = threading.Event()
        self._watchdog = None
        self._vault_values = {}

    def _runtime(self):
        if not self.runtime.available:
            raise RecorderError(self.runtime.message or "Node.js ou Playwright Codegen indisponível.")
        node = self.runtime.node
        entry = self.root / "server.js"
        if not entry.is_file():
            raise RecorderError("Código do recorder indisponível nesta instalação.")
        return [str(Path(node).resolve()), str(entry)]

    def start(self, parent_origin: str, owner: str = "") -> dict:
        origin = urlsplit(parent_origin)
        if origin.scheme != "http" or origin.hostname not in ("127.0.0.1", "localhost") or origin.path or origin.query or origin.fragment or origin.username:
            raise RecorderError("Origem local inválida.")
        with self._lock:
            if self._process and self._process.poll() is None and self._owner == owner and self._parent_origin == parent_origin:
                self._last_seen = time.monotonic()
                return self._snapshot()
            self._stop()
            command = self._runtime()
            env = {**os.environ, "RECORDER_PORT": "0", "RECORDER_PARENT_ORIGIN": parent_origin,
                   "RECORDER_MANAGED": "1", "RECORDER_PARENT_PID": str(os.getpid()),
                   "RECORDER_PLAYWRIGHT_MODULE": self.runtime.playwright_entry}
            try:
                self._process = subprocess.Popen(command, cwd=self.root, env=env, stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
                self._url = self._read_ready(self._process)
                if not self._healthy():
                    raise RecorderError("Recorder iniciou sem responder ao health check. Tente novamente.")
            except (OSError, RecorderError) as error:
                self._stop()
                if isinstance(error, RecorderError):
                    raise
                raise RecorderError("Não foi possível iniciar o recorder local. Confira o runtime Node.js.") from None
            self._owner = owner
            self._parent_origin = parent_origin
            self._last_seen = time.monotonic()
            self._sync_vault()
            self._start_watchdog()
            return self._snapshot()

    def _read_ready(self, process) -> str:
        messages = queue.Queue()

        def drain():
            for line in process.stdout:
                if line.startswith("PLAYWRIGHT_RECORDER_READY "):
                    messages.put(line.strip().split(" ", 1)[1])
            messages.put(None)

        threading.Thread(target=drain, daemon=True).start()
        try:
            value = messages.get(timeout=self.start_timeout)
        except queue.Empty:
            raise RecorderError("O recorder demorou demais para iniciar. Tente novamente.") from None
        try:
            parsed = urlsplit(value or "")
            valid = (parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and
                     parsed.port is not None and 0 < parsed.port <= 65535 and
                     value == f"http://127.0.0.1:{parsed.port}" and process.poll() is None)
        except ValueError:
            valid = False
        if not valid:
            raise RecorderError("O recorder não publicou um endereço local válido.")
        return value + "/?embedded=1"

    def _healthy(self):
        try:
            with urlopen(self._url.split("?", 1)[0] + "health", timeout=2) as response:
                return response.status == 200
        except OSError:
            return False

    def _snapshot(self):
        return {"state": "ready", "url": self._url} if self._process else {"state": "idle"}

    def status(self, owner: str = "") -> dict:
        with self._lock:
            if self._process and self._process.poll() is not None:
                self._stop()
            if owner and owner == self._owner:
                self._last_seen = time.monotonic()
            result = self._snapshot()
            if owner and self._owner and owner != self._owner:
                return {"state": "replaced"}
            return result

    def stop(self, owner: str | None = None) -> dict:
        with self._lock:
            # An unloading previous page must not terminate the replacement page.
            if owner is None or owner == self._owner:
                self._stop()
            return self._snapshot()

    def _stop(self):
        process = self._process
        if process is None:
            return
        try:
            if process.poll() is None:
                try:
                    process.stdin.write("shutdown\n")
                    process.stdin.flush()
                    process.wait(timeout=5)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        process.kill()
                    process.wait(timeout=5)
        finally:
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
            self._process = self._url = self._owner = self._parent_origin = None

    def reap_idle(self):
        with self._lock:
            if self._process and time.monotonic() - self._last_seen > self.idle_timeout:
                self._stop()

    def _start_watchdog(self):
        if self._watchdog and self._watchdog.is_alive():
            return
        self._watchdog_stop.clear()
        def watch():
            while not self._watchdog_stop.wait(10):
                self.reap_idle()
        self._watchdog = threading.Thread(target=watch, daemon=True)
        self._watchdog.start()
        atexit.register(self.shutdown)

    def shutdown(self):
        self._watchdog_stop.set()
        self.stop()
        self._vault_values.clear()

    def update_vault(self, values: dict):
        with self._lock:
            self._vault_values = dict(values)
            self._sync_vault()

    def _sync_vault(self):
        if self._process and self._process.poll() is None:
            self._process.stdin.write(json.dumps({'type': 'vault.update', 'values': self._vault_values}) + '\n')
            self._process.stdin.flush()
