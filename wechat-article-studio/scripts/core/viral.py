from __future__ import annotations

import json
import re
from typing import Any

import legacy_studio as legacy


VIRAL_BLUEPRINT_FIELDS = [
    "core_viewpoint",
    "secondary_viewpoints",
    "persuasion_strategies",
    "emotion_triggers",
    "target_quotes",
    "emotion_curve",
    "emotion_layers",
    "argument_modes",
    "perspective_shifts",
    "style_traits",
    "pain_points",
    "emotion_value_goals",
]

SCORE_WEIGHTS: list[tuple[str, int]] = [
    ("标题与开头爆点", 12),
    ("核心观点与副观点", 10),
    ("说服策略与论证多样性", 12),
    ("情绪触发与刺痛感", 12),
    ("金句与传播句密度", 10),
    ("情感曲线与节奏", 8),
    ("情感层次与共鸣", 8),
    ("视角转化与认知增量", 8),
    ("语言风格自然度", 10),
    ("可信度与检索支撑", 10),
]

DEFAULT_THRESHOLD = 88

EMOTION_VALUE_THRESHOLD = 6
PAIN_POINT_THRESHOLD = 4
SIGNATURE_LINE_THRESHOLD = 3
ARGUMENT_MODE_THRESHOLD = 3
PERSPECTIVE_SHIFT_THRESHOLD = 2
AI_SMELL_THRESHOLD = 2
CREDIBILITY_THRESHOLD = 6

EMOTION_VALUE_MARKERS = [
    "你不是",
    "你会发现",
    "别急着",
    "没关系",
    "这很正常",
    "不是你",
    "你并不",
    "可以先",
    "至少",
    "先别",
    "真正让人",
    "其实你",
    "放心",
    "说白了",
]

PAIN_POINT_MARKERS = [
    "焦虑",
    "卡住",
    "被淘汰",
    "越学越",
    "代价",
    "吃亏",
    "误判",
    "浪费",
    "没结果",
    "拖住",
    "困住",
    "不甘心",
    "刺痛",
    "害怕",
    "不敢",
    "最难受",
]

PERSUASION_MARKERS: dict[str, list[str]] = {
    "数据论证": [r"\d+(?:\.\d+)?%?", r"\d{4}年", r"\d+倍", r"\d+个"],
    "案例论证": [r"案例", r"比如", r"例如", r"有人", r"一个朋友", r"某家公司"],
    "对比论证": [r"不是.+而是", r"一边.+一边", r"对比", r"反而", r"但真正"],
    "拆解论证": [r"拆开看", r"拆解", r"分成", r"底层", r"本质"],
    "步骤论证": [r"第一", r"第二", r"第三", r"步骤", r"清单", r"先.+再"],
    "权威论证": [r"官方", r"报告", r"研究", r"数据显示", r"文档"],
    "场景论证": [r"场景", r"故事", r"那一刻", r"如果你", r"想象一下"],
}

EMOTION_LAYER_MARKERS: dict[str, list[str]] = {
    "焦虑层": ["焦虑", "担心", "害怕", "慌", "不安"],
    "自证层": ["不是你不行", "你不是", "这很正常", "别急着否定自己"],
    "理解层": ["真正的问题", "先把话说清楚", "本质上", "说白了"],
    "行动层": ["先做", "现在就", "今天", "接下来", "至少先"],
    "希望层": ["机会", "还有空间", "来得及", "能做到", "长期优势"],
}

STYLE_TRAIT_PATTERNS: list[tuple[str, list[str]]] = [
    ("短句推进", [r"。", r"！", r"？"]),
    ("直接下判断", [r"先说结论", r"说白了", r"真正", r"本质上", r"一句话"]),
    ("对比感强", [r"不是.+而是", r"但", r"却", r"反而"]),
    ("读者对话", [r"你", r"我们", r"别急", r"你会发现"]),
    ("行动导向", [r"先做", r"马上", r"今天", r"清单", r"步骤"]),
]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw or "")).strip(" -•\n\t")
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _ensure_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""
    if text[-1] not in "。！？!?；;":
        text += "。"
    return text


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _dedupe([str(item) for item in value])
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if "\n" in raw:
            parts = []
            for line in raw.splitlines():
                cleaned = re.sub(r"^[\-\*\d\.、\s]+", "", line).strip()
                if cleaned:
                    parts.append(cleaned)
            return _dedupe(parts)
        parts = [item.strip() for item in re.split(r"[；;。]\s*", raw) if item.strip()]
        return _dedupe(parts)
    return []


def _first_paragraphs(body: str, limit: int = 2) -> list[str]:
    paragraphs = []
    for block in legacy.list_paragraphs(body):
        if block.startswith("#"):
            continue
        paragraphs.append(block)
        if len(paragraphs) >= limit:
            break
    return paragraphs


def _clean_sentence(sentence: str) -> str:
    text = re.sub(r"^[-*>\d\.\s]+", "", sentence or "").strip()
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _section_heading_for_offset(body: str, sentence: str) -> str:
    current = "导语"
    for block in body.splitlines():
        line = block.strip()
        if re.match(r"^#{2,4}\s+", line):
            current = re.sub(r"^#{2,4}\s+", "", line).strip()
        if sentence[:12] and sentence[:12] in line:
            return current
    return current


def _sentence_objects(body: str, sentences: list[str], reason: str) -> list[dict[str, Any]]:
    payload = []
    for index, sentence in enumerate(_dedupe(sentences), start=1):
        cleaned = _ensure_sentence(_clean_sentence(sentence))
        if not cleaned:
            continue
        strength = min(1.0, round((legacy.cjk_len(cleaned) / 28), 2))
        payload.append(
            {
                "text": cleaned,
                "section_heading": _section_heading_for_offset(body, cleaned),
                "reason": reason,
                "strength": max(0.2, strength),
                "rank": index,
            }
        )
    return payload


def default_viral_blueprint(
    *,
    topic: str,
    title: str,
    angle: str,
    audience: str,
    research: dict[str, Any] | None = None,
    style_signals: list[str] | None = None,
) -> dict[str, Any]:
    research = research or {}
    style_signals = style_signals or []
    key_phrase = angle or topic or title or "这个主题"
    audience_text = audience or "公众号读者"
    style_defaults = _dedupe([*style_signals, "短段落", "判断句优先", "少模板连接词", "像真人编辑一样推进"])
    return {
        "core_viewpoint": _ensure_sentence(f"{key_phrase} 真正拉开差距的，不是信息更多，而是判断更准、动作更稳"),
        "secondary_viewpoints": [
            _ensure_sentence(f"{audience_text} 最容易被表面热闹牵着走，忽略真正起作用的底层动作"),
            _ensure_sentence("真正能带来传播和转化的内容，必须同时给出认知增量和情绪价值"),
            _ensure_sentence("文章要让读者一边被刺痛，一边觉得自己还有办法"),
        ],
        "persuasion_strategies": ["反常识判断", "场景代入", "步骤拆解", "案例或数据支撑"],
        "emotion_triggers": ["怕掉队", "怕努力没有结果", "想找到抓手", "希望尽快看到变化"],
        "target_quotes": [
            _ensure_sentence(f"{key_phrase} 不是你知道得不够多，而是你还没抓住真正决定结果的那一下"),
            _ensure_sentence("读者愿意转发的，从来不是信息堆积，而是那句替他把心里话说出来的话"),
            _ensure_sentence("真正有用的内容，不是让人点头，而是让人当场想保存"),
        ],
        "emotion_curve": [
            {"stage": "开头", "emotion": "刺痛", "goal": "让读者停下来"},
            {"stage": "中段", "emotion": "理解", "goal": "把问题讲透"},
            {"stage": "后段", "emotion": "希望", "goal": "让读者觉得自己能做"},
            {"stage": "结尾", "emotion": "行动", "goal": "促成收藏或转发"},
        ],
        "emotion_layers": ["焦虑层", "自证层", "理解层", "行动层", "希望层"],
        "argument_modes": ["对比", "拆解", "案例", "行动清单"],
        "perspective_shifts": ["读者视角", "旁观者视角", "编辑判断视角"],
        "style_traits": style_defaults[:5],
        "pain_points": [
            _ensure_sentence(f"{audience_text} 很容易越学越忙，却迟迟看不到结果"),
            _ensure_sentence("文章一旦只剩正确废话，读者会立刻划走"),
            _ensure_sentence("没有情绪价值的干货，往往只能被看见，不能被记住"),
        ],
        "emotion_value_goals": [
            "让读者觉得被理解",
            "让读者觉得问题说到了心口",
            "让读者获得一个马上能执行的动作",
        ],
    }


def blueprint_complete(blueprint: dict[str, Any] | None) -> bool:
    if not blueprint:
        return False
    for field in VIRAL_BLUEPRINT_FIELDS:
        value = blueprint.get(field)
        if isinstance(value, str):
            if not value.strip():
                return False
        elif isinstance(value, list):
            if not any(str(item).strip() for item in value):
                return False
        else:
            return False
    return True


def normalize_viral_blueprint(payload: Any, context: dict[str, Any]) -> dict[str, Any]:
    base = default_viral_blueprint(
        topic=str(context.get("topic") or context.get("selected_title") or context.get("title") or ""),
        title=str(context.get("selected_title") or context.get("title") or context.get("topic") or ""),
        angle=str(context.get("direction") or context.get("angle") or ""),
        audience=str(context.get("audience") or "大众读者"),
        research=context.get("research") or {},
        style_signals=context.get("style_signals") or [],
    )
    if isinstance(payload, dict):
        source = payload
    else:
        source = {}
    merged = dict(base)
    for field in VIRAL_BLUEPRINT_FIELDS:
        if field not in source:
            continue
        if isinstance(base[field], str):
            text = str(source.get(field) or "").strip()
            if text:
                merged[field] = _ensure_sentence(text)
        else:
            items = _normalize_list(source.get(field))
            if items:
                if field == "emotion_curve":
                    merged[field] = [
                        {"stage": f"阶段 {index}", "emotion": item, "goal": item}
                        for index, item in enumerate(items, start=1)
                    ]
                else:
                    merged[field] = [_ensure_sentence(item) if field in {"secondary_viewpoints", "target_quotes", "pain_points"} else item for item in items]
    curve = source.get("emotion_curve")
    if isinstance(curve, list) and curve:
        normalized_curve = []
        for entry in curve:
            if isinstance(entry, dict):
                stage = str(entry.get("stage") or entry.get("section") or entry.get("phase") or "").strip() or f"阶段 {len(normalized_curve) + 1}"
                emotion = str(entry.get("emotion") or entry.get("feeling") or entry.get("value") or "").strip() or stage
                goal = str(entry.get("goal") or entry.get("purpose") or emotion).strip() or emotion
                normalized_curve.append({"stage": stage, "emotion": emotion, "goal": goal})
            else:
                text = str(entry).strip()
                if text:
                    normalized_curve.append({"stage": f"阶段 {len(normalized_curve) + 1}", "emotion": text, "goal": text})
        if normalized_curve:
            merged["emotion_curve"] = normalized_curve
    return merged


def normalize_outline_payload(payload: Any, context: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        output = dict(payload)
    else:
        output = {}
    title = str(output.get("title") or context.get("selected_title") or context.get("title") or context.get("topic") or "未命名标题")
    angle = str(output.get("angle") or context.get("direction") or context.get("angle") or "")
    sections = output.get("sections")
    normalized_sections: list[dict[str, Any]] = []
    if isinstance(sections, list):
        for item in sections:
            if isinstance(item, dict):
                heading = str(item.get("heading") or item.get("title") or "").strip()
                if not heading:
                    continue
                normalized_sections.append(
                    {
                        "heading": heading,
                        "goal": str(item.get("goal") or item.get("purpose") or "展开该章节").strip(),
                        "evidence_need": str(item.get("evidence_need") or item.get("evidence") or "补充案例或事实支撑").strip(),
                    }
                )
            else:
                heading = str(item or "").strip()
                if heading:
                    normalized_sections.append({"heading": heading, "goal": "展开该章节", "evidence_need": "补充案例或事实支撑"})
    if not normalized_sections:
        normalized_sections = [
            {"heading": "先把问题说透", "goal": "建立阅读动机和刺痛感", "evidence_need": "场景或结果对比"},
            {"heading": "真正决定结果的分水岭", "goal": "讲清主观点与副观点", "evidence_need": "拆解或案例"},
            {"heading": "把判断变成动作", "goal": "给出读者能执行的路径", "evidence_need": "步骤或清单"},
            {"heading": "最后把动作落地", "goal": "收束并促成收藏转发", "evidence_need": "一句行动建议"},
        ]
    output["title"] = title
    output["angle"] = angle
    output["sections"] = normalized_sections
    output["viral_blueprint"] = normalize_viral_blueprint(output.get("viral_blueprint"), context | {"selected_title": title, "angle": angle})
    return output


def _extract_signatures(body: str) -> list[str]:
    quotes = list(legacy.extract_candidate_quotes(body))
    for match in re.findall(r"\*\*(.+?)\*\*", body, flags=re.S):
        cleaned = _clean_sentence(match)
        if 10 <= legacy.cjk_len(cleaned) <= 42:
            quotes.append(cleaned)
    for block in re.findall(r"^>\s*(.+)$", body, flags=re.M):
        cleaned = _clean_sentence(block)
        if 10 <= legacy.cjk_len(cleaned) <= 42:
            quotes.append(cleaned)
    return [_ensure_sentence(item) for item in _dedupe(quotes)[:8]]


def _extract_sentences_by_markers(body: str, markers: list[str], *, require_you: bool = False) -> list[str]:
    hits: list[str] = []
    clean_body = re.sub(r"^#{1,6}\s+", "", body, flags=re.M)
    for sentence in legacy.sentence_split(clean_body):
        cleaned = _clean_sentence(sentence)
        if legacy.cjk_len(cleaned) < 12:
            continue
        if require_you and "你" not in cleaned and "读者" not in cleaned:
            continue
        if any(marker in cleaned for marker in markers):
            hits.append(cleaned)
    return _dedupe(hits)


def _emotion_curve_from_body(body: str, headings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = _first_paragraphs(body, limit=3)
    curve: list[dict[str, Any]] = []
    intro = " ".join(blocks)
    if intro:
        curve.append({"stage": "开头", "emotion": "刺痛" if any(word in intro for word in PAIN_POINT_MARKERS) else "悬念", "goal": "让读者继续往下读"})
    for heading in headings[:2]:
        text = heading.get("text") or "正文"
        emotion = "理解"
        if re.search(r"方法|怎么|如何|步骤|清单", text):
            emotion = "掌控感"
        elif re.search(r"为什么|本质|真相|误区", text):
            emotion = "醒悟"
        curve.append({"stage": text, "emotion": emotion, "goal": "推进认知增量"})
    curve.append({"stage": "结尾", "emotion": "行动", "goal": "促成收藏或转发"})
    return curve[:4]


def _emotion_layers(body: str) -> list[str]:
    hits = []
    for name, markers in EMOTION_LAYER_MARKERS.items():
        if any(marker in body for marker in markers):
            hits.append(name)
    return hits or ["理解层", "行动层"]


def _argument_modes(body: str, blueprint: dict[str, Any] | None = None) -> list[str]:
    text = body or ""
    modes: list[str] = []
    for name, patterns in PERSUASION_MARKERS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                modes.append(name)
                break
    if blueprint:
        modes.extend(_normalize_list(blueprint.get("argument_modes")))
        modes.extend(_normalize_list(blueprint.get("persuasion_strategies")))
    return _dedupe(modes)


def _perspective_shifts(body: str, blueprint: dict[str, Any] | None = None) -> list[str]:
    shifts: list[str] = []
    if "你" in body or "读者" in body:
        shifts.append("读者视角")
    if "我们" in body:
        shifts.append("同行/群体视角")
    if any(word in body for word in ["很多人", "大多数人", "普通人"]):
        shifts.append("旁观者视角")
    if any(word in body for word in ["编辑", "运营", "作者", "我更想提醒"]):
        shifts.append("编辑判断视角")
    if blueprint:
        shifts.extend(_normalize_list(blueprint.get("perspective_shifts")))
    return _dedupe(shifts)


def _style_traits(body: str, blueprint: dict[str, Any] | None = None) -> list[str]:
    traits: list[str] = []
    for name, patterns in STYLE_TRAIT_PATTERNS:
        if any(re.search(pattern, body) for pattern in patterns):
            traits.append(name)
    if blueprint:
        traits.extend(_normalize_list(blueprint.get("style_traits")))
    return _dedupe(traits)[:6]


def _ai_smell_findings(body: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for phrase in getattr(legacy, "AI_STYLE_PHRASES", []) or []:
        hit_count = body.count(phrase)
        if not hit_count:
            continue
        findings.append({"type": "template_phrase", "pattern": phrase, "count": hit_count, "evidence": phrase})
    sentence_lengths = [legacy.cjk_len(sentence) for sentence in legacy.sentence_split(body)]
    if sentence_lengths:
        long_sentences = [length for length in sentence_lengths if length >= 55]
        if len(long_sentences) >= 3:
            findings.append({"type": "long_sentence_cluster", "pattern": "long_sentence", "count": len(long_sentences), "evidence": f"{len(long_sentences)} 个长句"})
    if body.count("首先") + body.count("其次") + body.count("最后") >= 2:
        findings.append({"type": "enumeration_voice", "pattern": "首先/其次/最后", "count": body.count("首先") + body.count("其次") + body.count("最后"), "evidence": "枚举式模板推进"})
    return findings


def build_heuristic_review(
    title: str,
    body: str,
    manifest: dict[str, Any],
    *,
    blueprint: dict[str, Any] | None = None,
    revision_round: int = 1,
    review_source: str = "heuristic",
    confidence: float = 0.58,
) -> dict[str, Any]:
    body = legacy.strip_image_directives(body)
    headings = legacy.extract_headings(body)
    intro = " ".join(_first_paragraphs(body, limit=2))
    blueprint = normalize_viral_blueprint(
        blueprint or manifest.get("viral_blueprint"),
        {
            "topic": manifest.get("topic") or title,
            "selected_title": title,
            "direction": manifest.get("direction") or "",
            "audience": manifest.get("audience") or "大众读者",
            "research": {},
            "style_signals": manifest.get("style_signals") or [],
        },
    )
    core_viewpoint = _ensure_sentence(
        blueprint.get("core_viewpoint")
        or intro
        or f"{title} 真正要说明的，是别再被表面信息带着跑，而要抓住真正决定结果的动作"
    )
    secondary_viewpoints = _dedupe(
        [_ensure_sentence(item) for item in _normalize_list(blueprint.get("secondary_viewpoints"))]
        + [_ensure_sentence(re.sub(r"[#*]", "", item.get("text") or "")) for item in headings[:3]]
    )[:4]
    argument_modes = _argument_modes(body, blueprint)
    emotion_value_sentences = _sentence_objects(body, _extract_sentences_by_markers(body, EMOTION_VALUE_MARKERS, require_you=True), "给读者情绪价值")
    pain_point_sentences = _sentence_objects(body, _extract_sentences_by_markers(body, PAIN_POINT_MARKERS), "刺痛读者处境")
    signature_lines = _sentence_objects(body, _extract_signatures(body), "可截图传播")
    ai_smell_findings = _ai_smell_findings(body)
    perspective_shifts = _perspective_shifts(body, blueprint)
    emotion_curve = _emotion_curve_from_body(body, headings)
    emotion_layers = _emotion_layers(body)
    style_traits = _style_traits(body, blueprint)
    strengths: list[str] = []
    issues: list[str] = []
    if len(signature_lines) >= SIGNATURE_LINE_THRESHOLD:
        strengths.append("文中已有可截图传播的金句密度。")
    else:
        issues.append("金句和传播句密度不够，缺少能单独流通的判断句。")
    if len(emotion_value_sentences) >= EMOTION_VALUE_THRESHOLD:
        strengths.append("文章能给读者明确的理解感和被安顿感。")
    else:
        issues.append("情绪价值不足，读者容易只看到信息，看不到被理解。")
    if len(pain_point_sentences) >= PAIN_POINT_THRESHOLD:
        strengths.append("文章能刺到读者真实处境，具备停留点。")
    else:
        issues.append("刺痛句不足，开头和中段还不够扎心。")
    if len(argument_modes) >= ARGUMENT_MODE_THRESHOLD:
        strengths.append("论证方式不是单一说教，具备拆解与对比。")
    else:
        issues.append("论证方式偏单一，需要补案例、对比或步骤。")
    if ai_smell_findings:
        issues.append("模板化表达仍然明显，需要进一步去 AI 味。")
    else:
        strengths.append("整体语言相对自然，没有明显模板腔堆积。")
    summary = (
        f"《{title}》当前稿件已经围绕“{core_viewpoint.rstrip('。')}”展开，"
        f"但仍需重点补强{('、'.join(item.rstrip('。') for item in issues[:3])) or '传播爆点与情绪价值'}。"
    )
    revision_priorities = _dedupe(
        [
            "补开头爆点与首屏刺痛感" if len(pain_point_sentences) < PAIN_POINT_THRESHOLD else "",
            "补情绪价值句，让读者感到被理解" if len(emotion_value_sentences) < EMOTION_VALUE_THRESHOLD else "",
            "补案例/对比/步骤，提升论证多样性" if len(argument_modes) < ARGUMENT_MODE_THRESHOLD else "",
            "补金句与可截图传播句" if len(signature_lines) < SIGNATURE_LINE_THRESHOLD else "",
            "清理模板连接词，继续去 AI 味" if ai_smell_findings else "",
        ]
    )
    return {
        "summary": summary,
        "findings": strengths + issues,
        "strengths": strengths,
        "issues": issues,
        "platform_notes": [
            "公众号正文优先短段落、强判断句和 2~4 级情绪推进。",
            "不要把爆款理解成堆砌形容词，而是要让读者被刺痛、被理解、被推动。",
        ],
        "viral_analysis": {
            "core_viewpoint": core_viewpoint,
            "secondary_viewpoints": secondary_viewpoints[:4],
            "persuasion_strategies": _dedupe(_normalize_list(blueprint.get("persuasion_strategies")) + argument_modes)[:5],
            "emotion_triggers": _dedupe(_normalize_list(blueprint.get("emotion_triggers")) + ["怕掉队" if pain_point_sentences else "", "想找到抓手" if emotion_value_sentences else ""])[:5],
            "signature_lines": signature_lines[:6],
            "emotion_curve": emotion_curve,
            "emotion_layers": emotion_layers,
            "argument_diversity": argument_modes[:6],
            "perspective_shifts": perspective_shifts[:5],
            "style_traits": style_traits[:6],
        },
        "emotion_value_sentences": emotion_value_sentences[:8],
        "pain_point_sentences": pain_point_sentences[:8],
        "ai_smell_findings": ai_smell_findings,
        "revision_priorities": revision_priorities,
        "revision_round": revision_round,
        "review_source": review_source,
        "source": review_source,
        "confidence": confidence,
        "generated_at": legacy.now_iso(),
    }


def normalize_review_payload(
    payload: Any,
    *,
    title: str,
    body: str,
    manifest: dict[str, Any],
    blueprint: dict[str, Any] | None = None,
    revision_round: int = 1,
    review_source: str = "provider",
) -> dict[str, Any]:
    heuristic = build_heuristic_review(
        title,
        body,
        manifest,
        blueprint=blueprint,
        revision_round=revision_round,
        review_source=review_source,
        confidence=0.72 if review_source != "heuristic" else 0.58,
    )
    if not isinstance(payload, dict):
        return heuristic
    result = json.loads(json.dumps(heuristic, ensure_ascii=False))
    value = str(payload.get("summary") or "").strip()
    if value:
        result["summary"] = value
    findings = _normalize_list(payload.get("findings"))
    strengths = _normalize_list(payload.get("strengths"))
    issues = _normalize_list(payload.get("issues"))
    platform_notes = _normalize_list(payload.get("platform_notes"))
    if findings:
        result["findings"] = findings
    if strengths:
        result["strengths"] = strengths
    if issues:
        result["issues"] = issues
    if platform_notes:
        result["platform_notes"] = platform_notes
    provider_analysis = payload.get("viral_analysis") if isinstance(payload.get("viral_analysis"), dict) else {}
    merged_analysis = dict(result["viral_analysis"])
    for field, base_value in merged_analysis.items():
        provider_value = provider_analysis.get(field) if provider_analysis else payload.get(field)
        if isinstance(base_value, str):
            text = str(provider_value or "").strip()
            if text:
                merged_analysis[field] = _ensure_sentence(text)
        elif field == "signature_lines":
            extra = []
            if isinstance(provider_value, list):
                for item in provider_value:
                    if isinstance(item, dict):
                        extra.append(str(item.get("text") or ""))
                    else:
                        extra.append(str(item))
            merged_analysis[field] = _sentence_objects(body, extra + [item["text"] for item in base_value], "可截图传播")[:8]
        elif field == "emotion_curve":
            if isinstance(provider_value, list):
                normalized_curve = []
                for entry in provider_value:
                    if isinstance(entry, dict):
                        stage = str(entry.get("stage") or entry.get("section") or "").strip() or f"阶段 {len(normalized_curve) + 1}"
                        emotion = str(entry.get("emotion") or entry.get("value") or stage).strip()
                        goal = str(entry.get("goal") or emotion).strip()
                        normalized_curve.append({"stage": stage, "emotion": emotion, "goal": goal})
                    else:
                        text = str(entry).strip()
                        if text:
                            normalized_curve.append({"stage": f"阶段 {len(normalized_curve) + 1}", "emotion": text, "goal": text})
                if normalized_curve:
                    merged_analysis[field] = normalized_curve[:6]
        else:
            items = _normalize_list(provider_value)
            if items:
                merged_analysis[field] = items[:6]
    result["viral_analysis"] = merged_analysis
    emotion_value_sentences = payload.get("emotion_value_sentences")
    if emotion_value_sentences:
        values = []
        for item in emotion_value_sentences:
            if isinstance(item, dict):
                values.append(str(item.get("text") or ""))
            else:
                values.append(str(item))
        result["emotion_value_sentences"] = _sentence_objects(body, values, "给读者情绪价值")[:8]
    pain_point_sentences = payload.get("pain_point_sentences")
    if pain_point_sentences:
        values = []
        for item in pain_point_sentences:
            if isinstance(item, dict):
                values.append(str(item.get("text") or ""))
            else:
                values.append(str(item))
        result["pain_point_sentences"] = _sentence_objects(body, values, "刺痛读者处境")[:8]
    ai_smell = payload.get("ai_smell_findings")
    if isinstance(ai_smell, list) and ai_smell:
        normalized_findings = []
        for item in ai_smell:
            if isinstance(item, dict):
                normalized_findings.append(
                    {
                        "type": str(item.get("type") or item.get("kind") or "provider").strip() or "provider",
                        "pattern": str(item.get("pattern") or item.get("label") or item.get("text") or "").strip(),
                        "count": int(item.get("count") or 1),
                        "evidence": str(item.get("evidence") or item.get("text") or item.get("pattern") or "").strip(),
                    }
                )
            else:
                text = str(item).strip()
                if text:
                    normalized_findings.append({"type": "provider", "pattern": text, "count": 1, "evidence": text})
        if normalized_findings:
            result["ai_smell_findings"] = normalized_findings
    priorities = _normalize_list(payload.get("revision_priorities"))
    if priorities:
        result["revision_priorities"] = priorities
    result["review_source"] = review_source
    result["source"] = review_source
    result["confidence"] = float(payload.get("confidence") or result.get("confidence") or 0.72)
    result["revision_round"] = int(payload.get("revision_round") or revision_round)
    result["generated_at"] = legacy.now_iso()
    return result


def _score_hot_intro(title: str, body: str, review: dict[str, Any]) -> tuple[int, str]:
    intro = legacy.intro_text(body)
    score = 3
    score += min(3, legacy.count_occurrences(title, getattr(legacy, "TITLE_CURIOSITY_WORDS", [])))
    score += min(2, legacy.count_occurrences(intro, getattr(legacy, "HOOK_WORDS", [])))
    if any(word in intro for word in PAIN_POINT_MARKERS):
        score += 2
    if any(word in intro for word in ["先说结论", "结果是", "但真正", "多数人"]):
        score += 1
    if review.get("pain_point_sentences"):
        score += 1
    return min(12, score), "标题和开头要同时制造反差、结果预期和首屏刺痛感。"


def _score_viewpoints(review: dict[str, Any]) -> tuple[int, str]:
    core = str(review.get("viral_analysis", {}).get("core_viewpoint") or "").strip()
    secondary = _normalize_list(review.get("viral_analysis", {}).get("secondary_viewpoints"))
    score = 3
    if core:
        score += 3
    score += min(4, len(secondary))
    return min(10, score), "文章需要一个主观点打穿全文，并有 2~4 个副观点负责展开。"


def _score_argument_diversity(review: dict[str, Any]) -> tuple[int, str]:
    modes = _normalize_list(review.get("viral_analysis", {}).get("argument_diversity"))
    strategies = _normalize_list(review.get("viral_analysis", {}).get("persuasion_strategies"))
    score = min(12, 2 + len(_dedupe(modes + strategies)) * 2)
    return score, "爆款稿不靠单向说教，至少要有拆解、对比、案例、步骤中的三种。"


def _score_emotion_trigger(review: dict[str, Any]) -> tuple[int, str]:
    emotion_count = len(review.get("emotion_value_sentences") or [])
    pain_count = len(review.get("pain_point_sentences") or [])
    score = min(12, 2 + min(5, emotion_count // 2) + min(5, pain_count))
    return score, "既要刺痛现实，也要给读者被理解和被托住的感觉。"


def _score_signature(review: dict[str, Any]) -> tuple[int, str]:
    count = len(review.get("viral_analysis", {}).get("signature_lines") or [])
    score = min(10, 1 + count * 3)
    return score, "金句要足够短、够准、能被截图和复述。"


def _score_emotion_curve(review: dict[str, Any], body: str) -> tuple[int, str]:
    curve_count = len(review.get("viral_analysis", {}).get("emotion_curve") or [])
    paragraph_count = len(legacy.list_paragraphs(body))
    score = 2
    if curve_count >= 3:
        score += 4
    if 6 <= paragraph_count <= 20:
        score += 2
    return min(8, score), "情绪推进要有起伏，从刺痛到理解，再到行动和希望。"


def _score_emotion_layers(review: dict[str, Any]) -> tuple[int, str]:
    layers = _normalize_list(review.get("viral_analysis", {}).get("emotion_layers"))
    score = min(8, 2 + len(layers))
    return score, "不要只有一种情绪，至少要能看到焦虑、理解、行动、希望中的多层推进。"


def _score_perspective(review: dict[str, Any]) -> tuple[int, str]:
    shifts = _normalize_list(review.get("viral_analysis", {}).get("perspective_shifts"))
    score = min(8, 2 + len(shifts) * 2)
    return score, "视角切换会带来认知增量，避免全文只站在一个角度说话。"


def _score_style(review: dict[str, Any], body: str) -> tuple[int, str]:
    ai_hits = len(review.get("ai_smell_findings") or [])
    sentence_lengths = [legacy.cjk_len(sentence) for sentence in legacy.sentence_split(body)]
    score = 8 - min(4, ai_hits * 2)
    if sentence_lengths and max(sentence_lengths) - min(sentence_lengths) >= 12:
        score += 1
    if any(word in body for word in ["你", "我们", "别急", "说白了"]):
        score += 1
    return int(legacy.clamp(score, 0, 10)), "像真人写出来的稿子，应该有判断感、节奏感和去模板腔的表达。"


def _score_credibility(body: str, manifest: dict[str, Any], review: dict[str, Any]) -> tuple[int, str]:
    source_urls = manifest.get("source_urls") or []
    evidence_bonus = len(re.findall(r"https?://", body))
    data_bonus = len(re.findall(r"\d{4}年|\d+(?:\.\d+)?%|\d+倍|第\d+", body))
    argument_modes = _normalize_list(review.get("viral_analysis", {}).get("argument_diversity"))
    score = min(10, min(4, len(source_urls) * 2) + min(3, evidence_bonus) + min(2, data_bonus) + (1 if "权威论证" in argument_modes else 0))
    return score, "事实型内容必须经得起回溯，最好能自然带出来源和依据。"


def _build_quality_gates(review: dict[str, Any], blueprint: dict[str, Any], credibility_score: int) -> dict[str, bool]:
    emotion_count = len(review.get("emotion_value_sentences") or [])
    pain_count = len(review.get("pain_point_sentences") or [])
    signature_count = len(review.get("viral_analysis", {}).get("signature_lines") or [])
    argument_count = len(_normalize_list(review.get("viral_analysis", {}).get("argument_diversity")))
    perspective_count = len(_normalize_list(review.get("viral_analysis", {}).get("perspective_shifts")))
    ai_smell_hits = len(review.get("ai_smell_findings") or [])
    return {
        "viral_blueprint_complete": blueprint_complete(blueprint),
        "emotion_value_enough": emotion_count >= EMOTION_VALUE_THRESHOLD,
        "pain_point_enough": pain_count >= PAIN_POINT_THRESHOLD,
        "signature_lines_enough": signature_count >= SIGNATURE_LINE_THRESHOLD,
        "argument_diverse": argument_count >= ARGUMENT_MODE_THRESHOLD,
        "perspective_shift_enough": perspective_count >= PERSPECTIVE_SHIFT_THRESHOLD,
        "de_ai_passed": ai_smell_hits <= AI_SMELL_THRESHOLD,
        "credibility_passed": credibility_score >= CREDIBILITY_THRESHOLD,
    }


def build_score_report(
    title: str,
    body: str,
    manifest: dict[str, Any],
    threshold: int | None = None,
    review: dict[str, Any] | None = None,
    revision_rounds: list[dict[str, Any]] | None = None,
    stop_reason: str = "",
) -> dict[str, Any]:
    threshold = int(threshold or manifest.get("score_threshold") or DEFAULT_THRESHOLD)
    blueprint = normalize_viral_blueprint(
        manifest.get("viral_blueprint"),
        {
            "topic": manifest.get("topic") or title,
            "selected_title": title,
            "direction": manifest.get("direction") or "",
            "audience": manifest.get("audience") or "大众读者",
            "research": {},
            "style_signals": manifest.get("style_signals") or [],
        },
    )
    review = review or build_heuristic_review(title, body, manifest, blueprint=blueprint)
    hot_intro, hot_intro_note = _score_hot_intro(title, body, review)
    viewpoint_score, viewpoint_note = _score_viewpoints(review)
    argument_score, argument_note = _score_argument_diversity(review)
    emotion_score, emotion_note = _score_emotion_trigger(review)
    signature_score, signature_note = _score_signature(review)
    curve_score, curve_note = _score_emotion_curve(review, body)
    layers_score, layers_note = _score_emotion_layers(review)
    perspective_score, perspective_note = _score_perspective(review)
    style_score, style_note = _score_style(review, body)
    credibility_score, credibility_note = _score_credibility(body, manifest, review)
    breakdown = [
        {"dimension": "标题与开头爆点", "weight": 12, "score": hot_intro, "note": hot_intro_note},
        {"dimension": "核心观点与副观点", "weight": 10, "score": viewpoint_score, "note": viewpoint_note},
        {"dimension": "说服策略与论证多样性", "weight": 12, "score": argument_score, "note": argument_note},
        {"dimension": "情绪触发与刺痛感", "weight": 12, "score": emotion_score, "note": emotion_note},
        {"dimension": "金句与传播句密度", "weight": 10, "score": signature_score, "note": signature_note},
        {"dimension": "情感曲线与节奏", "weight": 8, "score": curve_score, "note": curve_note},
        {"dimension": "情感层次与共鸣", "weight": 8, "score": layers_score, "note": layers_note},
        {"dimension": "视角转化与认知增量", "weight": 8, "score": perspective_score, "note": perspective_note},
        {"dimension": "语言风格自然度", "weight": 10, "score": style_score, "note": style_note},
        {"dimension": "可信度与检索支撑", "weight": 10, "score": credibility_score, "note": credibility_note},
    ]
    total = sum(item["score"] for item in breakdown)
    quality_gates = _build_quality_gates(review, blueprint, credibility_score)
    strengths = []
    weaknesses = []
    for item in breakdown:
        ratio = item["score"] / max(1, item["weight"])
        if ratio >= 0.8:
            strengths.append(f"{item['dimension']}表现较强：{item['note']}")
        elif ratio < 0.65:
            weaknesses.append(f"{item['dimension']}偏弱：{item['note']}")
    failed_gates = [name for name, ok in quality_gates.items() if not ok]
    mandatory_revisions = _dedupe(
        list(review.get("revision_priorities") or [])
        + [
            "补齐爆款蓝图，先把主观点、副观点、情绪触发点和论证方式定下来。" if not quality_gates["viral_blueprint_complete"] else "",
            "继续补情绪价值句，让读者感到被理解和被托住。" if not quality_gates["emotion_value_enough"] else "",
            "继续补刺痛句和现实代价，增强首屏停留与中段张力。" if not quality_gates["pain_point_enough"] else "",
            "补案例/对比/步骤，保证至少 3 种论证方式。" if not quality_gates["argument_diverse"] else "",
            "增加视角切换，避免整篇只从一个角度平铺。" if not quality_gates["perspective_shift_enough"] else "",
            "继续清理模板腔，压低 AI 痕迹。" if not quality_gates["de_ai_passed"] else "",
            "补来源、数据或官方依据，提升可信度。" if not quality_gates["credibility_passed"] else "",
        ]
    )
    suggestions = {
        "replacement_hook": blueprint.get("pain_points", [f"{title} 这件事最怕的，不是做得慢，而是从一开始就做错方向。"])[0],
        "sample_gold_quotes": [item["text"] for item in (review.get("viral_analysis", {}).get("signature_lines") or [])[:3]]
        or _normalize_list(blueprint.get("target_quotes"))[:3],
        "style_adjustments": _dedupe(
            [
                "判断句前置，别再用首先/其次/最后平推。",
                "让每一节至少出现一句能刺痛读者或安顿读者的话。",
                "补对比和案例，避免只讲观点不讲落地。",
            ]
        ),
        "failed_quality_gates": failed_gates,
        "revision_priorities": list(review.get("revision_priorities") or []),
    }
    ai_smell_hits = len(review.get("ai_smell_findings") or [])
    passed = total >= threshold and all(quality_gates.values())
    return {
        "title": title,
        "threshold": threshold,
        "total_score": total,
        "passed": passed,
        "score_breakdown": breakdown,
        "strengths": strengths[:5],
        "weaknesses": weaknesses[:5],
        "mandatory_revisions": mandatory_revisions[:7],
        "suggestions": suggestions,
        "candidate_quotes": [item["text"] for item in (review.get("viral_analysis", {}).get("signature_lines") or [])[:6]],
        "quality_gates": quality_gates,
        "viral_blueprint": blueprint,
        "viral_analysis": review.get("viral_analysis") or {},
        "emotion_value_sentences": review.get("emotion_value_sentences") or [],
        "pain_point_sentences": review.get("pain_point_sentences") or [],
        "ai_smell_findings": review.get("ai_smell_findings") or [],
        "ai_smell_hits": ai_smell_hits,
        "revision_rounds": revision_rounds or [],
        "best_round": max((item.get("round", 0) for item in revision_rounds or []), default=int(review.get("revision_round") or 1)),
        "stop_reason": stop_reason,
        "generated_at": legacy.now_iso(),
    }


def markdown_review_report(review: dict[str, Any]) -> str:
    analysis = review.get("viral_analysis") or {}
    lines = [
        "# 编辑评审报告",
        "",
        review.get("summary", ""),
        "",
        "## 爆款拆解",
        "",
        f"- 核心观点：{analysis.get('core_viewpoint') or '无'}",
    ]
    for label, key in [
        ("副观点", "secondary_viewpoints"),
        ("说服策略", "persuasion_strategies"),
        ("情绪触发点", "emotion_triggers"),
        ("情感层次", "emotion_layers"),
        ("论证方式多样性", "argument_diversity"),
        ("视角转化分析", "perspective_shifts"),
        ("语言风格特征", "style_traits"),
    ]:
        items = _normalize_list(analysis.get(key))
        lines.append(f"- {label}：{'、'.join(items) if items else '无'}")
    lines.extend(["", "## 金句", ""])
    for item in analysis.get("signature_lines") or []:
        lines.append(f"> {item.get('text') if isinstance(item, dict) else item}")
    lines.extend(["", "## 情感曲线分析", ""])
    for item in analysis.get("emotion_curve") or []:
        if isinstance(item, dict):
            lines.append(f"- {item.get('stage') or '阶段'}：{item.get('emotion') or ''}｜{item.get('goal') or ''}")
        else:
            lines.append(f"- {item}")
    lines.extend(["", "## 情绪价值句式", ""])
    for item in review.get("emotion_value_sentences") or []:
        lines.append(f"- {item.get('text')}｜{item.get('reason')}｜强度 {item.get('strength')}")
    lines.extend(["", "## 刺痛句式", ""])
    for item in review.get("pain_point_sentences") or []:
        lines.append(f"- {item.get('text')}｜{item.get('reason')}｜强度 {item.get('strength')}")
    lines.extend(["", "## AI 味检查", ""])
    for item in review.get("ai_smell_findings") or []:
        lines.append(f"- {item.get('type')}：{item.get('evidence')}（{item.get('count')}）")
    lines.extend(["", "## 修改优先级", ""])
    for item in review.get("revision_priorities") or ["当前结构完整，可进入下一步。"]:
        lines.append(f"- {item}")
    if review.get("strengths"):
        lines.extend(["", "## 当前亮点", ""])
        for item in review.get("strengths") or []:
            lines.append(f"- {item}")
    if review.get("issues"):
        lines.extend(["", "## 当前问题", ""])
        for item in review.get("issues") or []:
            lines.append(f"- {item}")
    return "\n".join(line for line in lines if line is not None).rstrip() + "\n"


def markdown_score_report(report: dict[str, Any]) -> str:
    lines = [
        f"# 文章评分报告：{report.get('title') or '未命名文章'}",
        "",
        f"- 总分：`{report.get('total_score', 0)}` / 100",
        f"- 阈值：`{report.get('threshold', DEFAULT_THRESHOLD)}`",
        f"- 结果：`{'通过' if report.get('passed') else '未通过'}`",
    ]
    stop_reason = str(report.get("stop_reason") or "").strip()
    if stop_reason:
        lines.append(f"- 停止原因：`{stop_reason}`")
    lines.extend(["", "## 分项得分", ""])
    for item in report.get("score_breakdown") or []:
        lines.append(f"- {item['dimension']}：`{item['score']}` / `{item['weight']}` - {item['note']}")
    lines.extend(["", "## 质量门槛", ""])
    for name, ok in (report.get("quality_gates") or {}).items():
        lines.append(f"- {name}：`{'通过' if ok else '未通过'}`")
    lines.extend(["", "## 失败原因与必须修改项", ""])
    for item in report.get("mandatory_revisions") or ["当前版本已达发布线。"]:
        lines.append(f"- {item}")
    lines.extend(["", "## 下一轮改稿优先级", ""])
    for item in (report.get("suggestions") or {}).get("revision_priorities") or ["优先守住当前爆点和节奏。"]:
        lines.append(f"- {item}")
    lines.extend(["", "## 爆款句密度", ""])
    lines.append(f"- 情绪价值句：`{len(report.get('emotion_value_sentences') or [])}`")
    lines.append(f"- 刺痛句：`{len(report.get('pain_point_sentences') or [])}`")
    lines.append(f"- 金句：`{len(report.get('candidate_quotes') or [])}`")
    lines.append(f"- AI 味命中：`{report.get('ai_smell_hits', 0)}`")
    revision_rounds = report.get("revision_rounds") or []
    if revision_rounds:
        lines.extend(["", "## 多轮修正记录", ""])
        for item in revision_rounds:
            lines.append(
                f"- Round {item.get('round')}：`{item.get('score')}` 分｜`{'通过' if item.get('passed') else '未通过'}`｜{item.get('article_path')}"
            )
    if report.get("candidate_quotes"):
        lines.extend(["", "## 已识别金句", ""])
        for quote in report["candidate_quotes"]:
            lines.append(f"> {quote}")
    if report.get("rewrite"):
        rewrite = report["rewrite"]
        lines.extend(["", "## 自动改写稿", ""])
        lines.append(f"- 改写稿：`{rewrite.get('output_path')}`")
        lines.append(f"- 模式：`{rewrite.get('mode')}`")
        lines.append(f"- 预评分：`{rewrite.get('preview_score')}` / 100")
        lines.append(f"- 预评分是否过线：`{'是' if rewrite.get('preview_passed') else '否'}`")
        for action in rewrite.get("applied_actions") or []:
            lines.append(f"- 已应用：{action}")
    return "\n".join(lines).rstrip() + "\n"
