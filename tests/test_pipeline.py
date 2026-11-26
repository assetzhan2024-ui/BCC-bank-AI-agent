import unittest

from requirements_validator.models import DocumentContent
from requirements_validator.pipeline import AuditPipeline


class FakeClient:
    def __init__(self):
        self.calls = 0

    def generate_json(self, _system, _user):
        self.calls += 1
        if self.calls == 1:
            return {"requirements": [{"document_id": "Ф-1", "section": "Функциональные", "quote": "Система должна отправить уведомление за одну минуту.", "summary": "Отправка уведомления"}]}
        if self.calls == 2:
            return {"reviews": [{"requirement_id": "REQ-001", "issues": []}]}
        return {"issues": []}


class PipelineTests(unittest.TestCase):
    def test_pipeline_assigns_internal_id(self):
        document = DocumentContent("test.md", "/test.md", "Система должна отправить уведомление за одну минуту.")
        result = AuditPipeline(FakeClient()).run(document, lambda _message: None)
        self.assertEqual("REQ-001", result.requirements[0].report_id)
        self.assertEqual("OK", result.requirement_reviews[0].status)


if __name__ == "__main__":
    unittest.main()
