import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec('PyInstaller'), 'PyInstaller necessário para validar o build')
class ExecutableBuildTests(unittest.TestCase):
    def test_custom_output_is_preserved_while_collecting_bundle_resources(self):
        path = Path(__file__).resolve().parents[1] / 'scripts' / 'build_executable.py'
        spec = importlib.util.spec_from_file_location('testaize_build', path)
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'another-release'
            def package(arguments):
                self.assertEqual(Path(arguments[arguments.index('--distpath') + 1]), output.resolve())
                self.assertIn('testplayer/templates', ';'.join(arguments))
                output.mkdir()
                (output / f'TestAiZe-{build.PACKAGE_VERSION}.exe').write_bytes(b'package')
            with patch.object(build.PyInstaller.__main__, 'run', side_effect=package), patch.dict(build.os.environ), contextlib.redirect_stdout(io.StringIO()):
                build.main(output)
            self.assertTrue((output / f'TestAiZe-{build.PACKAGE_VERSION}.exe').is_file())
