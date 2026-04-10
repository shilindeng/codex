from __future__ import annotations

import re
from typing import Any

import legacy_studio as legacy
from core.editorial_strategy import title_template_key


ABSOLUTE_TITLE_WORDS = ("唯一", "彻底", "一定", "所有", "必然", "100%", "永远")
HIGH_RISK_TITLE_FRAGMENTS = (
    "这次真正的信号",
    "真正值得聊的",
    "真正的分水岭在这里",
    "别急着下结论",
    "先别急着站队",
    "很多人看热闹",
    "最容易被忽略的那一步",
    "不是表面答案",
    "更深一层",
)
BROKEN_CONNECTOR_PATTERNS = (
    r"不是(?:这次真正的信号|真正值得聊的|别急着下结论|先别急着站队|很多人看热闹|最容易被忽略的那一步)",
    r"而真正(?:值得聊的|的分水岭)",
    r"(?:这次真正的信号|真正值得聊的).+(?:这次真正的信号|真正值得聊的)",
)
RISKY_TITLE_ENDINGS = ("这里", "那一步", "这一层")
TITLE_SCORE_THRESHOLD = 68
TITLE_LENGTH_TARGET = (16, 24)
TITLE_LENGTH_HARD_MAX = 28
TITLE_FAMILY_LABELS = {
    "viewpoint-direct": "观点直述型",
    "pain-truth": "痛点真相型",
    "counterintuitive": "反常识拆解型",
    "cost-consequence": "代价后果型",
    "method-rule": "方法规律型",
}
TITLE_DIMENSION_WEIGHTS: list[tuple[str, int]] = [
    ("普遍痛点", 12),
    ("信息差", 12),
    ("反常识", 10),
    ("低门槛理解", 10),
    ("高预期", 12),
    ("情绪共鸣", 12),
    ("传播性", 14),
    ("可信度", 10),
    ("新鲜度", 8),
]
TRUTH_WORDS = ("真相", "关键", "规律", "本质", "背后", "拐点", "忽略", "看清", "判断", "代价", "后果")
PAIN_WORDS = ("卡住", "吃亏", "焦虑", "失控", "被影响", "代价", "后果", "误判", "越忙越乱", "走弯路")
EMOTION_WORDS = ("太真实", "扎心", "被影响", "最容易", "总会", "越来越", "明明", "先吃亏", "卡住")
COUNTER_WORDS = ("反常识", "被忽略", "最容易看偏", "其实", "误判", "看错", "出人意料")
SHARE_WORDS = ("关键", "真相", "规律", "拐点", "代价", "后果", "这一步", "先吃亏", "看清")
DIRECT_FAMILY_PRIORITY = {"viewpoint-direct", "cost-consequence", "counterintuitive"}
ARCHETYPE_FAMILY_PRIORITIES = {
    "commentary": {"viewpoint-direct": 1.0, "counterintuitive": 0.8, "cost-consequence": 0.6, "pain-truth": 0.4, "method-rule": 0.1},
    "case-study": {"cost-consequence": 1.0, "viewpoint-direct": 0.8, "counterintuitive": 0.5, "pain-truth": 0.4, "method-rule": 0.2},
    "tutorial": {"method-rule": 1.0, "pain-truth": 0.8, "viewpoint-direct": 0.5, "counterintuitive": 0.3, "cost-consequence": 0.2},
    "narrative": {"pain-truth": 1.0, "viewpoint-direct": 0.7, "counterintuitive": 0.4, "cost-consequence": 0.3, "method-rule": 0.1},
}


def infer_title_family(title: str, candidate: dict[str, Any] | None = None) -> str:
    if isinstance(candidate, dict):
        explicit = str(candidate.get("title_family") or "").strip()
        if explicit:
            return explicit
    key = title_template_key(title)
    if key in TITLE_FAMILY_LABELS:
        return key
    return "viewpoint-direct"


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    value = str(text or "")
    return any(word in value for word in words)


def _separator_count(title: str) -> int:
    return title.count("：") + title.count("|") + title.count("｜")


def _question_count(title: str) -> int:
    return title.count("？") + title.count("?")


def _technical_token_count(title: str) -> int:
    acronyms = re.findall(r"\b[A-Z]{2,}\b", title)
    slashed = re.findall(r"[A-Za-z0-9]+/[A-Za-z0-9]+", title)
    return len(acronyms) + len(slashed)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _title_tokens(value: str) -> set[str]:
    text = _normalize_text(value)
    tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}", text)
    return {token.lower() for token in tokens if len(token.strip()) >= 2}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _title_similarity_score(left: str, right: str) -> float:
    left_tokens = _title_tokens(left)
    right_tokens = _title_tokens(right)
    token_overlap = _jaccard(left_tokens, right_tokens)
    compact_left = _normalize_text(left)
    compact_right = _normalize_text(right)
    if not compact_left or not compact_right:
        return token_overlap
    prefix_bonus = 0.2 if compact_left[:10] and compact_left[:10] == compact_right[:10] else 0.0
    family_bonus = 0.1 if title_template_key(left) == title_template_key(right) else 0.0
    return min(1.0, token_overlap + prefix_bonus + family_bonus)


def _candidate_bucket(candidate: dict[str, Any]) -> str:
    breakdown = candidate.get("decision_breakdown") or {}
    if float(breakdown.get("传播性") or 0) >= 8 and float(breakdown.get("高预期") or 0) >= 7:
        return "强打开型"
    if float(breakdown.get("信息差") or 0) >= 8 and float(breakdown.get("反常识") or 0) >= 7:
        return "强判断型"
    if float(breakdown.get("传播性") or 0) >= 7 and float(breakdown.get("情绪共鸣") or 0) >= 7:
        return "强传播型"
    return "稳妥保底型"


def _dedupe_near_duplicate_titles(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in candidates:
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        duplicate = False
        for existing in output:
            if _title_similarity_score(title, str(existing.get("title") or "")) >= 0.82:
                duplicate = True
                break
        if not duplicate:
            output.append(item)
    return output


def _diversify_title_candidates(candidates: list[dict[str, Any]], *, top_window: int = 6, same_family_cap: int = 2) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    family_counts: dict[str, int] = {}
    deferred: list[dict[str, Any]] = []
    for item in candidates:
        family = str(item.get("title_family") or "viewpoint-direct")
        current_count = int(family_counts.get(family) or 0)
        if len(selected) < top_window and current_count >= same_family_cap:
            deferred.append(item)
            continue
        selected.append(item)
        family_counts[family] = current_count + 1
    selected.extend(deferred)
    return selected


def _first_hit(items: list[dict[str, Any]], key: str) -> int:
    for item in items:
        if str(item.get("key") or "").strip() == key:
            try:
                return int(item.get("count") or 0)
            except (TypeError, ValueError):
                return 0
    return 0


def _author_fit_score(title: str, author_memory: dict[str, Any], editorial_blueprint: dict[str, Any], writing_persona: dict[str, Any]) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 5.5
    title_preferences = author_memory.get("title_preferences") or {}
    preferred_avg = float(title_preferences.get("average_length") or 0)
    current_length = len(_normalize_text(title))
    if preferred_avg > 0:
        gap = abs(current_length - preferred_avg)
        if gap <= 3:
            score += 2.0
            notes.append("长度接近这个号的常用标题长度")
        elif gap <= 6:
            score += 1.0
        else:
            score -= 1.2
            notes.append("长度偏离这个号的常用标题习惯")

    question_ratio = float(title_preferences.get("question_ratio") or 0)
    colon_ratio = float(title_preferences.get("colon_ratio") or 0)
    if ("？" in title or "?" in title) and question_ratio >= 0.3:
        score += 1.0
        notes.append("问句形式和这个号近期习惯一致")
    elif ("？" in title or "?" in title) and question_ratio <= 0.1:
        score -= 0.8
        notes.append("问句形式不太像这个号近期偏好")
    if any(mark in title for mark in ["：", ":", "｜", "|"]) and colon_ratio >= 0.25:
        score += 0.8
    elif any(mark in title for mark in ["：", ":", "｜", "|"]) and colon_ratio <= 0.05:
        score -= 0.6

    style_key = str((editorial_blueprint or {}).get("style_key") or "").strip()
    pattern = title_template_key(title)
    allowed = {str(item).strip() for item in ((editorial_blueprint or {}).get("allowed_title_patterns") or []) if str(item).strip()}
    if allowed and pattern in allowed:
        score += 1.4
        notes.append("标题路数和本篇既定风格一致")
    blocked = {str(item).strip() for item in ((editorial_blueprint or {}).get("blocked_title_patterns") or []) if str(item).strip()}
    if blocked and pattern in blocked:
        score -= 2.0
        notes.append("标题路数撞上近期高频模板")
    preferred_styles = {str(item).strip() for item in ((author_memory.get("editorial_preferences") or {}).get("preferred_style_keys") or []) if str(item).strip()}
    if style_key and style_key in preferred_styles:
        score += 0.8
    persona_name = str((writing_persona or {}).get("name") or "").strip()
    if persona_name == "cold-analyst":
        if "？" in title or "?" in title:
            score -= 0.6
            notes.append("问句形式偏离这篇稿子的专业人格")
        if any(mark in title for mark in ["：", ":"]):
            score += 0.4
    elif persona_name == "sharp-journalist":
        if current_length <= 20:
            score += 0.6
        if title.count("，") + title.count(",") >= 2:
            score -= 0.6
            notes.append("标题层级偏多，不够利落")
    elif persona_name == "warm-editor":
        if any(word in title for word in ["写给", "那一刻", "后来", "那个"]):
            score += 0.5
    elif persona_name == "industry-observer":
        if any(word in title for word in ["信号", "分水岭", "拐点", "重估"]):
            score += 0.5
    return round(max(0.0, min(score, 10.0)), 2), notes


def _trust_score(title: str, research: dict[str, Any], candidate: dict[str, Any]) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 6.0
    sources = list(research.get("sources") or [])
    evidence_items = list(research.get("evidence_items") or [])
    source_tier = str(candidate.get("source_tier") or "").strip()
    if sources or evidence_items:
        score += min(2.0, len(sources) * 0.4 + len(evidence_items) * 0.3)
        notes.append("当前主题已有来源或证据支撑")
    if source_tier == "官方":
        score += 1.0
    elif source_tier == "开源":
        score += 0.6
    if any(word in title for word in ABSOLUTE_TITLE_WORDS):
        score -= 1.5
        notes.append("标题用词过满，可信度风险更高")
    if re.search(r"[0-9一二三四五六七八九十]", title) and not (sources or evidence_items):
        score -= 0.6
        notes.append("标题带具体数字，但当前证据支撑偏弱")
    return round(max(0.0, min(score, 10.0)), 2), notes


def evaluate_title_open_rate(
    title: str,
    *,
    topic: str,
    audience: str,
    angle: str,
    candidate: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    recent_titles: list[str] | None = None,
    recent_patterns: list[dict[str, Any]] | None = None,
    account_strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    research = research or {}
    account_strategy = account_strategy or {}
    recent_titles = [str(item or "").strip() for item in (recent_titles or []) if str(item or "").strip()]
    recent_patterns = list(recent_patterns or [])
    family = infer_title_family(title, candidate)
    components = dict((candidate or {}).get("title_formula_components") or {})
    normalized = _normalize_text(title)
    token_set = _title_tokens(title)
    topic_tokens = _title_tokens(f"{topic} {angle}")
    overlap = _jaccard(token_set, topic_tokens) if topic_tokens else 0.0
    pattern_key = title_template_key(title)
    repeat_penalty = 0
    if title in recent_titles:
        repeat_penalty += 12
    if recent_titles and any(title.startswith(other[:10]) for other in recent_titles[:6] if len(other) >= 10):
        repeat_penalty += 4
    pattern_count = _first_hit(recent_patterns, pattern_key)
    if pattern_count:
        repeat_penalty += 4 + min(4, pattern_count)
    separator_count = _separator_count(title)
    question_count = _question_count(title)
    technical_tokens = _technical_token_count(title)
    absolute_hits = sum(1 for word in ABSOLUTE_TITLE_WORDS if word in title)
    old_template_hits = sum(1 for fragment in HIGH_RISK_TITLE_FRAGMENTS if fragment in title)
    pain_text = f"{title} {(components.get('pain_point') or '')}"
    truth_text = f"{title} {(components.get('truth_or_rule') or '')}"
    contrast_text = f"{title} {(components.get('counterintuitive_hook') or '')}"
    share_text = f"{title} {(components.get('share_hook') or '')}"

    dimensions: dict[str, float] = {}
    dimensions["普遍痛点"] = min(
        10.0,
        4.0
        + (2.2 if family in {"pain-truth", "cost-consequence"} else 1.2 if family == "viewpoint-direct" else 0.6)
        + (1.3 if _contains_any(pain_text, PAIN_WORDS) else 0.0)
        + (1.0 if any(word in title for word in [audience, "普通人", "团队", "打工人", "创业者", "新手"] if word) else 0.0)
        + (1.0 if overlap >= 0.18 else 0.0),
    )
    dimensions["信息差"] = min(
        10.0,
        4.0
        + (2.0 if family in {"viewpoint-direct", "counterintuitive"} else 1.0)
        + (2.0 if _contains_any(truth_text, TRUTH_WORDS) else 0.0)
        + (1.0 if "其实" in title or "看清" in title or "最容易被忽略" in title else 0.0),
    )
    dimensions["反常识"] = min(
        10.0,
        3.0
        + (3.0 if family == "counterintuitive" else 1.5 if family == "cost-consequence" else 0.6)
        + (1.8 if _contains_any(contrast_text, COUNTER_WORDS) else 0.0)
        + (0.8 if "不是" in title and "而是" in title else 0.0),
    )
    readability = 10.0
    if len(normalized) < TITLE_LENGTH_TARGET[0]:
        readability -= 1.4
    elif len(normalized) > TITLE_LENGTH_TARGET[1]:
        readability -= 1.6
    if len(normalized) > TITLE_LENGTH_HARD_MAX:
        readability -= 2.6
    readability -= max(0, separator_count - 1) * 2.0
    readability -= question_count * 0.7
    readability -= max(0, technical_tokens - 2) * 1.0
    dimensions["低门槛理解"] = round(max(1.0, min(readability, 10.0)), 2)
    dimensions["高预期"] = min(
        10.0,
        4.2
        + (2.0 if family in DIRECT_FAMILY_PRIORITY else 1.2)
        + (1.8 if _contains_any(share_text, SHARE_WORDS) else 0.0)
        + (1.0 if len(normalized) <= 24 else 0.0)
        + (0.6 if question_count == 1 else 0.0),
    )
    dimensions["情绪共鸣"] = min(
        10.0,
        4.0
        + (1.8 if family in {"pain-truth", "cost-consequence"} else 0.8)
        + (1.6 if _contains_any(pain_text, PAIN_WORDS + EMOTION_WORDS) else 0.0)
        + (1.0 if any(word in title for word in ["越", "总会", "先吃亏", "卡住", "影响"] ) else 0.0),
    )
    dimensions["传播性"] = min(
        10.0,
        4.0
        + (2.2 if family in DIRECT_FAMILY_PRIORITY else 1.4)
        + (1.6 if _contains_any(share_text, SHARE_WORDS) else 0.0)
        + (1.0 if separator_count <= 1 and len(normalized) <= 24 else 0.0)
        + (0.8 if question_count == 0 else 0.0),
    )
    trust_score = 8.0
    trust_score -= absolute_hits * 1.8
    trust_score -= max(0, separator_count - 1) * 1.6
    trust_score -= question_count * 0.8
    trust_score -= old_template_hits * 0.8
    if len(normalized) > TITLE_LENGTH_HARD_MAX:
        trust_score -= 1.6
    if research.get("sources") or research.get("evidence_items"):
        trust_score += 0.8
    dimensions["可信度"] = round(max(1.0, min(trust_score, 10.0)), 2)
    freshness = 10.0 - min(7.0, repeat_penalty / 2.2 + overlap * 5.0)
    if pattern_key in {"why-think-clear", "danger-not-but", "not-but"}:
        freshness -= 1.8
    dimensions["新鲜度"] = round(max(1.0, min(freshness, 10.0)), 2)

    weighted_total = 0.0
    score_breakdown: list[dict[str, Any]] = []
    for dimension, weight in TITLE_DIMENSION_WEIGHTS:
        value = round(float(dimensions.get(dimension) or 0), 2)
        weighted_total += value * weight / 10.0
        score_breakdown.append({"dimension": dimension, "weight": weight, "score": value, "note": ""})
    total_score = int(round(weighted_total))
    gate_reasons: list[str] = []
    for dimension, _weight in TITLE_DIMENSION_WEIGHTS:
        if float(dimensions.get(dimension) or 0) < 6.0:
            gate_reasons.append(f"{dimension}偏弱")
    if len(normalized) > TITLE_LENGTH_HARD_MAX:
        gate_reasons.append("标题过长")
    if separator_count > 1:
        gate_reasons.append("分隔符过多")
    if absolute_hits:
        gate_reasons.append("用词过满")
    if question_count > 1:
        gate_reasons.append("问句过强")
    gate_passed = bool(
        total_score >= TITLE_SCORE_THRESHOLD
        and dimensions["可信度"] >= 6.0
        and dimensions["新鲜度"] >= 5.0
        and dimensions["低门槛理解"] >= 6.0
    )
    gate_reason = "达到爆款门槛" if gate_passed else "、".join(dict.fromkeys(gate_reasons[:4])) or "标题未达爆款门槛"
    top_dims = sorted(dimensions.items(), key=lambda item: item[1], reverse=True)
    click_driver = f"会被点开：{top_dims[0][0]}和{top_dims[1][0]}更强。"
    return {
        "title_family": family,
        "title_formula_components": {
            "pain_point": str(components.get("pain_point") or ""),
            "truth_or_rule": str(components.get("truth_or_rule") or ""),
            "counterintuitive_hook": str(components.get("counterintuitive_hook") or ""),
            "share_hook": str(components.get("share_hook") or ""),
        },
        "title_emotion_mode": str((candidate or {}).get("title_emotion_mode") or "共鸣+反差"),
        "title_open_rate_score": total_score,
        "title_score": total_score,
        "title_score_threshold": TITLE_SCORE_THRESHOLD,
        "title_gate_passed": gate_passed,
        "title_gate_reason": gate_reason,
        "title_template_key": pattern_key,
        "title_repeat_penalty": repeat_penalty,
        "score_breakdown": score_breakdown,
        "dimension_scores": dimensions,
        "recent_title_overlap": round(overlap, 3),
        "click_driver": click_driver,
    }


def title_integrity_report(title: str, *, topic: str = "", account_strategy: dict[str, Any] | None = None) -> dict[str, Any]:
    strategy = account_strategy or {}
    issues: list[str] = []
    score = 10.0
    normalized = _normalize_text(title)
    blocked_patterns = {str(item).strip() for item in (strategy.get("blocked_title_patterns") or []) if str(item).strip()}
    blocked_fragments = {
        str(item).strip()
        for item in [*HIGH_RISK_TITLE_FRAGMENTS, *(strategy.get("blocked_title_fragments") or [])]
        if str(item).strip()
    }
    fragment_hits = [fragment for fragment in blocked_fragments if fragment in title]
    if len(fragment_hits) >= 2:
        score -= 4.0
        issues.append("标题同时叠了两层以上熟套路，像模板拼接。")
    for pattern in BROKEN_CONNECTOR_PATTERNS:
        if re.search(pattern, title):
            score -= 5.0
            issues.append("标题里的连接词前后不通顺，存在残句或硬拼接。")
            break
    if any(title.endswith(ending) for ending in RISKY_TITLE_ENDINGS):
        score -= 2.0
        issues.append("标题收在空泛尾巴上，读者读完还不知道具体在说什么。")
    if title.count("真正") >= 3:
        score -= 1.5
        issues.append("“真正”重复过多，明显像模板腔。")
    if re.search(r"[，,:：]{2,}", title) or re.search(r"[，,:：]\s*[，,:：]", title):
        score -= 2.5
        issues.append("标题标点异常，阅读不顺。")
    if _separator_count(title) > 1:
        score -= 2.5
        issues.append("主分隔符过多，标题像拼出来的。")
    if blocked_patterns and title_template_key(title) in blocked_patterns:
        score -= 2.0
        issues.append("标题路数撞上账号策略明确禁用的模板。")
    if fragment_hits:
        score -= min(2.5, len(fragment_hits) * 0.8)
        issues.append(f"标题命中高风险碎片：{'、'.join(fragment_hits[:3])}")
    if len(normalized) > TITLE_LENGTH_HARD_MAX:
        score -= 1.8
        issues.append("标题过长，首屏抓不住重点。")
    if topic and normalized and normalized == _normalize_text(topic) and len(fragment_hits) >= 1:
        score -= 1.5
        issues.append("原始主题本身已经像标题模板，不能直接拿来发。")
    passed = score >= 6.0 and not any("残句" in item or "硬拼接" in item for item in issues)
    notes = [] if issues else ["标题语义完整，句法顺，读起来不像拼出来的。"]
    return {
        "score": round(max(0.0, min(score, 10.0)), 2),
        "passed": passed,
        "issues": issues[:5],
        "notes": notes,
    }


def build_title_decision_report(
    *,
    topic: str,
    audience: str,
    angle: str,
    candidates: list[dict[str, Any]],
    manifest: dict[str, Any],
    research: dict[str, Any] | None = None,
    editorial_blueprint: dict[str, Any] | None = None,
    selected_title: str = "",
    account_strategy: dict[str, Any] | None = None,
    title_rewrite_round: int = 0,
) -> dict[str, Any]:
    research = research or {}
    editorial_blueprint = editorial_blueprint or {}
    account_strategy = account_strategy or {}
    recent_titles = [str(item or "").strip() for item in (manifest.get("recent_article_titles") or []) if str(item or "").strip()]
    recent_patterns = list((manifest.get("recent_corpus_summary") or {}).get("overused_title_patterns") or [])
    author_memory = manifest.get("author_memory") or {}
    writing_persona = manifest.get("writing_persona") or {}
    threshold = max(int(legacy.TITLE_SCORE_THRESHOLD or 0), TITLE_SCORE_THRESHOLD)
    archetype = str(
        (editorial_blueprint or {}).get("article_archetype")
        or (manifest.get("viral_blueprint") or {}).get("article_archetype")
        or manifest.get("article_archetype")
        or "commentary"
    ).strip().lower()
    family_priorities = ARCHETYPE_FAMILY_PRIORITIES.get(archetype, ARCHETYPE_FAMILY_PRIORITIES["commentary"])

    normalized_candidates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    source_candidates = list(candidates or [])
    if selected_title and all(str(item.get("title") or "").strip() != selected_title for item in source_candidates):
        source_candidates.append({"title": selected_title, "strategy": "显式指定标题", "audience_fit": audience, "risk_note": "显式指定标题，保留参与决策。"})

    for item in source_candidates:
        title = str(item.get("title") or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        author_fit_score, author_notes = _author_fit_score(title, author_memory, editorial_blueprint, writing_persona if isinstance(writing_persona, dict) else {})
        trust_score, trust_notes = _trust_score(title, research, item)
        integrity = title_integrity_report(title, topic=topic, account_strategy=account_strategy)
        open_rate = evaluate_title_open_rate(
            title,
            topic=topic,
            audience=audience,
            angle=angle,
            candidate=item,
            research=research,
            recent_titles=recent_titles,
            recent_patterns=recent_patterns,
            account_strategy=account_strategy,
        )
        total_score = int(open_rate["title_open_rate_score"])
        gate_passed = bool(open_rate["title_gate_passed"] and integrity.get("passed"))
        family_priority_score = float(family_priorities.get(str(open_rate.get("title_family") or ""), 0.3))
        dimension_scores = open_rate.get("dimension_scores") or {}
        decision_notes = []
        if float(dimension_scores.get("传播性") or 0) >= 7.0:
            decision_notes.append("传播性和打开率预期更强")
        if float(dimension_scores.get("信息差") or 0) >= 7.0:
            decision_notes.append("信息差更足，读者更容易想点开")
        if float(dimension_scores.get("新鲜度") or 0) >= 7.0:
            decision_notes.append("和近期高频标题骨架拉开了距离")
        if float(dimension_scores.get("情绪共鸣") or 0) >= 7.0:
            decision_notes.append("更容易触发“太真实了”的共鸣")
        if author_fit_score >= 7.0:
            decision_notes.append("更像这个号会发的标题气质")
        if integrity.get("passed"):
            decision_notes.append("语义完整，读起来不像硬拼接")
        decision_notes.extend(author_notes[:2])
        decision_notes.extend(trust_notes[:2])
        rejection_reason = []
        for item_name, score in (dimension_scores or {}).items():
            if float(score or 0) < 6.0:
                rejection_reason.append(f"{item_name}偏弱")
        if trust_score < 5.0:
            rejection_reason.append("可信度风险偏高")
        rejection_reason.extend(integrity.get("issues") or [])

        normalized_candidates.append(
            {
                **item,
                "title": title,
                "title_template_key": open_rate.get("title_template_key"),
                "title_score": total_score,
                "title_gate_passed": gate_passed,
                "title_open_rate_score": total_score,
                "title_score_threshold": threshold,
                "title_repeat_penalty": open_rate.get("title_repeat_penalty", 0),
                "title_score_breakdown": open_rate.get("score_breakdown") or [],
                "title_family": open_rate.get("title_family"),
                "title_formula_components": open_rate.get("title_formula_components") or {},
                "title_emotion_mode": open_rate.get("title_emotion_mode") or "共鸣+反差",
                "title_gate_reason": open_rate.get("title_gate_reason") or "",
                "title_rewrite_round": title_rewrite_round,
                "decision_breakdown": {
                    "普遍痛点": round(float(dimension_scores.get("普遍痛点") or 0), 2),
                    "信息差": round(float(dimension_scores.get("信息差") or 0), 2),
                    "反常识": round(float(dimension_scores.get("反常识") or 0), 2),
                    "低门槛理解": round(float(dimension_scores.get("低门槛理解") or 0), 2),
                    "高预期": round(float(dimension_scores.get("高预期") or 0), 2),
                    "情绪共鸣": round(float(dimension_scores.get("情绪共鸣") or 0), 2),
                    "传播性": round(float(dimension_scores.get("传播性") or 0), 2),
                    "篇型优先级": round(family_priority_score * 10, 2),
                    "作者匹配度": author_fit_score,
                    "可信度": trust_score,
                    "新鲜度": round(float(dimension_scores.get("新鲜度") or 0), 2),
                    "完整性": float(integrity.get("score") or 0),
                },
                "click_driver": open_rate.get("click_driver") or "",
                "family_priority_score": family_priority_score,
                "decision_notes": decision_notes[:5],
                "rejection_reason": rejection_reason[:5],
                "recent_title_overlap": open_rate.get("recent_title_overlap", 0),
                "title_integrity": integrity,
            }
        )

    normalized_candidates.sort(
        key=lambda item: (
            bool(item.get("title_gate_passed")),
            float(item.get("title_score") or 0) + float(item.get("family_priority_score") or 0) * 4,
            float((item.get("decision_breakdown") or {}).get("传播性") or 0),
            float((item.get("decision_breakdown") or {}).get("新鲜度") or 0),
            float((item.get("decision_breakdown") or {}).get("信息差") or 0),
        ),
        reverse=True,
    )
    normalized_candidates = _dedupe_near_duplicate_titles(normalized_candidates)
    normalized_candidates = _diversify_title_candidates(normalized_candidates)
    for item in normalized_candidates:
        item["title_bucket"] = _candidate_bucket(item)
    selected = normalized_candidates[0] if normalized_candidates else None
    selected_title_value = str(selected.get("title") or topic) if selected else topic
    selected_reason: list[str] = []
    selected_explainer = {"why_click": "", "why_better": "", "what_avoided": ""}
    if selected:
        scores = selected.get("decision_breakdown") or {}
        top_dims = sorted(
            [(key, float(value or 0)) for key, value in scores.items() if key in {"普遍痛点", "信息差", "反常识", "高预期", "情绪共鸣", "传播性"}],
            key=lambda item: item[1],
            reverse=True,
        )
        second = normalized_candidates[1] if len(normalized_candidates) > 1 else {}
        selected_explainer["why_click"] = (
            f"因为它同时抓住了{top_dims[0][0] if top_dims else '传播性'}和{top_dims[1][0] if len(top_dims) > 1 else '高预期'}，"
            "读者一眼就知道这篇会告诉自己什么。"
        )
        selected_explainer["why_better"] = (
            f"它比其他候选更强的地方是：传播分 {scores.get('传播性', 0)}、信息差 {scores.get('信息差', 0)}、新鲜度 {scores.get('新鲜度', 0)}。"
        )
        avoided = selected.get("title_integrity", {}).get("issues") or []
        if avoided:
            selected_explainer["what_avoided"] = "它仍有风险：" + "；".join(str(item) for item in avoided[:2])
        else:
            selected_explainer["what_avoided"] = "它避开了旧模板、高风险碎片、过满用词和明显拼接感。"
        selected_reason = [selected_explainer["why_click"], selected_explainer["why_better"], selected_explainer["what_avoided"]]
    return {
        "topic": topic,
        "audience": audience,
        "angle": angle,
        "threshold": threshold,
        "selected_title": selected_title_value,
        "selected_reason": selected_reason[:5],
        "selected_explainer": selected_explainer,
        "candidates": normalized_candidates,
        "candidate_groups": {
            "强打开型": [item for item in normalized_candidates if item.get("title_bucket") == "强打开型"][:3],
            "强判断型": [item for item in normalized_candidates if item.get("title_bucket") == "强判断型"][:3],
            "强传播型": [item for item in normalized_candidates if item.get("title_bucket") == "强传播型"][:3],
            "稳妥保底型": [item for item in normalized_candidates if item.get("title_bucket") == "稳妥保底型"][:3],
        },
        "title_rewrite_round": title_rewrite_round,
        "generated_at": legacy.now_iso(),
    }


def markdown_title_decision_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# 标题决策报告：{payload.get('selected_title') or '未命名标题'}",
        "",
        f"- 原始主题：{payload.get('topic') or ''}",
        f"- 决策阈值：{payload.get('threshold') or 0}",
        f"- 标题回炉轮次：{payload.get('title_rewrite_round') or 0}",
    ]
    explainer = payload.get("selected_explainer") or {}
    if explainer.get("why_click"):
        lines.extend(["", "## 为什么这个标题会被点开", "", f"- {explainer.get('why_click')}"])
    if explainer.get("why_better"):
        lines.extend(["", "## 为什么它比其他候选更强", "", f"- {explainer.get('why_better')}"])
    if explainer.get("what_avoided"):
        lines.extend(["", "## 它避开了哪些旧模板风险", "", f"- {explainer.get('what_avoided')}"])
    lines.append("")
    for candidate in (payload.get("candidates") or [])[:5]:
        breakdown = candidate.get("decision_breakdown") or {}
        components = candidate.get("title_formula_components") or {}
        lines.append(f"## {candidate.get('title') or '未命名标题'}")
        lines.append("")
        lines.append(f"- 总分：{candidate.get('title_score', 0)}｜{'通过' if candidate.get('title_gate_passed') else '未通过'}")
        lines.append(f"- 家族：{TITLE_FAMILY_LABELS.get(str(candidate.get('title_family') or ''), candidate.get('title_family') or '未标记')}｜情绪模式：{candidate.get('title_emotion_mode') or '共鸣+反差'}")
        lines.append(f"- 门槛判断：{candidate.get('title_gate_reason') or ''}")
        lines.append(
            f"- 公式拆解：痛点={components.get('pain_point') or ''}｜真相={components.get('truth_or_rule') or ''}｜反差={components.get('counterintuitive_hook') or ''}｜传播钩子={components.get('share_hook') or ''}"
        )
        lines.append(
            f"- 九项判断：痛点 {breakdown.get('普遍痛点', 0)} / 信息差 {breakdown.get('信息差', 0)} / 反常识 {breakdown.get('反常识', 0)} / 低门槛 {breakdown.get('低门槛理解', 0)} / 高预期 {breakdown.get('高预期', 0)} / 共鸣 {breakdown.get('情绪共鸣', 0)} / 传播 {breakdown.get('传播性', 0)} / 可信 {breakdown.get('可信度', 0)} / 新鲜 {breakdown.get('新鲜度', 0)}"
        )
        if candidate.get("click_driver"):
            lines.append(f"- 打开理由：{candidate.get('click_driver')}")
        for note in candidate.get("decision_notes") or []:
            lines.append(f"- 亮点：{note}")
        for note in candidate.get("rejection_reason") or []:
            lines.append(f"- 风险：{note}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
