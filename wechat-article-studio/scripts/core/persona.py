from __future__ import annotations

import json
import re
from typing import Any


WRITING_PERSONA_LIBRARY: dict[str, dict[str, Any]] = {
    "industry-observer": {
        "name": "industry-observer",
        "label": "行业观察者",
        "voice_density": 0.42,
        "evidence_pattern": "signal -> evidence -> implication -> boundary",
        "paragraph_rhythm": "balanced",
        "sentence_variance_target": "medium",
        "emotional_arc": "restrained_to_insight",
        "opening_tendency": "signal-or-scene",
        "closing_tendency": "judgment-with-aftertaste",
        "allowed_devices": ["趋势判断", "案例回看", "风险提醒", "轻微反差"],
        "avoid_moves": ["过度抒情", "鸡血式口号", "大而空的结论", "为了传播硬造冲突"],
        "prompt_summary": "像成熟行业作者，先把信号和证据讲清，再给出有边界的判断。",
    },
    "cold-analyst": {
        "name": "cold-analyst",
        "label": "冷静研究员",
        "voice_density": 0.26,
        "evidence_pattern": "framework -> data -> caveat",
        "paragraph_rhythm": "structured",
        "sentence_variance_target": "medium-low",
        "emotional_arc": "flat_with_insight",
        "opening_tendency": "thesis",
        "closing_tendency": "implication",
        "allowed_devices": ["框架拆解", "数据对照", "口径提醒", "假设说明"],
        "avoid_moves": ["网络热词", "煽动情绪", "模糊表态", "无来源的数字"],
        "prompt_summary": "像研究型作者，重证据和口径，专业但不要僵成研报。",
    },
    "warm-editor": {
        "name": "warm-editor",
        "label": "温和编辑",
        "voice_density": 0.52,
        "evidence_pattern": "scene -> feeling -> explanation -> evidence",
        "paragraph_rhythm": "wave",
        "sentence_variance_target": "medium-high",
        "emotional_arc": "gentle_to_clear",
        "opening_tendency": "scene",
        "closing_tendency": "soft-echo",
        "allowed_devices": ["场景切口", "感受回扣", "轻判断", "温和提醒"],
        "avoid_moves": ["说教口吻", "硬清单", "过满的形容词", "模板化安慰"],
        "prompt_summary": "像有经验的编辑，先把人带进场景，再把判断讲透。",
    },
    "sharp-journalist": {
        "name": "sharp-journalist",
        "label": "锐评记者",
        "voice_density": 0.34,
        "evidence_pattern": "claim -> evidence -> twist",
        "paragraph_rhythm": "staccato",
        "sentence_variance_target": "high",
        "emotional_arc": "cold_open_to_sharp_close",
        "opening_tendency": "cold-open",
        "closing_tendency": "sharp-statement",
        "allowed_devices": ["短句推进", "冷事实", "反转句", "锋利判断"],
        "avoid_moves": ["拖沓铺垫", "含糊立场", "空心抒情", "万能方法论"],
        "prompt_summary": "像新闻评论作者，短、准、稳，证据先行，判断要利落。",
    },
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" -•\n\r\t")


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9\-]+", "-", str(value or "").strip().lower()).strip("-")


def _deepcopy(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False))


def _author_preferred_persona(author_memory: dict[str, Any]) -> str:
    preferred_styles = {
        _normalize_key(item)
        for item in ((author_memory.get("editorial_preferences") or {}).get("preferred_style_keys") or [])
        if _normalize_key(item)
    }
    voice = " ".join(str(item or "") for item in (author_memory.get("voice_fingerprint") or []))
    if any(key in preferred_styles for key in {"signal-briefing", "case-memo"}):
        return "industry-observer"
    if any(key in preferred_styles for key in {"counterintuitive-column", "qa-cross-exam"}):
        return "sharp-journalist"
    if any(key in preferred_styles for key in {"open-letter", "field-observation"}):
        return "warm-editor"
    if any(word in voice for word in ["官方", "数据", "研究", "报告", "框架"]):
        return "cold-analyst"
    if any(word in voice for word in ["场景", "对话", "温和", "余味"]):
        return "warm-editor"
    return ""


def choose_writing_persona(context: dict[str, Any]) -> dict[str, Any]:
    archetype = _normalize_key(str(context.get("article_archetype") or ""))
    content_mode = _normalize_key(str(context.get("content_mode") or ""))
    audience = _normalize_text(str(context.get("audience") or ""))
    author_memory = context.get("author_memory") or {}
    strategy = context.get("account_strategy") or {}
    target_reader = _normalize_key(str(strategy.get("target_reader") or ""))
    primary_goal = _normalize_key(str(strategy.get("primary_goal") or ""))
    preferred_persona = _normalize_key(str(strategy.get("preferred_persona") or ""))

    explicit = _normalize_key(str(context.get("writing_persona") or context.get("persona") or ""))
    if explicit in WRITING_PERSONA_LIBRARY:
        return _deepcopy(WRITING_PERSONA_LIBRARY[explicit])
    if preferred_persona in WRITING_PERSONA_LIBRARY and content_mode != "tech-credible":
        if target_reader == "general-tech" and primary_goal == "open-and-read" and archetype in {"commentary", "case-study", "comparison"}:
            return _deepcopy(WRITING_PERSONA_LIBRARY[preferred_persona])

    preferred = _author_preferred_persona(author_memory if isinstance(author_memory, dict) else {})
    if preferred in WRITING_PERSONA_LIBRARY and archetype not in {"narrative"}:
        if content_mode == "tech-credible" and preferred != "warm-editor":
            return _deepcopy(WRITING_PERSONA_LIBRARY["cold-analyst"])
        return _deepcopy(WRITING_PERSONA_LIBRARY[preferred])

    if archetype == "narrative":
        return _deepcopy(WRITING_PERSONA_LIBRARY["warm-editor"])
    if archetype == "tutorial":
        return _deepcopy(WRITING_PERSONA_LIBRARY["industry-observer"])
    if content_mode == "tech-credible":
        return _deepcopy(WRITING_PERSONA_LIBRARY["cold-analyst"])
    if archetype == "case-study":
        if target_reader == "general-tech" and primary_goal == "open-and-read":
            return _deepcopy(WRITING_PERSONA_LIBRARY["warm-editor"])
        return _deepcopy(WRITING_PERSONA_LIBRARY["industry-observer"])
    if content_mode == "viral" and archetype in {"commentary", "case-study"}:
        return _deepcopy(WRITING_PERSONA_LIBRARY["sharp-journalist"])
    if any(word in audience for word in ["研究", "咨询", "投资", "企业负责人", "管理者"]):
        return _deepcopy(WRITING_PERSONA_LIBRARY["cold-analyst"])
    if target_reader == "general-tech" and primary_goal == "open-and-read":
        return _deepcopy(WRITING_PERSONA_LIBRARY["warm-editor"])
    return _deepcopy(WRITING_PERSONA_LIBRARY["industry-observer"])


def normalize_writing_persona(payload: Any, context: dict[str, Any]) -> dict[str, Any]:
    base = choose_writing_persona(context)
    source: dict[str, Any] = {}
    if isinstance(payload, str):
        key = _normalize_key(payload)
        if key in WRITING_PERSONA_LIBRARY:
            return _deepcopy(WRITING_PERSONA_LIBRARY[key])
    elif isinstance(payload, dict):
        source = dict(payload)
        key = _normalize_key(str(source.get("name") or source.get("key") or source.get("persona") or ""))
        if key in WRITING_PERSONA_LIBRARY:
            base = _deepcopy(WRITING_PERSONA_LIBRARY[key])

    merged = dict(base)
    for field in [
        "name",
        "label",
        "evidence_pattern",
        "paragraph_rhythm",
        "sentence_variance_target",
        "emotional_arc",
        "opening_tendency",
        "closing_tendency",
        "prompt_summary",
    ]:
        value = _normalize_text(str(source.get(field) or ""))
        if value:
            merged[field] = value
    for field in ["voice_density"]:
        try:
            value = float(source.get(field))
        except (TypeError, ValueError):
            continue
        merged[field] = max(0.0, min(1.0, round(value, 2)))
    for field in ["allowed_devices", "avoid_moves"]:
        value = source.get(field)
        if isinstance(value, list):
            items = [_normalize_text(str(item)) for item in value if _normalize_text(str(item))]
            if items:
                merged[field] = items[:8]
    return merged
