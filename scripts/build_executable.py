"""Build the Windows executable from explicit runtime resources."""

from pathlib import Path
import os
import sys

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from testplayer.version import PACKAGE_VERSION


def main() -> None:
    # Qt uses the Windows ICU ABI. Developer tools (e.g. Poppler) can put an
    # incompatible icuuc.dll on PATH; prefer the OS libraries during analysis.
    if os.name == 'nt':
        system_libraries = Path(os.environ['SystemRoot']) / 'System32'
        os.environ['PATH'] = str(system_libraries) + os.pathsep + os.environ.get('PATH', '')
    recorder = ROOT / "src" / "playwright-recorder"
    resources = [
        (ROOT / "src/testplayer/templates", "testplayer/templates"),
        (ROOT / "src/testplayer/static", "testplayer/static"),
        (recorder / "public", "playwright-recorder/public"),
        (recorder / "vendor", "playwright-recorder/vendor"),
    ]
    resources.extend((path, "playwright-recorder") for path in sorted(recorder.iterdir())
                     if path.is_file() and (path.suffix in {".js", ".cjs"} or path.name == "package.json"))
    arguments = [
        "--noconfirm", "--clean", "--onefile", "--windowed",
        "--name", f"TestAiZe-{PACKAGE_VERSION}",
        "--icon", str(ROOT / "assets/testaize.ico"),
        "--paths", str(ROOT / "src"),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build/executable"),
        "--specpath", str(ROOT / "build"),
        "--hidden-import", "pystray._win32",
        "--hidden-import", "capture_client.qt_host",
        "--hidden-import", "capture_client.__main__",
    ]
    for source, destination in resources:
        arguments.extend(["--add-data", f"{source};{destination}"])
    PyInstaller.__main__.run([*arguments, str(ROOT / "src/launcher.py")])
    executable = ROOT / "dist" / f"TestAiZe-{PACKAGE_VERSION}.exe"
    print(f"{executable.name}: {executable.stat().st_size / 1_000_000:.2f} MB")


if __name__ == "__main__":
    main()
