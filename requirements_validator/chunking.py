from __future__ import annotations

from .models import TextChunk


def split_text(text: str, max_chars: int = 18_000) -> list[TextChunk]:
    """Split on line boundaries while keeping source line ranges."""
    if max_chars < 2_000:
        raise ValueError("max_chars must be at least 2000")

    lines = text.splitlines()
    chunks: list[TextChunk] = []
    current: list[str] = []
    current_size = 0
    start_line = 1

    for line_number, line in enumerate(lines, start=1):
        addition = len(line) + 1
        if current and current_size + addition > max_chars:
            chunks.append(
                TextChunk(len(chunks) + 1, "\n".join(current).strip(), start_line, line_number - 1)
            )
            current = []
            current_size = 0
            start_line = line_number
        current.append(line)
        current_size += addition

    if current:
        chunks.append(TextChunk(len(chunks) + 1, "\n".join(current).strip(), start_line, len(lines)))
    return [chunk for chunk in chunks if chunk.text]
