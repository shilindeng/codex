from __future__ import annotations

import html
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Iterable


LAYOUT_STYLE_CHOICES = (
    "auto",
    "clean",
    "cards",
    "magazine",
    "business",
    "warm",
    "poster",
    "tech",
    "blueprint",
)

INPUT_FORMAT_CHOICES = ("auto", "md", "html")

DEFAULT_ACCENT_COLOR = "#0F766E"


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _is_hex_color(value: str) -> bool:
    return bool(_HEX_COLOR_RE.match((value or "").strip()))


def _normalize_key(value: str) -> str:
    return (value or "").strip().lower().replace("_", "-")


@dataclass(frozen=True)
class Theme:
    key: str
    label: str
    accent: str
    text: str
    heading: str
    muted: str
    line: str
    soft: str
    soft2: str
    quote_bg: str
    quote_border: str
    code_bg: str
    code_border: str
    pre_bg: str
    pre_text: str
    radius: str
    radius_sm: str


THEMES: dict[str, Theme] = {
    "clean": Theme(
        key="clean",
        label="清爽阅读",
        accent="#0F766E",
        text="#1f2937",
        heading="#111827",
        muted="#6b7280",
        line="#e5e7eb",
        soft="#f8fafc",
        soft2="#f3f7f9",
        quote_bg="#f8fafc",
        quote_border="#e2e8f0",
        code_bg="#f3f4f6",
        code_border="#e5e7eb",
        pre_bg="#111827",
        pre_text="#f9fafb",
        radius="16px",
        radius_sm="10px",
    ),
    "cards": Theme(
        key="cards",
        label="知识卡片",
        accent="#0F766E",
        text="#0f172a",
        heading="#0b1220",
        muted="#64748b",
        line="#e2e8f0",
        soft="#f8fafc",
        soft2="#f1f5f9",
        quote_bg="#ffffff",
        quote_border="#dbeafe",
        code_bg="#eef2ff",
        code_border="#c7d2fe",
        pre_bg="#0b1220",
        pre_text="#e2e8f0",
        radius="18px",
        radius_sm="12px",
    ),
    "magazine": Theme(
        key="magazine",
        label="杂志留白",
        accent="#0F766E",
        text="#111827",
        heading="#0b1220",
        muted="#6b7280",
        line="#e5e7eb",
        soft="#fbfbfd",
        soft2="#f5f5f7",
        quote_bg="#fbfbfd",
        quote_border="#e5e7eb",
        code_bg="#f3f4f6",
        code_border="#e5e7eb",
        pre_bg="#111827",
        pre_text="#f9fafb",
        radius="14px",
        radius_sm="10px",
    ),
    "business": Theme(
        key="business",
        label="商务报告",
        accent="#1d4ed8",
        text="#0f172a",
        heading="#0b1220",
        muted="#475569",
        line="#dbeafe",
        soft="#f8fafc",
        soft2="#eff6ff",
        quote_bg="#eff6ff",
        quote_border="#bfdbfe",
        code_bg="#eef2ff",
        code_border="#c7d2fe",
        pre_bg="#0b1220",
        pre_text="#e2e8f0",
        radius="12px",
        radius_sm="8px",
    ),
    "warm": Theme(
        key="warm",
        label="温暖生活",
        accent="#d97706",
        text="#1f2937",
        heading="#111827",
        muted="#6b7280",
        line="#f1e7d6",
        soft="#fff7ed",
        soft2="#ffedd5",
        quote_bg="#fff7ed",
        quote_border="#fed7aa",
        code_bg="#ffedd5",
        code_border="#fdba74",
        pre_bg="#1f2937",
        pre_text="#fef3c7",
        radius="18px",
        radius_sm="12px",
    ),
    "poster": Theme(
        key="poster",
        label="高对比海报",
        accent="#ef4444",
        text="#0b1220",
        heading="#030712",
        muted="#475569",
        line="#fee2e2",
        soft="#fff1f2",
        soft2="#ffe4e6",
        quote_bg="#fff1f2",
        quote_border="#fecaca",
        code_bg="#ffe4e6",
        code_border="#fecaca",
        pre_bg="#030712",
        pre_text="#f9fafb",
        radius="14px",
        radius_sm="10px",
    ),
    "tech": Theme(
        key="tech",
        label="技术手册",
        accent="#0ea5e9",
        text="#0f172a",
        heading="#0b1220",
        muted="#64748b",
        line="#e2e8f0",
        soft="#f8fafc",
        soft2="#ecfeff",
        quote_bg="#f8fafc",
        quote_border="#cbd5e1",
        code_bg="#f1f5f9",
        code_border="#cbd5e1",
        pre_bg="#0b1220",
        pre_text="#e2e8f0",
        radius="12px",
        radius_sm="8px",
    ),
    "blueprint": Theme(
        key="blueprint",
        label="蓝图理性",
        accent="#2563eb",
        text="#0b1220",
        heading="#0b1220",
        muted="#475569",
        line="#dbeafe",
        soft="#f8fafc",
        soft2="#eff6ff",
        quote_bg="#eff6ff",
        quote_border="#bfdbfe",
        code_bg="#eef2ff",
        code_border="#c7d2fe",
        pre_bg="#0b1220",
        pre_text="#e2e8f0",
        radius="14px",
        radius_sm="10px",
    ),
}


IMAGE_PRESET_TO_LAYOUT_STYLE: dict[str, str] = {
    "notion": "cards",
    "professional-corporate": "business",
    "minimal": "business",
    "bold": "poster",
    "pop": "poster",
    "abstract-geometric": "poster",
    "retro": "magazine",
    "editorial-grain": "magazine",
    "luxury-minimal": "magazine",
    "cute": "warm",
    "warm": "warm",
    "organic-natural": "warm",
    "illustrated-handdrawn": "warm",
    "scientific-blueprint": "blueprint",
    "chalkboard": "blueprint",
}


IMAGE_PRESET_TO_ACCENT: dict[str, str] = {
    "cute": "#ec4899",
    "fresh": "#10b981",
    "warm": "#d97706",
    "bold": "#ef4444",
    "minimal": "#334155",
    "retro": "#9a3412",
    "pop": "#e11d48",
    "notion": "#111827",
    "chalkboard": "#14b8a6",
    "editorial-grain": "#0f766e",
    "organic-natural": "#16a34a",
    "scientific-blueprint": "#2563eb",
    "professional-corporate": "#1d4ed8",
    "abstract-geometric": "#0ea5e9",
    "luxury-minimal": "#a16207",
    "illustrated-handdrawn": "#ea580c",
    "photoreal-sketch": "#475569",
}


_AUDIENCE_BUSINESS_KEYWORDS = ("职场", "运营", "商业", "管理", "企业", "老板", "创业", "B端")
_ARCHETYPE_TO_LAYOUT_STYLE = {
    "commentary": "magazine",
    "tutorial": "tech",
    "case-study": "business",
    "narrative": "warm",
}


def _article_archetype(manifest: dict[str, Any]) -> str:
    blueprint = manifest.get("viral_blueprint") or {}
    if isinstance(blueprint, dict):
        value = _normalize_key(str(blueprint.get("article_archetype") or ""))
        if value:
            return value
    corpus = " ".join(
        [
            str(manifest.get("selected_title") or ""),
            str(manifest.get("summary") or ""),
            str(manifest.get("topic") or ""),
        ]
    )
    scores = {
        "tutorial": len(re.findall(r"教程|指南|手把手|步骤|SOP|模板|上手|实操", corpus)) * 2 + len(re.findall(r"如何|怎么", corpus)),
        "case-study": len(re.findall(r"案例|复盘|拆解|项目|公司|产品", corpus)),
        "narrative": len(re.findall(r"故事|经历|生活|关系|焦虑|情绪|职场", corpus)),
        "commentary": len(re.findall(r"为什么|真相|趋势|信号|机会|风险|拐点|时代|当立|已死|判断", corpus)),
    }
    if scores["tutorial"] >= 3 and scores["tutorial"] > scores["commentary"]:
        return "tutorial"
    if scores["case-study"] >= 2:
        return "case-study"
    if scores["narrative"] >= 2 and scores["narrative"] > scores["commentary"]:
        return "narrative"
    if scores["commentary"] >= 1:
        return "commentary"
    return ""


def detect_input_format(path_name: str, input_format: str, text: str) -> str:
    fmt = _normalize_key(input_format)
    if fmt in {"md", "markdown"}:
        return "md"
    if fmt in {"html", "htm"}:
        return "html"
    # auto
    lower_name = (path_name or "").lower()
    if lower_name.endswith((".html", ".htm")):
        return "html"
    sample = (text or "").lstrip()[:256].lower()
    if sample.startswith("<!doctype") or sample.startswith("<html") or sample.startswith("<body") or sample.startswith("<div") or sample.startswith("<p"):
        return "html"
    return "md"


@dataclass(frozen=True)
class ContentSignals:
    has_code_block: bool
    inline_code_count: int
    has_table: bool
    list_item_count: int
    blockquote_count: int


def analyze_content_signals(text: str, fmt: str) -> ContentSignals:
    raw = text or ""
    if fmt == "html":
        lower = raw.lower()
        has_code_block = "<pre" in lower
        inline_code_count = lower.count("<code")
        has_table = "<table" in lower
        list_item_count = lower.count("<li")
        blockquote_count = lower.count("<blockquote")
        return ContentSignals(
            has_code_block=has_code_block,
            inline_code_count=inline_code_count,
            has_table=has_table,
            list_item_count=list_item_count,
            blockquote_count=blockquote_count,
        )

    # markdown
    has_code_block = "```" in raw
    inline_code_count = len(re.findall(r"`[^`]+`", raw))
    has_table = bool(
        re.search(
            r"^\s*\|?.+\|.+\|?\s*$\n^\s*\|?\s*[-: ]+\|[-|: ]*\s*$",
            raw,
            flags=re.M,
        )
    )
    list_item_count = len(re.findall(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", raw, flags=re.M))
    blockquote_count = len(re.findall(r"^\s*>\s+", raw, flags=re.M))
    return ContentSignals(
        has_code_block=has_code_block,
        inline_code_count=inline_code_count,
        has_table=has_table,
        list_item_count=list_item_count,
        blockquote_count=blockquote_count,
    )


@dataclass(frozen=True)
class LayoutDecision:
    style: str
    reason: str


def choose_layout_style(requested: str, content_signals: ContentSignals, manifest: dict[str, Any]) -> LayoutDecision:
    req = _normalize_key(requested or "auto")
    if req and req != "auto":
        if req not in THEMES:
            return LayoutDecision(style="clean", reason=f"unknown_layout_style={req} -> clean")
        return LayoutDecision(style=req, reason="explicit_layout_style")

    archetype = _article_archetype(manifest)
    # Rule 2: tech override for code-heavy content.
    if content_signals.has_code_block:
        return LayoutDecision(style="tech", reason="code_block_detected -> tech")
    if content_signals.inline_code_count >= 12 and archetype in {"", "tutorial"}:
        return LayoutDecision(style="tech", reason=f"inline_code_count={content_signals.inline_code_count} archetype={archetype or 'none'} -> tech")

    image_controls = manifest.get("image_controls") or {}
    preset = _normalize_key(str(image_controls.get("preset") or ""))
    if not preset:
        preset = _normalize_key(
            str(image_controls.get("preset_cover") or image_controls.get("preset_infographic") or image_controls.get("preset_inline") or "")
        )
    base = IMAGE_PRESET_TO_LAYOUT_STYLE.get(preset, "clean")
    if archetype in _ARCHETYPE_TO_LAYOUT_STYLE:
        base = _ARCHETYPE_TO_LAYOUT_STYLE[archetype]

    if preset in {"editorial-grain", "retro", "luxury-minimal"} and not content_signals.has_table and not content_signals.has_code_block:
        return LayoutDecision(style="magazine", reason=f"editorial_preset={preset} -> magazine")

    audience = str(manifest.get("audience") or "")
    audience_business = any(keyword in audience for keyword in _AUDIENCE_BUSINESS_KEYWORDS)
    if content_signals.has_table:
        boosted = "business"
        return LayoutDecision(
            style=boosted,
            reason=f"boost_business(table={content_signals.has_table}) preset={preset or 'none'} base={base}",
        )

    if audience_business and (preset in {"professional-corporate", "minimal"} or archetype == "case-study"):
        boosted = "business"
        return LayoutDecision(
            style=boosted,
            reason=f"boost_business(audience={audience_business},archetype={archetype or 'none'}) preset={preset or 'none'} base={base}",
        )

    if archetype == "tutorial" and content_signals.list_item_count >= 4:
        return LayoutDecision(style="tech", reason=f"archetype={archetype} list_items={content_signals.list_item_count} -> tech")

    if archetype == "narrative":
        return LayoutDecision(style="warm", reason=f"archetype={archetype} -> warm")

    if archetype == "commentary" and content_signals.blockquote_count >= 1:
        return LayoutDecision(style="magazine", reason=f"archetype={archetype} quote_detected -> magazine")

    if content_signals.list_item_count >= 8 or content_signals.blockquote_count >= 2:
        boosted = "cards"
        return LayoutDecision(
            style=boosted,
            reason=f"boost_cards(list_items={content_signals.list_item_count},quotes={content_signals.blockquote_count}) preset={preset or 'none'} base={base}",
        )

    return LayoutDecision(style=base, reason=f"preset={preset or 'none'} archetype={archetype or 'none'} -> {base}")


@dataclass(frozen=True)
class AccentDecision:
    accent: str
    reason: str


def choose_accent_color(style: str, accent_arg: str, manifest: dict[str, Any]) -> AccentDecision:
    theme = THEMES.get(style, THEMES["clean"])
    accent_arg = (accent_arg or "").strip()
    explicit = _is_hex_color(accent_arg) and accent_arg.lower() != DEFAULT_ACCENT_COLOR.lower()
    if explicit:
        return AccentDecision(accent=accent_arg, reason="explicit_accent_color")

    image_controls = manifest.get("image_controls") or {}
    preset = _normalize_key(str(image_controls.get("preset") or ""))
    if not preset:
        preset = _normalize_key(
            str(image_controls.get("preset_cover") or image_controls.get("preset_infographic") or image_controls.get("preset_inline") or "")
        )
    mapped = IMAGE_PRESET_TO_ACCENT.get(preset, "")
    if _is_hex_color(mapped):
        return AccentDecision(accent=mapped, reason=f"accent_from_image_preset({preset})")
    return AccentDecision(accent=theme.accent, reason=f"accent_from_theme({style})")


def _strip_outer_html_body(text: str) -> str:
    raw = text or ""
    match = re.search(r"<body\b[^>]*>(.*?)</body\s*>", raw, flags=re.I | re.S)
    if match:
        return match.group(1)
    return raw


def markdown_to_html(body: str) -> str:
    # Prefer deterministic no-deps path; keep the optional "markdown" package support if present.
    try:
        import markdown as markdown_module  # type: ignore
    except Exception:
        markdown_module = None

    if markdown_module is not None:
        try:
            return markdown_module.markdown(body, extensions=["extra", "sane_lists", "tables"])
        except Exception:
            # Fall back if the environment has a broken markdown install.
            pass
    return fallback_markdown_to_html(body)


def inline_markdown(text: str) -> str:
    escaped = html.escape(text or "")
    # Inline code first to reduce false positives in later patterns.
    escaped = re.sub(r"`([^`]+)`", lambda m: f"<code>{html.escape(m.group(1))}</code>", escaped)
    escaped = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        lambda m: f'<img src="{html.escape(m.group(2), quote=True)}" alt="{html.escape(m.group(1), quote=True)}" />',
        escaped,
    )
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        escaped,
    )
    escaped = re.sub(
        r"(?P<url>https?://[^\s<]+)",
        lambda m: f'<a href="{html.escape(m.group("url"), quote=True)}">{html.escape(m.group("url"))}</a>',
        escaped,
    )
    return escaped


def fallback_markdown_to_html(body: str) -> str:
    lines = (body or "").splitlines()
    out: list[str] = []
    in_code = False
    code_lines: list[str] = []
    code_lang: str = ""
    paragraph: list[str] = []
    list_mode: str | None = None
    list_buffer: list[str] = []
    quote_buffer: list[str] = []
    table_buffer: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append(f"<p>{inline_markdown(' '.join(paragraph).strip())}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_buffer, list_mode
        if list_buffer and list_mode:
            tag = "ul" if list_mode == "ul" else "ol"
            out.append(f"<{tag}>" + "".join(f"<li>{inline_markdown(item)}</li>" for item in list_buffer) + f"</{tag}>")
        list_buffer = []
        list_mode = None

    def flush_quote() -> None:
        nonlocal quote_buffer
        if quote_buffer:
            out.append(f"<blockquote>{''.join(f'<p>{inline_markdown(item)}</p>' for item in quote_buffer)}</blockquote>")
        quote_buffer = []

    def flush_table() -> None:
        nonlocal table_buffer
        if len(table_buffer) >= 2 and re.match(r"^\|?\s*[-: ]+\|", table_buffer[1]):
            headers = [cell.strip() for cell in table_buffer[0].strip("|").split("|")]
            body_rows = table_buffer[2:]
            html_rows = ["<table><thead><tr>" + "".join(f"<th>{inline_markdown(cell)}</th>" for cell in headers) + "</tr></thead><tbody>"]
            for row in body_rows:
                cells = [cell.strip() for cell in row.strip("|").split("|")]
                html_rows.append("<tr>" + "".join(f"<td>{inline_markdown(cell)}</td>" for cell in cells) + "</tr>")
            html_rows.append("</tbody></table>")
            out.append("".join(html_rows))
        else:
            for row in table_buffer:
                paragraph.append(row)
        table_buffer = []

    def append_list_item(content: str) -> None:
        nonlocal list_buffer
        stripped = content.strip()
        task = re.match(r"^\[(?P<mark>[ xX])\]\s+(?P<rest>.+)$", stripped)
        if task:
            mark = task.group("mark")
            box = "☑" if mark.strip().lower() == "x" else "□"
            stripped = f"{box} {task.group('rest').strip()}"
        list_buffer.append(stripped)

    for line in lines + [""]:
        fence = re.match(r"^```\s*(?P<lang>[A-Za-z0-9_+-]+)?\s*$", line.strip())
        if fence:
            flush_paragraph()
            flush_list()
            flush_quote()
            flush_table()
            if in_code:
                code_html = html.escape("\n".join(code_lines))
                attrs = f' data-lang="{html.escape(code_lang, quote=True)}"' if code_lang else ""
                out.append(f"<pre{attrs}><code{attrs}>{code_html}</code></pre>")
                code_lines = []
                code_lang = ""
                in_code = False
            else:
                in_code = True
                code_lang = (fence.group("lang") or "").strip().lower()
            continue
        if in_code:
            code_lines.append(line)
            continue

        # Table detection: treat pipe rows as table candidates.
        if "|" in line and line.strip():
            # Only capture contiguous table blocks; conservative to avoid false positives.
            if re.match(r"^\s*\|?.*\|.*\|?\s*$", line):
                flush_paragraph()
                flush_list()
                flush_quote()
                table_buffer.append(line)
                continue
        if table_buffer:
            flush_table()

        match_heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match_heading:
            flush_paragraph()
            flush_list()
            flush_quote()
            level = len(match_heading.group(1))
            # Keep WeChat heading hierarchy compact: map h1->h2, clamp >4 to h4.
            mapped = 2 if level <= 2 else (3 if level == 3 else 4)
            out.append(f"<h{mapped}>{inline_markdown(match_heading.group(2))}</h{mapped}>")
            continue

        if re.match(r"^-{3,}\s*$", line.strip()):
            flush_paragraph()
            flush_list()
            flush_quote()
            out.append("<hr />")
            continue

        match_image_line = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", line.strip())
        if match_image_line:
            flush_paragraph()
            flush_list()
            flush_quote()
            out.append(
                f'<p><img src="{html.escape(match_image_line.group(2), quote=True)}" alt="{html.escape(match_image_line.group(1), quote=True)}" /></p>'
            )
            continue

        match_ul = re.match(r"^[-*+]\s+(.+)$", line)
        if match_ul:
            flush_paragraph()
            flush_quote()
            if list_mode not in {None, "ul"}:
                flush_list()
            list_mode = "ul"
            append_list_item(match_ul.group(1))
            continue

        match_ol = re.match(r"^\d+[.)]\s+(.+)$", line)
        if match_ol:
            flush_paragraph()
            flush_quote()
            if list_mode not in {None, "ol"}:
                flush_list()
            list_mode = "ol"
            append_list_item(match_ol.group(1))
            continue

        match_quote = re.match(r"^>\s+(.+)$", line)
        if match_quote:
            flush_paragraph()
            flush_list()
            quote_buffer.append(match_quote.group(1).strip())
            continue

        if not line.strip():
            flush_paragraph()
            flush_list()
            flush_quote()
            continue

        paragraph.append(line.strip())

    return "\n".join(out)


_VOID_TAGS = {"img", "br", "hr"}
_DROP_TAGS = {"script", "style", "iframe", "object", "embed", "link", "meta"}

_TAG_MAP = {
    "h1": "h2",
    "h5": "h4",
    "h6": "h4",
    "b": "strong",
    "i": "em",
    "s": "del",
    "strike": "del",
}

_ALLOWED_TAGS = {
    "p",
    "br",
    "hr",
    "h2",
    "h3",
    "h4",
    "ul",
    "ol",
    "li",
    "blockquote",
    "pre",
    "code",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "img",
    "a",
    "strong",
    "em",
    "del",
    "sup",
    "sub",
}


_CALLOUT_TAG_MAP = {
    "TIP": "tip",
    "NOTE": "tip",
    "TAKEAWAY": "takeaway",
    "IMPORTANT": "takeaway",
    "WARNING": "warning",
    "CAUTION": "warning",
    "CHECKLIST": "checklist",
    "MYTHFACT": "mythfact",
}

_CALLOUT_LABELS = {
    "tip": "提示",
    "takeaway": "结论",
    "warning": "注意",
    "checklist": "清单",
    "mythfact": "误区/真相",
}

_BLOCKQUOTE_RE = re.compile(r"(?is)<blockquote(?P<attrs>[^>]*)>(?P<inner>.*?)</blockquote>")


def apply_callout_blocks(text: str) -> str:
    """Convert markdown-style callouts into styled blockquotes.

    Supported markers (case-insensitive) in the first <p> of a <blockquote>:
    - [!TIP], [!TAKEAWAY], [!WARNING], [!CHECKLIST], [!MYTHFACT]
    """
    raw = text or ""

    def replacer(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        inner = match.group("inner") or ""
        first = re.match(r"(?is)\s*<p>\s*\[!\s*(?P<tag>[A-Za-z]+)\s*\]\s*(?P<title>.*?)\s*</p>(?P<rest>.*)\Z", inner)
        if not first:
            return match.group(0)
        tag = (first.group("tag") or "").strip().upper()
        tone = _CALLOUT_TAG_MAP.get(tag)
        if not tone:
            return match.group(0)
        label = _CALLOUT_LABELS.get(tone, "提示")
        title_html = (first.group("title") or "").strip()
        rest = first.group("rest") or ""
        header = f"<p><strong>{html.escape(label)}</strong>"
        if title_html:
            header += " " + title_html
        header += "</p>"
        new_attrs = attrs
        if not re.search(r"(?i)\bdata-wx-tone\s*=", attrs):
            new_attrs = (attrs + f' data-wx-tone="{tone}"') if attrs.strip() else f' data-wx-tone="{tone}"'
        return f"<blockquote{new_attrs}>{header}{rest}</blockquote>"

    return _BLOCKQUOTE_RE.sub(replacer, raw)


def sanitize_html_fragment(text: str) -> str:
    parser = _Sanitizer(mode="sanitize")
    parser.feed(_strip_outer_html_body(text))
    parser.close()
    return parser.output()


def sanitize_and_style_for_wechat(text: str, theme: Theme, accent: str) -> str:
    parser = _Sanitizer(mode="wechat", theme=theme, accent=accent)
    parser.feed(_strip_outer_html_body(text))
    parser.close()
    return parser.output()


class _Sanitizer(HTMLParser):
    def __init__(self, mode: str, theme: Theme | None = None, accent: str = "") -> None:
        super().__init__(convert_charrefs=True)
        self._mode = mode
        self._theme = theme or THEMES["clean"]
        self._accent = accent or self._theme.accent
        self._out: list[str] = []
        self._stack: list[str | None] = []
        self._skip_depth = 0

    def output(self) -> str:
        return "".join(self._out)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth:
            self._skip_depth += 1
            return
        raw = tag.lower()
        if raw in _DROP_TAGS:
            self._skip_depth = 1
            return

        tag_name = _TAG_MAP.get(raw, raw)
        if tag_name not in _ALLOWED_TAGS:
            return

        attr_map = self._sanitize_attrs(tag_name, attrs)
        if self._mode == "wechat":
            style = self._style_for_tag(tag_name, attr_map)
            if style:
                attr_map["style"] = style
            # tone is only for internal styling; do not output it in WeChat HTML
            attr_map.pop("data-wx-tone", None)
        if tag_name in _VOID_TAGS:
            self._out.append("<" + tag_name + self._format_attrs(attr_map) + " />")
            return

        self._stack.append(tag_name)
        self._out.append("<" + tag_name + self._format_attrs(attr_map) + ">")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # HTMLParser uses this for self-closing tags; treat them as void.
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if self._skip_depth:
            self._skip_depth -= 1
            return
        raw = tag.lower()
        tag_name = _TAG_MAP.get(raw, raw)
        if tag_name in _VOID_TAGS:
            return
        if not self._stack:
            return
        # Pop until we find a matching tag; close any nested tags on the way.
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index] == tag_name:
                while len(self._stack) - 1 >= index:
                    closing = self._stack.pop()
                    self._out.append(f"</{closing}>")
                return
        # If the end tag doesn't match anything we opened, ignore it.

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self._out.append(html.escape(data or ""))

    def handle_comment(self, data: str) -> None:
        # Strip comments in all modes.
        return

    def _sanitize_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        keep: dict[str, str] = {}
        raw = {k.lower(): (v or "") for k, v in attrs}
        if tag == "a":
            href = raw.get("href", "").strip()
            if href and not href.lower().startswith(("javascript:", "vbscript:", "data:")):
                keep["href"] = href
        elif tag == "img":
            for key in ("src", "data-src", "alt"):
                value = raw.get(key, "").strip()
                if value:
                    keep[key] = value
        elif tag in {"pre", "code"}:
            lang = (raw.get("data-lang") or "").strip()
            if not lang:
                # Common patterns from markdown renderers.
                klass = (raw.get("class") or "").strip().lower()
                match = re.search(r"(?:language|lang)-([a-z0-9_+-]+)", klass)
                if match:
                    lang = match.group(1)
            if lang:
                keep["data-lang"] = lang
        elif tag == "blockquote":
            tone = (raw.get("data-wx-tone") or "").strip().lower()
            if tone in {"tip", "takeaway", "warning", "checklist", "mythfact"}:
                keep["data-wx-tone"] = tone
        return keep

    def _format_attrs(self, attrs: dict[str, str]) -> str:
        if not attrs:
            return ""
        parts = []
        for key, value in attrs.items():
            parts.append(f' {key}="{html.escape(value, quote=True)}"')
        return "".join(parts)

    def _theme_heading_style(self, level: str) -> str:
        t = self._theme
        base = f"color:{t.heading};font-weight:800;line-height:1.45;"
        if self._theme.key == "magazine":
            if level == "h2":
                return base + "margin:40px 0 16px;font-size:24px;letter-spacing:0.28px;border-bottom:1px solid #e8dbc8;padding-bottom:10px;"
            if level == "h3":
                return base + "margin:30px 0 12px;font-size:19px;color:#3f3328;"
            return base + "margin:22px 0 8px;font-size:17px;"
        if self._theme.key == "poster":
            if level == "h2":
                return base + f"margin:34px 0 14px;font-size:22px;padding:10px 12px;border-radius:{t.radius_sm};background:{t.soft2};border:1px solid {t.line};"
            if level == "h3":
                return base + "margin:26px 0 10px;font-size:18px;"
            return base + "margin:22px 0 8px;font-size:17px;"
        if self._theme.key == "business":
            if level == "h2":
                return base + f"margin:36px 0 16px;font-size:22px;padding:8px 0 8px 12px;border-left:5px solid {self._accent};background:linear-gradient(90deg, rgba(29,78,216,0.08), rgba(29,78,216,0));"
            if level == "h3":
                return base + "margin:28px 0 12px;font-size:18px;color:#18355f;"
            return base + "margin:22px 0 8px;font-size:17px;"
        if self._theme.key == "cards":
            if level == "h2":
                return base + f"margin:34px 0 14px;font-size:22px;padding:10px 12px;border-radius:{t.radius_sm};background:{t.soft};border:1px solid {t.line};"
            if level == "h3":
                return base + "margin:26px 0 10px;font-size:18px;"
            return base + "margin:22px 0 8px;font-size:17px;"
        if self._theme.key == "warm":
            if level == "h2":
                return base + f"margin:36px 0 16px;font-size:22px;padding:8px 0 8px 12px;border-left:5px solid {self._accent};background:linear-gradient(90deg, rgba(217,119,6,0.10), rgba(217,119,6,0));"
            if level == "h3":
                return base + "margin:28px 0 12px;font-size:18px;color:#7c4d12;"
            return base + "margin:22px 0 8px;font-size:17px;"
        if self._theme.key == "blueprint":
            if level == "h2":
                return base + f"margin:36px 0 16px;font-size:22px;padding-left:12px;border-left:5px solid {self._accent};background:{t.soft2};padding-top:8px;padding-bottom:8px;"
            if level == "h3":
                return base + "margin:28px 0 12px;font-size:18px;color:#21406e;"
            return base + "margin:22px 0 8px;font-size:17px;"
        if self._theme.key == "tech":
            if level == "h2":
                return base + f"margin:36px 0 16px;font-size:22px;padding:8px 0 8px 12px;border-left:5px solid {self._accent};background:linear-gradient(90deg, rgba(14,165,233,0.09), rgba(14,165,233,0));"
            if level == "h3":
                return base + "margin:28px 0 12px;font-size:18px;color:#11657f;"
            return base + "margin:22px 0 8px;font-size:17px;"
        # clean default
        if level == "h2":
            return base + f"margin:34px 0 14px;font-size:22px;padding-left:10px;border-left:3px solid {self._accent};"
        if level == "h3":
            return base + "margin:26px 0 10px;font-size:18px;"
        return base + "margin:22px 0 8px;font-size:17px;"

    def _style_for_tag(self, tag: str, attrs: dict[str, str]) -> str:
        t = self._theme
        if tag == "p":
            return f"margin:15px 0;line-height:1.92;font-size:16px;color:{t.text};letter-spacing:0.08px;"
        if tag in {"h2", "h3", "h4"}:
            return self._theme_heading_style(tag)
        if tag == "ul":
            return f"margin:16px 0;padding-left:22px;color:{t.text};"
        if tag == "ol":
            return f"margin:16px 0;padding-left:22px;color:{t.text};"
        if tag == "li":
            return "margin:8px 0;line-height:1.9;"
        if tag == "blockquote":
            tone = (attrs.get("data-wx-tone") or "").strip().lower()
            bg = t.quote_bg
            border = t.quote_border
            if tone == "takeaway":
                bg = t.soft2
                border = t.line
            elif tone == "warning":
                bg = "#fff7ed"
                border = "#fed7aa"
            elif tone == "checklist":
                bg = "#f0fdf4"
                border = "#bbf7d0"
            elif tone == "mythfact":
                bg = "#fdf2f8"
                border = "#fbcfe8"
            base = (
                f"margin:18px 0;padding:16px 18px;border-radius:{t.radius};"
                f"background:{bg};border:1px solid {border};color:{t.text};"
                "box-shadow:0 8px 24px rgba(15,23,42,0.04);"
            )
            if tone:
                base += f"border-left:4px solid {self._accent};"
            if t.key == "magazine":
                base += "box-shadow:none;"
            if t.key in {"business", "tech", "blueprint"}:
                base += "box-shadow:0 10px 24px rgba(15,23,42,0.05);"
            return base
        if tag == "a":
            return f"color:{self._accent};text-decoration:none;border-bottom:1px solid rgba(15,23,42,0.12);"
        if tag == "strong":
            return f"color:{t.heading};font-weight:800;"
        if tag == "em":
            return "font-style:italic;"
        if tag == "del":
            return "text-decoration:line-through;opacity:0.75;"
        if tag == "hr":
            return f"border:none;border-top:1px solid {t.line};margin:30px 0;"
        if tag == "img":
            # Add vertical rhythm directly on img to avoid relying on wrappers.
            shadow = "0 10px 30px rgba(15,23,42,0.06)"
            radius = t.radius
            if t.key in {"business", "tech"}:
                shadow = "0 8px 22px rgba(15,23,42,0.05)"
                radius = t.radius_sm
            if t.key == "magazine":
                shadow = "0 14px 28px rgba(90,72,38,0.08)"
            if t.key == "warm":
                shadow = "0 12px 26px rgba(180,120,40,0.10)"
            return (
                "display:block;width:100%;height:auto;margin:22px auto 18px;"
                f"border-radius:{radius};box-shadow:{shadow};"
            )
        if tag == "code":
            # Inside <pre>, keep code transparent.
            parent = next((item for item in reversed(self._stack) if item), "")
            if parent == "pre":
                return "padding:0;background:transparent;color:inherit;font-family:Cascadia Code,Consolas,monospace;font-size:0.92em;"
            return (
                f"padding:2px 6px;border-radius:{t.radius_sm};background:{t.code_bg};"
                f"border:1px solid {t.code_border};"
                "font-family:Cascadia Code,Consolas,monospace;font-size:0.92em;"
                "word-break:break-word;"
            )
        if tag == "pre":
            return (
                "overflow-x:auto;max-width:100%;"
                f"margin:18px 0;padding:14px 16px;border-radius:{t.radius};"
                f"background:{t.pre_bg};color:{t.pre_text};"
                "box-shadow:0 10px 30px rgba(15,23,42,0.06);"
            )
        if tag == "table":
            return (
                "width:100%;border-collapse:collapse;font-size:14px;margin:16px 0;"
                f"border-radius:{t.radius};overflow:hidden;"
            )
        if tag == "th":
            return f"padding:10px 12px;border:1px solid {t.line};background:{t.soft};text-align:left;vertical-align:top;color:{t.heading};"
        if tag == "td":
            return f"padding:10px 12px;border:1px solid {t.line};text-align:left;vertical-align:top;color:{t.text};"
        if tag == "sup":
            return f"color:{self._accent};font-size:12px;font-weight:800;vertical-align:super;"
        if tag == "sub":
            return f"color:{t.muted};font-size:12px;vertical-align:sub;"
        if tag == "br":
            return ""
        return ""


def preview_css(style: str) -> str:
    """Return CSS var overrides for preview page (article.html)."""
    theme = THEMES.get(style, THEMES["clean"])
    # Use CSS variables to keep theme changes compact and consistent with WeChat inline styles.
    return (
        f"body.wx-theme-{style},.wx-article.wx-theme-{style}{{"
        f"--accent:{theme.accent};--text:{theme.text};--heading:{theme.heading};--muted:{theme.muted};"
        f"--line:{theme.line};--soft:{theme.soft};--soft-2:{theme.soft2};"
        f"--code-bg:{theme.code_bg};--code-border:{theme.code_border};"
        f"--pre-bg:{theme.pre_bg};--pre-text:{theme.pre_text};"
        f"--quote-bg:{theme.quote_bg};--quote-border:{theme.quote_border};"
        f"--radius:{theme.radius};--radius-sm:{theme.radius_sm};"
        "}"
    )
