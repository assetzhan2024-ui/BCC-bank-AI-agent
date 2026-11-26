from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv

from .document_reader import SUPPORTED_EXTENSIONS, read_document
from .errors import ValidatorError
from .llm_client import GeminiClient
from .pipeline import AuditPipeline
from .report import build_report, write_report
from .versioning import agent_version

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="ИИ-агент статической проверки программных требований.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input", "-i", required=True, help="Путь к требованиям (.md, .txt, .pdf, .docx)")
    parser.add_argument("--output", "-o", required=True, help="Путь к итоговому Markdown-отчёту")
    parser.add_argument("--model", help="Имя Gemini-модели; переопределяет GEMINI_MODEL")
    parser.add_argument("--chunk-chars", type=int, default=18_000, help="Максимальный размер фрагмента документа")
    parser.add_argument("--batch-size", type=int, default=10, help="Требований в одном запросе поэлементной проверки")
    parser.add_argument("--quiet", action="store_true", help="Не показывать этапы выполнения")
    return parser


def main(argv: list[str] | None = None) -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    args = build_parser().parse_args(argv)
    progress = (lambda _message: None) if args.quiet else (lambda message: print(message, flush=True))

    try:
        document = read_document(args.input)
        model = args.model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        client = GeminiClient(
            os.getenv("GEMINI_API_KEY", ""),
            model,
            timeout=int(os.getenv("GEMINI_TIMEOUT_SECONDS", "180")),
            max_retries=int(os.getenv("GEMINI_MAX_RETRIES", "5")),
        )
        result = AuditPipeline(client, args.chunk_chars, args.batch_size).run(document, progress)
        timezone = _timezone(os.getenv("REPORT_TIMEZONE", "Asia/Almaty"))
        content = build_report(
            result,
            document.name,
            model,
            agent_version(PROJECT_ROOT),
            datetime.now(timezone),
        )
        output = write_report(args.output, content)
        print(f"Готово. Отчёт сохранён: {output}")
        return 0
    except (ValidatorError, ValueError) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Проверка остановлена пользователем.", file=sys.stderr)
        return 130


def _timezone(name: str):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")
