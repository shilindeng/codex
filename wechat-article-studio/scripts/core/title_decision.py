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
    if blocked_patterns and title_template_key(title) in blocked_patterns:
        score -= 2.0
        issues.append("标题路数撞上账号策略明确禁用的模板。")
    if fragment_hits:
        score -= min(2.5, len(fragment_hits) * 0.8)
        issues.append(f"标题命中高风险碎片：{'、'.join(fragment_hits[:3])}")
    if len(normalized) > 34:
        score -= 1.0
        issues.append("标题过长，首屏不利于快速抓住读者。")
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
) -> dict[str, Any]:
    research = research or {}
    editorial_blueprint = editorial_blueprint or {}
    account_strategy = account_strategy or {}
    recent_titles = [str(item or "").strip() for item in (manifest.get("recent_article_titles") or []) if str(item or "").strip()]
    recent_patterns = list((manifest.get("recent_corpus_summary") or {}).get("overused_title_patterns") or [])
    recent_title_patterns = {str(item.get("key") or "").strip() for item in recent_patterns if str(item.get("key") or "").strip()}
    recent_title_token_sets = [_title_tokens(item) for item in recent_titles[:20]]
    author_memory = manifest.get("author_memory") or {}
    writing_persona = manifest.get("writing_persona") or {}
    threshold = max(int(legacy.TITLE_SCORE_THRESHOLD or 0), 60)

    normalized_candidates: list[dict[str, Any]] = []
    seen_titles: set[str] = set()
    source_candidates = list(candidates or [])
    if topic and all(str(item.get("title") or "").strip() != topic for item in source_candidates):
        source_candidates.append({"title": topic, "strategy": "原始主题", "audience_fit": audience, "risk_note": "补入原始主题参与决策。"})
    if selected_title and all(str(item.get("title") or "").strip() != selected_title for item in source_candidates):
        source_candidates.append({"title": selected_title, "strategy": "显式指定标题", "audience_fit": audience, "risk_note": "显式指定标题，保留参与决策。"})

    for item in source_candidates:
        title = str(item.get("title") or "").strip()
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)
        base = legacy.title_dimension_score(title, audience, angle)
        template_key = title_template_key(title)
        token_set = _title_tokens(title)
        max_overlap = max((_jaccard(token_set, other) for other in recent_title_token_sets), default=0.0)
        repeat_penalty = 0
        if title in recent_titles:
            repeat_penalty += 12
        if recent_titles and any(title.startswith(other[:10]) for other in recent_titles[:6] if len(other) >= 10):
            repeat_penalty += 3
        pattern_count = _first_hit(recent_patterns, template_key)
        if template_key and template_key in recent_title_patterns:
            repeat_penalty += 4 + min(4, pattern_count)
        if max_overlap >= 0.5:
            repeat_penalty += 4
        elif max_overlap >= 0.3:
            repeat_penalty += 2

        propagation_score = round(max(1.0, min(10.0, float(base["total_score"]) / 10.0)), 2)
        novelty_score = round(max(1.0, 10.0 - min(8.0, repeat_penalty / 1.8)), 2)
        differentiation_score = 10.0
        if template_key in recent_title_patterns:
            differentiation_score -= 2.5
        differentiation_score -= min(3.0, max_overlap * 5.0)
        if title in recent_titles:
            differentiation_score -= 3.0
        differentiation_score = round(max(1.0, min(differentiation_score, 10.0)), 2)
        author_fit_score, author_notes = _author_fit_score(title, author_memory, editorial_blueprint, writing_persona if isinstance(writing_persona, dict) else {})
        trust_score, trust_notes = _trust_score(title, research, item)
        integrity = title_integrity_report(title, topic=topic, account_strategy=account_strategy)
        integrity_score = float(integrity.get("score") or 0)
        total_score = round(
            (
                propagation_score * 0.24
                + novelty_score * 0.20
                + differentiation_score * 0.18
                + author_fit_score * 0.13
                + trust_score * 0.10
                + integrity_score * 0.15
            )
            * 10
        )
        gate_passed = bool(
            total_score >= threshold
            and propagation_score >= 5.0
            and novelty_score >= 5.0
            and differentiation_score >= 5.0
            and integrity.get("passed")
        )
        decision_notes = []
        if novelty_score >= 7.0:
            decision_notes.append("和近期标题路数拉开了距离")
        if differentiation_score >= 7.0:
            decision_notes.append("没有明显撞上近期高频模板")
        if propagation_score >= 7.0:
            decision_notes.append("传播钩子和清晰度足够")
        if author_fit_score >= 7.0:
            decision_notes.append("更像这个号会用的标题气质")
        if integrity.get("passed"):
            decision_notes.append("语义完整，读起来不像拼接残句")
        decision_notes.extend(author_notes[:2])
        decision_notes.extend(trust_notes[:2])
        rejection_reason = []
        if novelty_score < 5.0:
            rejection_reason.append("和近期标题太像")
        if differentiation_score < 5.0:
            rejection_reason.append("仍然带明显旧模板")
        if propagation_score < 5.0:
            rejection_reason.append("传播性不够")
        if trust_score < 5.0:
            rejection_reason.append("可信度风险偏高")
        rejection_reason.extend(integrity.get("issues") or [])

        normalized_candidates.append(
            {
                **item,
                "title": title,
                "title_template_key": template_key,
                "title_score": total_score,
                "title_gate_passed": gate_passed,
                "title_score_threshold": threshold,
                "title_repeat_penalty": repeat_penalty,
                "title_score_breakdown": base.get("score_breakdown") or [],
                "decision_breakdown": {
                    "传播潜力": propagation_score,
                    "新鲜度": novelty_score,
                    "差异度": differentiation_score,
                    "作者匹配度": author_fit_score,
                    "可信度": trust_score,
                    "完整性": integrity_score,
                },
                "decision_notes": decision_notes[:5],
                "rejection_reason": rejection_reason[:5],
                "recent_title_overlap": round(max_overlap, 3),
                "title_integrity": integrity,
            }
        )

    normalized_candidates.sort(
        key=lambda item: (
            bool(item.get("title_gate_passed")),
            float(item.get("title_score") or 0),
            float((item.get("decision_breakdown") or {}).get("完整性") or 0),
            float((item.get("decision_breakdown") or {}).get("新鲜度") or 0),
            float((item.get("decision_breakdown") or {}).get("差异度") or 0),
        ),
        reverse=True,
    )
    selected = normalized_candidates[0] if normalized_candidates else None
    selected_title_value = str(selected.get("title") or topic) if selected else topic
    selected_reason = []
    if selected:
        selected_reason.extend(selected.get("decision_notes") or [])
        if not selected_reason:
            selected_reason.append("综合新鲜度、差异度和传播潜力后更优")
    return {
        "topic": topic,
        "audience": audience,
        "angle": angle,
        "threshold": threshold,
        "selected_title": selected_title_value,
        "selected_reason": selected_reason[:5],
        "candidates": normalized_candidates,
        "generated_at": legacy.now_iso(),
    }


def markdown_title_decision_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# 标题决策报告：{payload.get('selected_title') or '未命名标题'}",
        "",
        f"- 原始主题：{payload.get('topic') or ''}",
        f"- 决策阈值：{payload.get('threshold') or 0}",
    ]
    for item in payload.get("selected_reason") or []:
        lines.append(f"- 入选原因：{item}")
    lines.append("")
    for candidate in (payload.get("candidates") or [])[:6]:
        breakdown = candidate.get("decision_breakdown") or {}
        lines.append(f"## {candidate.get('title') or '未命名标题'}")
        lines.append("")
        lines.append(f"- 总分：{candidate.get('title_score', 0)}｜{'通过' if candidate.get('title_gate_passed') else '未通过'}")
        lines.append(
            f"- 六项判断：传播 {breakdown.get('传播潜力', 0)} / 新鲜 {breakdown.get('新鲜度', 0)} / 差异 {breakdown.get('差异度', 0)} / 作者匹配 {breakdown.get('作者匹配度', 0)} / 可信度 {breakdown.get('可信度', 0)} / 完整性 {breakdown.get('完整性', 0)}"
        )
        for note in candidate.get("decision_notes") or []:
            lines.append(f"- 亮点：{note}")
        for note in candidate.get("rejection_reason") or []:
            lines.append(f"- 风险：{note}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
