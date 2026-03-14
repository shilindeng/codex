from __future__ import annotations

import html

from core.layout import Theme, apply_callout_blocks, sanitize_and_style_for_wechat


def _title_style(theme: Theme, chosen_style: str) -> str:
    base = f"margin:0 0 14px;font-size:28px;line-height:1.35;color:{theme.heading};letter-spacing:0.2px;font-weight:800;"
    if chosen_style == "magazine":
        return f"margin:0 0 14px;font-size:30px;line-height:1.28;color:{theme.heading};letter-spacing:0.2px;font-weight:800;"
    if chosen_style == "poster":
        return f"margin:0 0 14px;font-size:30px;line-height:1.22;color:{theme.heading};letter-spacing:0.3px;font-weight:900;"
    return base


def render_wechat_fragment(
    content_html: str,
    *,
    title: str,
    summary: str,
    theme: Theme,
    accent: str,
    chosen_style: str,
    header_mode: str = "keep",
) -> str:
    """Render a WeChat-compatible HTML fragment with full inline styles."""
    content_html = apply_callout_blocks(content_html)
    styled_body = sanitize_and_style_for_wechat(content_html, theme=theme, accent=accent)

    normalized_header_mode = (header_mode or "keep").strip().lower()
    title_style = _title_style(theme, chosen_style)
    summary_style = (
        f"margin:0 0 20px;padding:12px 14px;border-radius:{theme.radius};"
        f"background:{theme.soft};color:{theme.muted};font-size:14px;line-height:1.8;border:1px solid {theme.line};"
    )
    header_parts: list[str] = []
    if normalized_header_mode == "keep":
        header_parts.append(f'<h1 style="{title_style}">{html.escape(title)}</h1>')
    if normalized_header_mode in {"keep", "drop-title"} and summary.strip():
        header_parts.append(f'<p style="{summary_style}">{html.escape(summary)}</p>')
    header = ""
    if header_parts:
        header = '<section style="margin:0 0 12px;padding:0 0 4px 0;">' + "".join(header_parts) + "</section>"
    outer_style = f"box-sizing:border-box;background:{theme.soft2};padding:18px 12px 28px;"
    inner_style = (
        "box-sizing:border-box;max-width:720px;margin:0 auto;"
        f"background:#ffffff;border:1px solid {theme.line};border-radius:{theme.radius};"
        "padding:16px 14px 28px;"
        "font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
        f"color:{theme.text};"
    )
    return f'<section style="{outer_style}"><section style="{inner_style}">' + header + styled_body + "</section></section>"

