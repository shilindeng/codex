from __future__ import annotations

from pathlib import Path
from typing import Any

import legacy_studio as legacy


DEFAULT_ACCOUNT_STRATEGY: dict[str, Any] = {
    "version": 1,
    "positioning": "industry-case",
    "positioning_label": "行业判断+案例",
    "target_reader": "general-tech",
    "target_reader_label": "泛科技读者",
    "primary_goal": "open-and-read",
    "primary_goal_label": "打开率+读完率",
    "reader_promises": [
        "把 AI 行业新闻翻译成普通读者能感知的代价、误判和后果。",
        "优先讲场景、案例和现实影响，而不是只讲参数和热度。",
        "每篇都要让读者带走一个更稳的判断，而不是一套空泛话术。",
    ],
    "preferred_archetypes": ["case-study", "commentary", "comparison"],
    "preferred_editorial_styles": ["case-memo", "field-observation"],
    "preferred_persona": "warm-editor",
    "preferred_opening_modes": ["场景切口", "新闻切口"],
    "preferred_ending_modes": ["判断收束", "风险提醒"],
    "blocked_title_patterns": ["not-but", "signal-briefing", "why-think-clear", "qa-cross-exam"],
    "blocked_title_fragments": [
        "这次真正的信号",
        "真正值得聊的",
        "真正的分水岭在这里",
        "别急着下结论",
        "很多人看热闹",
        "最容易被忽略的那一步",
        "不是表面答案",
        "更深一层",
    ],
    "discovery_priority_keywords": ["代价", "误判", "岗位", "成本", "影响", "决策", "案例", "落地", "风险"],
    "discovery_deprioritize_keywords": ["发布会", "榜单", "参数", "模型竞技", "融资", "热搜", "下载量"],
    "min_sources": 2,
    "min_evidence_items": 1,
    "require_evidence_for_archetypes": ["commentary", "case-study", "comparison", "narrative"],
    "image_density": "minimal",
    "max_inline_images": 2,
    "image_layout_family": "editorial",
    "preferred_image_presets": {
        "default": "editorial-grain",
        "pressure": "professional-corporate",
        "structured": "notion",
    },
    "blocked_image_presets": ["abstract-geometric", "cute", "warm", "illustrated-handdrawn"],
    "preferred_hero_modules": ["hero-scene", "hero-checkpoint"],
    "avoid_hero_meta": True,
}

HIGH_PRESSURE_VISUAL_KEYWORDS = [
    "成本",
    "岗位",
    "封杀",
    "危机",
    "租赁费",
    "算力",
    "银行",
    "H100",
    "风险",
    "OpenClaw",
    "Anthropic",
]

STRUCTURED_VISUAL_KEYWORDS = [
    "步骤",
    "对比",
    "流程",
    "清单",
    "复盘",
    "框架",
    "路径",
    "怎么做",
]

WEAK_SOURCE_DOMAINS = {"news.google.com"}


def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in output:
            output.append(text)
    return output


def default_account_strategy() -> dict[str, Any]:
    return legacy.json.loads(legacy.json.dumps(DEFAULT_ACCOUNT_STRATEGY, ensure_ascii=False))


def normalize_account_strategy(payload: Any) -> dict[str, Any]:
    strategy = default_account_strategy()
    if not isinstance(payload, dict):
        return strategy
    for key, value in payload.items():
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                strategy[key] = cleaned
        elif isinstance(value, list):
            normalized = _normalize_list(value)
            if normalized:
                strategy[key] = normalized
        elif isinstance(value, dict):
            merged = dict(strategy.get(key) or {})
            for child_key, child_value in value.items():
                child_text = str(child_value or "").strip()
                if child_text:
                    merged[str(child_key)] = child_text
            if merged:
                strategy[key] = merged
        elif value not in (None, "", [], {}):
            strategy[key] = value
    strategy["blocked_title_patterns"] = _normalize_list(strategy.get("blocked_title_patterns"))
    strategy["blocked_title_fragments"] = _normalize_list(strategy.get("blocked_title_fragments"))
    strategy["preferred_archetypes"] = _normalize_list(strategy.get("preferred_archetypes"))
    strategy["preferred_editorial_styles"] = _normalize_list(strategy.get("preferred_editorial_styles"))
    strategy["preferred_opening_modes"] = _normalize_list(strategy.get("preferred_opening_modes"))
    strategy["preferred_ending_modes"] = _normalize_list(strategy.get("preferred_ending_modes"))
    strategy["discovery_priority_keywords"] = _normalize_list(strategy.get("discovery_priority_keywords"))
    strategy["discovery_deprioritize_keywords"] = _normalize_list(strategy.get("discovery_deprioritize_keywords"))
    strategy["require_evidence_for_archetypes"] = _normalize_list(strategy.get("require_evidence_for_archetypes"))
    strategy["preferred_hero_modules"] = _normalize_list(strategy.get("preferred_hero_modules"))
    strategy["preferred_persona"] = str(strategy.get("preferred_persona") or DEFAULT_ACCOUNT_STRATEGY["preferred_persona"]).strip() or DEFAULT_ACCOUNT_STRATEGY["preferred_persona"]
    presets = dict(DEFAULT_ACCOUNT_STRATEGY.get("preferred_image_presets") or {})
    presets.update({key: str(value).strip() for key, value in (strategy.get("preferred_image_presets") or {}).items() if str(value).strip()})
    strategy["preferred_image_presets"] = presets
    blocked_presets = _normalize_list(strategy.get("blocked_image_presets"))
    strategy["blocked_image_presets"] = blocked_presets or list(DEFAULT_ACCOUNT_STRATEGY["blocked_image_presets"])
    try:
        strategy["min_sources"] = max(1, int(strategy.get("min_sources") or DEFAULT_ACCOUNT_STRATEGY["min_sources"]))
    except (TypeError, ValueError):
        strategy["min_sources"] = DEFAULT_ACCOUNT_STRATEGY["min_sources"]
    try:
        strategy["min_evidence_items"] = max(1, int(strategy.get("min_evidence_items") or DEFAULT_ACCOUNT_STRATEGY["min_evidence_items"]))
    except (TypeError, ValueError):
        strategy["min_evidence_items"] = DEFAULT_ACCOUNT_STRATEGY["min_evidence_items"]
    try:
        strategy["max_inline_images"] = max(1, int(strategy.get("max_inline_images") or DEFAULT_ACCOUNT_STRATEGY["max_inline_images"]))
    except (TypeError, ValueError):
        strategy["max_inline_images"] = DEFAULT_ACCOUNT_STRATEGY["max_inline_images"]
    strategy["image_density"] = str(strategy.get("image_density") or DEFAULT_ACCOUNT_STRATEGY["image_density"]).strip() or DEFAULT_ACCOUNT_STRATEGY["image_density"]
    strategy["image_layout_family"] = str(strategy.get("image_layout_family") or DEFAULT_ACCOUNT_STRATEGY["image_layout_family"]).strip() or DEFAULT_ACCOUNT_STRATEGY["image_layout_family"]
    strategy["avoid_hero_meta"] = bool(strategy.get("avoid_hero_meta", True))
    return strategy


def load_account_strategy(workspace: Path, manifest: dict[str, Any] | None = None, *, create_if_missing: bool = True) -> dict[str, Any]:
    path = workspace / str((manifest or {}).get("account_strategy_path") or "account-strategy.json")
    payload: dict[str, Any] = {}
    if path.exists():
        payload = legacy.read_json(path, default={}) or {}
    strategy = normalize_account_strategy(payload)
    if create_if_missing and (not path.exists() or payload != strategy):
        legacy.write_json(path, strategy)
    if manifest is not None:
        manifest["account_strategy_path"] = path.name
        manifest["account_strategy"] = strategy
        manifest.setdefault("audience", strategy.get("target_reader_label") or "泛科技读者")
    return strategy


def infer_visual_preset(title: str, summary: str, body: str, strategy: dict[str, Any]) -> str:
    corpus = " ".join([title or "", summary or "", body or ""])
    lowered = corpus.lower()
    presets = strategy.get("preferred_image_presets") or {}
    if any(keyword.lower() in lowered for keyword in HIGH_PRESSURE_VISUAL_KEYWORDS):
        return str(presets.get("pressure") or presets.get("default") or DEFAULT_ACCOUNT_STRATEGY["preferred_image_presets"]["pressure"])
    if any(keyword.lower() in lowered for keyword in STRUCTURED_VISUAL_KEYWORDS):
        return str(presets.get("structured") or presets.get("default") or DEFAULT_ACCOUNT_STRATEGY["preferred_image_presets"]["structured"])
    return str(presets.get("default") or DEFAULT_ACCOUNT_STRATEGY["preferred_image_presets"]["default"])


def weak_source_count(source_urls: list[str]) -> int:
    count = 0
    for raw in source_urls:
        url = str(raw or "").strip()
        if not url:
            continue
        domain = legacy.urllib.parse.urlparse(url).netloc.replace("www.", "").lower()
        if domain in WEAK_SOURCE_DOMAINS:
            count += 1
    return count


def research_requirements_status(research: dict[str, Any], manifest: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    source_urls: list[str] = []
    for item in research.get("sources") or manifest.get("source_urls") or []:
        if isinstance(item, dict):
            url = str(item.get("url") or "").strip()
        else:
            url = str(item or "").strip()
        if url:
            source_urls.append(url)
    evidence_items = _normalize_list(research.get("evidence_items"))
    archetype = str(
        (manifest.get("viral_blueprint") or {}).get("article_archetype")
        or manifest.get("article_archetype")
        or (manifest.get("recommended_archetype") or "")
    ).strip().lower()
    requires_evidence = archetype in {item.lower() for item in (strategy.get("require_evidence_for_archetypes") or [])}
    reasons: list[str] = []
    weak_sources = weak_source_count(source_urls)
    if requires_evidence and len(source_urls) < int(strategy.get("min_sources") or 2):
        reasons.append(f"来源不足：至少需要 {strategy.get('min_sources')} 条可回溯来源。")
    if requires_evidence and len(evidence_items) < int(strategy.get("min_evidence_items") or 1):
        reasons.append(f"证据不足：至少需要 {strategy.get('min_evidence_items')} 条可写入正文的证据卡。")
    if requires_evidence and source_urls and weak_sources == len(source_urls):
        reasons.append("当前来源几乎都是 RSS/聚合落地页，缺少真正可回溯原始材料。")
    return {
        "requires_evidence": requires_evidence,
        "archetype": archetype,
        "source_count": len(source_urls),
        "evidence_count": len(evidence_items),
        "weak_source_count": weak_sources,
        "passed": not reasons,
        "reasons": reasons,
    }
