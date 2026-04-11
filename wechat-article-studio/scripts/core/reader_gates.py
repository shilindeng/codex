from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.quality_checks import (
    broken_char_ratio,
    cost_signal_present,
    has_broken_char_run,
    lead_paragraph_count,
    metadata_integrity_report,
    normalize_visible_text,
    scene_signal_present,
    split_markdown_paragraphs,
    visible_length,
)
from core.visual_batch import summarize_visual_batch_collisions

_OPENING_ROUTE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("scene-entry", (r"会议室", r"办公室", r"工位", r"白板", r"那天", r"凌晨", r"晚上", r"中午", r"刚坐下", r"头像", r"窗口里")),
    ("counterintuitive-entry", (r"很多人", r"第一反应", r"你以为", r"表面上看", r"看上去", r"误判", r"真正的问题")),
    ("cost-entry", (r"代价", r"成本", r"返工", r"吃亏", r"买单", r"损失", r"后果", r"最贵的一笔")),
    ("news-inversion-entry", (r"\d{1,2}\s*月\s*\d{1,2}\s*日", r"今天", r"本周", r"刚刚", r"消息", r"报道", r"发布", r"披露", r"宣布")),
]

_ENDING_ROUTE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("judgment-close", (r"真正.*(是|该)", r"不是.+而是", r"先问的不是", r"真正会拉开差距", r"最该盯住的")),
    ("stance-question-close", (r"如果是你", r"你会怎么", r"你更认同", r"到底", r"该不该", r"你最想", r"你会先")),
    ("risk-close", (r"风险", r"代价", r"迟早", r"别把", r"会先", r"最先塌掉", r"不能默认")),
    ("action-close", (r"先做", r"第一步", r"从.*开始", r"先把", r"可以先", r"下一步")),
]

_TEMPLATE_PATTERNS: list[tuple[str, str]] = [
    ("not_but", r"不是[^。！？!?；;\n]{1,30}而是[^。！？!?；;\n]{1,30}"),
    ("worth_write_not_but", r"真正值得(?:写|看|聊|警惕|讨论|说明)的不是"),
    ("dont_rush", r"先别急着"),
    ("real_problem", r"真正的问题(?:不是|是)"),
    ("also_dont", r"也别把"),
]

_LEAD_CONFLICT_PATTERNS = (
    r"不是.+而是",
    r"但",
    r"却",
    r"误判",
    r"卡住",
    r"问题",
    r"冲突",
    r"尴尬",
    r"分水岭",
    r"安静下来",
    r"真正的问题",
)

_LEAD_STAKES_PATTERNS = (
    r"这次",
    r"今天",
    r"本周",
    r"刚刚",
    r"发布",
    r"披露",
    r"宣布",
    r"报道",
    r"关键",
    r"代价",
    r"风险",
    r"后果",
    r"影响",
    r"最贵",
    r"最伤",
    r"更累",
    r"拖垮",
    r"真正的问题",
)

_SUSPICIOUS_BULLET_RE = re.compile(r"^\s*[-*+]\s+")
_SUSPICIOUS_BULLET_DIGIT_RE = re.compile(r"\d")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def classify_opening_route(text: str) -> str:
    value = _normalize_text(text)
    if not value:
        return "none"
    for key, patterns in _OPENING_ROUTE_PATTERNS:
        if any(re.search(pattern, value) for pattern in patterns):
            return key
    return "generic"


def classify_ending_route(text: str) -> str:
    value = _normalize_text(text)
    if not value:
        return "none"
    for key, patterns in _ENDING_ROUTE_PATTERNS:
        if any(re.search(pattern, value) for pattern in patterns):
            return key
    return "generic"


def first_screen_signal_report(body: str) -> dict[str, Any]:
    paragraphs = split_markdown_paragraphs(body)
    lead = paragraphs[:2]
    lead_text = " ".join(lead)
    opening_route = classify_opening_route(lead[0] if lead else "")
    has_scene = any(scene_signal_present(item) for item in lead) or opening_route in {"scene-entry", "news-inversion-entry"}
    has_conflict = bool(any(re.search(pattern, lead_text) for pattern in _LEAD_CONFLICT_PATTERNS))
    has_stakes = bool(cost_signal_present(lead_text) or any(re.search(pattern, lead_text) for pattern in _LEAD_STAKES_PATTERNS))
    pre_h2_paragraphs = lead_paragraph_count(body)
    return {
        "opening_route": opening_route,
        "lead_excerpt": lead_text[:220],
        "lead_paragraphs": len(lead),
        "pre_h2_paragraphs": pre_h2_paragraphs,
        "has_scene": has_scene,
        "has_conflict": has_conflict,
        "has_stakes": has_stakes,
        "passed": len(lead) >= 2 and has_scene and has_conflict and has_stakes and pre_h2_paragraphs <= 4,
    }


def template_frequency_report(title: str, body: str, summary: str = "") -> dict[str, Any]:
    corpus = "\n".join([str(title or ""), str(summary or ""), str(body or "")])
    counts = {key: len(re.findall(pattern, corpus)) for key, pattern in _TEMPLATE_PATTERNS}
    paragraphs = split_markdown_paragraphs(body)
    starter_counts: dict[str, int] = {}
    for paragraph in paragraphs[:6]:
        match = re.match(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}", normalize_visible_text(paragraph))
        if not match:
            continue
        token = match.group(0)
        starter_counts[token] = int(starter_counts.get(token) or 0) + 1
    repeated_starters = {key: value for key, value in starter_counts.items() if value >= 2}
    ending_route = classify_ending_route(paragraphs[-1] if paragraphs else "")
    title_not_but = counts["not_but"] >= 1 and bool(re.search(r"不是[^。！？!?]{1,30}而是", str(title or "")))
    ending_not_but = bool(paragraphs and re.search(r"不是[^。！？!?]{1,30}而是", paragraphs[-1]))
    same_family_repeat = title_not_but and ending_not_but and ending_route == "judgment-close"
    matched_patterns = [key for key, value in counts.items() if value]
    if repeated_starters:
        matched_patterns.append("repeated_starters")
    if same_family_repeat:
        matched_patterns.append("title_ending_same_family")
    severe_pattern_hits = counts["worth_write_not_but"] + max(0, counts["not_but"] - 3)
    severe_pattern_hits += max(0, counts["dont_rush"] - 1)
    return {
        "counts": counts,
        "repeated_starters": repeated_starters,
        "same_family_repeat": same_family_repeat,
        "matched_patterns": matched_patterns,
        "passed": severe_pattern_hits <= 0 and len(repeated_starters) <= 1 and not same_family_repeat,
    }


def abnormal_text_report(title: str, summary: str, body: str) -> dict[str, Any]:
    metadata = metadata_integrity_report(title, summary)
    suspicious_bullets: list[str] = []
    suspicious_lines: list[str] = []
    for raw_line in str(body or "").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("|"):
            continue
        compact = normalize_visible_text(stripped)
        if not compact:
            continue
        if _SUSPICIOUS_BULLET_RE.match(stripped):
            bullet_text = _SUSPICIOUS_BULLET_RE.sub("", stripped).strip()
            bullet_compact = normalize_visible_text(bullet_text)
            if (
                has_broken_char_run(bullet_compact)
                or broken_char_ratio(bullet_compact) >= 0.15
                or (
                    visible_length(bullet_compact) <= 12
                    and bool(_SUSPICIOUS_BULLET_DIGIT_RE.search(bullet_compact))
                    and not re.search(r"[。！？!?]$", bullet_text)
                )
            ):
                suspicious_bullets.append(stripped)
            continue
        if has_broken_char_run(compact) or broken_char_ratio(compact) >= 0.3:
            suspicious_lines.append(stripped)
    return {
        "metadata": metadata,
        "suspicious_bullets": suspicious_bullets[:6],
        "suspicious_lines": suspicious_lines[:6],
        "passed": bool(metadata.get("passed")) and not suspicious_bullets and not suspicious_lines,
    }


def image_plan_gate_report(image_plan: dict[str, Any] | None, *, workspace: Path | None = None) -> dict[str, Any]:
    payload = image_plan or {}
    items = list(payload.get("items") or [])
    cover = next((item for item in items if str(item.get("type") or "") == "封面图"), {})
    first_inline = next((item for item in items if str(item.get("id") or "").startswith("inline-")), {})
    article_strategy = payload.get("article_visual_strategy") or {}
    visual_route = str(article_strategy.get("visual_route") or "")
    per_item_routes = {
        str((item.get("article_visual_strategy") or {}).get("visual_route") or visual_route)
        for item in items
        if str((item.get("article_visual_strategy") or {}).get("visual_route") or visual_route).strip()
    }
    cover_text_policy = str(cover.get("text_policy") or "")
    first_inline_text_policy = str(first_inline.get("text_policy") or "")
    batch_visual = summarize_visual_batch_collisions(workspace, payload) if workspace is not None else {"passed": True, "similar_items": []}
    return {
        "visual_route": visual_route,
        "visual_route_passed": bool(visual_route) and len(per_item_routes) <= 1,
        "visual_batch_uniqueness_passed": bool(batch_visual.get("passed", True)),
        "visual_batch": batch_visual,
        "cover_text_policy_passed": not cover or cover_text_policy == "none",
        "first_inline_text_policy_passed": not first_inline or first_inline_text_policy in {"none", "short-zh", "short-zh-numeric"},
        "passed": (
            (not cover or cover_text_policy == "none")
            and (not first_inline or first_inline_text_policy in {"none", "short-zh", "short-zh-numeric"})
            and (not visual_route or len(per_item_routes) <= 1)
            and bool(batch_visual.get("passed", True))
        ),
    }
