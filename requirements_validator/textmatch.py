"""Quote verification and location lookup.

Model quotes are compared with the source after a tolerant normalisation:
case, whitespace, ё/е, quote and dash variants, Markdown emphasis/backticks,
table pipes and PDF page markers are ignored. If that fails, a second pass
compares only letters and digits, which survives PDF line-break hyphenation
and punctuation differences. The words themselves must still match in order.
"""

from __future__ import annotations

import re

PAGE_MARKER = re.compile(r"^\[Страница (\d+)\]$")
MIN_SKELETON_LENGTH = 12

_CHAR_MAP = str.maketrans(
    {
        "ё": "е",
        "Ё": "Е",
        "«": '"',
        "»": '"',
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "−": "-",
        " ": " ",
        " ": " ",
        "­": "",
        "|": " ",
        "`": "",
        "*": "",
    }
)


def normalize(value: str) -> str:
    value = str(value or "").translate(_CHAR_MAP)
    value = re.sub(r"\s+", " ", value)
    return value.strip().casefold()


def skeleton(value: str) -> str:
    return "".join(char for char in normalize(value) if char.isalnum())


class SourceIndex:
    """Normalised copy of the document that remembers line and page numbers."""

    def __init__(self, text: str) -> None:
        chars: list[str] = []
        char_lines: list[int] = []
        self.line_pages: dict[int, int] = {}
        self.has_pages = False

        page = 0
        for number, line in enumerate(text.splitlines(), start=1):
            marker = PAGE_MARKER.match(line.strip())
            if marker:
                page = int(marker.group(1))
                self.has_pages = True
                continue
            self.line_pages[number] = page
            piece = normalize(line)
            if not piece:
                continue
            if chars:
                chars.append(" ")
                char_lines.append(number)
            chars.extend(piece)
            char_lines.extend([number] * len(piece))

        self.normalized = "".join(chars)
        self._char_lines = char_lines
        skeleton_positions = [index for index, char in enumerate(chars) if char.isalnum()]
        self._skeleton = "".join(chars[index] for index in skeleton_positions)
        self._skeleton_lines = [char_lines[index] for index in skeleton_positions]

    def _line_of(self, quote: str) -> int | None:
        needle = normalize(quote)
        if not needle:
            return None
        position = self.normalized.find(needle)
        if position >= 0:
            return self._char_lines[position]
        bones = skeleton(quote)
        if len(bones) < MIN_SKELETON_LENGTH:
            return None
        position = self._skeleton.find(bones)
        if position >= 0:
            return self._skeleton_lines[position]
        return None

    def contains(self, quote: str) -> bool:
        return self._line_of(quote) is not None

    def locate(self, quote: str) -> str:
        """Human-readable place of the quote: page for PDF, line otherwise."""
        line = self._line_of(quote)
        if line is None:
            return "место не определено"
        if self.has_pages:
            return f"стр. {self.line_pages.get(line, 0)}"
        return f"строка {line}"
