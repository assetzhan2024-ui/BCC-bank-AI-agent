import tempfile
import unittest
from pathlib import Path

from docx import Document

from requirements_validator.document_reader import read_document


class DocxTableTests(unittest.TestCase):
    def test_reads_paragraphs_and_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requirements.docx"
            document = Document()
            document.add_paragraph("Функциональные требования")
            table = document.add_table(rows=2, cols=2)
            table.cell(0, 0).text = "Параметр"
            table.cell(0, 1).text = "Ограничение"
            table.cell(1, 0).text = "amount"
            table.cell(1, 1).text = "1000–1000000"
            document.save(path)

            content = read_document(path)
            self.assertIn("Функциональные требования", content.text)
            self.assertIn("| amount | 1000–1000000 |", content.text)


if __name__ == "__main__":
    unittest.main()
