from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from core.editorial_strategy import ending_pattern_key, heading_pattern_key, opening_pattern_key


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower()).strip("-")


def _tokens(value: str) -> set[str]:
    return {item.lower() for item in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}", _normalize_text(value))}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _article_archetype(title: str, blueprint: dict[str, Any], manifest: dict[str, Any]) -> str:
    value = _normalize_key(str((blueprint or {}).get("article_archetype") or manifest.get("article_archetype") or ""))
    if value:
        return value
    corpus = " ".join([title, str(manifest.get("topic") or ""), str(manifest.get("summary") or "")])
    tutorial = len(re.findall(r"教程|指南|手把手|步骤|SOP|模板|上手|实操|如何|怎么", corpus))
    case_study = len(re.findall(r"案例|复盘|拆解|项目|公司|产品", corpus))
    narrative = len(re.findall(r"故事|经历|生活|关系|焦虑|情绪|职场", corpus))
    commentary = len(re.findall(r"为什么|真相|趋势|信号|机会|风险|拐点|判断", corpus))
    if tutorial >= 2 and tutorial > commentary:
        return "tutorial"
    if case_study >= 2:
        return "case-study"
    if narrative >= 2 and narrative > commentary:
        return "narrative"
    return "commentary"


def _heading_patterns_from_sections(sections: list[dict[str, Any]]) -> list[str]:
    patterns: list[str] = []
    for item in sections[:6]:
        key = heading_pattern_key(str(item.get("heading") or ""))
        if key and key not in {"none", "generic"} and key not in patterns:
            patterns.append(key)
    return patterns


def _evidence_modes_from_sections(sections: list[dict[str, Any]]) -> list[str]:
    modes: list[str] = []
    corpus = " ".join(str(item.get("evidence_need") or "") for item in sections)
    mapping = {
        "scene": ("场景", "瞬间", "现场"),
        "case": ("案例", "复盘", "实例"),
        "data": ("数据", "%", "指标", "研究", "报告"),
        "compare": ("对比", "差异", "不是", "而是"),
        "boundary": ("边界", "反方", "误判", "例外"),
    }
    for key, words in mapping.items():
        if any(word in corpus for word in words):
            modes.append(key)
    return modes


def build_outline_fingerprint(title: str, outline_meta: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    blueprint = dict(outline_meta.get("viral_blueprint") or manifest.get("viral_blueprint") or {})
    sections = list(outline_meta.get("sections") or [])
    opening_mode = str(outline_meta.get("opening_mode") or "")
    ending_mode = str(outline_meta.get("ending_mode") or "")
    interaction_goal = str(blueprint.get("primary_interaction_goal") or "")
    secondary_goal = str(blueprint.get("secondary_interaction_goal") or "")
    route_features = [
        _article_archetype(title, blueprint, manifest),
        _normalize_key(str((manifest.get("editorial_blueprint") or {}).get("style_key") or (outline_meta.get("editorial_blueprint") or {}).get("style_key") or "")),
        _normalize_key(opening_mode),
        _normalize_key(ending_mode),
        _normalize_key(interaction_goal),
        _normalize_key(secondary_goal),
    ]
    return {
        "title": title,
        "kind": "outline",
        "article_archetype": route_features[0],
        "editorial_style_key": route_features[1],
        "opening_pattern": route_features[2] or "planned-opening",
        "ending_pattern": route_features[3] or "planned-ending",
        "heading_patterns": _heading_patterns_from_sections(sections),
        "argument_modes": [str(item).strip() for item in (blueprint.get("argument_modes") or []) if str(item).strip()],
        "evidence_modes": _evidence_modes_from_sections(sections),
        "primary_interaction_goal": interaction_goal,
        "secondary_interaction_goal": secondary_goal,
        "keywords": sorted(_tokens(title) | _tokens(" ".join(str(item.get("heading") or "") for item in sections))),
        "layout_modules": [],
        "route_features": [item for item in route_features if item],
        "generated_at": legacy.now_iso(),
    }


def build_article_fingerprint(
    title: str,
    body: str,
    manifest: dict[str, Any],
    *,
    review: dict[str, Any] | None = None,
    blueprint: dict[str, Any] | None = None,
    layout_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blueprint = dict(blueprint or manifest.get("viral_blueprint") or {})
    review = review or {}
    layout_plan = layout_plan or {}
    paragraphs = legacy.list_paragraphs(body)
    headings = legacy.extract_headings(body)
    opening_pattern = opening_pattern_key(paragraphs[0]) if paragraphs else "none"
    second_opening = opening_pattern_key(paragraphs[1]) if len(paragraphs) > 1 else "none"
    ending_pattern = ending_pattern_key(paragraphs[-1]) if paragraphs else "none"
    heading_patterns: list[str] = []
    for item in headings[:6]:
        key = heading_pattern_key(str(item.get("text") or ""))
        if key and key not in {"none", "generic"} and key not in heading_patterns:
            heading_patterns.append(key)
    analysis = review.get("viral_analysis") or {}
    argument_modes = [
        str(item).strip()
        for item in (analysis.get("argument_diversity") or analysis.get("persuasion_strategies") or blueprint.get("argument_modes") or [])
        if str(item).strip()
    ]
    evidence_modes = []
    for mode in argument_modes:
        if any(word in mode for word in ["案例", "数据", "对比", "场景", "权威", "步骤"]):
            evidence_modes.append(mode)
    if not evidence_modes:
        evidence_modes = _evidence_modes_from_sections(layout_plan.get("section_plans") or [])
    route_features = [
        _article_archetype(title, blueprint, manifest),
        _normalize_key(str((manifest.get("editorial_blueprint") or {}).get("style_key") or "")),
        opening_pattern,
        second_opening,
        ending_pattern,
        _normalize_key(str(blueprint.get("primary_interaction_goal") or "")),
        _normalize_key(str(blueprint.get("secondary_interaction_goal") or "")),
    ]
    layout_modules = [str(item.get("module_type") or "") for item in (layout_plan.get("section_plans") or []) if str(item.get("module_type") or "").strip()]
    return {
        "title": title,
        "kind": "article",
        "article_archetype": route_features[0],
        "editorial_style_key": route_features[1],
        "opening_pattern": opening_pattern,
        "second_opening_pattern": second_opening,
        "ending_pattern": ending_pattern,
        "heading_patterns": heading_patterns,
        "argument_modes": list(dict.fromkeys(argument_modes))[:6],
        "evidence_modes": list(dict.fromkeys(evidence_modes))[:6],
        "primary_interaction_goal": str(blueprint.get("primary_interaction_goal") or ""),
        "secondary_interaction_goal": str(blueprint.get("secondary_interaction_goal") or ""),
        "layout_modules": layout_modules,
        "keywords": sorted(_tokens(title) | _tokens(" ".join(paragraphs[:3])) | _tokens(" ".join(item.get("text") or "" for item in headings[:4]))),
        "route_features": [item for item in route_features if item and item not in {"none", "generic"}],
        "generated_at": legacy.now_iso(),
    }


def compare_fingerprints(current: dict[str, Any], other: dict[str, Any]) -> float:
    score = 0.0
    weight = 0.0

    def add(value: float, factor: float) -> None:
        nonlocal score, weight
        score += value * factor
        weight += factor

    add(1.0 if current.get("article_archetype") == other.get("article_archetype") else 0.0, 0.18)
    add(1.0 if current.get("editorial_style_key") == other.get("editorial_style_key") and current.get("editorial_style_key") else 0.0, 0.10)
    add(1.0 if current.get("opening_pattern") == other.get("opening_pattern") and current.get("opening_pattern") not in {"", "none", "generic"} else 0.0, 0.10)
    add(1.0 if current.get("ending_pattern") == other.get("ending_pattern") and current.get("ending_pattern") not in {"", "none", "generic"} else 0.0, 0.10)
    add(_jaccard(set(current.get("heading_patterns") or []), set(other.get("heading_patterns") or [])), 0.14)
    add(_jaccard(set(current.get("argument_modes") or []), set(other.get("argument_modes") or [])), 0.14)
    add(_jaccard(set(current.get("evidence_modes") or []), set(other.get("evidence_modes") or [])), 0.08)
    add(1.0 if current.get("primary_interaction_goal") == other.get("primary_interaction_goal") and current.get("primary_interaction_goal") else 0.0, 0.06)
    add(_jaccard(set(current.get("layout_modules") or []), set(other.get("layout_modules") or [])), 0.05)
    add(_jaccard(set(current.get("route_features") or []), set(other.get("route_features") or [])), 0.14)
    add(_jaccard(set(current.get("keywords") or []), set(other.get("keywords") or [])), 0.10)
    if weight <= 0:
        return 0.0
    return round(score / weight, 3)


def summarize_collisions(current: dict[str, Any], recent_items: list[dict[str, Any]], threshold: float = 0.72) -> dict[str, Any]:
    similar_items: list[dict[str, Any]] = []
    max_similarity = 0.0
    for item in recent_items:
        similarity = compare_fingerprints(current, item)
        max_similarity = max(max_similarity, similarity)
        if similarity >= max(0.45, threshold - 0.18):
            similar_items.append(
                {
                    "title": item.get("title") or "",
                    "score": similarity,
                    "article_archetype": item.get("article_archetype") or "",
                    "opening_pattern": item.get("opening_pattern") or "",
                    "ending_pattern": item.get("ending_pattern") or "",
                }
            )
    similar_items.sort(key=lambda value: value.get("score") or 0, reverse=True)
    return {
        "max_route_similarity": round(max_similarity, 3),
        "route_similarity_passed": max_similarity <= threshold,
        "similar_items": similar_items[:5],
    }


def load_fingerprint(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
