import unittest
from pathlib import Path

from requirements_validator.document_reader import read_document
from requirements_validator.textmatch import SourceIndex

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


class PdfReaderTests(unittest.TestCase):
    def test_justified_cyrillic_pdf_keeps_words_and_pages(self):
        document = read_document(FIXTURE)
        self.assertEqual((), document.warnings)
        index = SourceIndex(document.text)
        quote = "На карту приходится максимум один такой push за календарный месяц."
        self.assertTrue(index.contains(quote))
        self.assertEqual("стр. 1", index.locate(quote))
        self.assertEqual("стр. 2", index.locate("Для чужой карты возвращается 404"))


if __name__ == "__main__":
    unittest.main()
