from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from core.editorial_strategy import ending_pattern_key, heading_pattern_key, opening_pattern_key, title_template_key
from core.quality_checks import (
    cost_signal_present,
    discussion_trigger_present,
    ending_excerpt_signature,
    lead_paragraph_count,
    opening_excerpt_signature,
    paragraph_overlap_signals,
    scene_signal_present,
    title_token_similarity,
    workspace_batch_key,
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower()).strip("-")


def _is_single_article_batch_workspace(path: Path, batch_key: str) -> bool:
    name = path.name
    if not name.startswith(f"{batch_key}-"):
        return False
    return "hot-topics" not in name.lower()


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
        f"title:{title_template_key(title)}",
        f"opening:{_normalize_key(opening_mode)}",
        f"ending:{_normalize_key(ending_mode)}",
        _normalize_key(interaction_goal),
        _normalize_key(secondary_goal),
    ]
    return {
        "title": title,
        "kind": "outline",
        "title_family": title_template_key(title),
        "article_archetype": route_features[0],
        "editorial_style_key": route_features[1],
        "opening_pattern": _normalize_key(opening_mode) or "planned-opening",
        "ending_pattern": _normalize_key(ending_mode) or "planned-ending",
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
    workspace_value = str(manifest.get("workspace") or "").strip()
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
        f"title:{title_template_key(title)}",
        f"opening:{opening_pattern}",
        f"opening2:{second_opening}",
        f"ending:{ending_pattern}",
        _normalize_key(str(blueprint.get("primary_interaction_goal") or "")),
        _normalize_key(str(blueprint.get("secondary_interaction_goal") or "")),
    ]
    layout_modules = [str(item.get("module_type") or "") for item in (layout_plan.get("section_plans") or []) if str(item.get("module_type") or "").strip()]
    summary = str(manifest.get("summary") or "").strip()
    return {
        "title": title,
        "kind": "article",
        "batch_key": workspace_batch_key(workspace_value),
        "title_family": title_template_key(title),
        "article_archetype": route_features[0],
        "editorial_style_key": route_features[1],
        "opening_pattern": opening_pattern,
        "second_opening_pattern": second_opening,
        "ending_pattern": ending_pattern,
        "summary_signature": opening_excerpt_signature(summary),
        "opening_excerpt_signature": opening_excerpt_signature(body),
        "ending_excerpt_signature": ending_excerpt_signature(body),
        "lead_paragraph_count": lead_paragraph_count(body),
        "title_length": len(re.sub(r"\s+", "", str(title or ""))),
        "summary_length": len(re.sub(r"\s+", "", str(manifest.get("summary") or ""))),
        "cost_signal_present": cost_signal_present(body),
        "scene_signal_present": scene_signal_present("\n".join(paragraphs[:2])),
        "discussion_trigger_present": discussion_trigger_present(body),
        "text_overlap_signals": [],
        "heading_patterns": heading_patterns,
        "argument_modes": list(dict.fromkeys(argument_modes))[:6],
        "evidence_modes": list(dict.fromkeys(evidence_modes))[:6],
        "primary_interaction_goal": str(blueprint.get("primary_interaction_goal") or ""),
        "secondary_interaction_goal": str(blueprint.get("secondary_interaction_goal") or ""),
        "layout_modules": layout_modules,
        "summary_keywords": sorted(_tokens(summary)),
        "keywords": sorted(_tokens(title) | _tokens(summary) | _tokens(" ".join(paragraphs[:3])) | _tokens(" ".join(item.get("text") or "" for item in headings[:4]))),
        "route_features": [item for item in route_features if item],
        "generated_at": legacy.now_iso(),
    }


def load_batch_article_items(current_workspace: Path) -> list[dict[str, Any]]:
    batch_key = workspace_batch_key(current_workspace)
    if not batch_key:
        return []
    parent = current_workspace.parent
    if not parent.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in parent.iterdir():
        if not path.is_dir() or path.resolve() == current_workspace.resolve():
            continue
        if workspace_batch_key(path) != batch_key:
            continue
        if not _is_single_article_batch_workspace(path, batch_key):
            continue
        article_path = path / "article.md"
        if not article_path.exists():
            continue
        try:
            raw = article_path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, other_body = legacy.split_frontmatter(raw)
        other_manifest = {}
        try:
            other_manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            other_manifest = {}
        other_review = {}
        try:
            other_review = json.loads((path / "review-report.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            other_review = {}
        other_layout_plan = {}
        try:
            other_layout_plan = json.loads((path / "layout-plan.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            other_layout_plan = {}
        fingerprint_path = path / "content-fingerprint.json"
        fingerprint = load_fingerprint(fingerprint_path) if fingerprint_path.exists() else {}
        if not fingerprint:
            other_title = (
                other_manifest.get("selected_title")
                or meta.get("title")
                or legacy.extract_title_from_body(other_body)
                or path.name
            )
            fingerprint = build_article_fingerprint(
                str(other_title),
                other_body,
                other_manifest | {"workspace": str(path.resolve())},
                review=other_review,
                blueprint=other_manifest.get("viral_blueprint") or {},
                layout_plan=other_layout_plan,
            )
        items.append(
            {
                "workspace": str(path.resolve()),
                "batch_key": batch_key,
                "title": str(fingerprint.get("title") or meta.get("title") or path.name),
                "body": other_body,
                "fingerprint": fingerprint,
            }
        )
    return items


def summarize_batch_collisions(
    current: dict[str, Any],
    *,
    current_title: str,
    current_body: str,
    batch_items: list[dict[str, Any]],
    threshold: float = 0.62,
    title_threshold: float = 0.72,
) -> dict[str, Any]:
    similar_items: list[dict[str, Any]] = []
    max_route_similarity = 0.0
    max_title_similarity = 0.0
    overlap_signals: list[dict[str, Any]] = []
    for item in batch_items:
        other_fp = dict(item.get("fingerprint") or {})
        other_title = str(item.get("title") or other_fp.get("title") or "")
        other_body = str(item.get("body") or "")
        route_similarity = compare_fingerprints(current, other_fp)
        title_similarity = title_token_similarity(current_title, other_title)
        overlap = paragraph_overlap_signals(current_body, other_body)
        matched_rules: list[str] = []
        if route_similarity > threshold:
            matched_rules.append("route_similarity")
        if title_similarity > title_threshold:
            matched_rules.append("title_token_similarity")
        if current.get("title_family") and current.get("title_family") == other_fp.get("title_family"):
            matched_rules.append("title_family")
        if current.get("summary_signature") and current.get("summary_signature") == other_fp.get("summary_signature"):
            matched_rules.append("summary_signature")
        if int(overlap.get("shared_paragraph_count") or 0) >= 2:
            matched_rules.append("shared_paragraphs")
        if int(overlap.get("shared_opening_paragraph_count") or 0) >= 1:
            matched_rules.append("shared_opening")
        if int(overlap.get("shared_ending_paragraph_count") or 0) >= 1:
            matched_rules.append("shared_ending")
        max_route_similarity = max(max_route_similarity, route_similarity)
        max_title_similarity = max(max_title_similarity, title_similarity)
        if matched_rules:
            signal = {
                "workspace": str(item.get("workspace") or ""),
                "title": other_title,
                "route_similarity": round(route_similarity, 3),
                "title_token_similarity": round(title_similarity, 3),
                "shared_paragraph_count": int(overlap.get("shared_paragraph_count") or 0),
                "shared_opening_paragraph_count": int(overlap.get("shared_opening_paragraph_count") or 0),
                "shared_ending_paragraph_count": int(overlap.get("shared_ending_paragraph_count") or 0),
                "matched_rules": matched_rules,
                "shared_paragraph_examples": list(overlap.get("shared_paragraph_examples") or []),
            }
            overlap_signals.append(signal)
            similar_items.append(
                {
                    "title": other_title,
                    "workspace": str(item.get("workspace") or ""),
                    "score": round(route_similarity, 3),
                    "title_token_similarity": round(title_similarity, 3),
                    "matched_rules": matched_rules,
                }
            )
    similar_items.sort(key=lambda value: (len(value.get("matched_rules") or []), value.get("score") or 0), reverse=True)
    return {
        "batch_key": str(current.get("batch_key") or ""),
        "passed": not overlap_signals,
        "max_route_similarity": round(max_route_similarity, 3),
        "max_title_token_similarity": round(max_title_similarity, 3),
        "batch_similar_items": similar_items[:5],
        "text_overlap_signals": overlap_signals[:5],
    }


def compare_fingerprints(current: dict[str, Any], other: dict[str, Any]) -> float:
    score = 0.0
    weight = 0.0

    def add(value: float, factor: float) -> None:
        nonlocal score, weight
        score += value * factor
        weight += factor

    add(1.0 if current.get("article_archetype") == other.get("article_archetype") else 0.0, 0.16)
    add(1.0 if current.get("editorial_style_key") == other.get("editorial_style_key") and current.get("editorial_style_key") else 0.0, 0.10)
    add(1.0 if current.get("title_family") == other.get("title_family") and current.get("title_family") else 0.0, 0.10)
    add(1.0 if current.get("opening_pattern") == other.get("opening_pattern") and current.get("opening_pattern") not in {"", "none"} else 0.0, 0.10)
    add(1.0 if current.get("ending_pattern") == other.get("ending_pattern") and current.get("ending_pattern") not in {"", "none"} else 0.0, 0.10)
    add(_jaccard(set(current.get("heading_patterns") or []), set(other.get("heading_patterns") or [])), 0.14)
    add(_jaccard(set(current.get("argument_modes") or []), set(other.get("argument_modes") or [])), 0.14)
    add(_jaccard(set(current.get("evidence_modes") or []), set(other.get("evidence_modes") or [])), 0.08)
    add(1.0 if current.get("primary_interaction_goal") == other.get("primary_interaction_goal") and current.get("primary_interaction_goal") else 0.0, 0.06)
    add(_jaccard(set(current.get("layout_modules") or []), set(other.get("layout_modules") or [])), 0.05)
    add(1.0 if current.get("summary_signature") and current.get("summary_signature") == other.get("summary_signature") else 0.0, 0.06)
    add(_jaccard(set(current.get("summary_keywords") or []), set(other.get("summary_keywords") or [])), 0.06)
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
