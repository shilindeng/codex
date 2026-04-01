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
        return [_normalize_text(str(item)) for item in value if _normalize_text(str(item))]
    if isinstance(value, str):
        items = [_normalize_text(item) for item in re.split(r"[；;\n]", value) if _normalize_text(item)]
        return items
    return []


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


def _section_evidence_targets(section: dict[str, Any], research: dict[str, Any]) -> list[str]:
    evidence_need = _normalize_text(str(section.get("evidence_need") or ""))
    evidence_items = _normalize_list(research.get("evidence_items"))[:6]
    sources = []
    for item in research.get("sources") or []:
        if isinstance(item, dict):
            label = _normalize_text(str(item.get("title") or item.get("url") or ""))
        else:
            label = _normalize_text(str(item))
        if label:
            sources.append(label)
    output = _dedupe([evidence_need, *evidence_items[:2], *sources[:2]])
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
) -> dict[str, Any]:
    blueprint = outline_meta.get("viral_blueprint") or {}
    core_judgment = _normalize_text(str(blueprint.get("core_viewpoint") or title))
    secondary = _normalize_list(blueprint.get("secondary_viewpoints"))
    evidence_items = _normalize_list(research.get("evidence_items"))
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
        "evidence_targets": evidence_items[:4],
        "disallowed_moves": disallowed_moves,
        "exemplar_snippets": exemplar_snippets[:3],
    }


def build_content_enhancement(
    *,
    title: str,
    outline_meta: dict[str, Any],
    manifest: dict[str, Any],
    research: dict[str, Any] | None = None,
    author_memory: dict[str, Any] | None = None,
    writing_persona: dict[str, Any] | None = None,
) -> dict[str, Any]:
    research = research or {}
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
    shared = _shared_materials(title, outline_meta, research, author_memory, writing_persona, strategy)
    hard_requirements = _dedupe(
        [
            "至少有一节明确补场景或动作瞬间。",
            "至少有一节明确补案例、数据或事实托底。",
            "至少有一节明确补反方、误判或适用边界。",
            "不要把所有段落都写成判断句卡片。",
        ]
        + [f"这篇稿子默认使用“{strategy_meta['label']}”策略。", strategy_meta["goal"]]
    )[:6]
    section_enhancements = []
    for index, section in enumerate(sections, start=1):
        section_enhancements.append(
            {
                "index": index,
                "heading": _normalize_text(str(section.get("heading") or f"第 {index} 节")),
                "section_goal": _normalize_text(str(section.get("goal") or "展开该章节")),
                "must_include": _section_must_include(strategy, section, title),
                "evidence_targets": _section_evidence_targets(section, research),
                "detail_anchors": _detail_anchors(title, section, archetype),
                "counterpoint_targets": _counterpoint_targets(section, archetype),
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
    for item in shared.get("evidence_targets") or []:
        lines.append(f"证据目标：{item}")
    for item in payload.get("section_enhancements") or []:
        heading = item.get("heading") or "未命名章节"
        lines.append(f"章节：{heading}")
        for field in ["must_include", "evidence_targets", "detail_anchors", "counterpoint_targets"]:
            for value in item.get(field) or []:
                lines.append(f"{heading} / {field}：{value}")
    report_lines = [line for line in lines if line]
    return "# 写前增强\n\n" + "\n".join(f"- {line}" for line in report_lines) + "\n"


def write_content_enhancement_artifacts(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(workspace / "content-enhancement.json", payload)
    write_text(workspace / "content-enhancement.md", markdown_content_enhancement(payload))


def load_content_enhancement(workspace: Path) -> dict[str, Any]:
    return read_json(workspace / "content-enhancement.json", default={}) or {}
