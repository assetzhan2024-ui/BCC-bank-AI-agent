from __future__ import annotations

import json
import re
from collections.abc import Callable

from .chunking import split_text
from .errors import LLMError
from .models import (
    AuditResult,
    DocumentContent,
    Issue,
    Requirement,
    RequirementReview,
    SpecificationIssue,
    SpecificationReview,
)
from .prompts import load_prompt

Progress = Callable[[str], None]
SEVERITIES = {"Критичный", "Высокий", "Средний", "Минорный"}


class AuditPipeline:
    def __init__(self, client, chunk_chars: int = 18_000, review_batch_size: int = 10) -> None:
        self.client = client
        self.chunk_chars = chunk_chars
        self.review_batch_size = review_batch_size

    def run(self, document: DocumentContent, progress: Progress = print) -> AuditResult:
        warnings = list(document.warnings)
        chunks = split_text(document.text, self.chunk_chars)
        progress(f"1/4 Извлечение требований: {len(chunks)} фрагмент(ов)")
        requirements = self._extract_requirements(document, chunks, warnings)
        if not requirements:
            raise LLMError("Агент не смог выделить ни одного требования из документа.")

        progress(f"2/4 Поэлементная проверка: {len(requirements)} требовани(й)")
        reviews = self._review_requirements(document, requirements, warnings)
        progress("3/4 Проверка набора требований целиком")
        specification = self._review_specification(document, requirements, warnings)
        progress("4/4 Подготовка детерминированного отчёта")
        return AuditResult(requirements, reviews, specification, warnings)

    def _extract_requirements(self, document, chunks, warnings) -> list[Requirement]:
        system = load_prompt("01_extract_requirements.md")
        extracted: list[dict] = []
        for chunk in chunks:
            user = (
                f"Документ: {document.name}\n"
                f"Фрагмент {chunk.index}, строки {chunk.start_line}–{chunk.end_line}.\n\n"
                f"{chunk.text}"
            )
            payload = self.client.generate_json(system, user)
            items = payload.get("requirements", [])
            if not isinstance(items, list):
                warnings.append(f"Фрагмент {chunk.index}: поле requirements не является массивом.")
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                quote = _clean(item.get("quote"))
                if not quote or not _contains_quote(document.text, quote):
                    warnings.append(f"Отброшена неточная цитата из фрагмента {chunk.index}: {quote[:80]}")
                    continue
                extracted.append(
                    {
                        "document_id": _clean(item.get("document_id")) or "—",
                        "section": _clean(item.get("section")) or "Не указан",
                        "quote": quote,
                        "summary": _clean(item.get("summary")) or _shorten(quote, 140),
                        "chunk": chunk.index,
                    }
                )

        unique: list[dict] = []
        seen: set[str] = set()
        for item in extracted:
            # The same source sentence may contain two atomic obligations. Keep
            # both when the neutral summaries differ, but remove exact repeats.
            key = "|".join((_normalize(item["quote"]), _normalize(item["summary"])))
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return [
            Requirement(f"REQ-{index:03d}", item["document_id"], item["section"], item["quote"], item["summary"], item["chunk"])
            for index, item in enumerate(unique, start=1)
        ]

    def _review_requirements(self, document, requirements, warnings) -> list[RequirementReview]:
        system = load_prompt("02_review_requirements.md")
        result: dict[str, RequirementReview] = {}
        for offset in range(0, len(requirements), self.review_batch_size):
            batch = requirements[offset : offset + self.review_batch_size]
            payload = self.client.generate_json(
                system,
                json.dumps({"document_name": document.name, "requirements": [_requirement_dict(r) for r in batch]}, ensure_ascii=False),
            )
            for raw in payload.get("reviews", []):
                review = _parse_requirement_review(raw, {r.report_id: r for r in batch}, document.text, warnings)
                if review:
                    result[review.requirement_id] = review

        for requirement in requirements:
            result.setdefault(requirement.report_id, RequirementReview(requirement.report_id, "НЕ ПРОВЕРЕНО", []))
            if result[requirement.report_id].status == "НЕ ПРОВЕРЕНО":
                warnings.append(f"{requirement.report_id} не получил корректную поэлементную проверку.")
        return [result[r.report_id] for r in requirements]

    def _review_specification(self, document, requirements, warnings) -> SpecificationReview:
        system = load_prompt("03_review_specification.md")
        compact = {
            "document_name": document.name,
            "requirements": [_requirement_dict(r) for r in requirements],
        }
        payload = self.client.generate_json(system, json.dumps(compact, ensure_ascii=False))
        known = {r.report_id for r in requirements}
        issues: list[SpecificationIssue] = []
        for raw in payload.get("issues", []):
            if not isinstance(raw, dict):
                continue
            ids = [value for value in raw.get("requirement_ids", []) if value in known]
            evidence = [_clean(value) for value in raw.get("evidence", []) if _clean(value)]
            valid_evidence = [value for value in evidence if _contains_quote(document.text, value)]
            if not valid_evidence:
                warnings.append("Отброшено системное замечание без подтверждённой цитаты.")
                continue
            issues.append(
                SpecificationIssue(
                    category=_clean(raw.get("category")) or "Прочее",
                    severity=_severity(raw.get("severity")),
                    requirement_ids=ids,
                    evidence=valid_evidence,
                    explanation=_clean(raw.get("explanation")),
                    risk=_clean(raw.get("risk")),
                    recommendation=_clean(raw.get("recommendation")),
                )
            )
        return SpecificationReview(issues)


def _parse_requirement_review(raw, requirements, document_text, warnings):
    if not isinstance(raw, dict):
        return None
    req_id = _clean(raw.get("requirement_id"))
    if req_id not in requirements:
        return None
    requirement = requirements[req_id]
    issues: list[Issue] = []
    for value in raw.get("issues", []):
        if not isinstance(value, dict):
            continue
        evidence = _clean(value.get("evidence"))
        if not evidence or not _contains_quote(document_text, evidence):
            evidence = requirement.quote
            warnings.append(f"{req_id}: неточная цитата заменена точной цитатой требования.")
        issues.append(
            Issue(
                criterion=_clean(value.get("criterion")) or "Не указан",
                severity=_severity(value.get("severity")),
                evidence=evidence,
                explanation=_clean(value.get("explanation")),
                risk=_clean(value.get("risk")),
                recommendation=_clean(value.get("recommendation")),
            )
        )
    return RequirementReview(req_id, "ДЕФЕКТ" if issues else "OK", issues)


def _requirement_dict(requirement: Requirement) -> dict:
    return {
        "report_id": requirement.report_id,
        "document_id": requirement.document_id,
        "section": requirement.section,
        "quote": requirement.quote,
        "summary": requirement.summary,
    }


def _contains_quote(text: str, quote: str) -> bool:
    return _normalize(quote) in _normalize(text)


def _normalize(value: str) -> str:
    value = value.replace("ё", "е").replace("Ё", "Е")
    return re.sub(r"\s+", " ", value).strip().casefold()


def _clean(value) -> str:
    return str(value or "").strip()


def _severity(value) -> str:
    cleaned = _clean(value).capitalize()
    return cleaned if cleaned in SEVERITIES else "Средний"


def _shorten(value: str, length: int) -> str:
    return value if len(value) <= length else value[: length - 1].rstrip() + "…"
