from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .models import AuditResult, Issue, SpecificationIssue

SEVERITY_ORDER = {"Критичный": 0, "Высокий": 1, "Средний": 2, "Минорный": 3}


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
    unchecked = sum(1 for review in result.requirement_reviews if review.status == "НЕ ПРОВЕРЕНО")
    verdict = _verdict(all_issues, unchecked)

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
        "| Идентификатор в отчёте | Идентификатор в документе | Раздел | Краткая формулировка / цитата |",
        "|---|---|---|---|",
    ]
    for requirement in result.requirements:
        out.append(
            f"| {requirement.report_id} | {_cell(requirement.document_id)} | {_cell(requirement.section)} | {_cell(requirement.summary)} |"
        )

    out.extend(["", "## 3. Проверка каждого требования", ""])
    review_by_id = {review.requirement_id: review for review in result.requirement_reviews}
    for requirement in result.requirements:
        review = review_by_id[requirement.report_id]
        max_severity = _max_severity(review.issues)
        status = review.status if not max_severity else f"ДЕФЕКТ — {max_severity}"
        out.extend(
            [
                f"### {requirement.report_id} — {requirement.document_id}",
                "",
                f"- **Статус:** {status}",
                f"- **Раздел:** {requirement.section}",
                f"- **Цитата:** «{requirement.quote}»",
            ]
        )
        if not review.issues:
            out.extend(["- **Результат:** нарушений по применимым критериям не обнаружено.", ""])
            continue
        out.append("")
        for index, issue in enumerate(sorted(review.issues, key=lambda x: SEVERITY_ORDER[x.severity]), start=1):
            out.extend(
                [
                    f"#### Дефект {index}",
                    "",
                    f"- **Критерий:** {issue.criterion}",
                    f"- **Критичность:** {issue.severity}",
                    f"- **Доказательство:** «{issue.evidence}»",
                    f"- **Суть:** {issue.explanation}",
                    f"- **Риск:** {issue.risk}",
                    f"- **Рекомендация:** {issue.recommendation}",
                    "",
                ]
            )

    out.extend(["## 4. Проверка всего набора требований", ""])
    categories = ["Полнота", "Противоречивость", "Дублирование", "Трассируемость", "Терминология", "Безопасность и эксплуатация"]
    for category in categories:
        matching = [i for i in spec_issues if i.category.casefold() == category.casefold()]
        out.extend([f"### {category}", ""])
        if not matching:
            out.extend(["Подтверждённых дефектов этой категории не обнаружено.", ""])
            continue
        for issue in sorted(matching, key=lambda x: SEVERITY_ORDER[x.severity]):
            refs = ", ".join(issue.requirement_ids) or "документ в целом"
            evidence = "; «".join(issue.evidence)
            evidence = f"«{evidence}»" if evidence else "—"
            out.extend(
                [
                    f"- **{issue.severity}; {refs}.** {issue.explanation}",
                    f"  - Доказательство: {evidence}",
                    f"  - Риск: {issue.risk}",
                    f"  - Рекомендация: {issue.recommendation}",
                    "",
                ]
            )
    other = [issue for issue in spec_issues if issue.category.casefold() not in {c.casefold() for c in categories}]
    if other:
        out.extend(["### Другие системные дефекты", ""])
        for issue in other:
            out.append(f"- **{issue.severity}; {', '.join(issue.requirement_ids) or 'документ в целом'}.** {issue.explanation} Рекомендация: {issue.recommendation}")
        out.append("")

    out.extend(
        [
            "## 5. Сводка",
            "",
            f"- **Всего выделено требований:** {len(result.requirements)}",
            f"- **Требований без замечаний:** {len(result.requirements) - defective - unchecked}",
            f"- **Требований с дефектами:** {defective}",
            f"- **Требований без корректного результата проверки:** {unchecked}",
            f"- **Общее число нарушений:** {len(all_issues)}",
            f"- **Критичных дефектов:** {len(critical)}",
            "",
            "### Критичные дефекты",
            "",
        ]
    )
    if critical:
        for issue in critical:
            out.append(f"- {_critical_line(issue)}")
    else:
        out.append("Критичных дефектов не обнаружено.")

    priorities = _priorities(all_issues)
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


def _verdict(issues, unchecked):
    severities = {issue.severity for issue in issues}
    if unchecked or "Критичный" in severities:
        return "НЕ РЕКОМЕНДУЕТСЯ (NO-GO)", "Начинать разработку и тестирование по текущей версии документа не рекомендуется: присутствуют критичные дефекты или непроверенные требования."
    if "Высокий" in severities or "Средний" in severities:
        return "УСЛОВНО ГОТОВО", "Работу можно начинать только после уточнения перечисленных дефектов и фиксации согласованной версии требований."
    return "ГОТОВО (GO)", "Документ не содержит выявленных блокирующих дефектов. Перед стартом всё равно требуется формальное согласование ответственными лицами."


def _priorities(issues) -> list[str]:
    ordered = sorted(issues, key=lambda x: SEVERITY_ORDER[x.severity])
    values: list[str] = []
    seen: set[str] = set()
    for issue in ordered:
        recommendation = issue.recommendation.strip()
        key = recommendation.casefold()
        if recommendation and key not in seen:
            seen.add(key)
            values.append(f"[{issue.severity}] {recommendation}")
        if len(values) == 10:
            break
    return values


def _critical_line(issue) -> str:
    if isinstance(issue, SpecificationIssue):
        refs = ", ".join(issue.requirement_ids) or "документ в целом"
        return f"**{refs}:** {issue.explanation}"
    return f"**{issue.criterion}:** {issue.explanation} Доказательство: «{issue.evidence}»"


def _max_severity(issues) -> str:
    return min((issue.severity for issue in issues), key=lambda x: SEVERITY_ORDER[x], default="")


def _cell(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())
