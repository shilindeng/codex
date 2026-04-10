from __future__ import annotations

import re
from typing import Any


SEVERITY_ORDER = {"strong": 3, "medium": 2, "weak": 1}
OPENING_SCENE_MARKERS = (
    "那天",
    "刚刚",
    "刚才",
    "会议室",
    "办公室",
    "工位",
    "白板",
    "凌晨",
    "中午",
    "晚上",
    "看到",
    "听到",
    "消息弹出来",
    "群里",
)
OPENING_PAIN_MARKERS = (
    "焦虑",
    "卡住",
    "害怕",
    "不敢",
    "迷茫",
    "被淘汰",
    "没流量",
    "没结果",
    "做不好",
    "不会",
)
OPENING_PROMISE_PATTERNS = (
    r"这篇文章",
    r"接下来",
    r"我会告诉你",
    r"你会看到",
    r"你将(?:会)?",
    r"帮你搞懂",
    r"帮你看清",
    r"答案",
    r"方法",
    r"只要记住",
)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _paragraphs(text: str) -> list[str]:
    return [_normalize_text(part) for part in re.split(r"\n\s*\n", str(text or "")) if _normalize_text(part)]


def _snippet(text: str, limit: int = 38) -> str:
    value = _normalize_text(text)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _append(
    findings: list[dict[str, Any]],
    *,
    kind: str,
    label: str,
    severity: str,
    count: int,
    evidence: str,
    rewrite_hint: str,
    source_skill: str,
    fingerprint_id: str,
) -> None:
    findings.append(
        {
            "type": kind,
            "label": label,
            "severity": severity,
            "count": max(1, int(count or 1)),
            "pattern": kind,
            "evidence": evidence,
            "rewrite_hint": rewrite_hint,
            "source_skill": source_skill,
            "fingerprint_id": fingerprint_id,
        }
    )


def _detect_dead_opening_self_intro(paragraphs: list[str], findings: list[dict[str, Any]]) -> None:
    if not paragraphs:
        return
    opening = paragraphs[0]
    match = re.search(
        r"^(大家好|你好(?:呀)?|我是[^，。]{1,12}|今天(?:想|来|给大家|我们)|欢迎来到|今天聊聊|今天分享)",
        opening,
    )
    if not match:
        return
    _append(
        findings,
        kind="dead_opening_self_intro",
        label="开头先自我介绍",
        severity="strong",
        count=1,
        evidence=f"开头直接自我介绍或主持腔：{match.group(0)}",
        rewrite_hint="把开头改成一个具体场景、结果反差或真正的问题，不要先报幕。",
        source_skill="dbs-hook",
        fingerprint_id="hook-1",
    )


def _detect_opening_triad(paragraphs: list[str], findings: list[dict[str, Any]]) -> None:
    if not paragraphs:
        return
    opening = "\n".join(paragraphs[:3])
    if any(marker in opening for marker in OPENING_SCENE_MARKERS):
        return
    hook_hit = any(re.search(r"^(如果你|你是不是|你是否|总觉得|很多人|别再)", paragraph) for paragraph in paragraphs[:2])
    pain_hits = sum(opening.count(marker) for marker in OPENING_PAIN_MARKERS)
    promise_hits = sum(len(re.findall(pattern, opening)) for pattern in OPENING_PROMISE_PATTERNS)
    if hook_hit and pain_hits >= 1 and promise_hits >= 1:
        _append(
            findings,
            kind="opening_triad",
            label="开头钩子+痛点+承诺三件套",
            severity="strong",
            count=pain_hits + promise_hits,
            evidence="开头先卖焦虑，再承诺答案，像标准化转化页，不像真人开场。",
            rewrite_hint="把开头改成真实处境或结果切口，先说你真正在意的事，不要先卖焦虑。",
            source_skill="dbs-ai-check",
            fingerprint_id="16",
        )


def _detect_reader_strawman(text: str, findings: list[dict[str, Any]]) -> None:
    patterns = [
        "你可能会觉得",
        "你也许会觉得",
        "你可能以为",
        "你可能会问",
        "也许你会说",
        "有人会说",
        "很多人会觉得",
        "很多人会说",
    ]
    hits = [(pattern, text.count(pattern)) for pattern in patterns if text.count(pattern)]
    total = sum(count for _pattern, count in hits)
    if total < 1:
        return
    evidence = " / ".join(pattern for pattern, _count in hits[:3])
    _append(
        findings,
        kind="reader_strawman",
        label="替读者预设观点再纠正",
        severity="strong" if total >= 2 else "medium",
        count=total,
        evidence=f"替读者先说一句话再回头纠正：{evidence}",
        rewrite_hint="删掉假想读者台词，直接写你真正想表达的判断和证据。",
        source_skill="dbs-ai-check",
        fingerprint_id="7",
    )


def _detect_concession_template(text: str, findings: list[dict[str, Any]]) -> None:
    patterns = [
        "当然",
        "也不是说",
        "不是说",
        "并不是说",
        "某种程度上",
        "换个角度",
        "话说回来",
    ]
    hits = [(pattern, text.count(pattern)) for pattern in patterns if text.count(pattern)]
    total = sum(count for _pattern, count in hits)
    if total < 3:
        return
    evidence = " / ".join(pattern for pattern, _count in hits[:3])
    _append(
        findings,
        kind="concession_template",
        label="同一种让步模板反复出现",
        severity="medium",
        count=total,
        evidence=f"让步转折句式反复出现：{evidence}",
        rewrite_hint="同类让步结构只留一处，其余位置改成直接判断、例子或删掉。",
        source_skill="dbs-ai-check",
        fingerprint_id="4",
    )


def _detect_naming_ritual(text: str, findings: list[dict[str, Any]]) -> None:
    pattern = r"(我把这叫做|我称之为|可以把它叫做|姑且叫它|暂且叫它|我更愿意把它叫做)"
    hits = re.findall(pattern, text)
    if len(hits) < 2:
        return
    _append(
        findings,
        kind="naming_ritual",
        label="概念命名仪式过多",
        severity="medium",
        count=len(hits),
        evidence=f"短文里多次给概念命名：{' / '.join(dict.fromkeys(hits))}",
        rewrite_hint="只保留一个真正必要的概念名，其余用普通话说清楚。",
        source_skill="dbs-ai-check",
        fingerprint_id="5",
    )


def _detect_translationese(text: str, findings: list[dict[str, Any]]) -> None:
    markers = [
        "作为",
        "对于",
        "关于",
        "基于",
        "进行",
        "实现",
        "通过",
        "围绕",
        "展开",
        "在…层面",
        "在…维度",
        "以便",
        "从而",
    ]
    counts = {marker: text.count(marker) for marker in markers if text.count(marker)}
    total = sum(counts.values())
    density = total / max(1, len(text))
    if total < 6 and density < 0.018:
        return
    evidence = " / ".join(list(counts.keys())[:4])
    _append(
        findings,
        kind="translationese",
        label="中文翻译腔",
        severity="medium",
        count=total,
        evidence=f"函数词密度偏高：{evidence}",
        rewrite_hint="把“作为、关于、基于、进行”这类词换成口语直说，按你平时会说的话重写。",
        source_skill="dbs-ai-check",
        fingerprint_id="19",
    )


def _detect_connective_overload(text: str, findings: list[dict[str, Any]]) -> None:
    patterns = [
        "然而",
        "与此同时",
        "此外",
        "另外",
        "事实上",
        "换句话说",
        "值得注意的是",
        "需要注意的是",
        "总的来说",
        "总而言之",
    ]
    hits = [(pattern, text.count(pattern)) for pattern in patterns if text.count(pattern)]
    total = sum(count for _pattern, count in hits)
    if total < 5:
        return
    evidence = " / ".join(pattern for pattern, _count in hits[:4])
    _append(
        findings,
        kind="connective_overload",
        label="连接词过密",
        severity="medium",
        count=total,
        evidence=f"逻辑连接词堆得太满：{evidence}",
        rewrite_hint="删掉一半连接词，让句子自己推动逻辑，不要每次都靠路标词领着读者走。",
        source_skill="dbs-ai-check",
        fingerprint_id="17",
    )


def _detect_certainty_overload(text: str, findings: list[dict[str, Any]]) -> None:
    assertive = ["一定", "必然", "永远", "所有", "唯一", "完全", "注定", "必须"]
    hedges = ["可能", "也许", "未必", "不一定", "大概", "某种程度", "例外", "前提"]
    strong_hits = sum(text.count(item) for item in assertive)
    hedge_hits = sum(text.count(item) for item in hedges)
    if strong_hits < 4 or hedge_hits >= 2 or len(text) < 220:
        return
    _append(
        findings,
        kind="certainty_overload",
        label="整篇没有犹豫感",
        severity="medium",
        count=strong_hits,
        evidence=f"高确定性词太多，但几乎没有边界词：确定词 {strong_hits} 次",
        rewrite_hint="补一句你真正不确定的地方，或者补一个适用边界，别把整篇写成全知判断。",
        source_skill="dbs-ai-check",
        fingerprint_id="9",
    )


def _detect_pseudo_depth(text: str, findings: list[dict[str, Any]]) -> None:
    markers = ["本质上", "归根结底", "更深层", "终极", "底层逻辑", "高维", "宏大命题"]
    hits = [(marker, text.count(marker)) for marker in markers if text.count(marker)]
    total = sum(count for _marker, count in hits)
    if total < 2:
        return
    evidence = " / ".join(marker for marker, _count in hits[:4])
    _append(
        findings,
        kind="pseudo_depth",
        label="对深刻感用力过猛",
        severity="medium",
        count=total,
        evidence=f"频繁把问题往“更深层/本质”上抬：{evidence}",
        rewrite_hint="少说“本质上、归根结底”，多给一个具体事实或动作来证明深度。",
        source_skill="dbs-ai-check",
        fingerprint_id="22",
    )


def _detect_body_feeling_answer(text: str, findings: list[dict[str, Any]]) -> None:
    markers = ["身体会知道", "身体知道答案", "身体不会说谎", "本能会告诉你", "跟着身体走", "让身体替你决定"]
    hits = [(marker, text.count(marker)) for marker in markers if text.count(marker)]
    total = sum(count for _marker, count in hits)
    if total < 1:
        return
    evidence = " / ".join(marker for marker, _count in hits[:3])
    _append(
        findings,
        kind="body_feeling_answer",
        label="用身体感受代替论证",
        severity="strong",
        count=total,
        evidence=f"在关键结论处拿身体感受收尾：{evidence}",
        rewrite_hint="把“身体知道答案”换成具体原因、例子或直接承认你还没讲透。",
        source_skill="dbs-ai-check",
        fingerprint_id="15",
    )


def _detect_blessing_close(paragraphs: list[str], findings: list[dict[str, Any]]) -> None:
    if not paragraphs:
        return
    closing = "\n".join(paragraphs[-2:])
    markers = ["你值得", "愿你", "希望你", "请相信自己", "配得上", "被温柔以待"]
    hits = [marker for marker in markers if marker in closing]
    if not hits:
        return
    _append(
        findings,
        kind="blessing_close",
        label="结尾祝福腔",
        severity="strong",
        count=len(hits),
        evidence=f"结尾突然切到祝福口吻：{' / '.join(hits)}",
        rewrite_hint="把结尾收回到判断、风险或余味，不要临门一脚变成安慰话术。",
        source_skill="dbs-ai-check",
        fingerprint_id="21",
    )


def _detect_precise_emotion(text: str, findings: list[dict[str, Any]]) -> None:
    if not re.search(r"\d+(?:\.\d+)?秒", text):
        return
    if not re.search(r"(心跳|窒息|崩溃|刺痛|想哭|慌|发麻)", text):
        return
    _append(
        findings,
        kind="fake_precision_emotion",
        label="情绪细节精确得不真实",
        severity="strong",
        count=1,
        evidence="用秒数或精确数字包装情绪体验，像后期补的拟真细节。",
        rewrite_hint="删掉伪精确数字，改成你当时真会说出口的感受。",
        source_skill="dbs-ai-check",
        fingerprint_id="10",
    )


def _detect_story_stub(paragraphs: list[str], findings: list[dict[str, Any]]) -> None:
    for paragraph in paragraphs:
        if not re.search(r"(我有个朋友|一个朋友|有人跟我说|之前认识一个|有个人)", paragraph):
            continue
        has_detail = bool(re.search(r"\d{4}年|\d+月|\d+点|\d+次|公司|会议室|办公室|项目|客户", paragraph))
        if has_detail:
            continue
        _append(
            findings,
            kind="story_stub",
            label="故事只有壳没有细节",
            severity="medium",
            count=1,
            evidence=f"故事起手很像例子，但细节不够：{_snippet(paragraph)}",
            rewrite_hint="故事要么补具体细节，要么删掉，别拿模糊“朋友案例”充当证据。",
            source_skill="dbs-ai-check",
            fingerprint_id="20",
        )
        return


def _detect_knowledge_dump(paragraphs: list[str], findings: list[dict[str, Any]]) -> None:
    jargon_markers = ("模型", "框架", "机制", "路径", "范式", "生态", "策略", "协同", "场景", "抓手", "能力")
    for paragraph in paragraphs:
        if paragraph.count("、") < 4:
            continue
        jargon_hits = sum(1 for marker in jargon_markers if marker in paragraph)
        if jargon_hits < 5:
            continue
        _append(
            findings,
            kind="knowledge_dump",
            label="知识一股脑倒出来",
            severity="medium",
            count=jargon_hits,
            evidence=f"一段里堆了太多抽象概念：{_snippet(paragraph)}",
            rewrite_hint="只留一个真正关键的概念，剩下的拆成例子、动作或删掉。",
            source_skill="dbs-ai-check",
            fingerprint_id="2",
        )
        return


def detect_ai_fingerprints(text: str, *, genre: str = "article") -> list[dict[str, Any]]:
    normalized = _normalize_text(text)
    paragraphs = _paragraphs(text)
    findings: list[dict[str, Any]] = []
    _detect_dead_opening_self_intro(paragraphs, findings)
    _detect_opening_triad(paragraphs, findings)
    _detect_reader_strawman(normalized, findings)
    _detect_concession_template(normalized, findings)
    _detect_naming_ritual(normalized, findings)
    _detect_translationese(normalized, findings)
    _detect_connective_overload(normalized, findings)
    _detect_certainty_overload(normalized, findings)
    _detect_pseudo_depth(normalized, findings)
    _detect_body_feeling_answer(normalized, findings)
    _detect_blessing_close(paragraphs, findings)
    _detect_precise_emotion(normalized, findings)
    _detect_story_stub(paragraphs, findings)
    _detect_knowledge_dump(paragraphs, findings)
    findings.sort(
        key=lambda item: (
            -SEVERITY_ORDER.get(str(item.get("severity") or "").lower(), 0),
            -int(item.get("count") or 0),
            str(item.get("type") or ""),
        )
    )
    return findings


def summarize_ai_fingerprints(findings: list[dict[str, Any]]) -> dict[str, Any]:
    relevant = [
        item
        for item in findings
        if item.get("fingerprint_id") or item.get("rewrite_hint") or item.get("source_skill")
    ]
    strong = [item for item in relevant if str(item.get("severity") or "") == "strong"]
    medium = [item for item in relevant if str(item.get("severity") or "") == "medium"]
    weak = [item for item in relevant if str(item.get("severity") or "") == "weak"]
    labels = [str(item.get("label") or item.get("type") or "").strip() for item in relevant if str(item.get("label") or item.get("type") or "").strip()]
    rewrite_hints = []
    for item in relevant:
        hint = str(item.get("rewrite_hint") or "").strip()
        if hint and hint not in rewrite_hints:
            rewrite_hints.append(hint)
    return {
        "strong_count": len(strong),
        "medium_count": len(medium),
        "weak_count": len(weak),
        "top_labels": labels[:5],
        "top_evidence": [str(item.get("evidence") or "").strip() for item in relevant[:5] if str(item.get("evidence") or "").strip()],
        "rewrite_hints": rewrite_hints[:5],
    }
