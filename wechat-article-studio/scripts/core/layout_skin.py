from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class LayoutSkin:
    key: str
    label: str
    accent: str
    secondary: str
    group: str


@dataclass(frozen=True)
class LayoutSkinDecision:
    key: str
    reason: str


SKINS: dict[str, LayoutSkin] = {
    "elegant": LayoutSkin("elegant", "素雅书卷", "#7ea8b8", "#d7e7ec", "classic"),
    "business": LayoutSkin("business", "商务克制", "#2b5ea7", "#d9e4f5", "classic"),
    "warm": LayoutSkin("warm", "文艺温暖", "#c47d5a", "#f1d6c5", "classic"),
    "sunrise": LayoutSkin("sunrise", "清晨日光", "#e8913a", "#f7d7ab", "classic"),
    "tech": LayoutSkin("tech", "科技极简", "#0ea5e9", "#7dd3fc", "professional"),
    "chinese": LayoutSkin("chinese", "国风雅韵", "#b5453a", "#8b7355", "professional"),
    "magazine": LayoutSkin("magazine", "潮流杂志", "#ff4757", "#ffc312", "professional"),
    "forest": LayoutSkin("forest", "知性墨绿", "#2d6a4f", "#7aa18a", "professional"),
    "aurora": LayoutSkin("aurora", "星雾时野", "#0891b2", "#7c3aed", "creative"),
    "morandi": LayoutSkin("morandi", "莫兰迪灰", "#b8a9a0", "#d9ccc4", "creative"),
    "mint": LayoutSkin("mint", "薄荷清新", "#10b981", "#6ee7b7", "creative"),
    "neon": LayoutSkin("neon", "电子玫瑰", "#ec4899", "#8b5cf6", "creative"),
}
LAYOUT_SKIN_CHOICES = ("auto",) + tuple(SKINS.keys())

_PRESET_SKIN_HINTS = {
    "editorial-grain": ("magazine", "elegant"),
    "retro": ("magazine", "morandi"),
    "luxury-minimal": ("elegant", "morandi"),
    "professional-corporate": ("business", "aurora"),
    "minimal": ("business", "morandi"),
    "notion": ("mint", "morandi"),
    "warm": ("warm", "forest"),
    "organic-natural": ("forest", "warm"),
    "illustrated-handdrawn": ("warm", "chinese"),
    "bold": ("sunrise", "neon"),
    "pop": ("neon", "sunrise"),
    "abstract-geometric": ("aurora", "neon"),
    "scientific-blueprint": ("aurora", "tech"),
    "chalkboard": ("tech", "business"),
    "fresh": ("mint", "elegant"),
}

_AUDIENCE_BUSINESS_KEYWORDS = (
    "企业",
    "商业",
    "老板",
    "创业",
    "管理",
    "组织",
    "效率",
    "增长",
    "运营",
    "品牌",
    "银行",
    "金融",
    "b端",
    "b2b",
    "to b",
    "to-b",
)
_COMPARISON_HINTS = (
    "对比",
    "比较",
    "差异",
    "竞争",
    "拐点",
    "趋势",
    "判断",
    "谁会",
    "窗口",
    "signal",
    "signals",
    "vs",
)
_PRACTICAL_HINTS = (
    "教程",
    "指南",
    "步骤",
    "方法",
    "流程",
    "清单",
    "上手",
    "实操",
    "模板",
    "避坑",
    "sop",
    "playbook",
)
_NARRATIVE_HINTS = (
    "故事",
    "人物",
    "一线",
    "现场",
    "经历",
    "记录",
    "那一天",
    "我在",
    "对话",
    "采访",
)
_EDITORIAL_HINTS = (
    "观察",
    "评论",
    "为什么",
    "背后",
    "信号",
    "启示",
    "真问题",
    "怎么看",
    "深聊",
)
_CALM_EDITORIAL_HINTS = (
    "复盘",
    "拆解",
    "回看",
    "边界",
    "误判",
    "冷静",
    "长期",
    "耐心",
)
_CULTURAL_HINTS = (
    "国风",
    "东方",
    "审美",
    "历史",
    "古典",
    "文化",
    "山水",
    "诗意",
)
_DATA_HINTS = (
    "数据",
    "图表",
    "样本",
    "指标",
    "测算",
    "财报",
    "统计",
    "percent",
    "benchmark",
)
_HERO_MODULE_HINTS = {
    "hero-compare": "comparison",
    "hero-checkpoint": "practical",
    "hero-scene": "narrative",
    "hero-judgment": "editorial",
}
_STRUCTURE_MODULE_HINTS = {
    "boundary-card": "comparison",
    "compare-grid": "comparison",
    "checklist": "practical",
    "action-list": "practical",
    "scene-open": "narrative",
    "quote-wall": "editorial",
    "summary-close": "editorial",
}


def get_skin(key: str) -> LayoutSkin:
    normalized = (key or "").strip().lower()
    return SKINS.get(normalized, SKINS["elegant"])


def normalize_layout_skin_request(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in LAYOUT_SKIN_CHOICES else "auto"


def choose_layout_skin(
    requested: str,
    chosen_style: str,
    manifest: dict[str, Any],
    content_signals: Any,
    *,
    rich_blocks: Iterable[str] = (),
) -> LayoutSkinDecision:
    req = normalize_layout_skin_request(requested)
    if req != "auto" and req in SKINS:
        return LayoutSkinDecision(key=req, reason="explicit_layout_skin")

    layout_plan = manifest.get("layout_plan") or {}
    archetype = str(
        layout_plan.get("layout_archetype") or (manifest.get("viral_blueprint") or {}).get("article_archetype") or ""
    ).strip().lower()
    normalized_rich_blocks = {str(item or "").strip().lower() for item in rich_blocks if str(item or "").strip()}
    image_controls = manifest.get("image_controls") or {}
    preset = str(
        image_controls.get("preset") or image_controls.get("preset_cover") or image_controls.get("preset_inline") or ""
    ).strip().lower()
    text_blob = _manifest_hint_blob(manifest)
    blockquote_count = int(getattr(content_signals, "blockquote_count", 0) or 0)
    list_item_count = int(getattr(content_signals, "list_item_count", 0) or 0)
    has_table = bool(getattr(content_signals, "has_table", False))
    has_code_block = bool(getattr(content_signals, "has_code_block", False))
    hero_module = str(layout_plan.get("hero_module") or "").strip().lower()
    structure_modules = {
        str(item or "").strip().lower() for item in (layout_plan.get("module_types") or []) if str(item or "").strip()
    }
    structure_hints = {_STRUCTURE_MODULE_HINTS.get(item) for item in structure_modules}
    audience_business = _contains_any(str(manifest.get("audience") or ""), _AUDIENCE_BUSINESS_KEYWORDS)
    comparison_like = (
        bool(normalized_rich_blocks.intersection({"compare", "timeline"}))
        or archetype == "comparison"
        or _HERO_MODULE_HINTS.get(hero_module) == "comparison"
        or "comparison" in structure_hints
        or _contains_any(text_blob, _COMPARISON_HINTS)
    )
    practical_like = (
        "steps" in normalized_rich_blocks
        or archetype == "tutorial"
        or _HERO_MODULE_HINTS.get(hero_module) == "practical"
        or "practical" in structure_hints
        or has_code_block
        or list_item_count >= 6
        or _contains_any(text_blob, _PRACTICAL_HINTS)
    )
    narrative_like = (
        "dialogue" in normalized_rich_blocks
        or archetype == "narrative"
        or _HERO_MODULE_HINTS.get(hero_module) == "narrative"
        or "narrative" in structure_hints
        or _contains_any(text_blob, _NARRATIVE_HINTS)
    )
    editorial_like = (
        ("quote" in normalized_rich_blocks and chosen_style == "magazine")
        or (archetype == "commentary" and blockquote_count >= 1)
        or _HERO_MODULE_HINTS.get(hero_module) == "editorial"
        or "editorial" in structure_hints
        or _contains_any(text_blob, _EDITORIAL_HINTS)
    )
    calm_editorial = _contains_any(text_blob, _CALM_EDITORIAL_HINTS)
    cultural_like = _contains_any(text_blob, _CULTURAL_HINTS)
    data_like = has_table or "stats" in normalized_rich_blocks or _contains_any(text_blob, _DATA_HINTS)

    if blockquote_count >= 2 and not has_table and not practical_like:
        if narrative_like or cultural_like:
            return LayoutSkinDecision(key="chinese", reason="quote_heavy_narrative_content")
        if calm_editorial:
            return LayoutSkinDecision(key="morandi", reason="quote_heavy_calm_editorial")
        return LayoutSkinDecision(key="magazine", reason="quote_heavy_editorial_content")

    if comparison_like:
        if has_table or audience_business or chosen_style == "business":
            return LayoutSkinDecision(key="business", reason="comparison_business_content")
        if chosen_style == "warm" or narrative_like:
            return LayoutSkinDecision(key="morandi", reason="comparison_story_content")
        return LayoutSkinDecision(key="aurora", reason="comparison_content")

    if practical_like:
        if audience_business and (data_like or chosen_style == "business"):
            return LayoutSkinDecision(key="business", reason="tutorial_business_content")
        if chosen_style in {"tech", "business", "blueprint"} or has_code_block:
            return LayoutSkinDecision(key="tech", reason="tutorial_content")
        return LayoutSkinDecision(key="mint", reason="tutorial_checklist_content")

    if narrative_like:
        if cultural_like or blockquote_count >= 2:
            return LayoutSkinDecision(key="chinese", reason="narrative_cultural_content")
        return LayoutSkinDecision(key="warm", reason="narrative_content")

    if data_like:
        if audience_business or archetype == "case-study":
            return LayoutSkinDecision(key="business", reason="data_business_content")
        return LayoutSkinDecision(key="aurora", reason="data_content")

    if editorial_like:
        if calm_editorial and blockquote_count >= 2:
            return LayoutSkinDecision(key="morandi", reason="calm_editorial_content")
        return LayoutSkinDecision(key="magazine", reason="editorial_content")

    if archetype == "case-study":
        return LayoutSkinDecision(key="business", reason="case_study_archetype")

    if list_item_count >= 8:
        return LayoutSkinDecision(key="mint", reason="dense_list_content")

    if preset in _PRESET_SKIN_HINTS:
        primary, secondary = _PRESET_SKIN_HINTS[preset]
        hinted = secondary if calm_editorial and secondary in SKINS else primary
        return LayoutSkinDecision(key=hinted, reason=f"image_preset({preset})")

    if cultural_like:
        return LayoutSkinDecision(key="chinese", reason="cultural_content")

    style_defaults = {
        "clean": "elegant",
        "editorial-clean": "elegant",
        "cards": "mint",
        "magazine": "magazine",
        "business": "business",
        "warm": "warm",
        "warm-journal": "warm",
        "poster": "sunrise",
        "tech": "tech",
        "blueprint": "aurora",
    }
    return LayoutSkinDecision(key=style_defaults.get(chosen_style, "elegant"), reason=f"layout_style({chosen_style})")


def _manifest_hint_blob(manifest: dict[str, Any]) -> str:
    layout_plan = manifest.get("layout_plan") or {}
    viral_blueprint = manifest.get("viral_blueprint") or {}
    parts = [
        manifest.get("selected_title"),
        manifest.get("summary"),
        manifest.get("topic"),
        manifest.get("angle"),
        manifest.get("direction"),
        manifest.get("audience"),
        layout_plan.get("hero_module"),
        layout_plan.get("layout_archetype"),
        viral_blueprint.get("article_angle"),
        viral_blueprint.get("article_archetype"),
    ]
    joined = " ".join(str(item or "") for item in parts if str(item or "").strip())
    return re.sub(r"\s+", " ", joined).strip().lower()


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    haystack = (text or "").lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def preview_skin_css(skin_key: str, theme: Any, accent: str) -> str:
    skin = get_skin(skin_key)
    secondary = skin.secondary or accent
    theme_class = f'[data-wx-skin="{skin.key}"]'
    return (
        f'.wx-article{theme_class} .wx-hero{{{_hero_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-hero-kicker{{{_hero_kicker_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-hero-title{{{_hero_title_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-hero-strap{{{_hero_strap_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content h2{{{_h2_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content h3{{{_h3_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content blockquote{{{_blockquote_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content hr{{{_hr_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content ul{{{_ul_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content ol{{{_ol_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content li{{{_li_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content table{{{_table_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content th{{{_th_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content td{{{_td_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="compare-header"]{{{_compare_header_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="compare-row"]{{{_compare_row_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="compare-head-left"],.wx-article{theme_class} .wx-content [data-wx-role="compare-head-right"]{{{_compare_head_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="compare-left"]{{{_compare_left_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="compare-right"]{{{_compare_right_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="quote-card"]{{{_quote_card_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="quote-mark"]{{{_quote_mark_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="quote-text"]{{{_quote_text_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="quote-author"]{{{_quote_author_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="stat-card"]{{{_stat_card_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="stat-value"]{{{_stat_value_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="stat-label"]{{{_stat_label_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="reference-card"]{{{_reference_card_css(skin.key, theme, accent, secondary)}}}'
        f'.wx-article{theme_class} .wx-content [data-wx-role="reference-link"]{{{_reference_link_css(skin.key, theme, accent, secondary)}}}'
    )


def role_style_override(skin_key: str, tag: str, role: str, theme: Any, accent: str) -> str | None:
    skin = get_skin(skin_key)
    secondary = skin.secondary or accent
    if tag == "section" and role in {"hero-judgment", "hero-scene", "hero-checkpoint", "hero-compare"}:
        return _hero_css(skin.key, theme, accent, secondary)
    if tag == "p" and role == "hero-kicker":
        return _hero_kicker_css(skin.key, theme, accent, secondary)
    if tag == "p" and role == "hero-title":
        return _hero_title_css(skin.key, theme, accent, secondary)
    if tag == "p" and role == "hero-strap":
        return _hero_strap_css(skin.key, theme, accent, secondary)
    if tag in {"h2", "h3", "h4"} and role in {"section-break", "section-label"}:
        return _h2_css(skin.key, theme, accent, secondary) if tag == "h2" else _h3_css(skin.key, theme, accent, secondary)
    if tag == "section" and role == "compare-header":
        return _compare_header_css(skin.key, theme, accent, secondary)
    if tag == "section" and role == "compare-row":
        return _compare_row_css(skin.key, theme, accent, secondary)
    if tag == "span" and role in {"compare-head-left", "compare-head-right"}:
        return _compare_head_css(skin.key, theme, accent, secondary)
    if tag == "span" and role == "compare-left":
        return _compare_left_css(skin.key, theme, accent, secondary)
    if tag == "span" and role == "compare-right":
        return _compare_right_css(skin.key, theme, accent, secondary)
    if tag == "section" and role == "quote-card":
        return _quote_card_css(skin.key, theme, accent, secondary)
    if tag == "p" and role == "quote-mark":
        return _quote_mark_css(skin.key, theme, accent, secondary)
    if tag == "p" and role == "quote-text":
        return _quote_text_css(skin.key, theme, accent, secondary)
    if tag == "p" and role == "quote-author":
        return _quote_author_css(skin.key, theme, accent, secondary)
    if tag == "section" and role == "stat-card":
        return _stat_card_css(skin.key, theme, accent, secondary)
    if tag == "p" and role == "stat-value":
        return _stat_value_css(skin.key, theme, accent, secondary)
    if tag == "p" and role == "stat-label":
        return _stat_label_css(skin.key, theme, accent, secondary)
    if tag == "section" and role == "reference-card":
        return _reference_card_css(skin.key, theme, accent, secondary)
    if tag == "a" and role == "reference-link":
        return _reference_link_css(skin.key, theme, accent, secondary)
    return None


def tag_style_override(skin_key: str, tag: str, attrs: dict[str, str], theme: Any, accent: str) -> str | None:
    skin = get_skin(skin_key)
    secondary = skin.secondary or accent
    if tag == "blockquote":
        return _blockquote_css(skin.key, theme, accent, secondary)
    if tag == "hr":
        return _hr_css(skin.key, theme, accent, secondary)
    if tag == "ul":
        return _ul_css(skin.key, theme, accent, secondary)
    if tag == "ol":
        return _ol_css(skin.key, theme, accent, secondary)
    if tag == "li":
        return _li_css(skin.key, theme, accent, secondary)
    if tag == "table":
        return _table_css(skin.key, theme, accent, secondary)
    if tag == "th":
        return _th_css(skin.key, theme, accent, secondary)
    if tag == "td":
        return _td_css(skin.key, theme, accent, secondary)
    return None


def _hero_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    mapping = {
        "elegant": f"margin:0 0 26px;padding:18px 20px;border-left:4px solid {accent};background:{theme.soft};border-radius:{theme.radius};border-top:none;border-right:none;border-bottom:none;box-shadow:none;",
        "business": f"margin:0 0 26px;padding:18px 18px 20px;border-left:4px solid {accent};border-bottom:1px solid {theme.line};background:#ffffff;border-radius:0;box-shadow:none;",
        "warm": f"margin:0 0 26px;padding:18px 18px 20px;border-top:1px solid {accent};border-bottom:1px solid {accent};background:{theme.soft};border-left:none;border-right:none;text-align:center;box-shadow:none;",
        "sunrise": f"margin:0 0 26px;padding:18px 20px;border-left:5px solid {accent};background:{theme.soft2};border-radius:{theme.radius};border-top:none;border-right:none;border-bottom:none;box-shadow:none;",
        "tech": f"margin:0 0 24px;padding:18px 18px 18px;border-bottom:2px solid {accent};background:#ffffff;border-left:none;border-right:none;border-top:none;border-radius:0;box-shadow:none;",
        "chinese": f"margin:0 0 26px;padding:18px 18px 20px;border-top:1px solid {secondary};border-bottom:1px solid {secondary};background:#ffffff;text-align:center;border-left:none;border-right:none;box-shadow:none;",
        "magazine": f"margin:0 0 24px;padding:0 0 18px;background:transparent;border:none;box-shadow:none;",
        "forest": f"margin:0 0 26px;padding:18px 20px;border-left:5px solid {accent};background:{theme.soft};border-radius:{theme.radius};border-top:none;border-right:none;border-bottom:none;box-shadow:none;",
        "aurora": f"margin:0 0 26px;padding:18px 18px 20px;border-bottom:2px solid {accent};box-shadow:inset 0 -5px 0 {secondary};background:#ffffff;border-top:none;border-left:none;border-right:none;border-radius:0;",
        "morandi": f"margin:0 0 26px;padding:18px 18px 20px;border-top:1px solid {theme.line};border-bottom:1px solid {theme.line};background:#ffffff;text-align:center;border-left:none;border-right:none;box-shadow:none;",
        "mint": f"margin:0 0 26px;padding:18px 18px 20px;border-bottom:2px solid {theme.soft2};background:#ffffff;border-left:none;border-right:none;border-top:none;border-radius:0;box-shadow:none;",
        "neon": f"margin:0 0 26px;padding:18px 18px 20px;border-bottom:2px solid {accent};box-shadow:inset 0 -5px 0 {secondary};background:#ffffff;border-top:none;border-left:none;border-right:none;border-radius:0;",
    }
    return mapping[key]


def _hero_kicker_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    center = "text-align:center;" if key in {"warm", "chinese", "morandi"} else ""
    letter = "0.32em" if key == "chinese" else "0.18em"
    color = accent if key not in {"magazine", "neon"} else (secondary if key == "magazine" else accent)
    return f"margin:0 0 8px;color:{color};font-size:12px;line-height:1.4;font-weight:900;letter-spacing:{letter};text-transform:uppercase;{center}"


def _hero_title_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    center = "text-align:center;" if key in {"warm", "chinese", "morandi"} else ""
    size = "20px" if key == "magazine" else "30px"
    weight = "900"
    color = accent if key == "neon" else theme.heading
    spacing = "4px" if key == "chinese" else ("1px" if key in {"magazine", "aurora"} else "0.04em")
    return f"margin:0;color:{color};font-size:{size};line-height:1.3;font-weight:{weight};letter-spacing:{spacing};{center}"


def _hero_strap_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    center = "text-align:center;" if key in {"warm", "chinese", "morandi"} else ""
    color = theme.text if key not in {"magazine", "neon"} else (theme.muted if key == "magazine" else secondary)
    return f"margin:12px 0 0;color:{color};font-size:16px;line-height:1.9;font-weight:700;{center}"


def _h2_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    mapping = {
        "elegant": f"margin:36px 0 20px;background:{theme.soft};border-left:4px solid {accent};padding:12px 18px;font-size:17px;font-weight:700;color:{theme.heading};line-height:1.6;letter-spacing:1px;",
        "business": f"margin:36px 0 20px;border-bottom:1px solid {theme.line};border-left:3px solid {accent};padding:0 0 12px 16px;font-size:17px;font-weight:700;color:{theme.heading};line-height:1.6;",
        "warm": f"margin:40px 0 20px;text-align:center;border-top:1px solid {accent};border-bottom:1px solid {accent};padding:16px 0;font-size:17px;font-weight:700;color:{accent};line-height:1.6;letter-spacing:3px;",
        "sunrise": f"margin:36px 0 20px;background:{theme.soft2};border-left:5px solid {accent};padding:12px 18px;font-size:17px;font-weight:700;color:{theme.heading};line-height:1.6;letter-spacing:1px;",
        "tech": f"margin:36px 0 20px;padding-bottom:10px;border-bottom:2px solid {accent};font-size:17px;font-weight:700;color:{theme.heading};line-height:1.6;",
        "chinese": f"margin:40px 0 20px;text-align:center;border-top:1px solid {secondary};border-bottom:1px solid {secondary};padding:16px 0;font-size:17px;font-weight:700;color:{theme.heading};line-height:1.6;letter-spacing:4px;",
        "magazine": f"margin:36px 0 20px;padding:0 0 8px;border-bottom:4px solid {accent};font-size:20px;font-weight:900;color:{theme.heading};line-height:1.4;letter-spacing:1px;",
        "forest": f"margin:36px 0 20px;background:{theme.soft};border-left:5px solid {accent};padding:12px 18px;font-size:17px;font-weight:700;color:{theme.heading};line-height:1.6;letter-spacing:1px;",
        "aurora": f"margin:36px 0 20px;padding:0 0 10px;border-bottom:2px solid {accent};box-shadow:inset 0 -5px 0 {secondary};font-size:17px;font-weight:700;color:{theme.heading};line-height:1.6;letter-spacing:1px;",
        "morandi": f"margin:36px 0 20px;text-align:center;border-top:1px solid {theme.line};border-bottom:1px solid {theme.line};padding:14px 0;font-size:16px;font-weight:600;color:{theme.heading};line-height:1.6;letter-spacing:2px;",
        "mint": f"margin:36px 0 20px;padding-bottom:10px;border-bottom:2px solid {theme.soft2};font-size:16px;font-weight:700;color:{theme.heading};line-height:1.6;",
        "neon": f"margin:36px 0 20px;padding:0 0 10px;border-bottom:2px solid {accent};box-shadow:inset 0 -5px 0 {secondary};font-size:17px;font-weight:700;color:{accent};line-height:1.6;letter-spacing:1px;",
    }
    return mapping[key]


def _h3_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    center = "text-align:center;" if key in {"warm", "chinese", "morandi"} else ""
    color = accent if key in {"warm", "neon"} else theme.heading
    return f"margin:28px 0 14px;font-size:15px;font-weight:700;color:{color};line-height:1.6;letter-spacing:1px;{center}"


def _blockquote_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    mapping = {
        "elegant": f"margin:24px 0;padding:18px 20px 18px 22px;background:{theme.soft};border-left:4px solid {accent};border-top:none;border-right:none;border-bottom:none;border-radius:0;color:{theme.text};box-shadow:none;",
        "business": f"margin:24px 0;padding:18px 22px;background:{theme.soft2};border-left:3px solid {accent};border-top:none;border-right:none;border-bottom:none;border-radius:0;color:{theme.text};box-shadow:none;",
        "warm": f"margin:24px 0;padding:18px 22px;background:{theme.soft};border-left:3px solid {accent};border-top:none;border-right:none;border-bottom:none;border-radius:0;color:{theme.text};box-shadow:none;",
        "sunrise": f"margin:24px 0;padding:18px 22px;background:{theme.soft2};border-left:4px solid {accent};border-top:none;border-right:none;border-bottom:none;border-radius:0;color:{theme.text};box-shadow:none;",
        "tech": f"margin:24px 0;padding:16px 20px;background:{theme.soft};border-left:3px solid {accent};border-top:none;border-right:none;border-bottom:none;border-radius:0;color:{theme.text};box-shadow:none;",
        "chinese": f"margin:24px 0;padding:18px 22px;background:{theme.soft};border-left:3px solid {accent};border-top:none;border-right:none;border-bottom:none;border-radius:0;color:{theme.text};box-shadow:none;",
        "magazine": f"margin:28px 0;padding:18px 0;border-top:3px solid #000;border-bottom:3px solid #000;border-left:none;border-right:none;border-radius:0;background:transparent;color:{accent};box-shadow:none;font-weight:700;",
        "forest": f"margin:24px 0;padding:18px 22px;background:{theme.soft};border-left:4px solid {accent};border-top:none;border-right:none;border-bottom:none;border-radius:0;color:{theme.text};box-shadow:none;",
        "aurora": f"margin:24px 0;padding:18px 22px;background:{theme.soft};border-left:3px solid {accent};border-right:3px solid {secondary};border-top:none;border-bottom:none;border-radius:0;color:{theme.text};box-shadow:none;",
        "morandi": f"margin:28px 0;padding:16px 0;border-top:1px solid {theme.line};border-bottom:1px solid {theme.line};border-left:none;border-right:none;border-radius:0;background:transparent;color:{theme.muted};box-shadow:none;text-align:center;font-style:italic;",
        "mint": f"margin:24px 0;padding:16px 20px;background:{theme.soft};border-left:4px solid {accent};border-top:none;border-right:none;border-bottom:none;border-radius:0;color:{theme.text};box-shadow:none;",
        "neon": f"margin:24px 0;padding:18px 22px;background:{theme.soft};border-left:3px solid {accent};border-right:3px solid {secondary};border-top:none;border-bottom:none;border-radius:0;color:{theme.text};box-shadow:none;",
    }
    return mapping[key]


def _hr_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    mapping = {
        "elegant": f"border:none;border-top:1px solid {accent};width:48px;margin:32px auto;",
        "business": f"border:none;border-top:2px solid {accent};width:48px;margin:36px auto;",
        "warm": f"border:none;border-top:1px dashed {accent};width:56px;margin:36px auto;",
        "sunrise": f"border:none;border-top:1px dashed {accent};width:56px;margin:32px auto;",
        "tech": f"border:none;border-top:1px dashed {theme.line};margin:36px 0;",
        "chinese": f"border:none;border-top:1px solid {secondary};width:72px;margin:36px auto;",
        "magazine": "border:none;border-top:4px solid #000;width:48px;margin:36px 0;",
        "forest": f"border:none;border-top:1px dashed {accent};width:60px;margin:32px auto;",
        "aurora": f"border:none;border-top:2px solid {accent};box-shadow:inset 0 -3px 0 {secondary};margin:32px 0;",
        "morandi": f"border:none;border-top:1px solid {theme.line};width:48px;margin:32px auto;opacity:0.6;",
        "mint": f"border:none;border-top:1px dotted {accent};width:54px;margin:32px auto;",
        "neon": f"border:none;border-top:2px solid {accent};box-shadow:inset 0 -3px 0 {secondary};margin:32px 0;",
    }
    return mapping[key]


def _ul_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    list_style = "square" if key in {"magazine", "tech"} else "disc"
    return f"margin:0 0 24px;padding-left:22px;color:{theme.text};list-style-type:{list_style};"


def _ol_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    list_style = "decimal-leading-zero" if key in {"business", "tech", "aurora"} else "decimal"
    return f"margin:0 0 24px;padding-left:22px;color:{theme.text};list-style-type:{list_style};"


def _li_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    return f"margin:8px 0;line-height:2;color:{theme.text};"


def _table_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    mapping = {
        "elegant": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border:1px solid {theme.line};border-radius:{theme.radius};overflow:hidden;background:#ffffff;box-shadow:none;",
        "business": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border:1px solid {theme.line};border-radius:0;overflow:hidden;background:#ffffff;box-shadow:none;",
        "warm": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border:1px solid {theme.line};border-radius:{theme.radius};overflow:hidden;background:#fffdf8;box-shadow:none;",
        "sunrise": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border:1px solid {theme.line};border-radius:{theme.radius};overflow:hidden;background:#ffffff;box-shadow:none;",
        "tech": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border:1px solid {theme.line};border-radius:10px;overflow:hidden;background:#f8fcff;box-shadow:none;",
        "chinese": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border-top:1px solid {secondary};border-bottom:1px solid {secondary};background:#ffffff;box-shadow:none;",
        "magazine": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:20px 0;border-top:2px solid {accent};border-bottom:2px solid #000;background:#ffffff;box-shadow:none;",
        "forest": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border:1px solid {theme.line};border-radius:{theme.radius};overflow:hidden;background:#fbfdfb;box-shadow:none;",
        "aurora": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border:1px solid {accent};border-radius:0;overflow:hidden;background:#ffffff;box-shadow:inset 0 -4px 0 {secondary};",
        "morandi": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border-top:1px solid {theme.line};border-bottom:1px solid {theme.line};background:#ffffff;box-shadow:none;",
        "mint": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border:1px solid {theme.line};border-radius:12px;overflow:hidden;background:#fbfffd;box-shadow:none;",
        "neon": f"width:100%;border-collapse:separate;border-spacing:0;font-size:14px;margin:18px 0;border:1px solid {accent};border-radius:0;overflow:hidden;background:#ffffff;box-shadow:inset 0 -4px 0 {secondary};",
    }
    return mapping[key]


def _th_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    mapping = {
        "magazine": f"padding:11px 12px;border-bottom:1px solid #000;background:#ffffff;text-align:left;vertical-align:top;color:{theme.heading};font-size:13px;font-weight:900;letter-spacing:0.08em;text-transform:uppercase;",
        "business": f"padding:11px 12px;border-bottom:1px solid {theme.line};background:{theme.soft2};text-align:left;vertical-align:top;color:{theme.heading};font-size:13px;font-weight:800;",
        "tech": f"padding:11px 12px;border-bottom:1px solid {theme.line};background:{theme.soft};text-align:left;vertical-align:top;color:{accent};font-size:13px;font-weight:800;",
        "aurora": f"padding:11px 12px;border-bottom:1px solid {accent};background:{theme.soft};text-align:left;vertical-align:top;color:{theme.heading};font-size:13px;font-weight:800;",
        "warm": f"padding:11px 12px;border-bottom:1px solid {theme.line};background:{theme.soft};text-align:left;vertical-align:top;color:{accent};font-size:13px;font-weight:800;",
        "chinese": f"padding:11px 12px;border-bottom:1px solid {secondary};background:#ffffff;text-align:left;vertical-align:top;color:{theme.heading};font-size:13px;font-weight:800;letter-spacing:0.12em;",
        "morandi": f"padding:11px 12px;border-bottom:1px solid {theme.line};background:{theme.soft};text-align:left;vertical-align:top;color:{theme.muted};font-size:13px;font-weight:700;",
        "neon": f"padding:11px 12px;border-bottom:1px solid {accent};background:{theme.soft};text-align:left;vertical-align:top;color:{accent};font-size:13px;font-weight:800;",
    }
    return mapping.get(
        key,
        f"padding:11px 12px;border-bottom:1px solid {theme.line};background:{theme.soft};text-align:left;vertical-align:top;color:{theme.heading};font-size:13px;font-weight:800;",
    )


def _td_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    border = secondary if key in {"aurora", "neon"} else theme.line
    color = theme.muted if key == "morandi" else theme.text
    return f"padding:11px 12px;border-bottom:1px solid {border};text-align:left;vertical-align:top;color:{color};line-height:1.72;background:#ffffff;"


def _compare_header_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    mapping = {
        "magazine": "display:flex;background:#111111;",
        "business": f"display:flex;background:{theme.soft2};border-bottom:1px solid {theme.line};",
        "tech": f"display:flex;background:{theme.soft};border-bottom:1px solid {theme.line};",
        "aurora": f"display:flex;background:{theme.soft};border-bottom:1px solid {accent};",
        "neon": f"display:flex;background:{theme.soft};border-bottom:1px solid {accent};",
    }
    return mapping.get(key, f"display:flex;background:{theme.soft2};")


def _compare_row_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    border = secondary if key in {"aurora", "neon"} else theme.line
    return f"display:flex;border-top:1px solid {border};"


def _compare_head_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    color = "#ffffff" if key == "magazine" else (accent if key in {"tech", "neon"} else theme.heading)
    return f"display:block;flex:1;padding:12px 14px;color:{color};line-height:1.5;font-size:13px;font-weight:800;letter-spacing:0.06em;"


def _compare_left_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    background = theme.soft if key in {"business", "tech", "mint", "forest"} else "#ffffff"
    return f"display:block;flex:1;padding:12px 14px;background:{background};color:{theme.muted};line-height:1.75;font-size:14px;font-weight:600;"


def _compare_right_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    color = accent if key == "neon" else theme.text
    return f"display:block;flex:1;padding:12px 14px;color:{color};line-height:1.75;font-size:14px;font-weight:700;"


def _quote_card_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    mapping = {
        "magazine": "margin:28px 0;padding:20px 0;border-top:3px solid #000;border-bottom:3px solid #000;background:transparent;border-left:none;border-right:none;border-radius:0;box-shadow:none;",
        "business": f"margin:24px 0;padding:18px 20px;background:{theme.soft2};border-left:3px solid {accent};border-top:none;border-right:none;border-bottom:none;border-radius:0;box-shadow:none;",
        "warm": f"margin:24px 0;padding:20px 20px;background:{theme.soft};border-top:1px solid {accent};border-bottom:1px solid {accent};border-left:none;border-right:none;border-radius:0;box-shadow:none;text-align:center;",
        "aurora": f"margin:24px 0;padding:18px 20px;background:#ffffff;border-bottom:2px solid {accent};box-shadow:inset 0 -5px 0 {secondary};border-radius:0;border-top:none;border-left:none;border-right:none;",
        "morandi": f"margin:28px 0;padding:18px 0;border-top:1px solid {theme.line};border-bottom:1px solid {theme.line};background:transparent;border-radius:0;box-shadow:none;text-align:center;",
        "neon": f"margin:24px 0;padding:18px 20px;background:#ffffff;border-bottom:2px solid {accent};box-shadow:inset 0 -5px 0 {secondary};border-radius:0;border-top:none;border-left:none;border-right:none;",
    }
    return mapping.get(
        key,
        f"margin:24px 0;padding:20px 20px;background:{theme.soft2};border-left:4px solid {accent};border-top:none;border-right:none;border-bottom:none;border-radius:{theme.radius};box-shadow:none;",
    )


def _quote_mark_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    color = "#000000" if key == "magazine" else accent
    return f"margin:0 0 8px;color:{color};font-size:28px;line-height:1;font-weight:800;"


def _quote_text_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    center = "text-align:center;" if key in {"warm", "morandi"} else ""
    color = accent if key == "neon" else theme.heading
    weight = "900" if key == "magazine" else "700"
    return f"margin:0;color:{color};font-size:17px;line-height:1.9;font-weight:{weight};letter-spacing:0.08px;{center}"


def _quote_author_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    center = "text-align:center;" if key in {"warm", "morandi"} else ""
    return f"margin:10px 0 0;color:{theme.muted};font-size:13px;line-height:1.6;{center}"


def _stat_card_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    mapping = {
        "business": f"box-sizing:border-box;flex:1 1 160px;min-width:140px;padding:18px 16px;border-left:4px solid {accent};border-radius:0;background:#ffffff;border-top:1px solid {theme.line};border-right:1px solid {theme.line};border-bottom:1px solid {theme.line};",
        "tech": f"box-sizing:border-box;flex:1 1 160px;min-width:140px;padding:18px 16px;border-bottom:2px solid {accent};border-radius:0;background:#ffffff;border-top:1px solid {theme.line};border-right:1px solid {theme.line};border-left:1px solid {theme.line};",
        "magazine": f"box-sizing:border-box;flex:1 1 160px;min-width:140px;padding:18px 16px;border-top:2px solid #000;border-bottom:2px solid {accent};border-radius:0;background:#ffffff;border-left:none;border-right:none;",
        "aurora": f"box-sizing:border-box;flex:1 1 160px;min-width:140px;padding:18px 16px;border-bottom:2px solid {accent};border-radius:0;background:#ffffff;box-shadow:inset 0 -4px 0 {secondary};border-top:1px solid {theme.line};border-left:1px solid {theme.line};border-right:1px solid {theme.line};",
        "morandi": f"box-sizing:border-box;flex:1 1 160px;min-width:140px;padding:18px 16px;border-top:1px solid {theme.line};border-bottom:1px solid {theme.line};border-radius:0;background:#ffffff;border-left:none;border-right:none;",
    }
    return mapping.get(
        key,
        f"box-sizing:border-box;flex:1 1 160px;min-width:140px;padding:18px 16px;border-radius:{theme.radius};background:{theme.soft};border:1px solid {theme.line};",
    )


def _stat_value_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    color = secondary if key == "magazine" else accent
    return f"margin:0;color:{color};font-size:28px;line-height:1.15;font-weight:900;"


def _stat_label_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    return f"margin:8px 0 0;color:{theme.muted};font-size:13px;line-height:1.7;"


def _reference_card_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    mapping = {
        "magazine": f"margin:16px 0 0;padding:16px 0 14px;border-top:1px solid #000;border-bottom:1px solid {theme.line};border-radius:0;background:transparent;border-left:none;border-right:none;box-shadow:none;",
        "business": f"margin:14px 0 0;padding:16px 16px 14px;border-left:3px solid {accent};border-radius:0;background:#ffffff;border-top:1px solid {theme.line};border-right:1px solid {theme.line};border-bottom:1px solid {theme.line};box-shadow:none;",
        "tech": f"margin:14px 0 0;padding:16px 16px 14px;border-bottom:2px solid {accent};border-radius:0;background:#ffffff;border-top:1px solid {theme.line};border-right:1px solid {theme.line};border-left:1px solid {theme.line};box-shadow:none;",
        "aurora": f"margin:14px 0 0;padding:16px 16px 14px;border-bottom:2px solid {accent};border-radius:0;background:#ffffff;box-shadow:inset 0 -4px 0 {secondary};border-top:1px solid {theme.line};border-left:1px solid {theme.line};border-right:1px solid {theme.line};",
        "morandi": f"margin:16px 0 0;padding:16px 0 14px;border-top:1px solid {theme.line};border-bottom:1px solid {theme.line};border-radius:0;background:transparent;border-left:none;border-right:none;box-shadow:none;",
    }
    return mapping.get(
        key,
        f"margin:14px 0 0;padding:16px 16px 14px;border-radius:{theme.radius};background:{theme.soft};border:1px solid {theme.line};box-shadow:none;",
    )


def _reference_link_css(key: str, theme: Any, accent: str, secondary: str) -> str:
    if key in {"magazine", "morandi", "chinese"}:
        return f"display:block;box-sizing:border-box;width:100%;margin:12px 0 0;padding:10px 0;border-radius:0;background:transparent;color:{accent};text-align:left;font-size:14px;font-weight:800;text-decoration:none;border:none;"
    return f"display:block;box-sizing:border-box;width:100%;margin:12px 0 0;padding:11px 14px;border-radius:999px;background:{theme.soft};color:{accent};text-align:center;font-size:14px;font-weight:800;text-decoration:none;border:1px solid {theme.line};"
