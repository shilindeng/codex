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
    ("场景切口", [r"你可能", r"某天", r"那一刻", r"刷到", r"看到", r"消息", r"视频"]),
    ("对比感强", [r"不是.+而是", r"但", r"却", r"反而"]),
    ("读者对话", [r"你", r"我们", r"别急", r"你会发现"]),
    ("证据穿插", [r"比如", r"例如", r"数据显示", r"报告", r"文档", r"https?://"]),
]

BLUEPRINT_EXTRA_LIST_FIELDS = [
    "opening_modes",
    "ending_modes",
    "voice_guardrails",
    "avoid_patterns",
]
BLUEPRINT_EXTRA_TEXT_FIELDS = [
    "article_archetype",
]

ARCHETYPE_KEYWORDS: dict[str, list[str]] = {
    "tutorial": ["教程", "指南", "手把手", "实操", "上手", "怎么做", "如何", "方法", "SOP", "清单", "流程", "模板"],
    "case-study": ["案例", "复盘", "拆解", "公司", "项目", "产品", "团队", "人物", "故事"],
    "narrative": ["故事", "经历", "焦虑", "关系", "成长", "生活", "日常", "情绪", "家庭", "职场"],
    "commentary": ["为什么", "真相", "趋势", "误区", "判断", "拐点", "变现", "竞争", "机会", "风险", "信号"],
}

ARCHETYPE_PROFILES: dict[str, dict[str, Any]] = {
    "commentary": {
        "label": "分析评论",
        "persuasion_strategies": ["反常识判断", "趋势拆解", "案例或数据支撑", "对比论证"],
        "argument_modes": ["对比", "拆解", "案例", "趋势"],
        "emotion_curve": [
            {"stage": "开头", "emotion": "悬念", "goal": "把读者带进正在发生的变化"},
            {"stage": "中段", "emotion": "识别", "goal": "讲清被误读的地方"},
            {"stage": "后段", "emotion": "判断", "goal": "给出比信息更重要的视角"},
            {"stage": "结尾", "emotion": "余味", "goal": "留下值得复述的判断"},
        ],
        "emotion_layers": ["警觉层", "理解层", "判断层", "余味层"],
        "style_traits": ["具体场景起笔", "判断克制", "证据穿插", "少自我解释", "段落有呼吸"],
        "pain_points": [
            "读者最容易被热闹牵着走，却忽略真正决定结果的那层变化。",
            "很多文章信息很多，但判断很少，读完之后什么都带不走。",
            "一旦只盯表面信号，就会在关键分水岭上慢半拍。",
        ],
        "emotion_value_goals": ["让读者觉得被点醒", "让读者获得新判断", "让读者愿意转发给同类人"],
        "opening_modes": ["场景切口", "反差判断", "新闻切口"],
        "ending_modes": ["判断收束", "余味回扣", "风险提醒"],
        "voice_guardrails": ["少自我解释", "少模板连接词", "别把文章写成讲义", "让判断落在具体事实上"],
        "avoid_patterns": ["先说结论", "接下来我会", "最后给你一个可执行清单", "如果你只想记住一句话"],
        "default_sections": [
            {"heading": "大家真正误判了什么", "goal": "先把被忽略的信号说透", "evidence_need": "新闻、案例或现象对比"},
            {"heading": "真正拉开差距的分水岭", "goal": "提出主判断并拆解逻辑", "evidence_need": "数据、案例或结构拆解"},
            {"heading": "这会怎样改写接下来的结果", "goal": "把趋势和代价讲明白", "evidence_need": "对比、风险或机会"},
            {"heading": "最后的判断", "goal": "收束全文并留下可复述观点", "evidence_need": "一句有记忆点的判断"},
        ],
    },
    "tutorial": {
        "label": "方法指南",
        "persuasion_strategies": ["误区澄清", "步骤拆解", "案例支撑", "关键提醒"],
        "argument_modes": ["拆解", "步骤", "案例", "提醒"],
        "emotion_curve": [
            {"stage": "开头", "emotion": "卡点共鸣", "goal": "说出读者为什么总是做不顺"},
            {"stage": "中段", "emotion": "掌控感", "goal": "把关键动作拆清楚"},
            {"stage": "后段", "emotion": "确定感", "goal": "让读者知道先做什么后做什么"},
            {"stage": "结尾", "emotion": "行动", "goal": "给读者一个真的能动手的起点"},
        ],
        "emotion_layers": ["焦虑层", "理解层", "掌控层", "行动层"],
        "style_traits": ["问题先行", "步骤清楚", "提醒具体", "少官话", "用场景解释抽象动作"],
        "pain_points": [
            "很多人不是不想做，而是不知道第一步该落在哪。",
            "方法文最怕看起来全对，做起来全乱。",
            "如果关键顺序没理清，努力只会继续消耗耐心。",
        ],
        "emotion_value_goals": ["让读者觉得终于讲明白了", "让读者知道先做哪一步", "让读者愿意保存备用"],
        "opening_modes": ["卡点共鸣", "误区切口", "场景切口"],
        "ending_modes": ["行动提示", "关键提醒", "适用边界"],
        "voice_guardrails": ["讲步骤但别像说明书", "每个动作都要解释为什么", "别堆砌空泛 checklist"],
        "avoid_patterns": ["先说结论", "这篇文章将", "综上所述", "万能清单"],
        "default_sections": [
            {"heading": "先别急着上手，真正的卡点在这里", "goal": "先拆误区和卡点", "evidence_need": "场景或失败案例"},
            {"heading": "把顺序理清，事情就简单了", "goal": "给出关键步骤和先后关系", "evidence_need": "步骤、示例或操作说明"},
            {"heading": "最容易做错的几个地方", "goal": "提前讲清边界和风险", "evidence_need": "反例或注意事项"},
            {"heading": "最后只记住这一个动作", "goal": "收束到最关键的一步", "evidence_need": "一句简短提醒"},
        ],
    },
    "case-study": {
        "label": "案例拆解",
        "persuasion_strategies": ["案例复盘", "对比论证", "结果回看", "可迁移判断"],
        "argument_modes": ["案例", "对比", "拆解", "判断"],
        "emotion_curve": [
            {"stage": "开头", "emotion": "代入", "goal": "把读者带进具体场景"},
            {"stage": "中段", "emotion": "理解", "goal": "讲清事情怎么一步步变化"},
            {"stage": "后段", "emotion": "醒悟", "goal": "指出案例真正说明了什么"},
            {"stage": "结尾", "emotion": "带走判断", "goal": "把个案提升为通用洞察"},
        ],
        "emotion_layers": ["代入层", "理解层", "醒悟层", "判断层"],
        "style_traits": ["案例开路", "细节说话", "判断后置", "少空话", "用结果反推过程"],
        "pain_points": [
            "读者常常看过案例，却没看懂案例真正说明了什么。",
            "复盘一旦只剩过程罗列，就很难长出真正可迁移的判断。",
            "最可惜的不是没看见案例，而是只看见热闹没有看见方法。",
        ],
        "emotion_value_goals": ["让读者觉得案例真的有启发", "让读者带走一层更稳的判断", "让读者愿意转给同类同行"],
        "opening_modes": ["人物/场景切口", "结果倒叙", "关键细节起笔"],
        "ending_modes": ["判断回扣", "迁移建议", "风险提醒"],
        "voice_guardrails": ["别把案例写成流水账", "先抓关键细节再下判断", "避免硬凑 checklist"],
        "avoid_patterns": ["先说结论", "第一第二第三机械平铺", "最后给你一个清单"],
        "default_sections": [
            {"heading": "事情是怎么开始变味的", "goal": "给读者一个能代入的场景", "evidence_need": "案例细节"},
            {"heading": "真正的分水岭出现在这里", "goal": "拆解案例中的关键决策点", "evidence_need": "过程或对比"},
            {"heading": "这个案例真正说明了什么", "goal": "把个案提炼成通用判断", "evidence_need": "对照或总结"},
            {"heading": "把这个判断带回你自己的处境", "goal": "收束并完成迁移", "evidence_need": "场景映射"},
        ],
    },
    "narrative": {
        "label": "叙事观察",
        "persuasion_strategies": ["场景代入", "情绪递进", "反差回看", "判断点题"],
        "argument_modes": ["场景", "对比", "判断"],
        "emotion_curve": [
            {"stage": "开头", "emotion": "代入", "goal": "让读者感觉这就是自己会遇到的场景"},
            {"stage": "中段", "emotion": "共鸣", "goal": "把表面情绪背后的原因讲出来"},
            {"stage": "后段", "emotion": "松动", "goal": "给读者一个重新理解自己的角度"},
            {"stage": "结尾", "emotion": "余温", "goal": "留下不生硬的回响"},
        ],
        "emotion_layers": ["代入层", "共鸣层", "理解层", "余温层"],
        "style_traits": ["具体细节起笔", "少口号", "对话感", "句式有长短落差", "判断别喊出来"],
        "pain_points": [
            "很多人真正难受的，不是问题本身，而是一直没人把那种感受说清楚。",
            "越是贴身的问题，越怕被写成一篇正确但没有温度的稿子。",
            "读者要的不是说教，而是被看见之后再被轻轻推一把。",
        ],
        "emotion_value_goals": ["让读者觉得被理解", "让读者放下自责", "让读者愿意收藏给以后看"],
        "opening_modes": ["场景切口", "人物细节", "一句不响亮但刺心的话"],
        "ending_modes": ["轻回扣", "余味", "温和提醒"],
        "voice_guardrails": ["少大词", "少立刻下定义", "少做教练式发号施令"],
        "avoid_patterns": ["先说结论", "最后给你一个可执行清单", "鸡汤式鼓励"],
        "default_sections": [
            {"heading": "那个让人一下子沉下去的瞬间", "goal": "建立代入感", "evidence_need": "具体场景或细节"},
            {"heading": "真正让人难受的，不是表面那件事", "goal": "把情绪背后的原因讲出来", "evidence_need": "对比或经历"},
            {"heading": "当你换个角度看，很多事会开始松动", "goal": "给读者新的理解方式", "evidence_need": "判断或故事回看"},
            {"heading": "最后留给你一句不那么生硬的话", "goal": "收束而不过度说教", "evidence_need": "一句带余温的判断"},
        ],
    },
}


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


def infer_article_archetype(*, topic: str, title: str, angle: str, research: dict[str, Any] | None = None) -> str:
    research = research or {}
    corpus = " ".join(
        [
            str(topic or ""),
            str(title or ""),
            str(angle or ""),
            " ".join(str(item or "") for item in research.get("information_gaps") or []),
            " ".join(str(item or "") for item in research.get("evidence_items") or []),
        ]
    )
    scores: dict[str, int] = {}
    for archetype, keywords in ARCHETYPE_KEYWORDS.items():
        scores[archetype] = sum(1 for keyword in keywords if keyword and keyword in corpus)
    if scores.get("tutorial", 0) >= 2:
        return "tutorial"
    if scores.get("case-study", 0) >= 2:
        return "case-study"
    if scores.get("narrative", 0) >= 2 and scores.get("tutorial", 0) == 0:
        return "narrative"
    if scores.get("commentary", 0) >= 1:
        return "commentary"
    return "commentary"


def archetype_profile(*, topic: str, title: str, angle: str, research: dict[str, Any] | None = None) -> dict[str, Any]:
    archetype = infer_article_archetype(topic=topic, title=title, angle=angle, research=research)
    return {"article_archetype": archetype, **ARCHETYPE_PROFILES.get(archetype, ARCHETYPE_PROFILES["commentary"])}


def default_outline_sections(archetype: str) -> list[dict[str, str]]:
    profile = ARCHETYPE_PROFILES.get(archetype, ARCHETYPE_PROFILES["commentary"])
    return json.loads(json.dumps(profile.get("default_sections") or ARCHETYPE_PROFILES["commentary"]["default_sections"], ensure_ascii=False))


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
    profile = archetype_profile(topic=topic, title=title, angle=angle, research=research)
    archetype = profile["article_archetype"]
    style_defaults = _dedupe([*style_signals, *profile.get("style_traits", []), "少模板连接词", "像真人编辑一样推进"])
    core_viewpoint_map = {
        "commentary": f"{key_phrase} 真正值得警惕的，不是表面的热闹变化，而是它背后那条正在改写结果的分水岭",
        "tutorial": f"{key_phrase} 最难的不是信息不够，而是顺序没理清；一旦顺序对了，动作就会一下子轻很多",
        "case-study": f"{key_phrase} 真正值得拆的，不是表面结果，而是它一路变化里那个最关键的决策点",
        "narrative": f"{key_phrase} 最让人反复卡住的，往往不是表面那件事，而是一直没人把更深一层的感受和逻辑说透",
    }
    secondary_viewpoints_map = {
        "commentary": [
            f"{audience_text} 最容易被表面信号牵着走，忽略真正起作用的底层变化",
            "一篇能被转发的分析稿，不是观点更大，而是判断更准、例子更贴、结尾更有余味",
            "真正有价值的文章，应该帮读者重新组织看问题的方式，而不是只补几条信息",
        ],
        "tutorial": [
            f"{audience_text} 不是不想做，而是常常卡在第一步就用错了力气",
            "方法文真正有用，不是因为清单多，而是它能讲清楚为什么先做这一步",
            "越是看起来简单的动作，越需要边界、顺序和反例来托住",
        ],
        "case-study": [
            "案例真正值钱的地方，不是热闹，而是它能暴露决策里的分水岭",
            "复盘如果只剩过程回放，读者带不走判断，也不会真的记住",
            "真正好的案例稿，最后一定能把个案提炼成一种看问题的方法",
        ],
        "narrative": [
            "贴身的问题一旦写成正确废话，读者会立刻划走，因为他感觉不到自己被看见",
            "真正打动人的，不是大词，而是那些被说准了的小处境和小念头",
            "好文章不会急着给答案，它会先把那种说不清的感受安顿下来",
        ],
    }
    target_quotes_map = {
        "commentary": [
            f"{key_phrase} 真正可怕的，从来不是消息本身，而是你还在拿旧判断理解新变化。",
            "一篇分析稿真正值钱的地方，不是信息密度，而是它替你省掉了多少误判。",
            "读者愿意转发的，不是正确结论，而是那个让他突然看清局势的判断。",
        ],
        "tutorial": [
            f"{key_phrase} 最怕的不是不会，而是一上来就把顺序做反了。",
            "真正能用的方法，不是步骤更多，而是关键动作更少、更准。",
            "一篇指南真正有用，不是看完点头，而是做的时候不再慌。",
        ],
        "case-study": [
            "案例真正厉害的地方，不是赢了，而是它把为什么赢讲得足够明白。",
            "复盘不是把过程再走一遍，而是把关键分水岭单独拎出来看。",
            "个案一旦能长出判断，它就不再只是个案了。",
        ],
        "narrative": [
            "很多时候，真正困住人的，不是事情本身，而是你一直不知道该怎么理解自己。",
            "被说中的感觉，往往比被安慰更重要。",
            "一篇有温度的文章，不会催你立刻改变，它会先让你不再那么孤单。",
        ],
    }
    return {
        "core_viewpoint": _ensure_sentence(core_viewpoint_map.get(archetype, core_viewpoint_map["commentary"])),
        "secondary_viewpoints": [_ensure_sentence(item) for item in secondary_viewpoints_map.get(archetype, secondary_viewpoints_map["commentary"])],
        "persuasion_strategies": list(profile.get("persuasion_strategies") or []),
        "emotion_triggers": ["怕误判", "怕做了很多却没抓到关键", "想找到更稳的判断", "想带走真正有用的东西"],
        "target_quotes": [_ensure_sentence(item) for item in target_quotes_map.get(archetype, target_quotes_map["commentary"])],
        "emotion_curve": json.loads(json.dumps(profile.get("emotion_curve") or [], ensure_ascii=False)),
        "emotion_layers": list(profile.get("emotion_layers") or []),
        "argument_modes": list(profile.get("argument_modes") or []),
        "perspective_shifts": ["读者视角", "旁观者视角", "编辑判断视角"],
        "style_traits": style_defaults[:5],
        "pain_points": [_ensure_sentence(item) for item in profile.get("pain_points") or []],
        "emotion_value_goals": list(profile.get("emotion_value_goals") or []),
        "article_archetype": archetype,
        "opening_modes": list(profile.get("opening_modes") or []),
        "ending_modes": list(profile.get("ending_modes") or []),
        "voice_guardrails": list(profile.get("voice_guardrails") or []),
        "avoid_patterns": list(profile.get("avoid_patterns") or []),
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
    for field in BLUEPRINT_EXTRA_LIST_FIELDS:
        items = _normalize_list(source.get(field))
        if items:
            merged[field] = items[:6]
    for field in BLUEPRINT_EXTRA_TEXT_FIELDS:
        text = str(source.get(field) or "").strip()
        if text:
            merged[field] = text
    return merged


def normalize_outline_payload(payload: Any, context: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        output = dict(payload)
    else:
        output = {}
    title = str(output.get("title") or context.get("selected_title") or context.get("title") or context.get("topic") or "未命名标题")
    angle = str(output.get("angle") or context.get("direction") or context.get("angle") or "")
    sections = output.get("sections")
    profile = archetype_profile(
        topic=str(context.get("topic") or output.get("title") or ""),
        title=str(context.get("selected_title") or output.get("title") or ""),
        angle=str(context.get("direction") or output.get("angle") or ""),
        research=context.get("research") or {},
    )
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
        normalized_sections = default_outline_sections(profile["article_archetype"])
    output["title"] = title
    output["angle"] = angle
    output["sections"] = normalized_sections
    output["viral_blueprint"] = normalize_viral_blueprint(output.get("viral_blueprint"), context | {"selected_title": title, "angle": angle})
    output.setdefault("article_archetype", output["viral_blueprint"].get("article_archetype") or profile["article_archetype"])
    output.setdefault("opening_mode", (output["viral_blueprint"].get("opening_modes") or profile.get("opening_modes") or ["场景切口"])[0])
    output.setdefault("ending_mode", (output["viral_blueprint"].get("ending_modes") or profile.get("ending_modes") or ["判断收束"])[0])
    output.setdefault("voice_guardrails", output["viral_blueprint"].get("voice_guardrails") or profile.get("voice_guardrails") or [])
    output.setdefault("avoid_patterns", output["viral_blueprint"].get("avoid_patterns") or profile.get("avoid_patterns") or [])
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
        if any(word in intro for word in PAIN_POINT_MARKERS):
            curve.append({"stage": "开头", "emotion": "刺痛", "goal": "让读者意识到问题不只是表面现象"})
        elif "?" in intro or "？" in intro or any(word in intro for word in ["为什么", "到底", "怎么会", "突然"]):
            curve.append({"stage": "开头", "emotion": "悬念", "goal": "让读者继续往下读"})
        else:
            curve.append({"stage": "开头", "emotion": "代入", "goal": "让读者先进入具体场景或处境"})
    for heading in headings[:2]:
        text = heading.get("text") or "正文"
        emotion = "理解"
        if re.search(r"方法|怎么|如何|步骤|清单", text):
            emotion = "掌控感"
        elif re.search(r"为什么|本质|真相|误区|分水岭|信号|判断", text):
            emotion = "醒悟"
        curve.append({"stage": text, "emotion": emotion, "goal": "推进认知增量"})
    if re.search(r"方法|怎么|如何|步骤|清单|SOP", body):
        curve.append({"stage": "结尾", "emotion": "行动", "goal": "让读者知道可以先从哪一步开始"})
    else:
        curve.append({"stage": "结尾", "emotion": "余味", "goal": "留下值得复述的判断或提醒"})
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
            "打散固定开头和结尾套路，别再回到一句话结论 + 万能清单" if any("先说结论" in str(item.get("evidence") or "") or "最后给你一个可执行清单" in str(item.get("evidence") or "") for item in ai_smell_findings) else "",
        ]
    )
    return {
        "summary": summary,
        "findings": strengths + issues,
        "strengths": strengths,
        "issues": issues,
        "platform_notes": [
            "公众号正文优先短段落和有呼吸感的节奏，但不等于所有段落都要碎成判断句。",
            "不要把爆款理解成固定模板，而是要让读者被带进问题、被点醒、再带走一个更稳的判断。",
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
    if any(word in intro for word in ["你可能", "刷到", "某天", "看到", "结果是", "但真正", "多数人"]):
        score += 1
    if "?" in intro or "？" in intro:
        score += 1
    if review.get("pain_point_sentences"):
        score += 1
    return min(12, score), "好的开头不靠固定模板，可以是场景、反差、问题、新闻切口或延迟亮观点，但必须把读者迅速带进问题。"


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
    return score, "爆款稿不靠单向说教，至少要能在拆解、对比、案例、趋势、场景、步骤里切换 3 种以上。"


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
    return min(8, score), "情绪推进要有起伏，可以从悬念/刺痛/代入走向理解，再落到判断、余味或行动。"


def _score_emotion_layers(review: dict[str, Any]) -> tuple[int, str]:
    layers = _normalize_list(review.get("viral_analysis", {}).get("emotion_layers"))
    score = min(8, 2 + len(layers))
    return score, "不要只有一种情绪，至少要能看到代入、理解、判断、余味或行动中的多层推进。"


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
        "opening_directions": _dedupe(
            _normalize_list(blueprint.get("opening_modes"))
            + [
                "从一个具体场景或最近发生的细节切入",
                "用反差判断切开问题，但别直接喊口号",
                "如果主题够强，也可以延迟亮观点，先把悬念立住",
            ]
        )[:4],
        "ending_directions": _dedupe(
            _normalize_list(blueprint.get("ending_modes"))
            + [
                "用判断收束，而不是默认上 checklist",
                "如果是教程，才考虑给动作；如果是分析稿，优先留余味或风险提醒",
            ]
        )[:4],
        "sample_gold_quotes": [item["text"] for item in (review.get("viral_analysis", {}).get("signature_lines") or [])[:3]]
        or _normalize_list(blueprint.get("target_quotes"))[:3],
        "style_adjustments": _dedupe(
            [
                "不同小节换不同进入方式，别把整篇写成同一套判断句模板。",
                "让每一节至少出现一句能刺痛读者、点醒读者或安顿读者的话。",
                "补对比、案例或细节，避免只讲观点不讲场景。",
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
