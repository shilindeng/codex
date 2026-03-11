from __future__ import annotations

import argparse
import html
import re
import textwrap
from pathlib import Path

from core.artifacts import extract_summary, read_text, split_frontmatter, strip_leading_h1, write_text
from core.layout import (
    DEFAULT_ACCENT_COLOR,
    THEMES,
    analyze_content_signals,
    choose_accent_color,
    choose_layout_style,
    detect_input_format,
    markdown_to_html,
    preview_css,
    sanitize_and_style_for_wechat,
    sanitize_html_fragment,
)
from core.manifest import ensure_workspace, load_manifest, relative_posix, save_manifest, workspace_path


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
        content_source = body
        content_html = markdown_to_html(content_source)
    else:
        content_source = body
        content_html = content_source

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

    safe_preview_html = sanitize_html_fragment(content_html)
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
    styled_body = sanitize_and_style_for_wechat(content_html, theme=theme, accent=accent_decision.accent)
    title_style = f"margin:0 0 14px;font-size:28px;line-height:1.35;color:{theme.heading};letter-spacing:0.2px;font-weight:800;"
    if chosen_style == "magazine":
        title_style = f"margin:0 0 14px;font-size:30px;line-height:1.28;color:{theme.heading};letter-spacing:0.2px;font-weight:800;"
    if chosen_style == "poster":
        title_style = f"margin:0 0 14px;font-size:30px;line-height:1.22;color:{theme.heading};letter-spacing:0.3px;font-weight:900;"
    summary_style = (
        f"margin:0 0 20px;padding:12px 14px;border-radius:{theme.radius};"
        f"background:{theme.soft};color:{theme.muted};font-size:14px;line-height:1.8;border:1px solid {theme.line};"
    )
    header = (
        '<section style="margin:0 0 12px;padding:0 0 4px 0;">'
        f'<h1 style="{title_style}">{html.escape(title)}</h1>'
        f'<p style="{summary_style}">{html.escape(summary)}</p>'
        "</section>"
    )
    wechat_outer_style = f"box-sizing:border-box;background:{theme.soft2};padding:18px 12px 28px;"
    wechat_inner_style = (
        "box-sizing:border-box;max-width:720px;margin:0 auto;"
        f"background:#ffffff;border:1px solid {theme.line};border-radius:{theme.radius};"
        "padding:16px 14px 28px;"
        "font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
        f"color:{theme.text};"
    )
    wechat_fragment = (
        f'<section style="{wechat_outer_style}">'
        f'<section style="{wechat_inner_style}">'
        + header
        + styled_body
        + "</section></section>"
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
    save_manifest(workspace, manifest)
    print(str(output_path))
    return 0
