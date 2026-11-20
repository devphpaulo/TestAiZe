"""Check release startup and the capture host without installing a browser runtime."""

from contextlib import contextmanager
import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


@contextmanager
def smoke_data_directory():
    temporary = tempfile.TemporaryDirectory(prefix="testaize-smoke-")
    try:
        yield Path(temporary.name)
    finally:
        # The onefile child can still be releasing its log handle after taskkill.
        deadline = time.monotonic() + 10
        while True:
            try:
                temporary.cleanup()
                break
            except PermissionError as exc:
                if getattr(exc, "winerror", None) not in (32, 33) or time.monotonic() >= deadline:
                    raise
                time.sleep(.2)


def check(executable: Path) -> None:
    with smoke_data_directory() as root:
        process = subprocess.Popen(
            [str(executable.resolve()), "--data-dir", str(root), "--no-browser", "--no-tray"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 45
            last_error = "Inicialização não concluída."
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"O executável encerrou com código {process.returncode}.")
                try:
                    runtime = json.loads((root / "config/runtime.json").read_text(encoding="utf-8"))
                    origin = f"http://127.0.0.1:{int(runtime['port'])}"
                    with urllib.request.urlopen(origin + "/health", timeout=2) as response:
                        assert response.status == 200
                    with urllib.request.urlopen(origin, timeout=2) as response:
                        assert response.status == 200
                    with urllib.request.urlopen(origin + '/bugs', timeout=2) as response:
                        assert 'Bugs por estado' in response.read().decode('utf-8')
                    for asset in (
                        'bugs.js', 'bugs.css', 'document-editor.js', 'image-editor.js', 'image-editor.css',
                        'header.js', 'header.css', 'theme.js', 'theme.css', 'alerts.js', 'frontend/progress.js', 'frontend/progress.css',
                    ):
                        with urllib.request.urlopen(origin + '/static/' + asset, timeout=2) as response:
                            assert response.status == 200 and response.read()
                    assert (root / 'bugs' / 'bugs.sqlite').is_file()
                    capture_log = (root / "logs/captura.log").read_text(encoding="utf-8")
                    if "host de captura pronto" in capture_log:
                        print("Executável: servidor local e host Qt de captura iniciados.")
                        return
                except (OSError, ValueError, KeyError, urllib.error.URLError) as exc:
                    last_error = str(exc)
                time.sleep(.2)
            raise RuntimeError(f"Falha no smoke: {last_error}")
        finally:
            # End only this release instance and its children, including the onefile bootloader.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            process.wait(timeout=10)


if __name__ == "__main__":
    check(Path(sys.argv[1]))
