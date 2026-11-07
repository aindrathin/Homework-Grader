"""Helpers for reading Java source files and telling code apart from comments and strings."""

from __future__ import annotations

import re
from pathlib import Path

_NOT_NEWLINE = re.compile(r"[^\n]")


def read_java(path: Path) -> str:
    """Read a .java file, accepting UTF-8 (with or without BOM) or Windows-1252."""
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def split_segments(src: str) -> list[tuple[bool, str]]:
    """Split Java source into ``(is_code, text)`` pieces.

    Comments, string literals, text blocks, and char literals are returned with
    ``is_code=False`` so callers can edit code without touching text inside quotes.
    Joining every piece gives back the original source.
    """
    out: list[tuple[bool, str]] = []
    n = len(src)
    i = start = 0
    while i < n:
        if src.startswith("//", i):
            end = src.find("\n", i)
            end = n if end < 0 else end
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            end = n if end < 0 else end + 2
        elif src.startswith('"""', i):
            end = _text_block_end(src, i + 3)
        elif src[i] in "\"'":
            end = _quote_end(src, i)
        else:
            i += 1
            continue
        if start < i:
            out.append((True, src[start:i]))
        out.append((False, src[i:end]))
        i = start = end
    if start < n:
        out.append((True, src[start:]))
    return out


def code_only(src: str) -> str:
    """Return the source with comments and literals blanked out (newlines kept)."""
    return "".join(
        text if is_code else _NOT_NEWLINE.sub(" ", text) for is_code, text in split_segments(src)
    )


def _quote_end(src: str, i: int) -> int:
    quote = src[i]
    j = i + 1
    while j < len(src):
        c = src[j]
        if c == "\\":
            j += 2
            continue
        if c == quote:
            return j + 1
        if c == "\n":  # unterminated literal; stop at end of line
            return j
        j += 1
    return len(src)


def _text_block_end(src: str, j: int) -> int:
    while j < len(src):
        if src[j] == "\\":
            j += 2
            continue
        if src.startswith('"""', j):
            return j + 3
        j += 1
    return len(src)
