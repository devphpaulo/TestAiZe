from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
from waitress.server import create_server

from testplayer.backup import make_backup
from testplayer.storage import ensure_root
from testplayer.version import APP_VERSION
from testplayer.web import create_app


_base_log_record_factory = logging.getLogRecordFactory()


def _versioned_log_record(*args, **kwargs) -> logging.LogRecord:
    record = _base_log_record_factory(*args, **kwargs)
    record.app_version = APP_VERSION
    return record


logging.setLogRecordFactory(_versioned_log_record)


def documents_dir() -> Path:
    configured = Path.home() / "Documents"
    if os.name == "nt":
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buffer) == 0 and buffer.value:
            configured = Path(buffer.value)
    for candidate in (Path.home() / "OneDrive" / "Documentos",
                      Path.home() / "OneDrive" / "Documents"):
        if candidate.is_dir():
            return candidate
    return configured


def default_data_dir() -> Path:
    return documents_dir() / "TestAiZe"


def _message(message: str, title: str = "TestAíZé", error: bool = False) -> None:
    if sys.stdout:
        print(message)
    elif os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10 if error else 0x40)


def _notice(message: str) -> None:
    logging.info(message)
    if sys.stdout:
        print(message)


def _lock(root: Path):
    import msvcrt
    path = root / "config" / "instancia.lock"
    handle = path.open("a+b")
    handle.seek(0)
    if handle.read(1) == b"":
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    return handle


def _open_browser(port: int):
    url = f"http://127.0.0.1:{port}/"
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1).close()
            webbrowser.open(url)
            return
        except Exception:
            time.sleep(0.1)
    logging.warning("Navegador não abriu automaticamente; endereço: %s", url)


def _tray_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, 63, 63), radius=14, fill="#ffffff")
    draw.polygon([(11, 9), (8, 11), (8, 19), (12, 29), (4, 37), (17, 34), (25, 29),
                  (32, 28), (39, 29), (47, 34), (60, 37), (52, 29), (56, 19),
                  (55, 11), (51, 9), (45, 10), (40, 16), (32, 15), (24, 16), (19, 10)], fill="#111111")
    draw.polygon([(3, 40), (12, 34), (22, 30), (28, 31), (32, 35), (36, 31),
                  (42, 30), (52, 34), (61, 40), (52, 48), (39, 54), (36, 46),
                  (32, 43), (28, 46), (25, 54), (12, 48)], fill="#111111")
    draw.ellipse((14, 33, 29, 43), fill="#ffffff")
    draw.ellipse((35, 33, 50, 43), fill="#ffffff")
    draw.ellipse((19, 35, 25, 41), fill="#111111")
    draw.ellipse((39, 35, 45, 41), fill="#111111")
    draw.polygon([(27, 48), (32, 43), (37, 48), (32, 54)], fill="#111111")
    return image


def _notify(text: str) -> None:
    if os.name != "nt":
        logging.info(text)
        return
    ctypes.windll.user32.MessageBoxW(None, text, "TestAíZé", 0x40)


def _run_tray(root: Path, port: int, broker) -> None:
    url = f"http://127.0.0.1:{port}/"

    def open_app(icon, item):
        webbrowser.open(url)

    def open_data(icon, item):
        os.startfile(root)

    def define_hotkey(icon, item):
        if not broker.host_seen:
            _notify("A captura ainda está iniciando. Tente de novo em alguns segundos.")
            return
        broker.request_hotkey_record()

    def hotkey_text(item):
        return f"Atalho da captura    {broker.hotkey_label or 'PrintScreen'}"

    def quit_app(icon, item):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Abrir aplicativo", open_app, default=True),
        pystray.MenuItem(hotkey_text, define_hotkey),
        pystray.MenuItem("Abrir pasta de dados", open_data),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Encerrar aplicativo", quit_app),
    )
    pystray.Icon("testaize", _tray_image(), "TestAíZé", menu).run()


def _capture_job():
    """Kill the capture host if this process is terminated without running shutdown."""
    if os.name != "nt":
        return None
    kernel = ctypes.windll.kernel32
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        return None

    class BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class ExtendedLimit(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimit),
            ("IoInfo", ctypes.c_uint64 * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    info = ExtendedLimit()
    info.BasicLimitInformation.LimitFlags = 0x2000
    if not kernel.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        kernel.CloseHandle(job)
        return None
    return job


def _assign_capture_job(job, process: subprocess.Popen) -> None:
    if job is None:
        return
    try:
        ctypes.windll.kernel32.AssignProcessToJobObject(job, int(process._handle))
    except (OSError, AttributeError, ValueError):
        logging.info("captura seguira sem vinculo de encerramento automatico")


def _start_capture_host(port: int, token: str, root: Path) -> subprocess.Popen | None:
    env = os.environ.copy()
    env["TESTAIZE_CAPTURE_URL"] = f"http://127.0.0.1:{port}"
    env["TESTAIZE_CAPTURE_TOKEN"] = token
    env["TESTAIZE_DATA_DIR"] = str(root)
    src = str(Path(__file__).resolve().parent)
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    command = [sys.executable, "--capture-host"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "capture_client"]
    try:
        return subprocess.Popen(command, env=env, cwd=src)
    except OSError:
        logging.exception("Nao foi possivel iniciar o host de captura")
        return None


def _stop_capture_host(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
    logging.info("host de captura encerrado")


def main():
    if "--capture-host" in sys.argv:
        from capture_client.qt_host import main as capture_main
        raise SystemExit(capture_main())
    parser = argparse.ArgumentParser(description="TestAíZé: executor local de casos de teste")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--no-browser", action="store_true", help="Não abrir o navegador automaticamente")
    parser.add_argument("--no-tray", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--backup", action="store_true", help="Criar backup com o aplicativo fechado")
    args = parser.parse_args()
    root = (args.data_dir or default_data_dir()).resolve()
    ensure_root(root)
    handlers = [RotatingFileHandler(root / "logs" / "aplicativo.log", maxBytes=1_000_000,
                                    backupCount=3, encoding="utf-8")]
    if sys.stdout:
        handlers.append(logging.StreamHandler(sys.stdout))
    formatter = logging.Formatter(
        "%(asctime)s | TestAíZé v%(app_version)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    for handler in handlers:
        handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True)
    lock = _lock(root)
    runtime_file = root / "config" / "runtime.json"
    if lock is None:
        if args.backup:
            _message("Feche o aplicativo antes de criar o backup.", error=True)
            return
        try:
            runtime = json.loads(runtime_file.read_text(encoding="utf-8"))
            _open_browser(int(runtime["port"]))
            _notice("O aplicativo já está em execução.")
        except Exception:
            _message("O aplicativo já está em execução, mas não foi possível abrir o navegador.", error=True)
        return
    if args.backup:
        try:
            output = make_backup(root)
            _message(f"Backup criado e validado em:\n{output}")
        finally:
            lock.close()
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server = None
    app = None
    capture_process = None
    capture_job = None
    try:
        app = create_app(root)
        runtime = app.extensions["automation_runtime"]
        if not runtime.available:
            _notice(runtime.message)
        sock.bind(("127.0.0.1", 0))
        sock.listen(128)
        port = sock.getsockname()[1]
        runtime_file.write_text(json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8")
        _notice(f"TestAíZé v{APP_VERSION} iniciado: http://127.0.0.1:{port}/")
        server = create_server(app, sockets=[sock], threads=4, expose_tracebacks=False)
        capture_job = _capture_job()
        capture_process = _start_capture_host(port, app.extensions["capture_broker"].token, root)
        _assign_capture_job(capture_job, capture_process) if capture_process is not None else None
        if capture_process is not None:
            _notice("Host de captura iniciado.")
        if not args.no_browser:
            threading.Thread(target=_open_browser, args=(port,), daemon=True).start()
        if args.no_tray:
            server.run()
        else:
            threading.Thread(target=server.run, daemon=True).start()
            _run_tray(root, port, app.extensions["capture_broker"])
    except KeyboardInterrupt:
        _notice("Aplicativo encerrado.")
    finally:
        _stop_capture_host(capture_process)
        if capture_job is not None:
            ctypes.windll.kernel32.CloseHandle(capture_job)
        if app is not None:
            app.extensions['automation_suite'].shutdown()
            app.extensions["automation_recorder"].shutdown()
            app.extensions["automation_vault"].clear()
        runtime_file.unlink(missing_ok=True)
        if server is not None:
            server.close()
            server.task_dispatcher.shutdown()
        sock.close()
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logging.exception("Falha ao iniciar o aplicativo")
        if getattr(sys, "frozen", False):
            _message(f"Não foi possível iniciar o aplicativo.\n\n{exc}", error=True)
        else:
            raise
