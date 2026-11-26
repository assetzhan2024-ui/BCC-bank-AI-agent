import tempfile
import unittest
from pathlib import Path

from requirements_validator.document_reader import read_document
from requirements_validator.errors import DocumentError


class DocumentReaderTests(unittest.TestCase):
    def test_reads_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requirements.md"
            path.write_text("# Требования\nСистема должна работать.", encoding="utf-8")
            document = read_document(path)
            self.assertIn("Система должна работать", document.text)

    def test_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.md"
            path.write_text("", encoding="utf-8")
            with self.assertRaises(DocumentError):
                read_document(path)

    def test_rejects_unsupported_format(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requirements.csv"
            path.write_text("a,b", encoding="utf-8")
            with self.assertRaises(DocumentError):
                read_document(path)


if __name__ == "__main__":
    unittest.main()
