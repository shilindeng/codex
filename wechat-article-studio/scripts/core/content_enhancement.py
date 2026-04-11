from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.artifacts import now_iso, read_json, write_json, write_text


ENHANCEMENT_STRATEGIES: dict[str, dict[str, str]] = {
    "angle-discovery": {"label": "角度发现", "goal": "把切口讲尖，避免空泛平铺"},
    "density-strengthening": {"label": "密度强化", "goal": "把步骤、数字和条件分支补实"},
    "detail-anchoring": {"label": "细节锚定", "goal": "把场景、时间、动作和代价补出来"},
    "real-voice-comparison": {"label": "真实体感", "goal": "把真实体验、适用人群和反例讲出来"},
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" -•\n\r\t")


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        output: list[str] = []
        for item in value:
            if isinstance(item, dict):
                value_text = _normalize_text(
                    str(
                        item.get("sentence")
                        or item.get("quote")
                        or item.get("text")
                        or item.get("page_title")
                        or item.get("title")
                        or item.get("url")
                        or ""
                    )
                )
            else:
                value_text = _normalize_text(str(item))
            if value_text:
                output.append(value_text)
        return output
    if isinstance(value, str):
        items = [_normalize_text(item) for item in re.split(r"[；;\n]", value) if _normalize_text(item)]
        return items
    return []


def _keyword_tokens(*values: str) -> list[str]:
    raw = " ".join(_normalize_text(value) for value in values if _normalize_text(value))
    if not raw:
        return []
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9._-]{1,}|[\u4e00-\u9fff]{2,8}", raw)
    output: list[str] = []
    seen: set[str] = set()
    stop = {"这个", "那个", "问题", "事情", "方法", "步骤", "工具", "系统", "平台", "最后", "真正", "先别", "怎么", "如何"}
    for token in tokens:
        lowered = token.lower()
        if lowered in seen or token in stop:
            continue
        seen.add(lowered)
        output.append(token)
    return output[:10]


def enhancement_strategy_for_archetype(archetype: str, title: str = "") -> str:
    key = _normalize_text(archetype).lower()
    title_text = _normalize_text(title)
    if key in {"tutorial", "playbook", "list-practical"}:
        return "density-strengthening"
    if key in {"case-study", "story", "narrative", "retrospective"}:
        return "detail-anchoring"
    if key in {"comparison", "review"} or any(word in title_text for word in ["对比", "选型", "测评", "A 还是 B", "横评"]):
        return "real-voice-comparison"
    return "angle-discovery"


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    for raw in values:
        value = _normalize_text(raw)
        if value and value not in output:
            output.append(value)
    return output


def _dedupe_dicts(items: list[dict[str, Any]], *, key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = "||".join(_normalize_text(str(item.get(field) or "")) for field in key_fields)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _source_cards(research: dict[str, Any], evidence_report: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for item in (research.get("sources") or []):
        if isinstance(item, dict):
            title = _normalize_text(str(item.get("title") or item.get("page_title") or item.get("url") or ""))
            url = _normalize_text(str(item.get("url") or ""))
            note = _normalize_text(str(item.get("note") or item.get("credibility") or item.get("source_type") or ""))
            quote = _normalize_text(str(item.get("sentence") or item.get("quote") or item.get("description") or ""))
        else:
            title = _normalize_text(str(item))
            url = _normalize_text(str(item))
            note = ""
            quote = ""
        if title or url:
            cards.append({"title": title or url, "url": url, "note": note, "quote": quote})
    for item in ((evidence_report or {}).get("items") or []):
        if not isinstance(item, dict):
            continue
        title = _normalize_text(str(item.get("page_title") or item.get("title") or item.get("url") or ""))
        url = _normalize_text(str(item.get("url") or ""))
        note = _normalize_text(str(item.get("description") or item.get("source_type") or item.get("domain") or ""))
        quote = _normalize_text(str(item.get("sentence") or item.get("quote") or ""))
        if title or url or quote:
            cards.append({"title": title or url or "来源", "url": url, "note": note, "quote": quote})
    return _dedupe_dicts(cards, key_fields=("title", "url", "quote"))[:8]


def _evidence_quotes(research: dict[str, Any], evidence_report: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in (research.get("evidence_items") or []):
        if isinstance(item, dict):
            text = _normalize_text(str(item.get("sentence") or item.get("quote") or item.get("text") or item.get("page_title") or ""))
            title = _normalize_text(str(item.get("page_title") or item.get("title") or item.get("url") or ""))
            url = _normalize_text(str(item.get("url") or ""))
            note = _normalize_text(str(item.get("description") or item.get("source_type") or ""))
        else:
            text = _normalize_text(str(item))
            title = ""
            url = ""
            note = ""
        if text:
            entries.append({"text": text, "title": title, "url": url, "note": note})
    for item in ((evidence_report or {}).get("items") or []):
        if not isinstance(item, dict):
            continue
        text = _normalize_text(str(item.get("sentence") or item.get("quote") or ""))
        title = _normalize_text(str(item.get("page_title") or item.get("title") or item.get("url") or ""))
        url = _normalize_text(str(item.get("url") or ""))
        note = _normalize_text(str(item.get("description") or item.get("source_type") or item.get("domain") or ""))
        if text:
            entries.append({"text": text, "title": title, "url": url, "note": note})
    return _dedupe_dicts(entries, key_fields=("text", "url"))[:12]


def _match_materials(section: dict[str, Any], materials: list[dict[str, Any]], title: str, limit: int = 3) -> list[dict[str, Any]]:
    section_tokens = _keyword_tokens(
        title,
        str(section.get("heading") or ""),
        str(section.get("goal") or ""),
        str(section.get("evidence_need") or ""),
    )
    if not materials:
        return []

    def score(item: dict[str, Any]) -> tuple[int, int]:
        text = " ".join(str(item.get(field) or "") for field in ["text", "title", "note", "quote"])
        material_tokens = set(_keyword_tokens(text))
        overlap = len(set(section_tokens) & material_tokens)
        richness = 1 if item.get("url") else 0
        if item.get("quote") or item.get("text"):
            richness += 1
        return overlap, richness

    ranked = sorted(materials, key=score, reverse=True)
    best = [item for item in ranked if score(item)[0] > 0][:limit]
    if len(best) < limit:
        for item in ranked[:limit]:
            if item not in best:
                best.append(item)
            if len(best) >= limit:
                break
    return best[:limit]


def _section_evidence_targets(section: dict[str, Any], research: dict[str, Any], evidence_report: dict[str, Any] | None = None) -> list[str]:
    evidence_need = _normalize_text(str(section.get("evidence_need") or ""))
    evidence_items = [item.get("text") or item.get("quote") or "" for item in _evidence_quotes(research, evidence_report)[:3]]
    sources = [item.get("title") or item.get("url") or "" for item in _source_cards(research, evidence_report)[:3]]
    output = _dedupe([evidence_need, *evidence_items, *sources])
    return output[:4]


def _detail_anchors(title: str, section: dict[str, Any], archetype: str) -> list[str]:
    heading = _normalize_text(str(section.get("heading") or ""))
    anchors = [
        "补一个能被看见的具体动作或瞬间。",
        "补一个时间锚、数字锚或结果锚。",
    ]
    if archetype in {"case-study", "narrative"}:
        anchors.extend(
            [
                f"围绕“{heading or title}”补一处人物说法、决策动作或代价变化。",
                "优先写会议、群聊、页面、工单、客户反馈这类真实场景。",
            ]
        )
    else:
        anchors.append(f"不要只解释“{heading or title}”，要写出它在真实工作里是怎么发生的。")
    return _dedupe(anchors)[:4]


def _counterpoint_targets(section: dict[str, Any], archetype: str) -> list[str]:
    heading = _normalize_text(str(section.get("heading") or ""))
    if archetype == "tutorial":
        return [
            f"写清“{heading or '这一节'}”最容易做反的地方。",
            "补一个不适用场景或前提限制。",
        ]
    return [
        f"给“{heading or '这一节'}”补一个常见误判或反方看法。",
        "说明什么情况下这个判断不成立，避免写成单向宣讲。",
    ]


def _cost_targets(title: str, section: dict[str, Any]) -> list[str]:
    heading = _normalize_text(str(section.get("heading") or title or "这一节"))
    return [
        f"围绕“{heading}”补一段现实代价，写清谁在付、付在哪里、后果是什么。",
        "不要只说成本很高，要把代价落到对象、时间、返工、损耗或风险上。",
    ]


def _discussion_targets(title: str, section: dict[str, Any]) -> list[str]:
    heading = _normalize_text(str(section.get("heading") or title or "这一节"))
    return [
        f"围绕“{heading}”补一个会让读者想接话的问题、站队点或经验分歧。",
        "评论点要来自正文判断本身，不要最后再硬塞一句“如果是你”。",
    ]


def _table_targets(title: str, section: dict[str, Any], archetype: str) -> list[str]:
    heading = _normalize_text(str(section.get("heading") or title or "这一节"))
    evidence_need = _normalize_text(str(section.get("evidence_need") or ""))
    if archetype == "tutorial":
        return [
            f"围绕“{heading}”补一张小表格，至少列出步骤、常见错误和判断依据。",
            "表格优先帮助读者快速看清顺序、条件或成本，不要做装饰。",
        ]
    if any(word in f"{heading} {evidence_need}" for word in ["对比", "选型", "成本", "差异", "趋势", "分水岭", "判断"]):
        return [
            f"围绕“{heading}”补一张 2 到 4 列的小表格，帮助读者一眼看懂差异、趋势或成本。",
            "表格必须服务判断，至少要能回答“差在哪”“贵在哪”或“该怎么选”。",
        ]
    return [
        f"如果“{heading}”里出现多个对象、阶段或结果，优先补一张表格把差异讲清楚。",
        "没有结构化表格时，至少提前想好指标、现状、风险、判断这几列该怎么摆。",
    ]


def _analogy_targets(title: str, section: dict[str, Any]) -> list[str]:
    heading = _normalize_text(str(section.get("heading") or title or "这一节"))
    return [
        f"围绕“{heading}”补一段类比分析，把抽象问题讲成读者一听就懂的画面。",
        "类比要服务解释，不要为了好看硬凑比喻。",
    ]


def _comparison_targets(title: str, section: dict[str, Any], archetype: str) -> list[str]:
    heading = _normalize_text(str(section.get("heading") or title or "这一节"))
    if archetype == "tutorial":
        return [
            f"围绕“{heading}”补一个做对与做错的对比，让读者知道差别会落在哪。",
            "对比要落到结果、成本或适用条件，别只写抽象判断。",
        ]
    return [
        f"围绕“{heading}”补一段对比分析，讲清表面像什么、实际差在哪。",
        "对比至少要落到对象、路径、成本、风险中的一项。",
    ]


def _citation_targets(section: dict[str, Any], research: dict[str, Any], evidence_report: dict[str, Any] | None = None) -> list[str]:
    cards = _source_cards(research, evidence_report)
    quotes = _evidence_quotes(research, evidence_report)
    output: list[str] = []
    for item in quotes[:2]:
        text = _normalize_text(str(item.get("text") or ""))
        if text:
            output.append(f"把这条证据自然写进正文：{text}")
    for item in cards[:2]:
        title_text = _normalize_text(str(item.get("title") or item.get("url") or "来源"))
        if title_text:
            output.append(f"把“{title_text}”自然融进句子，不要只在文末挂来源。")
    if not output:
        heading = _normalize_text(str(section.get("heading") or "这一节"))
        output = [f"围绕“{heading}”至少补 2 处来源化表达，让判断有出处。"] 
    return _dedupe(output)[:4]


def _section_must_include(strategy: str, section: dict[str, Any], title: str) -> list[str]:
    heading = _normalize_text(str(section.get("heading") or title or ""))
    if strategy == "angle-discovery":
        return [
            f"把“{heading}”这节真正要打穿的判断说成一句能转述的话。",
            "补一个主流说法，再补一个你自己的反差角度。",
        ]
    if strategy == "density-strengthening":
        return [
            f"围绕“{heading}”补至少一个具体步骤、一个工具或一个数字。",
            "说明适合谁、不适合谁，别写成万能方法。",
        ]
    if strategy == "detail-anchoring":
        return [
            f"围绕“{heading}”补场景、动作和代价变化。",
            "尽量留下一个能让读者脑子里有画面的细节。",
        ]
    return [
        f"围绕“{heading}”补真实体验差异和适用人群。",
        "至少讲一个踩坑点或反例，不要只列优点。",
    ]


def _shared_materials(
    title: str,
    outline_meta: dict[str, Any],
    research: dict[str, Any],
    author_memory: dict[str, Any],
    writing_persona: dict[str, Any],
    strategy: str,
    evidence_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blueprint = outline_meta.get("viral_blueprint") or {}
    core_judgment = _normalize_text(str(blueprint.get("core_viewpoint") or title))
    secondary = _normalize_list(blueprint.get("secondary_viewpoints"))
    evidence_items = _evidence_quotes(research, evidence_report)
    sources = _source_cards(research, evidence_report)
    exemplar_snippets = []
    for item in (author_memory.get("example_snippets") or [])[:3]:
        if isinstance(item, dict):
            text = _normalize_text(str(item.get("text") or ""))
            if text:
                exemplar_snippets.append({"slot": item.get("slot") or "example", "text": text})
    disallowed_moves = _dedupe(
        _normalize_list((outline_meta.get("editorial_blueprint") or {}).get("forbidden_moves"))
        + _normalize_list((writing_persona or {}).get("avoid_moves"))
        + _normalize_list(author_memory.get("playbook_summary"))
    )[:8]
    counter_angles = []
    if strategy == "angle-discovery":
        counter_angles = _dedupe(
            [
                "不要只复述大家已经在说的表面热闹。",
                "优先找被低估的影响路径、代价或边界。",
                "如果观点不够尖，就先补证据再收窄切口。",
            ]
            + [f"把“{item}”换成更有分水岭的判断。" for item in secondary[:2]]
        )[:4]
    return {
        "core_judgment": core_judgment,
        "mainstream_views": secondary[:4],
        "counter_angles": counter_angles,
        "opening_requirements": [
            "前 300~400 字必须同时出现主判断和一个具体场景/动作。",
            "第一个小标题前最多 4 段，不要先铺成长背景说明。",
            "首屏至少让读者看见一个人、一个动作、一个代价，三项里至少占两项。",
        ],
        "summary_requirements": [
            "摘要必须同时包含主判断和现实后果。",
            "摘要长度控制在 45~90 个可见字符之间。",
            "摘要要和正文前 3 段对齐，不要单独喊口号。",
        ],
        "material_requirements": [
            "正文至少落下 4 类素材：数据、表格、引用、类比、案例、对比分析、反方/边界。",
            "至少补 1 个 Markdown 表格，而且表格必须帮助读者看懂差异、趋势或成本。",
            "至少补 2 处自然来源化表达或引用，不要只在文末堆来源。",
            "至少补 1 段类比分析和 1 段对比分析，把抽象问题讲直白。",
            "正文至少补 1 段现实代价和 1 个可讨论分歧点。",
        ],
        "evidence_targets": [item.get("text") or "" for item in evidence_items[:4]],
        "source_cards": sources[:4],
        "evidence_quotes": evidence_items[:4],
        "disallowed_moves": disallowed_moves,
        "exemplar_snippets": exemplar_snippets[:3],
    }


def build_content_enhancement(
    *,
    title: str,
    outline_meta: dict[str, Any],
    manifest: dict[str, Any],
    research: dict[str, Any] | None = None,
    evidence_report: dict[str, Any] | None = None,
    author_memory: dict[str, Any] | None = None,
    writing_persona: dict[str, Any] | None = None,
) -> dict[str, Any]:
    research = research or {}
    evidence_report = evidence_report or {}
    author_memory = author_memory or {}
    writing_persona = writing_persona or {}
    blueprint = outline_meta.get("viral_blueprint") or {}
    raw_sections = list(outline_meta.get("sections") or [])
    sections: list[dict[str, Any]] = []
    for index, item in enumerate(raw_sections, start=1):
        if isinstance(item, dict):
            sections.append(item)
        else:
            heading = _normalize_text(str(item or ""))
            if heading:
                sections.append({"heading": heading, "goal": "展开该章节", "evidence_need": "补充案例或事实支撑"})
    if not sections:
        sections = [{"heading": "导语", "goal": "先把核心判断立住", "evidence_need": "场景或事实支撑"}]
    archetype = _normalize_text(str(blueprint.get("article_archetype") or manifest.get("article_archetype") or "commentary")).lower()
    strategy = enhancement_strategy_for_archetype(archetype, title)
    strategy_meta = ENHANCEMENT_STRATEGIES.get(strategy, ENHANCEMENT_STRATEGIES["angle-discovery"])
    shared = _shared_materials(title, outline_meta, research, author_memory, writing_persona, strategy, evidence_report)
    hard_requirements = _dedupe(
        [
            "至少有一节明确补场景或动作瞬间。",
            "至少有一节明确补案例、数据或事实托底。",
            "至少有一节明确补表格，帮助读者更快看懂差异、趋势或成本。",
            "至少有一节明确补类比分析，把抽象概念讲直白。",
            "至少有一节明确补对比分析，讲清表面像什么、实际差在哪。",
            "至少有一节明确补现实代价，写清谁在付、付在哪里、会多出什么后果。",
            "至少有一节明确补可讨论分歧点，给评论和转发留入口。",
            "正文至少出现 2 处自然来源化表达或引用。",
            "至少有一节明确补反方、误判或适用边界。",
            "前 300~400 字必须同时给出主判断和具体场景。",
            "第一个小标题前最多 4 段，不要把背景说明写成首屏主体。",
            "不要把所有段落都写成判断句卡片。",
        ]
        + [f"这篇稿子默认使用“{strategy_meta['label']}”策略。", strategy_meta["goal"]]
    )[:8]
    section_enhancements = []
    all_quotes = _evidence_quotes(research, evidence_report)
    all_sources = _source_cards(research, evidence_report)
    for index, section in enumerate(sections, start=1):
        matched_quotes = _match_materials(section, all_quotes, title, limit=2)
        matched_sources = _match_materials(section, all_sources, title, limit=2)
        section_enhancements.append(
            {
                "index": index,
                "heading": _normalize_text(str(section.get("heading") or f"第 {index} 节")),
                "section_goal": _normalize_text(str(section.get("goal") or "展开该章节")),
                "must_include": _section_must_include(strategy, section, title),
                "evidence_targets": _section_evidence_targets(section, research, evidence_report),
                "table_targets": _table_targets(title, section, archetype),
                "analogy_targets": _analogy_targets(title, section),
                "comparison_targets": _comparison_targets(title, section, archetype),
                "citation_targets": _citation_targets(section, research, evidence_report),
                "detail_anchors": _detail_anchors(title, section, archetype),
                "counterpoint_targets": _counterpoint_targets(section, archetype),
                "cost_targets": _cost_targets(title, section),
                "discussion_targets": _discussion_targets(title, section),
                "support_quotes": matched_quotes,
                "support_sources": matched_sources,
            }
        )
    return {
        "title": title,
        "generated_at": now_iso(),
        "article_archetype": archetype or "commentary",
        "strategy_key": strategy,
        "strategy_label": strategy_meta["label"],
        "strategy_goal": strategy_meta["goal"],
        "writing_persona": (writing_persona or {}).get("name") or "",
        "research_snapshot": {
            "source_count": len(all_sources),
            "evidence_count": len(all_quotes),
        },
        "hard_requirements": hard_requirements,
        "shared_materials": shared,
        "section_enhancements": section_enhancements,
    }


def markdown_content_enhancement(payload: dict[str, Any]) -> str:
    lines = [
        f"标题：{payload.get('title') or '未命名标题'}",
        f"策略：{payload.get('strategy_label') or ''}",
        f"目标：{payload.get('strategy_goal') or ''}",
        f"人格：{payload.get('writing_persona') or ''}",
    ]
    for item in payload.get("hard_requirements") or []:
        lines.append(f"硬要求：{item}")
    shared = payload.get("shared_materials") or {}
    if shared.get("core_judgment"):
        lines.append(f"核心判断：{shared['core_judgment']}")
    for item in shared.get("counter_angles") or []:
        lines.append(f"角度提醒：{item}")
    for item in shared.get("material_requirements") or []:
        lines.append(f"素材要求：{item}")
    for item in shared.get("evidence_targets") or []:
        lines.append(f"证据目标：{item}")
    for item in shared.get("source_cards") or []:
        if isinstance(item, dict):
            title_text = item.get("title") or item.get("url") or "来源"
            note_text = item.get("note") or ""
            lines.append(f"来源卡：{title_text}" + (f"｜{note_text}" if note_text else ""))
    for item in shared.get("evidence_quotes") or []:
        if isinstance(item, dict):
            lines.append(f"证据句：{item.get('text') or ''}")
    for item in payload.get("section_enhancements") or []:
        heading = item.get("heading") or "未命名章节"
        lines.append(f"章节：{heading}")
        for field in ["must_include", "evidence_targets", "table_targets", "analogy_targets", "comparison_targets", "citation_targets", "detail_anchors", "counterpoint_targets"]:
            for value in item.get(field) or []:
                lines.append(f"{heading} / {field}：{value}")
        for support in item.get("support_quotes") or []:
            if isinstance(support, dict):
                lines.append(f"{heading} / support_quotes：{support.get('text') or ''}")
        for support in item.get("support_sources") or []:
            if isinstance(support, dict):
                lines.append(f"{heading} / support_sources：{support.get('title') or support.get('url') or ''}")
    report_lines = [line for line in lines if line]
    return "# 写前增强\n\n" + "\n".join(f"- {line}" for line in report_lines) + "\n"


def write_content_enhancement_artifacts(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(workspace / "content-enhancement.json", payload)
    write_text(workspace / "content-enhancement.md", markdown_content_enhancement(payload))


def load_content_enhancement(workspace: Path) -> dict[str, Any]:
    return read_json(workspace / "content-enhancement.json", default={}) or {}
