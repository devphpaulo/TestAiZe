"""The browser's PDF is accepted only after it contains at least one readable page."""

import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from testplayer.pdf_export import _wait_for_valid_pdf


class PdfValidationTests(unittest.TestCase):
    def test_missing_truncated_and_empty_files_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.pdf"
            self.assertFalse(_wait_for_valid_pdf(path, 0))
            path.write_bytes(b"%PDF-1.7\n" + b" " * 1500)
            self.assertFalse(_wait_for_valid_pdf(path, 0))
            path.write_bytes(b"")
            self.assertFalse(_wait_for_valid_pdf(path, 0))

    def test_complete_page_is_accepted_and_zero_pages_are_rejected(self):
        from pypdf import PdfWriter
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.pdf"
            for with_page in (False, True):
                writer = PdfWriter()
                if with_page:
                    writer.add_blank_page(width=300, height=400)
                writer.add_metadata({"/Subject": "Validação " * 200})
                content = io.BytesIO()
                writer.write(content)
                path.write_bytes(content.getvalue())
                self.assertEqual(_wait_for_valid_pdf(path, 0), with_page)
