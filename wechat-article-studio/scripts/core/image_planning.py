from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ImagePlanConfig:
    compose_prompt: Callable[[str, str, dict[str, Any], dict[str, Any], str], str]
    resolve_image_text_policy: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    visual_profile_for_item: Callable[[dict[str, Any], dict[str, Any]], dict[str, str]]
    candidate_keywords: Callable[[str], list[str]]
    extract_summary: Callable[[str, int], str]
    item_native_aspect_ratio: Callable[[dict[str, Any]], str]
    item_safe_crop_policy: Callable[[dict[str, Any]], str]
    infer_article_category_label: Callable[[str, str, str], str]
    cjk_len: Callable[[str], int]
    now_iso: Callable[[], str]


def image_planning_diagnostics(sections: list[dict[str, Any]], inline_sections: list[dict[str, Any]], requested_inline_count: int) -> dict[str, Any]:
    skipped_sections: list[str] = []
    forced_sections: list[str] = []
    eligible_sections = 0
    for section in sections:
        if bool(section.get("is_reference_section")):
            continue
        directives = section.get("image_directives") or {}
        if directives.get("skip"):
            skipped_sections.append(section.get("heading", ""))
            continue
        eligible_sections += 1
        if directives.get("force") or directives.get("count", 0) > 0:
            forced_sections.append(section.get("heading", ""))
    planned_count = len(inline_sections)
    reasons: list[str] = []
    if planned_count < requested_inline_count:
        reasons.append("当前密度规划已请求更多正文图，但可用章节和长章节复用次数有限。")
    if skipped_sections:
        reasons.append(f"有 {len(skipped_sections)} 个章节被显式标记为 skip。")
    if eligible_sections < requested_inline_count:
        reasons.append(f"可配图章节只有 {eligible_sections} 个。")
    return {
        "skipped_sections": skipped_sections,
        "forced_sections": forced_sections,
        "planning_shortfall_reason": " ".join(reasons).strip(),
    }


def enrich_plan_items(
    items: list[dict[str, Any]],
    *,
    title: str,
    summary: str,
    body: str,
    provider: str,
    article_strategy: dict[str, Any],
    effective_controls: dict[str, Any],
    audience: str,
    cfg: ImagePlanConfig,
) -> list[dict[str, Any]]:
    for item in items:
        item["provider"] = provider
        item["article_visual_strategy"] = {
            "visual_direction": article_strategy.get("visual_direction", ""),
            "style_family": article_strategy.get("style_family", ""),
            "content_mode": article_strategy.get("content_mode", ""),
            "type_bias": article_strategy.get("type_bias", {}),
        }
        item.update(cfg.visual_profile_for_item(effective_controls, item))
        item["style_reason"] = item.get("style_reason") or "按文章视觉策略自动决定。"
        item["semantic_focus"] = cfg.extract_summary(f"{item.get('section_heading') or ''} {item.get('section_excerpt') or ''}", 64)
        item["keyword_glossary"] = cfg.candidate_keywords(
            " ".join(
                [
                    title,
                    summary,
                    str(item.get("section_heading") or ""),
                    str(item.get("section_excerpt") or ""),
                    str(item.get("anchor_block_excerpt") or ""),
                ]
            )
        )
        item["native_aspect_ratio"] = cfg.item_native_aspect_ratio(item)
        item["safe_crop_policy"] = cfg.item_safe_crop_policy(item)
        text_policy = cfg.resolve_image_text_policy(effective_controls, item)
        item["text_policy"] = text_policy["mode"]
        item["text_policy_label"] = text_policy["label"]
        item["text_policy_reason"] = text_policy["reason"]
        item["label_language"] = text_policy["label_language"]
        item["label_strategy"] = text_policy["label_strategy"]
        item["text_budget"] = text_policy["text_budget"]
        item["visual_reason"] = f"{item.get('type_reason', '')} {item.get('style_reason', '')}".strip()
        item["prompt"] = cfg.compose_prompt(title, summary, effective_controls, item, audience)
        item["revised_prompt"] = item["prompt"]
        item["asset_path"] = None
        item["source_meta"] = {}
    return items


def build_plan_payload(
    *,
    title: str,
    body: str,
    provider: str,
    decision_source: str,
    auto_reason: str,
    inline_sections: list[dict[str, Any]],
    requested_inline_count: int,
    diagnostics: dict[str, Any],
    effective_controls: dict[str, Any],
    user_controls: dict[str, Any],
    article_strategy: dict[str, Any],
    items: list[dict[str, Any]],
    cfg: ImagePlanConfig,
) -> dict[str, Any]:
    article_category = cfg.infer_article_category_label(title, "", body)
    return {
        "title": title,
        "provider": provider,
        "strategy": "mixed-section-density",
        "decision_source": decision_source,
        "article_category": article_category,
        "auto_reason": auto_reason,
        "article_char_count": cfg.cjk_len(re.sub(r"^#{1,6}\s+", "", body, flags=re.M)),
        "planned_inline_count": len(inline_sections),
        "requested_inline_count": requested_inline_count,
        "density_mode": effective_controls.get("density", "balanced"),
        "layout_family": effective_controls.get("layout_family", ""),
        "planning_shortfall_reason": diagnostics["planning_shortfall_reason"],
        "skipped_sections": diagnostics["skipped_sections"],
        "forced_sections": diagnostics["forced_sections"],
        "image_controls": effective_controls,
        "user_image_controls": user_controls,
        "article_visual_strategy": {
            "visual_direction": article_strategy.get("visual_direction", ""),
            "style_family": article_strategy.get("style_family", ""),
            "content_mode": article_strategy.get("content_mode", ""),
            "style_mode": article_strategy.get("style_mode", ""),
            "type_bias": article_strategy.get("type_bias", {}),
            "decision_reasoning": article_strategy.get("decision_reasoning", []),
            "explicit_overrides": article_strategy.get("explicit_overrides", []),
        },
        "items": items,
        "generated_at": cfg.now_iso(),
    }
