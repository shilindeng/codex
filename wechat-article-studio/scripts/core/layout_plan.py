from __future__ import annotations

from typing import Any

import legacy_studio as legacy


STYLE_ALIAS_MAP = {
    "editorial-clean": "clean",
    "warm-journal": "warm",
}

ARCHETYPE_LAYOUT_MAP: dict[str, dict[str, Any]] = {
    "commentary": {
        "recommended_style": "magazine",
        "hero_module": "hero-judgment",
        "closing_module": "summary-close",
        "module_density": "balanced",
        "spacing_profile": "editorial-air",
    },
    "tutorial": {
        "recommended_style": "editorial-clean",
        "hero_module": "hero-checkpoint",
        "closing_module": "action-close",
        "module_density": "dense",
        "spacing_profile": "procedure-clear",
    },
    "case-study": {
        "recommended_style": "business",
        "hero_module": "hero-scene",
        "closing_module": "migration-close",
        "module_density": "balanced",
        "spacing_profile": "case-rhythm",
    },
    "narrative": {
        "recommended_style": "warm-journal",
        "hero_module": "hero-scene",
        "closing_module": "soft-close",
        "module_density": "airy",
        "spacing_profile": "story-breathing",
    },
    "comparison": {
        "recommended_style": "business",
        "hero_module": "hero-compare",
        "closing_module": "decision-close",
        "module_density": "balanced",
        "spacing_profile": "comparison-tight",
    },
}


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _actual_style(value: str) -> str:
    key = _normalize_key(value)
    return STYLE_ALIAS_MAP.get(key, key or "clean")


def _heading_role(index: int, total: int, module_type: str) -> str:
    if index == 0:
        return "section-break"
    if total >= 4 and index == total - 1:
        return "section-break"
    if module_type in {"turning-point-card", "summary-close", "action-close", "migration-close", "soft-close", "decision-close"}:
        return "section-break"
    return "section-label"


def _commentary_module(index: int, total: int, corpus: str) -> str:
    if index == 0:
        return "lead-note"
    if index == total - 1:
        return "summary-close"
    if any(word in corpus for word in ["数据", "报告", "研究", "证据", "事实", "%", "指标"]):
        return "evidence-strip"
    if any(word in corpus for word in ["误区", "误判", "边界", "反方", "别把", "前提"]):
        return "boundary-card"
    if any(word in corpus for word in ["分水岭", "真正", "关键", "判断", "被低估"]):
        return "keyline"
    return "evidence-strip" if index % 2 == 1 else "boundary-card"


def _tutorial_module(index: int, total: int, corpus: str) -> str:
    if any(word in corpus for word in ["误区", "容易错", "别", "坑", "风险", "注意"]):
        return "pitfall-card"
    if index == total - 1:
        return "action-close"
    return "step-stack"


def _case_module(index: int, total: int, corpus: str) -> str:
    if index == 0:
        return "scene-card"
    if any(word in corpus for word in ["转折", "结果", "分水岭", "关键一步", "变化"]):
        return "turning-point-card"
    if index == total - 1:
        return "migration-close"
    return "evidence-strip"


def _narrative_module(index: int, total: int, corpus: str) -> str:
    if index == 0:
        return "scene-card"
    if any(word in corpus for word in ["情绪", "那一刻", "突然", "后来", "一下子", "心里"]):
        return "emotion-turn"
    if any(word in corpus for word in ["引语", "那句话", "一句话", "说"]):
        return "quote-card"
    if index == total - 1:
        return "soft-close"
    return "scene-card"


def _comparison_module(index: int, total: int, corpus: str) -> str:
    if index == 0:
        return "compare-grid"
    if any(word in corpus for word in ["适合", "不适合", "人群", "场景", "边界"]):
        return "fit-card"
    if index == total - 1:
        return "decision-close"
    return "compare-grid"


def _pick_module_type(archetype: str, index: int, total: int, section: dict[str, Any], blueprint: dict[str, Any]) -> tuple[str, str]:
    heading = str(section.get("heading") or "")
    goal = str(section.get("goal") or "")
    evidence_need = str(section.get("evidence_need") or "")
    corpus = " ".join([heading, goal, evidence_need, str(blueprint.get("core_viewpoint") or "")])
    normalized_archetype = _normalize_key(archetype)
    if normalized_archetype == "tutorial":
        module_type = _tutorial_module(index, total, corpus)
    elif normalized_archetype == "case-study":
        module_type = _case_module(index, total, corpus)
    elif normalized_archetype == "narrative":
        module_type = _narrative_module(index, total, corpus)
    elif normalized_archetype == "comparison":
        module_type = _comparison_module(index, total, corpus)
    else:
        module_type = _commentary_module(index, total, corpus)
    reason_map = {
        "lead-note": "首节先用短导语卡，把读者拉进问题本身。",
        "evidence-strip": "这一节更适合证据条，先用事实压住判断。",
        "boundary-card": "这一节更适合边界卡，把误判和前提单独拎出来。",
        "keyline": "这一节适合关键句模块，形成可截图的核心判断。",
        "step-stack": "这一节更适合步骤栈，帮助移动端快速扫读操作顺序。",
        "pitfall-card": "这一节更适合易错点卡，把风险和误区集中收住。",
        "scene-card": "这一节更适合场景卡，让读者先进入人物和处境。",
        "turning-point-card": "这一节更适合转折卡，突出关键变化点。",
        "compare-grid": "这一节更适合比较网格，帮助读者快速对照。",
        "fit-card": "这一节更适合适用人群卡，把适配边界说清。",
        "summary-close": "最后一节用判断收束，不要让结尾散掉。",
        "action-close": "最后一节给一个最小动作，适合教程稿收束。",
        "migration-close": "最后一节把案例提炼成可迁移判断。",
        "soft-close": "最后一节轻回扣，保留余味，不做硬总结。",
        "decision-close": "最后一节明确建议，帮助读者做选择。",
        "emotion-turn": "这一节更适合情绪转折模块，让读感有波峰。",
        "quote-card": "这一节更适合引语卡，单独抬出一句值得记住的话。",
    }
    return module_type, reason_map.get(module_type, "按篇型给这一节安排更合适的排版模块。")


def build_layout_plan(title: str, summary: str, outline_meta: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    blueprint = dict(outline_meta.get("viral_blueprint") or manifest.get("viral_blueprint") or {})
    sections = list(outline_meta.get("sections") or [])
    archetype = _normalize_key(str(blueprint.get("article_archetype") or outline_meta.get("article_archetype") or manifest.get("article_archetype") or "commentary"))
    profile = ARCHETYPE_LAYOUT_MAP.get(archetype, ARCHETYPE_LAYOUT_MAP["commentary"])
    strategy = manifest.get("account_strategy") or {}
    preferred_heroes = [str(item).strip() for item in (strategy.get("preferred_hero_modules") or []) if str(item).strip()]
    hero_module = profile["hero_module"]
    if archetype == "commentary":
        if "hero-checkpoint" in preferred_heroes:
            hero_module = "hero-checkpoint"
        elif "hero-scene" in preferred_heroes:
            hero_module = "hero-scene"
    elif archetype in {"case-study", "narrative"}:
        if "hero-scene" in preferred_heroes:
            hero_module = "hero-scene"
    elif archetype == "comparison" and "hero-compare" in preferred_heroes:
        hero_module = "hero-compare"

    section_modules: list[dict[str, Any]] = []
    for index, section in enumerate(sections):
        module_type, reason = _pick_module_type(archetype, index, len(sections), section, blueprint)
        heading_role = _heading_role(index, len(sections), module_type)
        section_modules.append(
            {
                "slot": f"section-{index + 1}",
                "heading": str(section.get("heading") or ""),
                "module_type": module_type,
                "heading_role": heading_role,
                "reason": reason,
                "goal": str(section.get("goal") or ""),
                "evidence_need": str(section.get("evidence_need") or ""),
            }
        )

    # Keep legacy field for compatibility.
    section_plans = list(section_modules)
    recommended_style = profile["recommended_style"]
    return {
        "title": title,
        "article_archetype": archetype,
        "layout_archetype": archetype,
        "hero_module": hero_module,
        "closing_module": profile["closing_module"],
        "module_density": profile["module_density"],
        "spacing_profile": profile["spacing_profile"],
        "recommended_style": recommended_style,
        "recommended_style_reason": f"当前篇型为 {archetype}，优先使用 {recommended_style} 这类更贴近公众号阅读节奏的皮肤。",
        "section_modules": section_modules,
        "section_plans": section_plans,
        "module_types": [item.get("module_type") for item in section_modules if item.get("module_type")],
        "generated_at": legacy.now_iso(),
    }


def markdown_layout_plan(payload: dict[str, Any]) -> str:
    lines = [
        f"# 版式规划：{payload.get('title') or '未命名标题'}",
        "",
        f"- 篇型骨架：{payload.get('layout_archetype') or 'commentary'}",
        f"- 首屏模块：{payload.get('hero_module') or ''}",
        f"- 结尾模块：{payload.get('closing_module') or ''}",
        f"- 模块密度：{payload.get('module_density') or ''}",
        f"- 留白策略：{payload.get('spacing_profile') or ''}",
        f"- 推荐皮肤：{payload.get('recommended_style') or 'magazine'}",
        f"- 原因：{payload.get('recommended_style_reason') or ''}",
        "",
    ]
    for item in payload.get("section_modules") or payload.get("section_plans") or []:
        heading = item.get("heading") or item.get("slot") or "未命名位置"
        lines.append(f"## {heading}")
        lines.append("")
        lines.append(f"- 模块：{item.get('module_type') or ''}")
        lines.append(f"- 标题角色：{item.get('heading_role') or ''}")
        lines.append(f"- 原因：{item.get('reason') or ''}")
        if item.get("goal"):
            lines.append(f"- 目标：{item.get('goal')}")
        if item.get("evidence_need"):
            lines.append(f"- 证据需求：{item.get('evidence_need')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
