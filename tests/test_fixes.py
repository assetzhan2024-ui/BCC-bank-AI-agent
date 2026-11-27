"""Regression tests for the issues found in the code review."""

import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from requirements_validator.errors import LLMError
from requirements_validator.llm_client import GeminiClient
from requirements_validator.models import (
    AuditResult,
    DocumentContent,
    Issue,
    Requirement,
    RequirementReview,
    SpecificationIssue,
    SpecificationReview,
)
from requirements_validator.pipeline import AuditPipeline
from requirements_validator.report import build_report
from requirements_validator.textmatch import SourceIndex
from requirements_validator.versioning import agent_version

DOC = (
    "## Функциональные требования\n"
    "* **Ф-1.** Порог от 1 000 до 1 000 000 ₸ включительно.\n"
    "* **Ф-3.** На карту приходится максимум один такой push за календарный месяц.\n"
    "### Критерии приемки\n"
    "заполняются тестировщиками\n"
    "Для чужой карты возвращается 404, как и для отсутствующей карты.\n"
)


class SourceIndexTests(unittest.TestCase):
    def test_ignores_markdown_and_finds_line(self):
        index = SourceIndex(DOC)
        self.assertTrue(index.contains("Ф-3. На карту приходится максимум один такой push"))
        self.assertEqual("строка 3", index.locate("максимум один такой push"))

    def test_pdf_page_markers_and_hyphenation(self):
        text = "\n[Страница 1]\nКлиент получает уведомле-\n\n[Страница 2]\nние о достижении порога."
        index = SourceIndex(text)
        self.assertTrue(index.contains("Клиент получает уведомление о достижении порога."))
        self.assertEqual("стр. 1", index.locate("Клиент получает"))
        self.assertEqual("стр. 2", index.locate("о достижении порога"))

    def test_rejects_invented_quote(self):
        self.assertFalse(SourceIndex(DOC).contains("Система обязана работать круглосуточно"))


class ScriptedClient:
    """Fake Gemini: returns scripted answers and records prompts."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.prompts = []

    def generate_json(self, system, user):
        self.prompts.append(user)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


EXTRACT = {
    "requirements": [
        {"document_id": "Ф-1", "section": "ФТ", "quote": "Порог от 1 000 до 1 000 000 ₸ включительно.", "summary": "Порог"},
        {"document_id": "Ф-3", "section": "ФТ", "quote": "На карту приходится максимум один такой push за календарный месяц.", "summary": "1 push"},
    ]
}


class PipelineFixTests(unittest.TestCase):
    def document(self):
        return DocumentContent("doc.md", "/doc.md", DOC)

    def test_skipped_review_is_retried_individually(self):
        client = ScriptedClient(
            [
                EXTRACT,
                {"reviews": [{"requirement_id": "REQ-001", "issues": []}]},  # REQ-002 skipped
                {"reviews": [{"requirement_id": "REQ-002", "issues": []}]},  # retry
                {"issues": []},
            ]
        )
        result = AuditPipeline(client).run(self.document(), lambda _m: None)
        self.assertEqual(["OK", "OK"], [r.status for r in result.requirement_reviews])

    def test_failed_batch_does_not_crash_run(self):
        client = ScriptedClient([EXTRACT, LLMError("boom"), LLMError("boom"), {"issues": []}])
        result = AuditPipeline(client).run(self.document(), lambda _m: None)
        self.assertEqual(["НЕ ПРОВЕРЕНО", "НЕ ПРОВЕРЕНО"], [r.status for r in result.requirement_reviews])

    def test_specification_review_receives_full_document(self):
        client = ScriptedClient(
            [
                EXTRACT,
                {"reviews": [{"requirement_id": "REQ-001", "issues": []}, {"requirement_id": "REQ-002", "issues": []}]},
                {
                    "issues": [
                        {
                            "category": "Полнота",
                            "severity": "Критичный",
                            "requirement_ids": [],
                            "evidence": ["заполняются тестировщиками"],
                            "explanation": "Критерии приёмки не заполнены",
                            "risk": "r",
                            "recommendation": "Заполнить",
                        }
                    ]
                },
            ]
        )
        result = AuditPipeline(client).run(self.document(), lambda _m: None)
        self.assertIn("Для чужой карты возвращается 404", client.prompts[-1])
        issue = result.specification_review.issues[0]
        self.assertEqual(["строка 5"], issue.locations)

    def test_inexact_evidence_is_flagged(self):
        client = ScriptedClient(
            [
                EXTRACT,
                {
                    "reviews": [
                        {"requirement_id": "REQ-001", "issues": [{"criterion": "Однозначность", "severity": "Высокий", "evidence": "выдумка", "explanation": "e", "risk": "r", "recommendation": "x"}]},
                        {"requirement_id": "REQ-002", "issues": []},
                    ]
                },
                {"issues": []},
            ]
        )
        result = AuditPipeline(client).run(self.document(), lambda _m: None)
        issue = result.requirement_reviews[0].issues[0]
        self.assertFalse(issue.evidence_exact)
        self.assertEqual("строка 2", issue.location)


def _result(reviews, spec_issues=(), completed=True):
    requirements = [
        Requirement("REQ-001", "Ф-1", "ФТ", "Порог от 1 000 до 1 000 000 ₸ включительно.", "Порог", 1, "строка 2"),
        Requirement("REQ-002", "", "ФТ", "На карту приходится максимум один такой push за календарный месяц.", "1 push", 1, "строка 3"),
    ]
    return AuditResult(requirements, reviews, SpecificationReview(list(spec_issues), completed))


class ReportFixTests(unittest.TestCase):
    def build(self, result):
        return build_report(result, "doc.md", "m", "commit abc", datetime.now(timezone.utc))

    def test_unchecked_requirement_is_not_reported_as_clean(self):
        report = self.build(
            _result([RequirementReview("REQ-001", "OK", []), RequirementReview("REQ-002", "НЕ ПРОВЕРЕНО", [])])
        )
        section = report.split("### REQ-002", 1)[1].split("##", 1)[0]
        self.assertIn("не выполнена", section)
        self.assertNotIn("не обнаружено", section)

    def test_unchecked_alone_gives_conditional_not_no_go(self):
        report = self.build(
            _result([RequirementReview("REQ-001", "OK", []), RequirementReview("REQ-002", "НЕ ПРОВЕРЕНО", [])])
        )
        self.assertIn("УСЛОВНО ГОТОВО", report)
        self.assertNotIn("NO-GO", report)

    def test_other_and_critical_spec_issues_have_quotes(self):
        issue = SpecificationIssue(
            "Иное", "Критичный", [], ["заполняются тестировщиками"], "Пусто", "r", "fix", ["строка 5"]
        )
        report = self.build(
            _result([RequirementReview("REQ-001", "OK", []), RequirementReview("REQ-002", "OK", [])], [issue])
        )
        other = report.split("### Другие системные дефекты", 1)[1].split("## 5.", 1)[0]
        self.assertIn("«заполняются тестировщиками»", other)
        critical = report.split("### Критичные дефекты", 1)[1].split("## 6.", 1)[0]
        self.assertIn("«заполняются тестировщиками» (строка 5)", critical)
        self.assertIn("NO-GO", report)

    def test_item_critical_line_has_requirement_and_place(self):
        bad = Issue("Проверяемость", "Критичный", "максимум один такой push", "e", "r", "fix", "строка 3")
        report = self.build(
            _result([RequirementReview("REQ-001", "OK", []), RequirementReview("REQ-002", "ДЕФЕКТ", [bad])])
        )
        critical = report.split("### Критичные дефекты", 1)[1].split("## 6.", 1)[0]
        self.assertIn("REQ-002", critical)
        self.assertIn("(строка 3)", critical)

    def test_failed_specification_review_is_visible(self):
        report = self.build(
            _result([RequirementReview("REQ-001", "OK", []), RequirementReview("REQ-002", "OK", [])], completed=False)
        )
        self.assertIn("Системная проверка не выполнена", report)
        self.assertNotIn("ГОТОВО (GO)", report)


class VersionTests(unittest.TestCase):
    def test_git_commit_wins_over_agent_version_env(self):
        with tempfile.TemporaryDirectory() as directory:
            run = lambda *a: subprocess.run(["git", *a], cwd=directory, check=True, capture_output=True)
            run("init", "-q")
            Path(directory, "f.txt").write_text("x")
            run("add", ".")
            run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init")
            with mock.patch.dict(os.environ, {"AGENT_VERSION": "1.0.0"}):
                version = agent_version(Path(directory))
            self.assertTrue(version.startswith("commit "), version)

    def test_outside_git_falls_back_to_version_file(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "VERSION").write_text("2.0.0")
            with mock.patch.dict(os.environ, {"AGENT_VERSION": ""}):
                self.assertIn("2.0.0", agent_version(Path(directory)))


class Gemini2026Tests(unittest.TestCase):
    """Free-tier limits, model changes and fail-fast behaviour."""

    def document(self):
        return DocumentContent("doc.md", "/doc.md", DOC)

    def test_missing_reviews_are_retried_in_one_request(self):
        three = {"requirements": EXTRACT["requirements"] + [
            {"document_id": "", "section": "S", "quote": "Для чужой карты возвращается 404, как и для отсутствующей карты.", "summary": "404"}]}
        client = ScriptedClient(
            [
                three,
                {"reviews": [{"requirement_id": "REQ-001", "issues": []}]},
                {"reviews": [{"requirement_id": "REQ-002", "issues": []}, {"requirement_id": "REQ-003", "issues": []}]},
                {"issues": []},
            ]
        )
        result = AuditPipeline(client).run(self.document(), lambda _m: None)
        self.assertEqual(4, len(client.prompts))
        self.assertEqual(["OK", "OK", "OK"], [r.status for r in result.requirement_reviews])

    def test_whole_run_uses_three_requests_by_default(self):
        client = ScriptedClient(
            [
                EXTRACT,
                {"reviews": [{"requirement_id": "REQ-001", "issues": []}, {"requirement_id": "REQ-002", "issues": []}]},
                {"issues": []},
            ]
        )
        AuditPipeline(client).run(self.document(), lambda _m: None)
        self.assertEqual(3, len(client.prompts))

    def test_fatal_error_stops_run_without_more_requests(self):
        from requirements_validator.errors import FatalLLMError

        client = ScriptedClient([EXTRACT, FatalLLMError("HTTP 404 model not found")])
        with self.assertRaises(FatalLLMError):
            AuditPipeline(client).run(self.document(), lambda _m: None)
        self.assertEqual(2, len(client.prompts))

    def test_empty_extraction_explains_the_reason(self):
        client = ScriptedClient([LLMError("HTTP 503: overloaded")])
        with self.assertRaises(LLMError) as ctx:
            AuditPipeline(client).run(self.document(), lambda _m: None)
        self.assertIn("HTTP 503: overloaded", str(ctx.exception))


class FakeResponse:
    def __init__(self, status, payload, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _ok(body):
    return FakeResponse(200, {"candidates": [{"content": {"parts": [{"text": json.dumps(body)}]}}]})


class GeminiClientTests(unittest.TestCase):
    def make(self, responses):
        sleeps = []
        client = GeminiClient("key", "model", max_retries=3, sleep=sleeps.append)
        client.session = mock.Mock()
        client.session.post.side_effect = responses
        return client, sleeps

    def test_rate_limit_waits_for_server_hint(self):
        limited = FakeResponse(429, {"error": {"message": "quota", "details": [{"retryDelay": "41s"}]}})
        client, sleeps = self.make([limited, _ok({"a": 1})])
        with mock.patch("builtins.print"):
            self.assertEqual({"a": 1}, client.generate_json("s", "u"))
        self.assertEqual([42.0], sleeps)

    def test_invalid_key_fails_fast_with_reason(self):
        bad = FakeResponse(400, {"error": {"message": "API key not valid"}})
        client, sleeps = self.make([bad])
        with self.assertRaises(LLMError) as ctx:
            client.generate_json("s", "u")
        self.assertIn("API key not valid", str(ctx.exception))
        self.assertEqual([], sleeps)
        self.assertEqual(1, client.session.post.call_count)


class QuotaClassificationTests(unittest.TestCase):
    def make(self, responses):
        sleeps = []
        client = GeminiClient("key", "model", max_retries=3, sleep=sleeps.append)
        client.session = mock.Mock()
        client.session.post.side_effect = responses
        return client, sleeps

    @staticmethod
    def quota(quota_id, delay=None):
        details = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
                                    "quotaId": quota_id}]}]
        if delay:
            details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay})
        message = "You exceeded your current quota, please check your plan and billing details."
        return FakeResponse(429, {"error": {"code": 429, "message": message, "details": details}})

    def test_per_minute_limit_with_quota_text_waits_and_retries(self):
        limited = self.quota("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "20s")
        client, sleeps = self.make([limited, _ok({"ok": True})])
        with mock.patch("builtins.print"):
            self.assertEqual({"ok": True}, client.generate_json("s", "u"))
        self.assertEqual([21.0], sleeps)

    def test_daily_limit_fails_fast(self):
        from requirements_validator.errors import QuotaExceededError

        client, sleeps = self.make([self.quota("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "40s")])
        with self.assertRaises(QuotaExceededError) as ctx:
            client.generate_json("s", "u")
        self.assertIn("13:00", str(ctx.exception))
        self.assertEqual([], sleeps)

    def test_unknown_model_is_fatal_with_api_reason(self):
        from requirements_validator.errors import FatalLLMError

        gone = FakeResponse(404, {"error": {"message": "This model models/gemini-2.5-flash is no longer available to new users."}})
        client, sleeps = self.make([gone])
        with self.assertRaises(FatalLLMError) as ctx:
            client.generate_json("s", "u")
        self.assertIn("no longer available", str(ctx.exception))
        self.assertEqual(1, client.session.post.call_count)


class CliDefaultsTests(unittest.TestCase):
    def test_default_model_is_current(self):
        from requirements_validator import cli

        self.assertEqual("gemini-3.8-flash", cli.DEFAULT_MODEL)
        example = (Path(__file__).resolve().parent.parent / ".env.example").read_text(encoding="utf-8")
        self.assertIn("GEMINI_MODEL=gemini-3.8-flash", example)
        self.assertRegex(example, r"(?m)^GEMINI_API_KEY=$")


if __name__ == "__main__":
    unittest.main()
