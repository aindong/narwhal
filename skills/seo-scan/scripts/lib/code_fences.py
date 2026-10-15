"""Shared root-level fenced-code rules for the limited report Markdown subset."""

import re
from typing import NamedTuple, Optional


class CodeFence(NamedTuple):
    """Opening marker, indentation and a bounded, safe optional language label."""

    marker: str
    length: int
    indent: int
    language: str


_OPENING = re.compile(r'^( {0,3})(`{3,}|~{3,})(.*)$')
_LANGUAGE = re.compile(r'^([A-Za-z0-9_+-]{1,80})(?=\s|$)')


def markdown_lines(text: str, *, terminal_empty=False) -> list:
    """Normalize CR/LF endings only, preserving other literal code characters."""
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if not terminal_empty and lines[-1] == '':
        lines.pop()
    return lines


def opening_fence(line: str) -> Optional[CodeFence]:
    """Recognize 3+ backticks/tildes with at most three leading ASCII spaces."""
    match = _OPENING.match(line)
    if not match:
        return None
    indent, markers, info = match.groups()
    if markers[0] == '`' and '`' in info:
        return None
    language = _LANGUAGE.match(info.strip())
    return CodeFence(markers[0], len(markers), len(indent), language.group(1) if language else '')


def closes_fence(line: str, fence: CodeFence) -> bool:
    """Close only with the same marker, enough repeats and trailing space/tabs."""
    body = line.lstrip(' ')
    if len(line) - len(body) > 3:
        return False
    body = body.rstrip(' \t')
    return len(body) >= fence.length and body.count(fence.marker) == len(body)
