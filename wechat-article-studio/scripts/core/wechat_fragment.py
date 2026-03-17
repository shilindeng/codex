from __future__ import annotations

import html

from core.layout import Theme, apply_callout_blocks, sanitize_and_style_for_wechat


def _title_style(theme: Theme, chosen_style: str) -> str:
    base = f"margin:0 0 14px;font-size:28px;line-height:1.35;color:{theme.heading};letter-spacing:0.2px;font-weight:800;"
    if chosen_style == "magazine":
        return f"margin:0 0 14px;font-size:31px;line-height:1.24;color:{theme.heading};letter-spacing:0.28px;font-weight:800;"
    if chosen_style == "poster":
        return f"margin:0 0 14px;font-size:30px;line-height:1.22;color:{theme.heading};letter-spacing:0.3px;font-weight:900;"
    if chosen_style == "business":
        return f"margin:0 0 14px;font-size:30px;line-height:1.24;color:{theme.heading};letter-spacing:0.18px;font-weight:850;"
    return base


def _summary_style(theme: Theme, chosen_style: str) -> str:
    if chosen_style == "magazine":
        return (
            f"margin:0 0 20px;padding:14px 16px;border-radius:{theme.radius};"
            "background:#faf1e2;color:#756251;font-size:14px;line-height:1.9;"
            "border:1px solid #eadfce;"
        )
    if chosen_style in {"business", "blueprint"}:
        return (
            f"margin:0 0 20px;padding:14px 16px;border-radius:{theme.radius};"
            f"background:{theme.soft2};color:{theme.muted};font-size:14px;line-height:1.9;"
            f"border:1px solid {theme.line};"
        )
    if chosen_style == "warm":
        return (
            f"margin:0 0 20px;padding:14px 16px;border-radius:{theme.radius};"
            "background:#fff4e4;color:#7b6243;font-size:14px;line-height:1.9;"
            "border:1px solid #f2dfc1;"
        )
    return (
        f"margin:0 0 20px;padding:12px 14px;border-radius:{theme.radius};"
        f"background:{theme.soft};color:{theme.muted};font-size:14px;line-height:1.8;border:1px solid {theme.line};"
    )


def _container_styles(theme: Theme, chosen_style: str, accent: str) -> tuple[str, str, str]:
    outer = f"box-sizing:border-box;background:{theme.soft2};padding:18px 12px 28px;"
    inner = (
        "box-sizing:border-box;max-width:760px;margin:0 auto;"
        f"background:#ffffff;border:1px solid {theme.line};border-radius:{theme.radius};"
        "padding:18px 16px 30px;"
        "font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
        f"color:{theme.text};box-shadow:0 14px 40px rgba(15,23,42,0.06);"
    )
    header = f"margin:0 0 18px;padding:0 0 18px;border-bottom:1px solid {theme.line};"
    if chosen_style == "magazine":
        outer = "box-sizing:border-box;background:linear-gradient(180deg,#f5efe6 0%,#efe7da 100%);padding:20px 12px 32px;"
        inner = (
            "box-sizing:border-box;max-width:760px;margin:0 auto;"
            "background:#fffdf8;border:1px solid #eadfce;border-radius:16px;"
            "padding:22px 18px 34px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            "color:#111827;box-shadow:0 20px 46px rgba(90,72,38,0.08);"
        )
        header = "margin:0 0 22px;padding:0 0 18px;border-bottom:1px solid #eadfce;"
    elif chosen_style == "business":
        outer = "box-sizing:border-box;background:linear-gradient(180deg,#edf4ff 0%,#f7fbff 100%);padding:20px 12px 32px;"
        inner = (
            f"box-sizing:border-box;max-width:760px;margin:0 auto;background:#ffffff;border:1px solid #d7e5fb;border-radius:{theme.radius};"
            "padding:22px 18px 34px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            "color:#0f172a;box-shadow:0 18px 44px rgba(29,78,216,0.09);"
        )
        header = "margin:0 0 22px;padding:0 0 18px;border-bottom:1px solid #d7e5fb;"
    elif chosen_style == "warm":
        outer = "box-sizing:border-box;background:linear-gradient(180deg,#fff5ea 0%,#fff0df 100%);padding:20px 12px 32px;"
        inner = (
            "box-sizing:border-box;max-width:760px;margin:0 auto;background:#fffdf8;border:1px solid #f2dfc1;border-radius:18px;"
            "padding:22px 18px 34px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            "color:#1f2937;box-shadow:0 18px 42px rgba(180,120,40,0.09);"
        )
        header = "margin:0 0 22px;padding:0 0 18px;border-bottom:1px solid #f2dfc1;"
    elif chosen_style == "tech":
        outer = "box-sizing:border-box;background:linear-gradient(180deg,#edfafe 0%,#f7fbff 100%);padding:20px 12px 32px;"
        inner = (
            "box-sizing:border-box;max-width:760px;margin:0 auto;background:#fbfeff;border:1px solid #cfe7f2;border-radius:12px;"
            "padding:22px 18px 34px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            "color:#0f172a;box-shadow:0 18px 42px rgba(14,165,233,0.08);"
        )
        header = "margin:0 0 22px;padding:0 0 18px;border-bottom:1px solid #cfe7f2;"
    elif chosen_style == "blueprint":
        outer = "box-sizing:border-box;background:#eef5ff;padding:20px 12px 32px;"
        inner = (
            "box-sizing:border-box;max-width:760px;margin:0 auto;background:rgba(255,255,255,0.96);border:1px solid #d2e3ff;border-radius:14px;"
            "padding:22px 18px 34px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            "color:#0b1220;box-shadow:0 18px 44px rgba(37,99,235,0.08);"
        )
        header = "margin:0 0 22px;padding:0 0 18px;border-bottom:1px solid #d2e3ff;"
    return outer, inner, header


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
    summary_style = _summary_style(theme, chosen_style)
    outer_style, inner_style, header_shell_style = _container_styles(theme, chosen_style, accent)
    header_parts: list[str] = []
    if normalized_header_mode == "keep":
        header_parts.append(f'<h1 style="{title_style}">{html.escape(title)}</h1>')
    if normalized_header_mode in {"keep", "drop-title"} and summary.strip():
        header_parts.append(f'<p style="{summary_style}">{html.escape(summary)}</p>')
    header = ""
    if header_parts:
        header = f'<section style="{header_shell_style}">' + "".join(header_parts) + "</section>"
    return f'<section style="{outer_style}"><section style="{inner_style}">' + header + styled_body + "</section></section>"

