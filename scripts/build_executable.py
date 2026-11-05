"""Build the Windows executable from explicit runtime resources."""

from pathlib import Path
import argparse
import os
import sys

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from testplayer.version import PACKAGE_VERSION


def main(output_dir: Path | None = None) -> None:
    # Qt uses the Windows ICU ABI. Developer tools (e.g. Poppler) can put an
    # incompatible icuuc.dll on PATH; prefer the OS libraries during analysis.
    if os.name == 'nt':
        system_libraries = Path(os.environ['SystemRoot']) / 'System32'
        os.environ['PATH'] = str(system_libraries) + os.pathsep + os.environ.get('PATH', '')
    destination = (output_dir or ROOT / "dist").resolve()
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
        "--distpath", str(destination),
        "--workpath", str(ROOT / "build/executable"),
        "--specpath", str(ROOT / "build"),
        "--hidden-import", "pystray._win32",
        "--hidden-import", "capture_client.qt_host",
        "--hidden-import", "capture_client.__main__",
    ]
    for source, resource_destination in resources:
        arguments.extend(["--add-data", f"{source};{resource_destination}"])
    PyInstaller.__main__.run([*arguments, str(ROOT / "src/launcher.py")])
    executable = destination / f"TestAiZe-{PACKAGE_VERSION}.exe"
    print(f"{executable.name}: {executable.stat().st_size / 1_000_000:.2f} MB")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gerar o executável Windows do TestAíZé")
    parser.add_argument('--dist-dir', type=Path, default=None,
                        help="Pasta de saída alternativa quando outro executável está em uso")
    main(parser.parse_args().dist_dir)
