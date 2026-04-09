from __future__ import annotations

import html
import re

from core.layout import THEMES, Theme, apply_callout_blocks, sanitize_and_style_for_wechat


def _plain_text(value: str) -> str:
    cleaned = re.sub(r"<[^>]+>", " ", value or "")
    return re.sub(r"\s+", " ", cleaned).strip()


def _hero_strap(summary: str, lead_text: str, hero_module: str) -> str:
    lead = _plain_text(lead_text)
    summary_text = _plain_text(summary)
    candidate = lead if hero_module == "hero-scene" and lead else summary_text or lead
    if not candidate:
        return ""
    candidate = re.split(r"[。！？!?]", candidate, maxsplit=1)[0].strip() or candidate
    candidate = candidate.strip("“”\"")
    if len(candidate) > 54:
        candidate = re.split(r"[，,:：；;]", candidate, maxsplit=1)[0].strip() or candidate[:54]
    if len(candidate) > 60:
        candidate = candidate[:60].rstrip("，,:：；; ") + "…"
    return candidate


def build_header_module_html(
    *,
    title: str,
    summary: str,
    hero_module: str,
    archetype: str,
    lead_text: str = "",
    show_summary: bool = True,
) -> str:
    normalized_hero = (hero_module or "hero-judgment").strip().lower()
    normalized_archetype = (archetype or "commentary").strip().lower()
    kicker_map = {
        "commentary": "深度观察",
        "tutorial": "实操卡点",
        "case-study": "案例拆解",
        "narrative": "场景观察",
        "comparison": "对比判断",
    }
    kicker = kicker_map.get(normalized_archetype, "内容编排")
    strap = _hero_strap(summary, lead_text, normalized_hero) if show_summary else ""
    parts = [f'<section class="wx-header wx-hero" data-wx-role="{html.escape(normalized_hero, quote=True)}">']
    parts.append(f'<p class="wx-hero-kicker" data-wx-role="hero-kicker">{html.escape(kicker)}</p>')
    parts.append(f'<p class="wx-hero-title" data-wx-role="hero-title">{html.escape(title)}</p>')
    if strap:
        parts.append(f'<p class="wx-hero-strap" data-wx-role="hero-strap">{html.escape(strap)}</p>')
    parts.append("</section>")
    return "".join(parts)


def _title_style(theme: Theme, chosen_style: str) -> str:
    mode = _normalize_publication_style(chosen_style)
    base = f"margin:0 0 14px;font-size:28px;line-height:1.35;color:{theme.heading};letter-spacing:0.2px;font-weight:800;"
    if mode in {"business", "blueprint", "wechat-briefing"}:
        return f"margin:0 0 12px;font-size:29px;line-height:1.26;color:{theme.heading};letter-spacing:0.08px;font-weight:850;"
    if mode in {"tech", "wechat-tech"}:
        return f"margin:0 0 12px;font-size:28px;line-height:1.28;color:{theme.heading};letter-spacing:0.04px;font-weight:820;"
    if mode in {"magazine", "poster"}:
        return f"margin:0 0 12px;font-size:30px;line-height:1.22;color:{theme.heading};letter-spacing:0.12px;font-weight:880;"
    if mode in {"warm", "wechat-warm"}:
        return f"margin:0 0 12px;font-size:29px;line-height:1.25;color:{theme.heading};letter-spacing:0.06px;font-weight:840;"
    return f"margin:0 0 12px;font-size:30px;line-height:1.24;color:{theme.heading};letter-spacing:0.08px;font-weight:850;"


def _summary_style(theme: Theme, chosen_style: str) -> str:
    mode = _normalize_publication_style(chosen_style)
    bg = theme.soft
    border = theme.line
    color = theme.muted
    if mode == "magazine":
        bg = "#faf4ea"
        border = "#eadfce"
        color = "#756251"
    elif mode in {"business", "blueprint", "wechat-briefing"}:
        bg = theme.soft2
        border = theme.line
        color = "#425a78"
    elif mode in {"warm", "wechat-warm"}:
        bg = "#fff7ef"
        border = "#f0dcc2"
        color = "#7a6347"
    return (
        f"margin:0 0 18px;padding:10px 12px;border-radius:{theme.radius_sm};"
        f"background:{bg};color:{color};font-size:14px;line-height:1.8;border:1px solid {border};"
    )


def _container_styles(theme: Theme, chosen_style: str, accent: str) -> tuple[str, str, str]:
    mode = _normalize_publication_style(chosen_style)
    outer = "box-sizing:border-box;background:#f6f7f8;padding:12px 8px 22px;"
    inner = (
        "box-sizing:border-box;max-width:760px;margin:0 auto;"
        f"background:#ffffff;border:1px solid {theme.line};border-radius:12px;"
        "padding:18px 16px 24px;"
        "font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
        f"color:{theme.text};box-shadow:0 4px 14px rgba(15,23,42,0.03);"
    )
    header = f"margin:0 0 14px;padding:0 0 14px;border-bottom:1px solid {theme.line};"
    if mode in {"business", "blueprint", "wechat-briefing"}:
        outer = "box-sizing:border-box;background:#f5f8fc;padding:12px 8px 22px;"
        inner = (
            "box-sizing:border-box;max-width:760px;margin:0 auto;"
            f"background:#ffffff;border:1px solid {theme.line};border-radius:10px;"
            "padding:18px 16px 24px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            f"color:{theme.text};box-shadow:0 4px 14px rgba(29,78,216,0.04);"
        )
    elif mode in {"tech", "wechat-tech"}:
        outer = "box-sizing:border-box;background:#f4f8fa;padding:12px 8px 22px;"
        inner = (
            "box-sizing:border-box;max-width:760px;margin:0 auto;"
            f"background:#ffffff;border:1px solid {theme.line};border-radius:10px;"
            "padding:18px 16px 24px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            f"color:{theme.text};box-shadow:0 4px 14px rgba(14,165,233,0.04);"
        )
    elif mode == "magazine":
        outer = "box-sizing:border-box;background:#f7f4ef;padding:12px 8px 22px;"
        inner = (
            "box-sizing:border-box;max-width:760px;margin:0 auto;"
            "background:#fffdf9;border:1px solid #eadfce;border-radius:10px;"
            "padding:18px 16px 24px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            "color:#111827;box-shadow:0 4px 14px rgba(90,72,38,0.04);"
        )
        header = "margin:0 0 14px;padding:0 0 14px;border-bottom:1px solid #eadfce;"
    elif mode in {"warm", "wechat-warm"}:
        outer = "box-sizing:border-box;background:#faf4ea;padding:12px 8px 22px;"
        inner = (
            "box-sizing:border-box;max-width:760px;margin:0 auto;"
            "background:#fffdf8;border:1px solid #f0dcc2;border-radius:10px;"
            "padding:18px 16px 24px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            "color:#1f2937;box-shadow:0 4px 14px rgba(180,120,40,0.04);"
        )
        header = "margin:0 0 14px;padding:0 0 14px;border-bottom:1px solid #f0dcc2;"
    elif mode == "poster":
        outer = "box-sizing:border-box;background:#fff5f5;padding:12px 8px 22px;"
        inner = (
            "box-sizing:border-box;max-width:760px;margin:0 auto;"
            "background:#ffffff;border:1px solid #f3d0d0;border-radius:10px;"
            "padding:18px 16px 24px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            f"color:{theme.text};box-shadow:0 4px 14px rgba(239,68,68,0.04);"
        )
        header = "margin:0 0 14px;padding:0 0 14px;border-bottom:1px solid #f3d0d0;"
    elif mode == "cards":
        outer = "box-sizing:border-box;background:#f4f7f9;padding:12px 8px 22px;"
        inner = (
            "box-sizing:border-box;max-width:760px;margin:0 auto;"
            f"background:#ffffff;border:1px solid {theme.line};border-radius:12px;"
            "padding:18px 16px 24px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;"
            f"color:{theme.text};box-shadow:0 4px 14px rgba(15,23,42,0.03);"
        )
    return outer, inner, header


def _normalize_publication_style(style: str) -> str:
    normalized = (style or "").strip().lower()
    aliases = {
        "wechat-clean": "clean",
        "wechat-briefing": "business",
        "wechat-tech": "tech",
        "editorial-clean": "clean",
        "warm-journal": "warm",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in THEMES:
        return normalized
    return "wechat-clean"


def choose_wechat_publication_style(
    chosen_style: str,
    manifest: dict[str, Any],
    *,
    rich_blocks: list[str] | None = None,
    publication_report: dict[str, Any] | None = None,
) -> str:
    report = publication_report or {}
    normalized_chosen = _normalize_publication_style(chosen_style)
    explicit_publication_preference = str(manifest.get("wechat_publication_style_preference") or "").strip().lower()
    if explicit_publication_preference and explicit_publication_preference not in {"", "auto"}:
        normalized_preference = _normalize_publication_style(explicit_publication_preference)
        if normalized_preference in WECHAT_PUBLICATION_STYLES:
            return normalized_preference
    if normalized_chosen in WECHAT_PUBLICATION_STYLES:
        return normalized_chosen
    suggested = _normalize_publication_style(str(report.get("suggested_wechat_style") or manifest.get("publication_style") or "").strip().lower())
    if suggested in WECHAT_PUBLICATION_STYLES:
        return suggested
    blocks = {str(item or "").strip().lower() for item in (rich_blocks or []) if str(item or "").strip()}
    archetype = str((manifest.get("viral_blueprint") or {}).get("article_archetype") or manifest.get("article_archetype") or "").strip().lower()
    audience = str(manifest.get("audience") or "")
    if "steps" in blocks or report.get("code_block_count"):
        return "tech"
    if "compare" in blocks or "stats" in blocks:
        return "business"
    if archetype in {"narrative"}:
        return "warm"
    if archetype in {"case-study", "comparison"} or any(word in audience for word in ["企业", "商业", "老板", "管理", "运营", "银行", "金融"]):
        return "business"
    return "clean"


WECHAT_PUBLICATION_STYLES = set(THEMES.keys()) | {"wechat-clean", "wechat-briefing", "wechat-tech"}


def render_wechat_fragment(
    content_html: str,
    *,
    title: str,
    summary: str,
    theme: Theme,
    accent: str,
    chosen_style: str,
    skin_key: str = "elegant",
    header_mode: str = "keep",
    hero_module: str = "hero-judgment",
    layout_archetype: str = "commentary",
    lead_text: str = "",
) -> str:
    """Render a WeChat-compatible HTML fragment with full inline styles."""
    publication_style = _normalize_publication_style(chosen_style)
    content_html = apply_callout_blocks(content_html)
    styled_body = sanitize_and_style_for_wechat(content_html, theme=theme, accent=accent, skin_key=skin_key)

    normalized_header_mode = (header_mode or "keep").strip().lower()
    outer_style, inner_style, header_shell_style = _container_styles(theme, publication_style, accent)
    header = ""
    if normalized_header_mode in {"keep", "drop-title", "drop-title-summary"}:
        header_html = build_header_module_html(
            title=title,
            summary=summary,
            hero_module=hero_module,
            archetype=layout_archetype,
            lead_text=lead_text,
            show_summary=normalized_header_mode != "drop-title-summary",
        )
        header = sanitize_and_style_for_wechat(header_html, theme=theme, accent=accent, skin_key=skin_key)
    else:
        title_style = _title_style(theme, publication_style)
        summary_style = _summary_style(theme, publication_style)
        header_parts: list[str] = [f'<h1 style="{title_style}">{html.escape(title)}</h1>']
        if normalized_header_mode != "drop-title-summary" and summary.strip():
            header_parts.append(f'<p style="{summary_style}">{html.escape(summary)}</p>')
        header = f'<section style="{header_shell_style}">' + "".join(header_parts) + "</section>"
    return f'<section style="{outer_style}"><section style="{inner_style}">' + header + styled_body + "</section></section>"

