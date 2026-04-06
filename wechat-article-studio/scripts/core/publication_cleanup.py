from __future__ import annotations

import re


AI_LABEL_PHRASES = ("行业判断", "事实/依据", "事实依据", "边界/误判", "边界误判", "误判/边界")

_INLINE_BULLET_SPLIT_RE = re.compile(r"(?<=[。！？!?；;：:）)\]】])\s+(?=[-*+]\s+)")
_INLINE_ORDERED_SPLIT_RE = re.compile(r"(?<=[。！？!?；;：:）)\]】])\s+(?=\d+[.)]\s+)")


def strip_ai_label_phrases(text: str) -> str:
    normalized = text or ""
    label_alt = "|".join(re.escape(item) for item in AI_LABEL_PHRASES)
    normalized = re.sub(rf"(?mi)^\s*#{{1,6}}\s*(?:{label_alt})\s*$\n?", "", normalized)
    normalized = re.sub(rf"(?mi)^(\s*(?:>\s*)?(?:[-*+]\s*)?)(?:{label_alt})\s*[：:]\s*", r"\1", normalized)
    normalized = re.sub(rf"(?mi)^\s*(?:{label_alt})\s*$\n?", "", normalized)
    return normalized


def expand_compact_markdown_lists(text: str) -> str:
    raw = text or ""
    if not raw.strip():
        return raw
    lines: list[str] = []
    for line in raw.splitlines():
        expanded = _expand_bullet_line(line)
        if len(expanded) == 1:
            expanded = _expand_ordered_line(line)
        lines.extend(expanded)
    normalized = "\n".join(lines)
    return normalized + ("\n" if raw.endswith("\n") else "")


def _expand_bullet_line(line: str) -> list[str]:
    match = re.match(r"^(?P<indent>\s*)(?P<marker>[-*+])\s+(?P<body>.+)$", line)
    if not match:
        return [line]
    indent = match.group("indent")
    content = f"{match.group('marker')} {match.group('body').strip()}"
    segments = [item.strip() for item in _INLINE_BULLET_SPLIT_RE.split(content) if item.strip()]
    if len(segments) <= 1 or not all(re.match(r"^[-*+]\s+\S+", item) for item in segments):
        return [line]
    return [f"{indent}{item}" for item in segments]


def _expand_ordered_line(line: str) -> list[str]:
    match = re.match(r"^(?P<indent>\s*)(?P<marker>\d+[.)])\s+(?P<body>.+)$", line)
    if not match:
        return [line]
    indent = match.group("indent")
    content = f"{match.group('marker')} {match.group('body').strip()}"
    segments = [item.strip() for item in _INLINE_ORDERED_SPLIT_RE.split(content) if item.strip()]
    if len(segments) <= 1 or not all(re.match(r"^\d+[.)]\s+\S+", item) for item in segments):
        return [line]
    return [f"{indent}{item}" for item in segments]
