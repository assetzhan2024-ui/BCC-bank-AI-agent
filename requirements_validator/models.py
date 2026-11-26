from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DocumentContent:
    name: str
    path: str
    text: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    start_line: int
    end_line: int


@dataclass
class Requirement:
    report_id: str
    document_id: str
    section: str
    quote: str
    summary: str
    source_chunk: int
    location: str = ""


@dataclass
class Issue:
    criterion: str
    severity: str
    evidence: str
    explanation: str
    risk: str
    recommendation: str
    location: str = ""
    evidence_exact: bool = True


@dataclass
class RequirementReview:
    requirement_id: str
    status: str
    issues: list[Issue] = field(default_factory=list)


@dataclass
class SpecificationIssue:
    category: str
    severity: str
    requirement_ids: list[str]
    evidence: list[str]
    explanation: str
    risk: str
    recommendation: str
    locations: list[str] = field(default_factory=list)


@dataclass
class SpecificationReview:
    issues: list[SpecificationIssue] = field(default_factory=list)
    completed: bool = True


@dataclass
class AuditResult:
    requirements: list[Requirement]
    requirement_reviews: list[RequirementReview]
    specification_review: SpecificationReview
    run_warnings: list[str] = field(default_factory=list)
