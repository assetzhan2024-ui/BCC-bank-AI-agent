from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .models import AuditResult, Issue, SpecificationIssue

SEVERITY_ORDER = {"Критичный": 0, "Высокий": 1, "Средний": 2, "Минорный": 3}
NOT_CHECKED = "НЕ ПРОВЕРЕНО"
SPEC_CATEGORIES = [
    "Полнота",
    "Противоречивость",
    "Дублирование",
    "Трассируемость",
    "Терминология",
    "Безопасность и эксплуатация",
]


def build_report(
    result: AuditResult,
    document_name: str,
    model_name: str,
    agent_version: str,
    run_at: datetime,
) -> str:
    item_issues = [issue for review in result.requirement_reviews for issue in review.issues]
    spec_issues = result.specification_review.issues
    all_issues: list[Issue | SpecificationIssue] = [*item_issues, *spec_issues]
    critical = [issue for issue in all_issues if issue.severity == "Критичный"]
    defective = sum(1 for review in result.requirement_reviews if review.issues)
    unchecked = [review.requirement_id for review in result.requirement_reviews if review.status == NOT_CHECKED]
    spec_completed = result.specification_review.completed
    verdict = _verdict(all_issues, unchecked, spec_completed)
    requirement_by_id = {requirement.report_id: requirement for requirement in result.requirements}

    out: list[str] = [
        "# Отчёт статической проверки требований",
        "",
        "## 1. Паспорт прогона",
        "",
        f"- **Проверяемый документ:** {document_name}",
        f"- **Дата и время проверки:** {run_at.isoformat(timespec='seconds')}",
        f"- **Модель LLM:** {model_name}",
        f"- **Версия агента:** {agent_version}",
        "- **Нормативная база:** ISO/IEC/IEEE 29148:2018 (п. 5.2.5, 5.2.6); IEEE Std 830-1998 (п. 4.3)",
        "",
        "## 2. Таблица нарезки требований",
        "",
        "| ID в отчёте | ID в документе | Раздел | Место | Краткая формулировка |",
        "|---|---|---|---|---|",
    ]
    for requirement in result.requirements:
        out.append(
            f"| {requirement.report_id} | {_cell(requirement.document_id) or '—'} | {_cell(requirement.section)} "
            f"| {_cell(requirement.location) or '—'} | {_cell(requirement.summary)} |"
        )

    out.extend(["", "## 3. Проверка каждого требования", ""])
    review_by_id = {review.requirement_id: review for review in result.requirement_reviews}
    for requirement in result.requirements:
        review = review_by_id[requirement.report_id]
        title = requirement.report_id
        if requirement.document_id:
            title += f" ({requirement.document_id})"
        out.extend(
            [
                f"### {title}",
                "",
                f"- **Статус:** {_status(review)}",
                f"- **Раздел:** {requirement.section}",
                f"- **Цитата ({requirement.location or 'место не определено'}):** «{requirement.quote}»",
            ]
        )
        if review.status == NOT_CHECKED:
            out.extend(
                [
                    "- **Результат:** проверка не выполнена из-за сбоя ответа модели. "
                    "Отсутствие замечаний **не означает**, что требование корректно; повторите прогон.",
                    "",
                ]
            )
            continue
        if not review.issues:
            out.extend(["- **Результат:** нарушений по применимым критериям не обнаружено.", ""])
            continue
        out.append("")
        for index, issue in enumerate(sorted(review.issues, key=lambda x: SEVERITY_ORDER[x.severity]), start=1):
            evidence_note = "" if issue.evidence_exact else " _(точная цитата модели не подтверждена — приведено требование целиком)_"
            out.extend(
                [
                    f"#### Дефект {index}",
                    "",
                    f"- **Критерий:** {issue.criterion}",
                    f"- **Критичность:** {issue.severity}",
                    f"- **Доказательство ({issue.location or requirement.location}):** «{issue.evidence}»{evidence_note}",
                    f"- **Суть:** {issue.explanation}",
                    f"- **Риск:** {issue.risk}",
                    f"- **Рекомендация:** {issue.recommendation}",
                    "",
                ]
            )

    out.extend(["## 4. Проверка всего набора требований", ""])
    if not spec_completed:
        out.extend(
            [
                "> **Системная проверка не выполнена** из-за ошибки обращения к модели. "
                "Противоречия и пропуски между требованиями не оценивались; повторите прогон.",
                "",
            ]
        )
    known = {c.casefold() for c in SPEC_CATEGORIES}
    for category in SPEC_CATEGORIES:
        matching = [i for i in spec_issues if i.category.casefold() == category.casefold()]
        out.extend([f"### {category}", ""])
        if not matching:
            message = "Подтверждённых дефектов этой категории не обнаружено." if spec_completed else "Не проверялось."
            out.extend([message, ""])
            continue
        for issue in sorted(matching, key=lambda x: SEVERITY_ORDER[x.severity]):
            out.extend(_spec_issue_lines(issue))
    other = [issue for issue in spec_issues if issue.category.casefold() not in known]
    if other:
        out.extend(["### Другие системные дефекты", ""])
        for issue in sorted(other, key=lambda x: SEVERITY_ORDER[x.severity]):
            out.extend(_spec_issue_lines(issue, show_category=True))

    total = len(result.requirements)
    out.extend(
        [
            "## 5. Сводка",
            "",
            f"- **Всего выделено требований:** {total}",
            f"- **Требований без замечаний:** {total - defective - len(unchecked)}",
            f"- **Требований с дефектами:** {defective}",
            f"- **Требований, не прошедших проверку из-за сбоя модели:** {len(unchecked)}"
            + (f" ({', '.join(unchecked)})" if unchecked else ""),
            f"- **Нарушений в отдельных требованиях:** {len(item_issues)}",
            f"- **Нарушений на уровне набора:** {len(spec_issues)}",
            f"- **Общее число нарушений:** {len(all_issues)}",
            f"- **Критичных дефектов:** {len(critical)}",
            "",
            "### Распределение по критичности",
            "",
            "| Критичность | Количество |",
            "|---|---|",
        ]
    )
    for severity in SEVERITY_ORDER:
        out.append(f"| {severity} | {sum(1 for issue in all_issues if issue.severity == severity)} |")
    out.extend(["", "### Критичные дефекты", ""])
    if critical:
        for issue in critical:
            out.append(f"- {_critical_line(issue, review_by_id, requirement_by_id)}")
    else:
        out.append("Критичных дефектов не обнаружено.")

    priorities = _priorities(all_issues, review_by_id)
    out.extend(
        [
            "",
            "## 6. Итоговый вердикт",
            "",
            f"**{verdict[0]}**",
            "",
            verdict[1],
            "",
            "### Что исправить в первую очередь",
            "",
        ]
    )
    if priorities:
        out.extend(f"{index}. {value}" for index, value in enumerate(priorities, start=1))
    else:
        out.append("1. Блокирующих исправлений не выявлено; провести финальное экспертное ревью перед передачей в разработку.")

    if result.run_warnings:
        out.extend(["", "## Приложение. Технические предупреждения прогона", ""])
        out.extend(f"- {warning}" for warning in result.run_warnings)
    return "\n".join(out).rstrip() + "\n"


def write_report(path_value: str | Path, content: str) -> Path:
    path = Path(path_value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
    return path


def _status(review) -> str:
    if review.status == NOT_CHECKED:
        return f"{NOT_CHECKED} (сбой модели)"
    max_severity = _max_severity(review.issues)
    return f"ДЕФЕКТ — {max_severity}" if max_severity else "OK"


def _spec_issue_lines(issue: SpecificationIssue, show_category: bool = False) -> list[str]:
    refs = ", ".join(issue.requirement_ids) or "документ в целом"
    prefix = f"{issue.category}; " if show_category else ""
    lines = [f"- **{prefix}{issue.severity}; {refs}.** {issue.explanation}"]
    for index, quote in enumerate(issue.evidence):
        place = issue.locations[index] if index < len(issue.locations) else "место не определено"
        lines.append(f"  - Доказательство ({place}): «{quote}»")
    lines.extend([f"  - Риск: {issue.risk}", f"  - Рекомендация: {issue.recommendation}", ""])
    return lines


def _verdict(issues, unchecked, spec_completed):
    severities = {issue.severity for issue in issues}
    incomplete = bool(unchecked) or not spec_completed
    note = (
        " Проверка выполнена не полностью (см. сводку и приложение); перед окончательным решением повторите прогон."
        if incomplete
        else ""
    )
    if "Критичный" in severities:
        return (
            "НЕ РЕКОМЕНДУЕТСЯ (NO-GO)",
            "Начинать разработку и тестирование по текущей версии документа не рекомендуется: "
            "есть критичные дефекты, которые не позволяют однозначно реализовать или проверить требования." + note,
        )
    if "Высокий" in severities or "Средний" in severities or incomplete:
        return (
            "УСЛОВНО ГОТОВО (CONDITIONAL)",
            "Работу можно начинать только после уточнения перечисленных дефектов и фиксации согласованной версии требований." + note,
        )
    return (
        "ГОТОВО (GO)",
        "Документ не содержит выявленных блокирующих дефектов. Перед стартом всё равно требуется формальное согласование ответственными лицами.",
    )


def _issue_refs(issue, review_by_id) -> str:
    if isinstance(issue, SpecificationIssue):
        return ", ".join(issue.requirement_ids) or "документ в целом"
    for requirement_id, review in review_by_id.items():
        if any(candidate is issue for candidate in review.issues):
            return requirement_id
    return "—"


def _priorities(issues, review_by_id) -> list[str]:
    ordered = sorted(issues, key=lambda x: SEVERITY_ORDER[x.severity])
    values: list[str] = []
    seen: set[str] = set()
    for issue in ordered:
        recommendation = issue.recommendation.strip()
        key = recommendation.casefold()
        if recommendation and key not in seen:
            seen.add(key)
            values.append(f"[{issue.severity}; {_issue_refs(issue, review_by_id)}] {recommendation}")
        if len(values) == 10:
            break
    return values


def _critical_line(issue, review_by_id, requirement_by_id) -> str:
    refs = _issue_refs(issue, review_by_id)
    if isinstance(issue, SpecificationIssue):
        quotes = "; ".join(
            f"«{quote}» ({issue.locations[i] if i < len(issue.locations) else 'место не определено'})"
            for i, quote in enumerate(issue.evidence)
        )
        return f"**{refs} — {issue.category}:** {_sentence(issue.explanation)} Доказательство: {quotes}"
    place = issue.location or (requirement_by_id[refs].location if refs in requirement_by_id else "")
    return f"**{refs} — {issue.criterion}:** {_sentence(issue.explanation)} Доказательство: «{issue.evidence}» ({place or 'место не определено'})"


def _sentence(value: str) -> str:
    value = value.strip()
    return value if not value or value[-1] in ".!?…" else value + "."


def _max_severity(issues) -> str:
    return min((issue.severity for issue in issues), key=lambda x: SEVERITY_ORDER[x], default="")


def _cell(value: str) -> str:
    return " ".join(str(value or "").replace("|", "\\|").split())
