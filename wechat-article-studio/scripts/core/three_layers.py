from __future__ import annotations

import math
import re
from typing import Any

from core.quality_checks import (
    cost_signal_present,
    discussion_trigger_present,
    scene_signal_present,
    split_markdown_paragraphs,
    title_hook_shape,
    title_token_set,
)
from core.reader_gates import first_screen_signal_report


HOOK_TRIGGER_PATTERNS = (
    r"不是.+而是",
    r"最先",
    r"最容易",
    r"先讲清楚",
    r"先要",
    r"代价",
    r"风险",
    r"拐点",
    r"真相",
    r"\d+(?:\.\d+)?%?",
    r"\d+(?:亿|万|个|次|倍)",
)

REUSABLE_METHOD_PATTERNS = (
    r"框架",
    r"检查表",
    r"清单",
    r"原则",
    r"模板",
    r"SOP",
    r"步骤",
    r"先看",
    r"先问",
    r"下次",
)

SAVE_TRIGGER_PATTERNS = (
    r"收藏",
    r"保存",
    r"留着",
    r"下次",
    r"以后",
    r"直接套",
    r"拿去用",
    r"转给",
    r"判断卡",
    r"检查框架",
)

TAKEAWAY_OBJECT_PATTERNS = (
    r"判断卡",
    r"框架",
    r"检查表",
    r"清单",
    r"模板",
    r"原则",
    r"SOP",
    r"一句话",
    r"记住这",
)

TAKEAWAY_SECTION_PATTERNS = (
    r"带走",
    r"记住",
    r"判断卡",
    r"检查表",
    r"清单",
    r"框架",
    r"原则",
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _tokens(value: str) -> set[str]:
    return {item.lower() for item in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}", _normalize_text(value))}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _tail_paragraphs(body: str) -> list[str]:
    paragraphs = split_markdown_paragraphs(body)
    if not paragraphs:
        return []
    count = max(2, int(math.ceil(len(paragraphs) * 0.2)))
    return paragraphs[-count:]


def _tail_headings(body: str) -> list[str]:
    headings = re.findall(r"(?m)^\s*##\s+(.+?)\s*$", body or "")
    return [str(item).strip() for item in headings[-2:]]


def default_layer_strategies(*, archetype: str, title: str, topic: str, audience: str) -> dict[str, dict[str, Any]]:
    subject = _normalize_text(topic or title or "这篇文章")
    commentary = {
        "hook_strategy": {
            "goal": "让读者在 0.3 秒内停下来。",
            "trigger_mode": "反常识/代价/新闻倒挂",
            "position": "标题 + 前两段",
            "forbidden_moves": ["标题把答案说死", "前两段只讲背景", "开头泛泛铺垫没有冲突"],
        },
        "insight_strategy": {
            "goal": "让读者觉得这篇文章真的有值。",
            "trigger_mode": "新判断 + 证据托底 + 可迁移解释",
            "position": "中段主展开区",
            "forbidden_moves": ["只有态度没有新判断", "只有抽象词没有展开", "只有信息没有迁移价值"],
        },
        "takeaway_strategy": {
            "goal": "让读者愿意保存和转发。",
            "trigger_mode": "判断卡 / 检查框架 / 可复用结论",
            "position": "最后 15%~20% 正文",
            "forbidden_moves": ["只剩判断收束", "只剩欢迎留言", "只有风险提醒没有带走内容"],
            "allowed_shapes": ["判断卡", "检查框架", "一句可复用结论"],
            "heading_hint": "最后带走这张判断卡",
            "save_trigger_hint": "收藏这条，下次遇到同类问题时直接对照。",
        },
    }
    tutorial = {
        "hook_strategy": {
            "goal": "让读者立刻意识到这篇能解决自己的卡点。",
            "trigger_mode": "痛点/误区/做反了的代价",
            "position": "标题 + 前两段",
            "forbidden_moves": ["先讲概念再讲问题", "一上来就变成说明书", "标题像目录"],
        },
        "insight_strategy": {
            "goal": "让读者知道为什么这个方法值得用。",
            "trigger_mode": "步骤背后的原理 + 失败对照 + 边界",
            "position": "中段主展开区",
            "forbidden_moves": ["只列步骤不讲原因", "只有清单没有判断", "没有边界和反例"],
        },
        "takeaway_strategy": {
            "goal": "让读者愿意保存，之后直接拿来用。",
            "trigger_mode": "动作清单 / 模板 / SOP",
            "position": "最后 15%~20% 正文",
            "forbidden_moves": ["动作不够具体", "没有可复用结构", "只有情绪鼓励没有工具"],
            "allowed_shapes": ["动作清单", "模板", "SOP"],
            "heading_hint": "最后带走这份动作清单",
            "save_trigger_hint": "收藏这条，下次照着这套顺序直接做。",
        },
    }
    case_study = {
        "hook_strategy": {
            "goal": "先把读者带进案例的关键现场。",
            "trigger_mode": "结果倒挂 / 人物场景 / 冲突切口",
            "position": "标题 + 前两段",
            "forbidden_moves": ["先交代背景", "案例开头没有现场感", "热闹但没有问题"],
        },
        "insight_strategy": {
            "goal": "让读者带走比案例本身更值钱的判断。",
            "trigger_mode": "关键分水岭 + 复盘拆解 + 可迁移结论",
            "position": "中段主展开区",
            "forbidden_moves": ["流水账", "只复盘过程不提炼", "只有故事没有方法"],
        },
        "takeaway_strategy": {
            "goal": "让读者想把复盘框架留着以后照着看。",
            "trigger_mode": "迁移原则 / 决策提醒 / 复盘框架",
            "position": "最后 15%~20% 正文",
            "forbidden_moves": ["只讲感受", "只有评价没有框架", "只有提问没有带走内容"],
            "allowed_shapes": ["复盘框架", "迁移原则", "决策提醒"],
            "heading_hint": "最后带走这套复盘框架",
            "save_trigger_hint": "把这条留着，下次遇到类似案例时直接套这套看法。",
        },
    }
    narrative = {
        "hook_strategy": {
            "goal": "让读者觉得这就是自己会遇到的场景。",
            "trigger_mode": "人物/场景/一句刺心的话",
            "position": "标题 + 前两段",
            "forbidden_moves": ["空泛感慨", "先讲道理", "没有人物或动作"],
        },
        "insight_strategy": {
            "goal": "把情绪背后的新理解讲出来。",
            "trigger_mode": "新视角 + 对照 + 具体处境解释",
            "position": "中段主展开区",
            "forbidden_moves": ["只有情绪没有新理解", "只有共鸣没有增量", "只有安慰没有解释"],
        },
        "takeaway_strategy": {
            "goal": "让读者愿意把一句话或一张对照框留给以后。",
            "trigger_mode": "可复述判断 / 自测问题 / 处境对照框",
            "position": "最后 15%~20% 正文",
            "forbidden_moves": ["只留余味", "只剩提问", "没有带走的话或框架"],
            "allowed_shapes": ["可复述判断", "自测问题", "处境对照框"],
            "heading_hint": "最后带走这一句判断",
            "save_trigger_hint": "把这句话留着，下次情绪又上来的时候拿出来对照。",
        },
    }
    mapping = {
        "tutorial": tutorial,
        "case-study": case_study,
        "narrative": narrative,
        "commentary": commentary,
    }
    payload = mapping.get(str(archetype or "").strip().lower() or "commentary", commentary)
    if subject:
        payload = {key: {**value} for key, value in payload.items()}
        payload["hook_strategy"]["subject"] = subject
        payload["insight_strategy"]["subject"] = subject
        payload["takeaway_strategy"]["subject"] = subject
        payload["hook_strategy"]["audience"] = audience or "公众号读者"
    return payload


def normalize_layer_strategy(value: Any, default: dict[str, Any]) -> dict[str, Any]:
    result = dict(default or {})
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, list):
                cleaned = [str(part).strip() for part in item if str(part).strip()]
                if cleaned:
                    result[key] = cleaned
            elif item not in (None, ""):
                result[key] = str(item).strip() if isinstance(item, str) else item
    result.setdefault("goal", str(default.get("goal") or "").strip())
    result.setdefault("trigger_mode", str(default.get("trigger_mode") or "").strip())
    result.setdefault("position", str(default.get("position") or "").strip())
    result.setdefault("forbidden_moves", list(default.get("forbidden_moves") or []))
    result.setdefault("allowed_shapes", list(default.get("allowed_shapes") or []))
    result.setdefault("heading_hint", str(default.get("heading_hint") or "").strip())
    result.setdefault("save_trigger_hint", str(default.get("save_trigger_hint") or "").strip())
    return result


def build_takeaway_scaffold(strategy: dict[str, Any]) -> dict[str, Any]:
    subject = str(strategy.get("subject") or "这件事").strip()
    heading = str(strategy.get("heading_hint") or "最后带走这张卡").strip()
    save_trigger = str(strategy.get("save_trigger_hint") or "收藏这条，下次直接对照。").strip()
    shapes = [str(item).strip() for item in (strategy.get("allowed_shapes") or []) if str(item).strip()]
    primary_shape = shapes[0] if shapes else "判断卡"
    if primary_shape == "动作清单":
        core_line = f"把这份动作清单留着：下次再遇到 {subject}，先按这套顺序开始做。"
    elif primary_shape in {"模板", "SOP"}:
        core_line = f"把这套 {primary_shape} 留着：下次处理 {subject} 时，直接照着这套框架套。"
    elif primary_shape in {"复盘框架", "迁移原则", "决策提醒"}:
        core_line = f"把这套 {primary_shape} 留着：下次再遇到类似情况，先拿它对照再做判断。"
    elif primary_shape in {"可复述判断", "自测问题", "处境对照框"}:
        core_line = f"把这一句留着：下次情绪或处境再卡住时，先拿它来对照自己现在到底困在哪。"
    else:
        core_line = f"把这张{primary_shape}留着：下次再遇到 {subject}，先拿这条判断对照。"
    return {
        "heading": heading,
        "primary_shape": primary_shape,
        "allowed_shapes": shapes,
        "core_line": core_line,
        "save_trigger_line": save_trigger,
    }


def title_problem_alignment(title: str, body: str) -> dict[str, Any]:
    lead = " ".join(split_markdown_paragraphs(body)[:2])
    title_tokens = title_token_set(title)
    lead_tokens = _tokens(lead)
    overlap = _jaccard(title_tokens, lead_tokens)
    shared = sorted(title_tokens & lead_tokens)
    return {
        "score": round(overlap, 3),
        "shared_tokens": shared[:6],
        "passed": overlap >= 0.08 or len(shared) >= 1,
    }


def hook_layer_report(title: str, body: str, *, topic: str = "", audience: str = "") -> dict[str, Any]:
    first_screen = first_screen_signal_report(body)
    title_shape = title_hook_shape(title, topic=topic, audience=audience)
    alignment = title_problem_alignment(title, body)
    title_has_trigger = bool(any(re.search(pattern, str(title or "")) for pattern in HOOK_TRIGGER_PATTERNS) or title_shape.get("shape_score", 0) >= 2)
    lead_hook_passed = bool(
        int(first_screen.get("lead_paragraphs") or 0) >= 2
        and (
            (
                bool(first_screen.get("has_scene"))
                and (bool(first_screen.get("has_conflict")) or bool(first_screen.get("has_stakes")))
            )
            or (bool(first_screen.get("has_conflict")) and bool(first_screen.get("has_stakes")))
            or (
                str(first_screen.get("opening_route") or "") in {"news-hook", "news-inversion-entry", "cost-entry", "cost-upfront"}
                and bool(first_screen.get("has_stakes"))
            )
        )
    )
    alignment_passed = bool(alignment.get("passed") or (lead_hook_passed and title_has_trigger))
    score = 0
    score += 10 if title_has_trigger else 4
    score += 12 if lead_hook_passed else 4 + int(first_screen.get("has_scene")) * 2 + int(first_screen.get("has_conflict")) * 2 + int(first_screen.get("has_stakes")) * 2
    score += 8 if alignment_passed else 3
    alignment["passed"] = alignment_passed
    return {
        "score": min(30, int(score)),
        "passed": bool(title_has_trigger and lead_hook_passed and alignment_passed),
        "title_has_trigger": title_has_trigger,
        "lead_hook_passed": lead_hook_passed,
        "first_screen": first_screen,
        "alignment": alignment,
    }


def insight_layer_report(
    body: str,
    *,
    analysis: dict[str, Any] | None = None,
    depth: dict[str, Any] | None = None,
    material_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis = analysis or {}
    depth = depth or {}
    material_signals = material_signals or {}
    new_judgment_present = bool(str(analysis.get("core_viewpoint") or "").strip()) and (
        int(depth.get("counterpoint_paragraph_count") or 0) >= 1 or len(analysis.get("secondary_viewpoints") or []) >= 2
    )
    reusable_method_present = bool(
        material_signals.get("has_table")
        or int(material_signals.get("comparison_count") or 0) >= 1
        or int(material_signals.get("analogy_count") or 0) >= 1
        or re.search("|".join(REUSABLE_METHOD_PATTERNS), body or "")
    )
    information_gap_present = bool(
        int(depth.get("evidence_paragraph_count") or 0) >= 1
        and (
            int(material_signals.get("citation_count") or 0) >= 1
            or int(material_signals.get("coverage_count") or 0) >= 3
            or bool(material_signals.get("has_table"))
        )
    )
    expanded_explanation_present = bool(
        int(depth.get("long_paragraph_count") or 0) >= 1
        or int(depth.get("paragraph_count") or 0) >= 6
    )
    transferability_present = bool(
        material_signals.get("has_table")
        or int(material_signals.get("comparison_count") or 0) >= 1
        or int(material_signals.get("analogy_count") or 0) >= 1
        or reusable_method_present
    )
    core_hits = sum(1 for item in [new_judgment_present, reusable_method_present, information_gap_present] if item)
    score = 0
    score += 15 if new_judgment_present else 6
    score += 12 if reusable_method_present else 4
    score += 10 if information_gap_present else 3
    score += 4 if expanded_explanation_present else 0
    score += 4 if transferability_present else 0
    return {
        "score": min(45, int(score)),
        "passed": bool(core_hits >= 2 and expanded_explanation_present and transferability_present and information_gap_present),
        "new_judgment_present": new_judgment_present,
        "reusable_method_present": reusable_method_present,
        "information_gap_present": information_gap_present,
        "expanded_explanation_present": expanded_explanation_present,
        "transferability_present": transferability_present,
    }


def takeaway_layer_report(
    body: str,
    *,
    archetype: str,
    analysis: dict[str, Any] | None = None,
    material_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis = analysis or {}
    material_signals = material_signals or {}
    tail_paragraphs = _tail_paragraphs(body)
    tail_text = " ".join(tail_paragraphs)
    tail_headings = _tail_headings(body)
    takeaway_object_present = bool(
        any(re.search(pattern, tail_text) for pattern in TAKEAWAY_OBJECT_PATTERNS)
        or any(re.search(pattern, heading) for heading in tail_headings for pattern in TAKEAWAY_SECTION_PATTERNS)
        or (str(archetype or "").strip().lower() == "tutorial" and (material_signals.get("has_table") or re.search(r"步骤|清单|模板", tail_text)))
    )
    reusable_present = bool(
        takeaway_object_present
        or re.search("|".join(REUSABLE_METHOD_PATTERNS), tail_text)
        or material_signals.get("has_table")
    )
    save_trigger_present = bool(
        any(re.search(pattern, tail_text) for pattern in SAVE_TRIGGER_PATTERNS)
        or any(re.search(pattern, str(analysis.get("ending_interaction_design") or "")) for pattern in SAVE_TRIGGER_PATTERNS)
    )
    question_only = bool(discussion_trigger_present(tail_text) and not reusable_present)
    score = 0
    score += 10 if takeaway_object_present else 4
    score += 8 if reusable_present else 3
    score += 7 if save_trigger_present else 2
    return {
        "score": min(25, int(score)),
        "passed": bool(takeaway_object_present and reusable_present and save_trigger_present and not question_only),
        "tail_excerpt": tail_text[:220],
        "tail_headings": tail_headings,
        "takeaway_object_present": takeaway_object_present,
        "reusable_present": reusable_present,
        "save_trigger_present": save_trigger_present,
        "question_only": question_only,
    }


def build_three_layer_diagnostics(
    *,
    title: str,
    body: str,
    blueprint: dict[str, Any],
    analysis: dict[str, Any] | None = None,
    depth: dict[str, Any] | None = None,
    material_signals: dict[str, Any] | None = None,
    topic: str = "",
    audience: str = "",
) -> dict[str, Any]:
    hook = hook_layer_report(title, body, topic=topic or title, audience=audience)
    insight = insight_layer_report(body, analysis=analysis, depth=depth, material_signals=material_signals)
    takeaway = takeaway_layer_report(
        body,
        archetype=str((blueprint or {}).get("article_archetype") or "commentary"),
        analysis=analysis,
        material_signals=material_signals,
    )
    return {
        "hook": hook,
        "insight": insight,
        "takeaway": takeaway,
    }
