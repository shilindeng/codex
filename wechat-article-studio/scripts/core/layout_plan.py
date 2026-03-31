from __future__ import annotations

from typing import Any

import legacy_studio as legacy


ARCHETYPE_STYLE_MAP = {
    "commentary": "magazine",
    "tutorial": "tech",
    "case-study": "business",
    "narrative": "warm",
}


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _pick_module_type(index: int, total: int, section: dict[str, Any], blueprint: dict[str, Any]) -> tuple[str, str]:
    heading = str(section.get("heading") or "")
    goal = str(section.get("goal") or "")
    evidence_need = str(section.get("evidence_need") or "")
    corpus = " ".join([heading, goal, evidence_need])
    if index == 0:
        return "opening-card", "首屏优先做开场卡，强化代入感和进入速度。"
    if any(word in corpus for word in ["案例", "复盘", "结果", "项目", "公司"]):
        return "case-card", "这一段更适合案例卡，让读者先看到发生了什么。"
    if any(word in corpus for word in ["误区", "误判", "别再", "混淆", "边界", "反方"]):
        return "myth-card", "这一段更适合误区卡，把常见误判和边界拎出来。"
    if any(word in corpus for word in ["对比", "差异", "不是", "而是", "分水岭"]):
        return "compare-card", "这一段更适合对比卡，帮助读者快速看清分水岭。"
    if any(word in corpus for word in ["数据", "事实", "证据", "研究", "报告", "%", "指标"]):
        return "evidence-card", "这一段更适合证据卡，压实可信度。"
    if index == total - 1:
        return "conclusion-card", "结尾优先做结论卡，保证全文有明确收束。"
    if _normalize_key(str(blueprint.get("primary_interaction_goal") or "")).startswith("comment"):
        return "comment-prompt-card", "本篇主互动目标偏评论，这一段适合留下讨论钩子。"
    return "insight-card", "这一段适合做判断卡，承接正文推进。"


def build_layout_plan(title: str, summary: str, outline_meta: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    blueprint = dict(outline_meta.get("viral_blueprint") or manifest.get("viral_blueprint") or {})
    sections = list(outline_meta.get("sections") or [])
    archetype = str(blueprint.get("article_archetype") or outline_meta.get("article_archetype") or "commentary")
    section_plans: list[dict[str, Any]] = [
        {
            "slot": "summary",
            "module_type": "summary-card",
            "reason": "公众号正文默认保留首屏摘要卡，帮助读者快速进入主题。",
            "summary": summary or "",
        }
    ]
    for index, section in enumerate(sections):
        module_type, reason = _pick_module_type(index, len(sections), section, blueprint)
        section_plans.append(
            {
                "slot": f"section-{index + 1}",
                "heading": str(section.get("heading") or ""),
                "module_type": module_type,
                "reason": reason,
                "goal": str(section.get("goal") or ""),
                "evidence_need": str(section.get("evidence_need") or ""),
            }
        )
    interaction_goal = _normalize_key(str(blueprint.get("primary_interaction_goal") or ""))
    if "comment" in interaction_goal and not any(item.get("module_type") == "comment-prompt-card" for item in section_plans):
        section_plans.append(
            {
                "slot": "ending-interaction",
                "module_type": "comment-prompt-card",
                "reason": "本篇主目标偏评论，收尾补一个评论引导卡。",
                "heading": "结尾互动",
            }
        )
    recommended_style = ARCHETYPE_STYLE_MAP.get(archetype, "magazine")
    return {
        "title": title,
        "article_archetype": archetype,
        "recommended_style": recommended_style,
        "recommended_style_reason": f"当前篇型为 {archetype}，优先使用更贴近该篇型的公众号阅读风格。",
        "section_plans": section_plans,
        "module_types": [item.get("module_type") for item in section_plans if item.get("module_type")],
        "generated_at": legacy.now_iso(),
    }


def markdown_layout_plan(payload: dict[str, Any]) -> str:
    lines = [
        f"# 版式规划：{payload.get('title') or '未命名标题'}",
        "",
        f"- 推荐版式：{payload.get('recommended_style') or 'magazine'}",
        f"- 原因：{payload.get('recommended_style_reason') or ''}",
        "",
    ]
    for item in payload.get("section_plans") or []:
        heading = item.get("heading") or item.get("slot") or "未命名位置"
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(f"- 模块：{item.get('module_type') or ''}")
        lines.append(f"- 原因：{item.get('reason') or ''}")
        if item.get("goal"):
            lines.append(f"- 目标：{item.get('goal')}")
        if item.get("evidence_need"):
            lines.append(f"- 证据需求：{item.get('evidence_need')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
