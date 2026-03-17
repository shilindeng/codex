from __future__ import annotations

import argparse
import html
import re
import textwrap
from pathlib import Path
from urllib.parse import urlparse

import legacy_studio as legacy
from core.artifacts import extract_summary, read_json, read_text, split_frontmatter, strip_leading_h1, write_text
from core.layout import (
    DEFAULT_ACCENT_COLOR,
    THEMES,
    apply_callout_blocks,
    analyze_content_signals,
    choose_accent_color,
    choose_layout_style,
    detect_input_format,
    markdown_to_html,
    preview_css,
    sanitize_html_fragment,
)
from core.manifest import ensure_workspace, load_manifest, relative_posix, save_manifest, workspace_path
from core.wechat_fragment import render_wechat_fragment


_TECH_MASK_PREFIX = "__WXMASK"
_TECH_TOKEN_PATTERNS = [
    re.compile(r"(?<!`)(--[a-z0-9][a-z0-9-]*)"),
    re.compile(r"(?<!`)\b([A-Z][A-Z0-9_]{2,})\b"),
    re.compile(r"(?<![`\\w])((?:[A-Za-z]:\\|/)[\w.\-/\\]+)"),
    re.compile(r"(?<![`\\w])((?:/v?\d+)?/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+)"),
    re.compile(r"(?<!`)\b([a-z0-9]+(?:[._/-][a-z0-9]+){1,})\b"),
    re.compile(r"(?<!`)\b([A-Z][a-z0-9]+[A-Z][A-Za-z0-9]+|[a-z]+_[a-z0-9_]+)\b"),
]


def _mask_technical_spans(text: str) -> tuple[str, list[str]]:
    masks: list[str] = []

    def replacer(match: re.Match[str]) -> str:
        token = f"{_TECH_MASK_PREFIX}{len(masks)}__"
        masks.append(match.group(0))
        return token

    masked = re.sub(r"\[\![A-Za-z]+\]|!\[[^\]]*\]\([^)]+\)|\[[^\]]+\]\([^)]+\)|https?://[^\s)]+", replacer, text)
    return masked, masks


def _restore_technical_spans(text: str, masks: list[str]) -> str:
    restored = text
    for index, value in enumerate(masks):
        restored = restored.replace(f"{_TECH_MASK_PREFIX}{index}__", value)
    return restored


def _wrap_technical_tokens(segment: str) -> str:
    updated = segment
    for pattern in _TECH_TOKEN_PATTERNS:
        parts = re.split(r"(`[^`]+`)", updated)
        rebuilt: list[str] = []
        for part in parts:
            if part.startswith("`") and part.endswith("`"):
                rebuilt.append(part)
            else:
                rebuilt.append(pattern.sub(lambda m: f"`{m.group(1)}`", part))
        updated = "".join(rebuilt)
    return updated


def highlight_technical_terms_markdown(body: str) -> str:
    lines = (body or "").splitlines()
    in_code = False
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            output.append(line)
            continue
        if in_code or re.match(r"^\s*\|.*\|\s*$", line) or re.match(r"^\s*\|?[\-: ]+\|[\-|: ]*$", line):
            output.append(line)
            continue
        parts = re.split(r"(`[^`]+`)", line)
        rebuilt: list[str] = []
        for part in parts:
            if not part or (part.startswith("`") and part.endswith("`")):
                rebuilt.append(part)
                continue
            masked, masks = _mask_technical_spans(part)
            rebuilt.append(_restore_technical_spans(_wrap_technical_tokens(masked), masks))
        output.append("".join(rebuilt))
    return "\n".join(output)


def build_reference_cards_html(workspace: Path, manifest: dict[str, Any]) -> str:
    path = workspace / str(manifest.get("references_path") or "references.json")
    if not path.exists():
        return ""
    payload = read_json(path, default={}) or {}
    items = payload.get("items") or []
    if not items:
        return ""
    cards: list[str] = ['<h2>参考资料</h2>']
    for item in items:
        index = int(item.get("index") or 0)
        title = html.escape(str(item.get("title") or "参考资料").strip())
        domain = html.escape(str(item.get("domain") or urlparse(str(item.get("url") or "")).netloc.replace("www.", "")).strip())
        note = html.escape(str(item.get("note") or "").strip())
        url = html.escape(str(item.get("url") or "").strip(), quote=True)
        cards.append(
            '<blockquote data-wx-tone="tip">'
            f'<p><strong>[{index}]</strong> {title}</p>'
            f'<p>{domain}' + (f" · {note}" if note else "") + '</p>'
            + (f'<p><a href="{url}">查看原文</a></p>' if url else "")
            + '</blockquote>'
        )
    return "\n".join(cards)


def normalize_publication_markdown(title: str, body: str) -> str:
    normalized = body or ""
    normalized = re.sub(r"(?m)^(\s*>\s*)?金句\s*\d+\s*[：:]\s*", lambda m: m.group(1) or "", normalized)
    normalized = re.sub(
        r"(?ms)^\s*>\s*\[!(?:TIP|NOTE)\]\s*(?:参考资料|参考来源|参考与延伸).*?(?=^\s*(?:#|$)|\Z)",
        "",
        normalized,
    )
    intro_blocks, sections = legacy.split_sections(normalized)
    sections = [section for section in sections if not legacy.is_reference_heading(section.get("heading", ""))]
    rebuilt = legacy.reconstruct_body(intro_blocks, sections).strip()
    return (rebuilt + "\n") if rebuilt else ""


def cmd_render(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)

    input_rel = args.input or manifest.get("assembled_path") or "assembled.md"
    input_path = workspace / input_rel
    if not input_path.exists():
        input_path = workspace / (manifest.get("article_path") or "article.md")
    if not input_path.exists():
        raise SystemExit(f"找不到待渲染文件：{input_path}")

    raw = read_text(input_path)
    meta, body = split_frontmatter(raw)
    title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名文章"
    body = strip_leading_h1(body, title)

    input_format_arg = getattr(args, "input_format", "auto")
    fmt = detect_input_format(input_path.name, str(input_format_arg), body)
    if fmt == "md":
        body = normalize_publication_markdown(title, body)
        content_source = highlight_technical_terms_markdown(body)
        content_html = markdown_to_html(content_source)
    else:
        content_source = body
        content_html = content_source

    reference_cards_html = build_reference_cards_html(workspace, manifest)
    if reference_cards_html:
        content_html = content_html + "\n" + reference_cards_html

    signals = analyze_content_signals(content_source if fmt == "md" else content_html, fmt)
    layout_style_arg = getattr(args, "layout_style", "auto")
    layout_decision = choose_layout_style(str(layout_style_arg), signals, manifest)
    chosen_style = layout_decision.style

    accent_arg = getattr(args, "accent_color", DEFAULT_ACCENT_COLOR) or DEFAULT_ACCENT_COLOR
    accent_decision = choose_accent_color(chosen_style, str(accent_arg), manifest)

    theme = THEMES.get(chosen_style, THEMES["clean"])

    def plain_text_from_html(value: str) -> str:
        cleaned = re.sub(r"<[^>]+>", " ", value or "")
        cleaned = re.sub(r"\\s+", " ", cleaned).strip()
        return cleaned

    preview_html = apply_callout_blocks(content_html)
    safe_preview_html = sanitize_html_fragment(preview_html)
    summary_source = body if fmt == "md" else plain_text_from_html(safe_preview_html)
    summary = meta.get("summary") or manifest.get("summary") or extract_summary(summary_source)

    skill_dir = Path(__file__).resolve().parents[2]
    assets_dir = skill_dir / "assets"
    base_css = read_text(assets_dir / "wechat-style.css")
    themed_css = base_css + "\n" + preview_css(chosen_style)
    template = read_text(assets_dir / "wechat-template.html")

    theme_class = f"wx-theme-{chosen_style}"
    article_style = f"--accent:{accent_decision.accent};"

    rendered = (
        template.replace("{{title}}", html.escape(title))
        .replace("{{summary}}", html.escape(summary))
        .replace("{{style}}", themed_css)
        .replace("{{theme_class}}", theme_class)
        .replace("{{article_style}}", article_style)
        .replace("{{content}}", textwrap.indent(safe_preview_html, "      ").strip())
    )

    output_path = workspace / (args.output or "article.html")
    write_text(output_path, rendered)

    # WeChat fragment uses full inline styles and a safe tag whitelist.
    wechat_header_mode = str(getattr(args, "wechat_header_mode", "") or manifest.get("wechat_header_mode") or "drop-title")
    wechat_fragment = render_wechat_fragment(
        content_html,
        title=title,
        summary=summary,
        theme=theme,
        accent=accent_decision.accent,
        chosen_style=chosen_style,
        header_mode=wechat_header_mode,
    )

    wechat_output = workspace / (Path(output_path.name).stem + ".wechat.html")
    write_text(wechat_output, wechat_fragment)

    manifest["html_path"] = relative_posix(output_path, workspace)
    manifest["wechat_html_path"] = relative_posix(wechat_output, workspace)
    manifest["layout_style"] = chosen_style
    manifest["layout_style_reason"] = layout_decision.reason
    manifest["accent_color"] = accent_decision.accent
    manifest["accent_color_reason"] = accent_decision.reason
    manifest["render_input_format"] = fmt
    manifest["wechat_header_mode"] = wechat_header_mode
    save_manifest(workspace, manifest)
    print(str(output_path))
    return 0
