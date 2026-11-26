from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .errors import DocumentError
from .models import DocumentContent

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".docx"}


def read_document(path_value: str | Path) -> DocumentContent:
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise DocumentError(f"Входной файл не найден: {path}")
    if not path.is_file():
        raise DocumentError(f"Входной путь не является файлом: {path}")

    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise DocumentError(f"Формат {suffix or '(без расширения)'} не поддерживается. Допустимо: {allowed}")

    warnings: list[str] = []
    try:
        if suffix in {".md", ".txt"}:
            text = _read_plain_text(path)
        elif suffix == ".pdf":
            text, warnings = _read_pdf(path)
        else:
            text = _read_docx(path)
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(f"Не удалось прочитать {path.name}: {exc}") from exc

    text = text.replace("\x00", "").strip()
    if not text:
        raise DocumentError(
            "В документе не найден текст. Если PDF является сканом, сначала выполните OCR."
        )
    return DocumentContent(path.name, str(path), text, tuple(warnings))


def _read_plain_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentError(f"Не удалось определить кодировку файла {path.name}")


def _read_pdf(path: Path) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    pages: list[str] = []
    empty_pages: list[int] = []
    for number, page in enumerate(reader.pages, start=1):
        value = (page.extract_text() or "").strip()
        if not value:
            empty_pages.append(number)
        pages.append(f"\n[Страница {number}]\n{value}")

    warnings = []
    if empty_pages:
        listed = ", ".join(map(str, empty_pages[:20]))
        suffix = "…" if len(empty_pages) > 20 else ""
        warnings.append(f"В PDF не извлечён текст со страниц: {listed}{suffix}. Возможно, нужен OCR.")
    return "\n".join(pages), warnings


def _read_docx(path: Path) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(path)
    blocks: list[str] = []
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if text:
                blocks.append(text)
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            rows = [[_clean_cell(cell.text) for cell in row.cells] for row in table.rows]
            blocks.extend(_table_to_markdown(rows))
    return "\n\n".join(blocks)


def _clean_cell(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def _table_to_markdown(rows: list[list[str]]) -> Iterable[str]:
    if not rows:
        return []
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    result = ["| " + " | ".join(padded[0]) + " |"]
    result.append("| " + " | ".join(["---"] * width) + " |")
    result.extend("| " + " | ".join(row) + " |" for row in padded[1:])
    return result
