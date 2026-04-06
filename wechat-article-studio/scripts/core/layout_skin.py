from __future__ import annotations

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


def get_skin(key: str) -> LayoutSkin:
    normalized = (key or "").strip().lower()
    return SKINS.get(normalized, SKINS["elegant"])


def choose_layout_skin(
    requested: str,
    chosen_style: str,
    manifest: dict[str, Any],
    content_signals: Any,
    *,
    rich_blocks: Iterable[str] = (),
) -> LayoutSkinDecision:
    req = (requested or "").strip().lower()
    if req and req != "auto" and req in SKINS:
        return LayoutSkinDecision(key=req, reason="explicit_layout_skin")

    archetype = str((manifest.get("layout_plan") or {}).get("layout_archetype") or (manifest.get("viral_blueprint") or {}).get("article_archetype") or "").strip().lower()
    normalized_rich_blocks = {str(item or "").strip().lower() for item in rich_blocks if str(item or "").strip()}
    image_controls = manifest.get("image_controls") or {}
    preset = str(image_controls.get("preset") or image_controls.get("preset_cover") or image_controls.get("preset_inline") or "").strip().lower()

    if "compare" in normalized_rich_blocks or archetype == "comparison":
        return LayoutSkinDecision(key="aurora" if chosen_style != "warm" else "morandi", reason="comparison_content")
    if "steps" in normalized_rich_blocks or archetype == "tutorial":
        return LayoutSkinDecision(key="tech" if chosen_style in {"tech", "business", "blueprint"} else "mint", reason="tutorial_content")
    if "dialogue" in normalized_rich_blocks:
        return LayoutSkinDecision(key="warm", reason="dialogue_content")
    if "quote" in normalized_rich_blocks and chosen_style == "magazine":
        return LayoutSkinDecision(key="magazine", reason="quote_heavy_magazine")
    if getattr(content_signals, "has_table", False):
        return LayoutSkinDecision(key="business", reason="table_content")
    if archetype == "narrative":
        return LayoutSkinDecision(key="chinese" if getattr(content_signals, "blockquote_count", 0) else "warm", reason="narrative_archetype")
    if archetype == "case-study":
        return LayoutSkinDecision(key="business", reason="case_study_archetype")
    if preset in _PRESET_SKIN_HINTS:
        return LayoutSkinDecision(key=_PRESET_SKIN_HINTS[preset][0], reason=f"image_preset({preset})")

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
