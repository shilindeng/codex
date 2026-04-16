from __future__ import annotations

import html
import re
from typing import Any


_BLOCK_RE = re.compile(
    r"(?is)"
    r"<hr\s*/?>"
    r"|<(p|ul|ol|blockquote|pre|table|h2|h3|h4)\b[^>]*>.*?</\1>"
)
_TOP_TAG_RE = re.compile(r"(?is)^<(?P<tag>[a-z0-9]+)\b")
_PARAGRAPH_RE = re.compile(r"(?is)<p\b[^>]*>(.*?)</p>")
_LIST_ITEM_RE = re.compile(r"(?is)<li\b[^>]*>(.*?)</li>")
_TABLE_ROW_RE = re.compile(r"(?is)<tr\b[^>]*>(.*?)</tr>")
_TABLE_CELL_RE = re.compile(r"(?is)<t([hd])\b[^>]*>(.*?)</t\1>")
_CALLOUT_MARKER_RE = re.compile(r"\[\!\s*(TIP|NOTE|TAKEAWAY|IMPORTANT|WARNING|CAUTION|CHECKLIST|MYTHFACT)\s*\]", re.I)
_DIALOGUE_RE = re.compile(r"^(?P<speaker>[^：:\n]{1,8})\s*[：:]\s*(?P<text>.+)$")
_TIME_ITEM_RE = re.compile(
    r"^(?P<time>"
    r"(?:\d{4}(?:年|\.\d{1,2}(?:月)?|-\d{1,2}(?:-\d{1,2})?)?"
    r"|Q[1-4]\s*\d{4}"
    r"|(?:第)?[一二三四五六七八九十\d]+(?:步|阶段)"
    r"|(?:上午|中午|下午|傍晚|晚上|夜里|凌晨)"
    r"|Day\s*\d+"
    r"|Step\s*\d+)"
    r")\s*[：:]\s*(?P<content>.+)$",
    re.I,
)
_STAT_LABEL_VALUE_RE = re.compile(
    r"^(?P<label>[^：:\n]{1,14})\s*[：:]\s*(?P<value>(?:约|近|超)?\d[\d.,]*(?:%|倍|万|亿|w|W|个|条|次|人|天|小时|分钟|月|年)?(?:\s*[+＋])?)$"
)
_STAT_VALUE_LABEL_RE = re.compile(
    r"^(?P<value>(?:约|近|超)?\d[\d.,]*(?:%|倍|万|亿|w|W|个|条|次|人|天|小时|分钟|月|年)?(?:\s*[+＋])?)(?:\s+(?P<label>.+))$"
)


def _strip_tags(text: str) -> str:
    raw = re.sub(r"(?is)<br\s*/?>", "\n", text or "")
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    raw = html.unescape(raw)
    return re.sub(r"\s+", " ", raw).strip()


def _top_tag(text: str) -> str:
    match = _TOP_TAG_RE.match((text or "").strip())
    return (match.group("tag") if match else "").lower()


def _inner_html(block: str) -> str:
    match = re.match(r"(?is)^<([a-z0-9]+)\b[^>]*>(.*)</\1>$", (block or "").strip())
    return (match.group(2) if match else block or "").strip()


def _trim_wrapping_paragraphs(value: str) -> str:
    current = value.strip()
    while True:
        match = re.fullmatch(r"(?is)<p\b[^>]*>(.*)</p>", current)
        if not match:
            return current
        inner = (match.group(1) or "").strip()
        if re.search(r"(?is)</?(?:p|ul|ol|blockquote|pre|table|h2|h3|h4)\b", inner):
            return current
        current = inner


def _split_blocks(raw_html: str) -> list[str]:
    blocks: list[str] = []
    position = 0
    for match in _BLOCK_RE.finditer(raw_html or ""):
        leading = (raw_html[position:match.start()] or "").strip()
        if leading:
            blocks.append(leading)
        blocks.append(match.group(0))
        position = match.end()
    trailing = (raw_html[position:] or "").strip()
    if trailing:
        blocks.append(trailing)
    return blocks


def _list_items(block: str) -> list[str]:
    return [_trim_wrapping_paragraphs(item) for item in _LIST_ITEM_RE.findall(block or "")]


def _extract_table(block: str) -> tuple[list[str], list[list[str]]] | None:
    rows: list[list[str]] = []
    header: list[str] = []
    saw_header = False
    for raw_row in _TABLE_ROW_RE.findall(block or ""):
        cells = _TABLE_CELL_RE.findall(raw_row)
        if not cells:
            continue
        values = [_trim_wrapping_paragraphs(value) for _, value in cells]
        if len(values) != 2:
            return None
        if any(kind.lower() == "h" for kind, _ in cells):
            header = values
            saw_header = True
        else:
            rows.append(values)
    if not saw_header or not header or len(rows) < 1 or len(rows) > 6:
        return None
    average_cell_length = sum(len(_strip_tags(cell)) for row in rows for cell in row) / max(len(rows) * 2, 1)
    if average_cell_length > 54:
        return None
    return header, rows


def _parse_time_item(text: str) -> tuple[str, str] | None:
    match = _TIME_ITEM_RE.match(text.strip())
    if not match:
        return None
    return match.group("time").strip(), match.group("content").strip()


def _parse_stat_item(item_html: str) -> tuple[str, str] | None:
    plain = _strip_tags(item_html)
    if not plain or len(plain) > 24:
        return None
    match = _STAT_LABEL_VALUE_RE.match(plain)
    if match:
        return match.group("value").strip(), match.group("label").strip()
    match = _STAT_VALUE_LABEL_RE.match(plain)
    if match:
        label = (match.group("label") or "").strip()
        if not label:
            return None
        return match.group("value").strip(), label
    return None


def _remove_dialogue_speaker(inner_html: str, speaker: str) -> str:
    escaped = re.escape(speaker)
    patterns = [
        rf"(?is)^\s*<strong>\s*{escaped}\s*[：:]\s*</strong>\s*",
        rf"(?is)^\s*{escaped}\s*[：:]\s*",
    ]
    result = inner_html.strip()
    for pattern in patterns:
        updated = re.sub(pattern, "", result, count=1)
        if updated != result:
            return updated.strip()
    return result


def _render_steps(items: list[str]) -> str:
    parts = ['<section data-wx-role="steps">']
    for index, item in enumerate(items, start=1):
        parts.extend(
            [
                '<section data-wx-role="steps-item">',
                f'<span data-wx-role="steps-index">{index}</span>',
                f'<span data-wx-role="steps-content">{item}</span>',
                "</section>",
            ]
        )
    parts.append("</section>")
    return "".join(parts)


def _render_timeline(entries: list[tuple[str, str]]) -> str:
    parts = ['<section data-wx-role="timeline">']
    for time_label, content in entries:
        parts.extend(
            [
                '<section data-wx-role="timeline-item">',
                f'<span data-wx-role="timeline-time">{html.escape(time_label)}</span>',
                '<span data-wx-role="timeline-dot">●</span>',
                f'<span data-wx-role="timeline-content">{content}</span>',
                "</section>",
            ]
        )
    parts.append("</section>")
    return "".join(parts)


def _render_compare(header: list[str], rows: list[list[str]]) -> str:
    parts = [
        '<section data-wx-role="compare">',
        '<section data-wx-role="compare-header">',
        f'<span data-wx-role="compare-head-left">{header[0]}</span>',
        f'<span data-wx-role="compare-head-right">{header[1]}</span>',
        "</section>",
    ]
    for left, right in rows:
        parts.extend(
            [
                '<section data-wx-role="compare-row">',
                f'<span data-wx-role="compare-left">{left}</span>',
                f'<span data-wx-role="compare-right">{right}</span>',
                "</section>",
            ]
        )
    parts.append("</section>")
    return "".join(parts)


def _render_dialogue(lines: list[tuple[str, str]]) -> str:
    speaker_sides: dict[str, str] = {}
    parts = ['<section data-wx-role="dialogue">']
    for speaker, text_html in lines:
        if speaker not in speaker_sides:
            speaker_sides[speaker] = "left" if len(speaker_sides) % 2 == 0 else "right"
        side = speaker_sides[speaker]
        parts.extend(
            [
                f'<section data-wx-role="dialogue-bubble" data-wx-side="{side}">',
                f'<p data-wx-role="dialogue-speaker">{html.escape(speaker)}</p>',
                f'<p data-wx-role="dialogue-text">{text_html}</p>',
                "</section>",
            ]
        )
    parts.append("</section>")
    return "".join(parts)


def _render_quote(text_parts: list[str], author: str) -> str:
    quote_text = "<br />".join(part for part in text_parts if part.strip())
    parts = [
        '<section data-wx-role="quote-card">',
        '<p data-wx-role="quote-mark">“</p>',
        f'<p data-wx-role="quote-text">{quote_text}</p>',
    ]
    if author:
        parts.append(f'<p data-wx-role="quote-author">- {html.escape(author)}</p>')
    parts.append("</section>")
    return "".join(parts)


def _render_stats(stats: list[tuple[str, str]]) -> str:
    parts = ['<section data-wx-role="stats-grid">']
    for value, label in stats:
        parts.extend(
            [
                '<section data-wx-role="stat-card">',
                f'<p data-wx-role="stat-value">{html.escape(value)}</p>',
                f'<p data-wx-role="stat-label">{html.escape(label)}</p>',
                "</section>",
            ]
        )
    parts.append("</section>")
    return "".join(parts)


def _add_role_attr(block: str, role: str) -> str:
    if not block or not role:
        return block
    if 'data-wx-role="' in block:
        return re.sub(r'data-wx-role="[^"]+"', f'data-wx-role="{html.escape(role, quote=True)}"', block, count=1)
    return re.sub(r"(?is)^<([a-z0-9]+)\b", lambda m: f'<{m.group(1)} data-wx-role="{html.escape(role, quote=True)}"', block, count=1)


def _split_sections_from_blocks(blocks: list[str]) -> tuple[list[str], list[dict[str, Any]]]:
    intro_blocks: list[str] = []
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for block in blocks:
        tag = _top_tag(block)
        if tag in {"h2", "h3", "h4"}:
            current = {
                "heading_block": block,
                "heading_text": _strip_tags(_inner_html(block)),
                "content_blocks": [],
            }
            sections.append(current)
            continue
        if current is None:
            intro_blocks.append(block)
        else:
            current["content_blocks"].append(block)
    return intro_blocks, sections


def _flatten_sections(intro_blocks: list[str], sections: list[dict[str, Any]]) -> list[str]:
    parts: list[str] = []
    parts.extend(block for block in intro_blocks if str(block).strip())
    for section in sections:
        if section.get("heading_block"):
            parts.append(str(section["heading_block"]))
        parts.extend(str(block) for block in (section.get("content_blocks") or []) if str(block).strip())
    return parts


def _wrap_module(role: str, blocks: list[str], *, label: str = "") -> list[str]:
    content = "".join(blocks).strip()
    if not content:
        return blocks
    parts = [f'<section data-wx-role="{role}">']
    label_role_map = {
        "evidence-strip": "evidence-strip-label",
        "boundary-card": "boundary-label",
        "scene-card": "scene-label",
        "turning-point-card": "turning-point-label",
        "pitfall-card": "pitfall-label",
        "fit-card": "fit-label",
        "emotion-turn": "emotion-turn-label",
    }
    label_role = label_role_map.get(role)
    if label and label_role:
        parts.append(f'<p data-wx-role="{label_role}">{html.escape(label)}</p>')
    parts.append(content)
    parts.append("</section>")
    return ["".join(parts)]


def _render_keyline(blocks: list[str]) -> list[str]:
    for index, block in enumerate(blocks):
        if _top_tag(block) == "p":
            text = _strip_tags(_inner_html(block))
            if text:
                keyline = (
                    '<section data-wx-role="keyline">'
                    f'<p data-wx-role="keyline-text">{html.escape(text)}</p>'
                    "</section>"
                )
                return [keyline] + [item for j, item in enumerate(blocks) if j != index]
    return _wrap_module("keyline", blocks)


def _apply_layout_plan(enhanced_blocks: list[str], manifest: dict[str, Any] | None = None) -> list[str]:
    manifest = manifest or {}
    layout_plan = manifest.get("layout_plan") or {}
    section_modules = list(layout_plan.get("section_modules") or layout_plan.get("section_plans") or [])
    if not section_modules:
        return enhanced_blocks

    intro_blocks, sections = _split_sections_from_blocks(enhanced_blocks)
    if not sections:
        return enhanced_blocks

    if intro_blocks:
        first_plan = section_modules[0] if section_modules else {}
        if str(first_plan.get("module_type") or "") == "lead-note":
            for index, block in enumerate(intro_blocks):
                if _top_tag(block) == "p":
                    text = _strip_tags(_inner_html(block))
                    if text:
                        intro_blocks[index] = (
                            '<section data-wx-role="lead-note">'
                            f'<p data-wx-role="lead-note-text">{html.escape(text)}</p>'
                            "</section>"
                        )
                        break

    label_text_map = {
        "evidence-strip": "关键细节",
        "boundary-card": "别急着下结论",
        "scene-card": "先到现场",
        "turning-point-card": "变化从这里开始",
        "pitfall-card": "最容易踩坑的地方",
        "fit-card": "更适合谁",
        "emotion-turn": "情绪一下变了",
    }

    for index, section in enumerate(sections):
        plan = section_modules[index] if index < len(section_modules) else {}
        heading_role = str(plan.get("heading_role") or "")
        if heading_role and section.get("heading_block"):
            section["heading_block"] = _add_role_attr(str(section["heading_block"]), heading_role)
        module_type = str(plan.get("module_type") or "")
        content_blocks = list(section.get("content_blocks") or [])
        if not content_blocks:
            continue
        if module_type == "keyline":
            section["content_blocks"] = _render_keyline(content_blocks)
        elif module_type in {"evidence-strip", "boundary-card", "scene-card", "turning-point-card", "pitfall-card", "fit-card", "emotion-turn", "summary-close", "action-close", "migration-close", "soft-close", "decision-close", "takeaway-card"}:
            section["content_blocks"] = _wrap_module(module_type, content_blocks, label=label_text_map.get(module_type, ""))
        elif module_type == "quote-card":
            if not any('data-wx-role="quote-card"' in block for block in content_blocks):
                section["content_blocks"] = _render_keyline(content_blocks)
        elif module_type == "compare-grid":
            if not any('data-wx-role="compare"' in block for block in content_blocks):
                section["content_blocks"] = _wrap_module("fit-card", content_blocks, label="比较维度")
        elif module_type == "step-stack":
            if not any('data-wx-role="steps"' in block for block in content_blocks):
                section["content_blocks"] = _wrap_module("pitfall-card", content_blocks, label="步骤说明")
    return _flatten_sections(intro_blocks, sections)


def _dialogue_from_blocks(blocks: list[str], start: int) -> tuple[str, int] | None:
    entries: list[tuple[str, str]] = []
    cursor = start
    while cursor < len(blocks) and _top_tag(blocks[cursor]) == "p":
        inner = _inner_html(blocks[cursor])
        plain = _strip_tags(inner)
        match = _DIALOGUE_RE.match(plain)
        if not match:
            break
        speaker = match.group("speaker").strip()
        text_html = _remove_dialogue_speaker(inner, speaker)
        if not text_html:
            text_html = html.escape(match.group("text").strip())
        entries.append((speaker, text_html))
        cursor += 1
    speakers = {speaker for speaker, _ in entries}
    if len(entries) >= 2 and (len(speakers) >= 2 or len(entries) >= 3):
        return _render_dialogue(entries), cursor
    return None


def _quote_from_block(blockquote_html: str) -> str | None:
    paragraphs = [_trim_wrapping_paragraphs(item) for item in _PARAGRAPH_RE.findall(blockquote_html or "")]
    if not paragraphs:
        return None
    plain_parts = [_strip_tags(item) for item in paragraphs if _strip_tags(item)]
    if not plain_parts:
        return None
    if any(_CALLOUT_MARKER_RE.search(part) for part in plain_parts):
        return None
    total_length = sum(len(part) for part in plain_parts)
    if total_length < 14 or total_length > 120 or len(plain_parts) > 3:
        return None
    author = ""
    text_parts = list(paragraphs)
    if len(plain_parts) >= 2 and len(plain_parts[-1]) <= 18 and re.fullmatch(r"(?:[-—–]{1,2}\s*)?[A-Za-z0-9\u4e00-\u9fff·]{2,18}", plain_parts[-1]):
        author = re.sub(r"^(?:[-—–]{1,2}\s*)", "", plain_parts[-1]).strip()
        text_parts = paragraphs[:-1]
    if not text_parts:
        return None
    return _render_quote(text_parts, author)


def enhance_content_html(raw_html: str, manifest: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    cleaned_html = re.sub(r"(?is)<p\b[^>]*>\s*(?:&gt;|>)\s*</p>", "", raw_html or "")
    blocks = _split_blocks(cleaned_html)
    if not blocks:
        return cleaned_html, []

    enhanced: list[str] = []
    used: list[str] = []
    cursor = 0

    while cursor < len(blocks):
        dialogue = _dialogue_from_blocks(blocks, cursor)
        if dialogue:
            block_html, next_cursor = dialogue
            enhanced.append(block_html)
            used.append("dialogue")
            cursor = next_cursor
            continue

        block = blocks[cursor]
        tag = _top_tag(block)

        if tag in {"ul", "ol"}:
            items = _list_items(block)
            parsed_times = [_parse_time_item(_strip_tags(item)) for item in items]
            timeline_entries = [entry for entry in parsed_times if entry]
            if len(items) >= 2 and len(timeline_entries) >= 2 and len(timeline_entries) == len(items):
                enhanced.append(_render_timeline([(time_label, html.escape(content)) for time_label, content in timeline_entries]))
                used.append("timeline")
                cursor += 1
                continue

            parsed_stats = [_parse_stat_item(item) for item in items]
            stat_entries = [entry for entry in parsed_stats if entry]
            if 2 <= len(stat_entries) <= 4 and len(stat_entries) == len(items):
                enhanced.append(_render_stats(stat_entries))
                used.append("stats")
                cursor += 1
                continue

            if tag == "ol" and 2 <= len(items) <= 6:
                average_length = sum(len(_strip_tags(item)) for item in items) / max(len(items), 1)
                if average_length <= 80:
                    enhanced.append(_render_steps(items))
                    used.append("steps")
                    cursor += 1
                    continue

        if tag == "table":
            parsed_table = _extract_table(block)
            if parsed_table:
                header, rows = parsed_table
                enhanced.append(_render_compare(header, rows))
                used.append("compare")
                cursor += 1
                continue

        if tag == "blockquote":
            quote_card = _quote_from_block(block)
            if quote_card:
                enhanced.append(quote_card)
                used.append("quote")
                cursor += 1
                continue

        enhanced.append(block)
        cursor += 1

    enhanced = _apply_layout_plan(enhanced, manifest)
    unique_used = list(dict.fromkeys(used))
    section_modules = list(((manifest or {}).get("layout_plan") or {}).get("section_modules") or [])
    unique_used.extend(
        [
            str(item.get("module_type") or "")
            for item in section_modules
            if str(item.get("module_type") or "") and str(item.get("module_type") or "") not in unique_used
        ]
    )
    return "\n".join(block for block in enhanced if str(block).strip()), unique_used
