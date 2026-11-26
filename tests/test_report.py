import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from requirements_validator.models import AuditResult, Requirement, RequirementReview, SpecificationReview
from requirements_validator.report import build_report, write_report


class ReportTests(unittest.TestCase):
    def test_report_has_all_mandatory_sections(self):
        result = AuditResult(
            [Requirement("REQ-001", "Ф-1", "Функциональные", "Система должна работать.", "Работа системы", 1)],
            [RequirementReview("REQ-001", "OK", [])],
            SpecificationReview([]),
        )
        report = build_report(result, "requirements.md", "test-model", "abc123", datetime.now(timezone.utc))
        for heading in ("Паспорт прогона", "Таблица нарезки", "Проверка каждого", "Проверка всего", "Сводка", "Итоговый вердикт"):
            self.assertIn(heading, report)

    def test_write_report_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "output" / "report.md"
            write_report(target, "report")
            self.assertEqual("report", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
