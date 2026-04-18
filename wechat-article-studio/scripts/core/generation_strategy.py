from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from core.analysis_11d import list_batch_workspaces
from core.editorial_strategy import opening_pattern_key, title_template_key
from core.quality_checks import split_markdown_paragraphs, workspace_batch_key

TITLE_TAIL_PATTERNS = ["真正", "最先", "从今天开始", "被改写的是"]

OPENING_ROUTE_LABELS = {
    "scene-cut": "场景切口",
    "cost-upfront": "代价先行切口",
    "news-hook": "新闻切口",
    "reader-scene": "读者代入切口",
}

OPENING_LABEL_TO_KEY = {value: key for key, value in OPENING_ROUTE_LABELS.items()}

ENDING_SHAPE_TO_MODE = {
    "judgment_card": "可转述判断",
    "risk_warning": "风险提醒",
    "reusable_question": "站队式问题",
}

ENDING_SHAPE_HINTS = {
    "judgment_card": {
        "allowed_shapes": ["判断卡"],
        "heading_hint": "最后带走这张判断卡",
    },
    "risk_warning": {
        "allowed_shapes": ["风险提醒"],
        "heading_hint": "最后记住这条风险线",
    },
    "reusable_question": {
        "allowed_shapes": ["自测问题"],
        "heading_hint": "最后先问自己这个问题",
    },
}

READER_OBJECT_MARKERS = (
    "团队",
    "老板",
    "家长",
    "学生",
    "开发者",
    "管理者",
    "普通人",
    "用户",
    "孩子",
    "公司",
)

COST_MARKERS = (
    "代价",
    "后果",
    "返工",
    "风险",
    "误判",
    "边界",
    "速度差",
    "掉队",
    "失控",
)

BENEFIT_MARKERS = (
    "判断",
    "抓手",
    "带走",
    "收藏",
    "保存",
    "更稳",
    "看懂",
    "理解",
)


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = _clean(item)
        if text and text not in output:
            output.append(text)
    return output


def _count_tables(body: str) -> int:
    return len(re.findall(r"(?m)^\|.+\|\s*\n\|(?:\s*:?-+:?\s*\|)+", body or ""))


def _ending_shape_from_body(body: str) -> str:
    paragraphs = split_markdown_paragraphs(body)
    tail = " ".join(paragraphs[-2:]) if paragraphs else ""
    headings = [str(item.get("text") or "").strip() for item in legacy.extract_headings(body) if int(item.get("level") or 0) == 2]
    last_heading = headings[-1] if headings else ""
    if any(keyword in last_heading for keyword in ("带走这张", "带走这条", "判断卡", "检查表", "清单")):
        return "judgment_card"
    if any(keyword in tail for keyword in ("风险", "后果", "别把", "不能", "越过去")):
        return "risk_warning"
    if "？" in tail or "?" in tail or any(keyword in tail for keyword in ("如果是你", "你会怎么", "先问自己")):
        return "reusable_question"
    return ""


def _shape_priority(archetype: str) -> list[str]:
    archetype_key = str(archetype or "").strip().lower()
    if archetype_key == "tutorial":
        return ["reusable_question", "judgment_card", "risk_warning"]
    if archetype_key == "narrative":
        return ["risk_warning", "judgment_card", "reusable_question"]
    return ["judgment_card", "risk_warning", "reusable_question"]


def _pick_allowed_shape(archetype: str, forbidden: list[str], preferred: str = "") -> str:
    blocked = {str(item or "").strip() for item in forbidden if str(item or "").strip()}
    if preferred and preferred not in blocked:
        return preferred
    for item in _shape_priority(archetype):
        if item not in blocked:
            return item
    return preferred or "judgment_card"


def _route_candidates(manifest: dict[str, Any]) -> list[str]:
    strategy = manifest.get("account_strategy") or {}
    candidates: list[str] = []
    for item in _normalize_list(strategy.get("preferred_opening_modes")):
        key = OPENING_LABEL_TO_KEY.get(item, "")
        if key and key not in candidates:
            candidates.append(key)
    for fallback in ["scene-cut", "cost-upfront", "news-hook", "reader-scene"]:
        if fallback not in candidates:
            candidates.append(fallback)
    return candidates


def _pick_opening_route(manifest: dict[str, Any], forbidden: list[str], preferred: str = "") -> str:
    blocked = {str(item or "").strip() for item in forbidden if str(item or "").strip()}
    if preferred and preferred not in {"", "none", "generic"} and preferred not in blocked:
        return preferred
    for item in _route_candidates(manifest):
        if item not in blocked:
            return item
    return preferred or "scene-cut"


def _extract_reader_object(title: str, audience: str, core_viewpoint: str) -> str:
    corpus = " ".join([title, audience, core_viewpoint])
    for item in READER_OBJECT_MARKERS:
        if item in corpus:
            return item
    return audience or "读者"


def _extract_marker_sentence(text: str, markers: tuple[str, ...], fallback: str) -> str:
    paragraphs = split_markdown_paragraphs(text)
    for paragraph in paragraphs:
        if any(marker in paragraph for marker in markers):
            return _clean(paragraph)[:48]
    return fallback


def build_batch_guidance_payload(jobs_root: Path, batch_key: str, *, current_workspace: Path | None = None) -> dict[str, Any]:
    workspaces = list_batch_workspaces(jobs_root, batch_key)
    peers = [item for item in workspaces if current_workspace is None or item.resolve() != current_workspace.resolve()]
    opening_counts: dict[str, int] = {}
    title_counts: dict[str, int] = {}
    ending_counts: dict[str, int] = {}
    double_table_seen = False
    peer_examples: list[dict[str, Any]] = []
    for workspace in peers:
        raw = legacy.read_text(workspace / "article.md")
        meta, body = legacy.split_frontmatter(raw)
        title = str(meta.get("title") or workspace.name).strip()
        paragraphs = split_markdown_paragraphs(body)
        opening_route = opening_pattern_key(paragraphs[0]) if paragraphs else "none"
        title_pattern = title_template_key(title)
        ending_shape = _ending_shape_from_body(body) or "generic"
        table_count = _count_tables(body)
        if table_count >= 2:
            double_table_seen = True
        if opening_route not in {"none", "generic"}:
            opening_counts[opening_route] = int(opening_counts.get(opening_route) or 0) + 1
        if title_pattern not in {"", "generic"}:
            title_counts[title_pattern] = int(title_counts.get(title_pattern) or 0) + 1
        ending_counts[ending_shape] = int(ending_counts.get(ending_shape) or 0) + 1
        peer_examples.append(
            {
                "workspace": str(workspace),
                "title": title,
                "opening_route": opening_route,
                "title_pattern": title_pattern,
                "ending_shape": ending_shape,
                "table_count": table_count,
            }
        )
    forbidden_opening_routes = [key for key, count in opening_counts.items() if count >= 2]
    forbidden_title_patterns = [key for key, count in title_counts.items() if count >= 2]
    forbidden_ending_shapes = [key for key, count in ending_counts.items() if key == "judgment_card" and count >= 1]
    forbidden_ending_shapes.extend([key for key, count in ending_counts.items() if key != "judgment_card" and count >= 2])
    forbidden_ending_shapes = list(dict.fromkeys(forbidden_ending_shapes))
    return {
        "jobs_root": str(jobs_root),
        "batch_key": batch_key,
        "current_workspace": str(current_workspace.resolve()) if current_workspace is not None else "",
        "forbidden_opening_routes": forbidden_opening_routes,
        "forbidden_title_patterns": forbidden_title_patterns,
        "forbidden_ending_shapes": forbidden_ending_shapes,
        "max_table_count": 1 if double_table_seen else 2,
        "recommended_image_density": "balanced",
        "peer_examples": peer_examples[:5],
        "generated_at": legacy.now_iso(),
    }


def build_generation_strategy(
    *,
    title: str,
    manifest: dict[str, Any],
    body: str = "",
    analysis_11d: dict[str, Any] | None = None,
    batch_guidance: dict[str, Any] | None = None,
    outline_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis_11d = analysis_11d or {}
    batch_guidance = batch_guidance or {}
    outline_meta = outline_meta or {}
    archetype = str(
        (outline_meta.get("viral_blueprint") or {}).get("article_archetype")
        or (manifest.get("viral_blueprint") or {}).get("article_archetype")
        or manifest.get("article_archetype")
        or "commentary"
    ).strip().lower()
    core_viewpoint = _clean(analysis_11d.get("core_viewpoint") or "")
    interaction_hooks = dict(analysis_11d.get("interaction_hooks") or {})
    language_style = dict(analysis_11d.get("language_style") or {})
    forbidden_title_patterns = _normalize_list(batch_guidance.get("forbidden_title_patterns"))
    forbidden_title_tail_patterns = list(dict.fromkeys(TITLE_TAIL_PATTERNS))
    title_pattern = title_template_key(title)
    title_strategy = {
        "pattern_family": title_pattern,
        "reader_object": _extract_reader_object(title, str(manifest.get("audience") or ""), core_viewpoint),
        "reader_cost": _extract_marker_sentence(core_viewpoint or title, COST_MARKERS, "写清这件事最先落到谁头上的代价"),
        "reader_benefit": _extract_marker_sentence(" ".join((interaction_hooks.get("save_triggers") or []) + [core_viewpoint]), BENEFIT_MARKERS, "让读者带走一个更稳的判断"),
        "forbidden_tail_patterns": forbidden_title_tail_patterns,
        "batch_collision_reasons": [f"同批次已高频使用标题模板：{title_pattern}"] if title_pattern in forbidden_title_patterns else [],
    }
    preferred_opening = opening_pattern_key(split_markdown_paragraphs(body)[0]) if body else ""
    opening_route = _pick_opening_route(manifest, _normalize_list(batch_guidance.get("forbidden_opening_routes")), preferred=preferred_opening)
    opening_strategy = {
        "route": opening_route,
        "route_label": OPENING_ROUTE_LABELS.get(opening_route, ""),
        "scene_required": True,
        "conflict_required": True,
        "cost_required": True,
        "max_pre_h2_paragraphs": 4,
        "batch_collision_reasons": [f"同批次已重复开头路线：{opening_route}"] if opening_route in _normalize_list(batch_guidance.get("forbidden_opening_routes")) else [],
    }
    preferred_shape = _ending_shape_from_body(body)
    ending_shape = _pick_allowed_shape(archetype, _normalize_list(batch_guidance.get("forbidden_ending_shapes")), preferred=preferred_shape)
    ending_strategy = {
        "shape": ending_shape,
        "mode_label": ENDING_SHAPE_TO_MODE.get(ending_shape, ""),
        "save_trigger_required": True,
        "comment_trigger_required": True,
        "forbidden_heading_patterns": ["带走这张", "带走这条"] if "judgment_card" in _normalize_list(batch_guidance.get("forbidden_ending_shapes")) else [],
        "batch_collision_reasons": [f"同批次已高频使用结尾形状：{ending_shape}"] if ending_shape in _normalize_list(batch_guidance.get("forbidden_ending_shapes")) else [],
        **ENDING_SHAPE_HINTS.get(ending_shape, ENDING_SHAPE_HINTS["judgment_card"]),
    }
    return {
        "title_strategy": title_strategy,
        "opening_strategy": opening_strategy,
        "ending_strategy": ending_strategy,
        "max_table_count": int(batch_guidance.get("max_table_count") or 1),
        "recommended_image_density": str(batch_guidance.get("recommended_image_density") or "balanced"),
        "template_risk_signals": list(language_style.get("template_risk_signals") or [])[:6],
        "generated_at": legacy.now_iso(),
    }


def ensure_batch_guidance(workspace: Path, manifest: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    batch_key = workspace_batch_key(workspace)
    if not batch_key:
        manifest["batch_guidance"] = {}
        return {}
    path = workspace / "batch-guidance.json"
    if path.exists() and not force:
        payload = legacy.read_json(path, default={}) or {}
    else:
        payload = build_batch_guidance_payload(workspace.parent, batch_key, current_workspace=workspace)
        legacy.write_json(path, payload)
    manifest["batch_guidance_path"] = "batch-guidance.json"
    manifest["batch_guidance"] = payload
    return payload
