from __future__ import annotations

import hashlib
import re
import struct
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from core.artifacts import extract_summary, now_iso, read_json, read_text, split_frontmatter
from core.quality_checks import normalize_visible_text, split_markdown_paragraphs, visible_length


FACTORY_QUALITY_SCHEMA_VERSION = "2026-05-viral-factory-quality-v1"

_FACT_KEYWORDS = (
    "发布",
    "披露",
    "宣布",
    "报道",
    "政策",
    "监管",
    "财报",
    "融资",
    "上市",
    "收购",
    "模型",
    "产品",
    "功能",
    "价格",
    "利率",
    "汇率",
    "贷款",
    "数据",
    "同比",
    "环比",
    "增长",
    "下降",
    "首次",
    "正式",
)
_EVIDENCE_KEYWORDS = ("报道", "数据显示", "公开", "提到", "发布", "披露", "宣布", "例如", "比如", "案例", "来源", "根据")
_ANALYSIS_KEYWORDS = ("意味着", "说明", "真正", "关键", "背后", "影响", "风险", "代价", "边界", "如果", "但", "不是", "而是")
_VIEWPOINT_KEYWORDS = ("不是", "而是", "关键", "真正", "最", "应该", "需要", "不能", "值得", "说明", "意味着")
_STOPWORDS = {
    "这个",
    "那个",
    "一种",
    "一个",
    "一些",
    "不是",
    "而是",
    "真正",
    "关键",
    "问题",
    "时候",
    "今天",
    "最近",
    "这次",
    "如果",
    "可以",
    "需要",
    "已经",
    "正在",
}


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _load_article(workspace: Path, manifest: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    rel = _clean(manifest.get("article_path") or "article.md")
    path = workspace / rel
    if not path.exists():
        return {}, "", ""
    meta, body = split_frontmatter(read_text(path))
    title = _clean(manifest.get("selected_title") or meta.get("title") or manifest.get("topic"))
    return meta, title, body


def _article_signature(title: str, body: str) -> str:
    digest = hashlib.sha1()
    digest.update(str(title or "").strip().encode("utf-8"))
    digest.update(b"\n---\n")
    digest.update(str(body or "").strip().encode("utf-8"))
    return digest.hexdigest()


def _tokens(value: str, *, limit: int = 80) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9\.-]{1,}|[\u4e00-\u9fff]{2,8}", value or ""):
        cleaned = token.strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in seen or cleaned in _STOPWORDS:
            continue
        seen.add(lowered)
        output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def _source_entries(workspace: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    def add_entry(kind: str, payload: dict[str, Any], fallback_url: str = "") -> None:
        text = " ".join(
            _clean(payload.get(key))
            for key in ("title", "name", "summary", "snippet", "quote", "claim", "text", "source", "publisher")
            if _clean(payload.get(key))
        )
        url = _clean(payload.get("url") or payload.get("link") or payload.get("source_url") or fallback_url)
        if not text and not url:
            return
        entries.append(
            {
                "kind": kind,
                "title": _clean(payload.get("title") or payload.get("name") or url),
                "url": url,
                "domain": urlparse(url).netloc.lower() if url else "",
                "text": text or url,
            }
        )

    references = read_json(workspace / _clean(manifest.get("references_path") or "references.json"), default={}) or {}
    for item in references.get("items") or []:
        if isinstance(item, dict):
            add_entry("reference", item)
    evidence_report = read_json(workspace / _clean(manifest.get("evidence_report_path") or "evidence-report.json"), default={}) or {}
    for item in evidence_report.get("items") or evidence_report.get("evidence_items") or []:
        if isinstance(item, dict):
            add_entry("evidence", item)
    research = read_json(workspace / _clean(manifest.get("research_path") or "research.json"), default={}) or {}
    for item in research.get("sources") or []:
        if isinstance(item, dict):
            add_entry("research_source", item)
    for item in research.get("evidence_items") or []:
        if isinstance(item, dict):
            add_entry("research_evidence", item)
    for url in manifest.get("source_urls") or []:
        if str(url or "").strip():
            add_entry("manifest_url", {}, str(url).strip())
    return entries


def _critical_fact_sentences(body: str) -> list[str]:
    sentences = re.split(r"(?<=[。！？!?])\s*|\n+", body or "")
    output: list[str] = []
    seen: set[str] = set()
    for raw in sentences:
        sentence = normalize_visible_text(raw)
        if not sentence or len(sentence) < 12:
            continue
        has_number = bool(re.search(r"\d|[一二三四五六七八九十百千万亿]+(?:元|人|家|个|次|年|月|日|%)", sentence))
        has_date = bool(re.search(r"\d{1,4}\s*年|\d{1,2}\s*月|\d{1,2}\s*日|今天|昨日|本周|今年|去年", sentence))
        has_fact_word = any(word in sentence for word in _FACT_KEYWORDS)
        if not (has_number or has_date or has_fact_word):
            continue
        key = sentence[:80]
        if key in seen:
            continue
        seen.add(key)
        output.append(sentence)
        if len(output) >= 24:
            break
    return output


def build_fact_source_map(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    meta, title, body = _load_article(workspace, manifest)
    sources = _source_entries(workspace, manifest)
    source_tokens = [(entry, set(_tokens(" ".join([entry.get("title", ""), entry.get("text", ""), entry.get("url", "")])))) for entry in sources]
    facts = _critical_fact_sentences(body)
    mapped: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    for fact in facts:
        fact_tokens = set(_tokens(fact))
        best_entry: dict[str, Any] | None = None
        best_overlap = 0
        for entry, tokens in source_tokens:
            overlap = len(fact_tokens & tokens)
            if overlap > best_overlap:
                best_overlap = overlap
                best_entry = entry
        is_mapped = bool(best_entry and (best_overlap >= 2 or best_entry.get("url") and len(source_tokens) == 1))
        item = {
            "claim": fact,
            "claim_tokens": sorted(fact_tokens)[:12],
            "source_title": best_entry.get("title") if best_entry else "",
            "source_url": best_entry.get("url") if best_entry else "",
            "token_overlap": best_overlap,
            "mapped": is_mapped,
        }
        if is_mapped:
            mapped.append(item)
        else:
            unmapped.append(item)
    passed = bool(not facts or (sources and not unmapped))
    return {
        "schema_version": FACTORY_QUALITY_SCHEMA_VERSION,
        "title": title or _clean(meta.get("title")),
        "body_signature": _article_signature(title, body) if body else "",
        "source_count": len(sources),
        "critical_fact_count": len(facts),
        "mapped_fact_count": len(mapped),
        "unmapped_fact_count": len(unmapped),
        "mapped_facts": mapped[:20],
        "unmapped_facts": unmapped[:20],
        "checks": {
            "has_sources_when_facts_present": bool(not facts or sources),
            "all_critical_facts_mapped": bool(not facts or (sources and not unmapped)),
        },
        "failed_checks": [key for key, ok in {"has_sources_when_facts_present": bool(not facts or sources), "all_critical_facts_mapped": bool(not facts or (sources and not unmapped))}.items() if not ok],
        "passed": passed,
        "generated_at": now_iso(),
    }


def _section_blocks(body: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    current_heading = "开头"
    current_lines: list[str] = []
    for line in (body or "").splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line.strip())
        if match:
            if current_lines:
                blocks.append({"heading": current_heading, "body": "\n".join(current_lines).strip()})
            current_heading = match.group(1).strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        blocks.append({"heading": current_heading, "body": "\n".join(current_lines).strip()})
    return [item for item in blocks if normalize_visible_text(item.get("body", ""))]


def build_section_quality_map(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _meta, title, body = _load_article(workspace, manifest)
    blocks = _section_blocks(body)
    sections: list[dict[str, Any]] = []
    for index, block in enumerate(blocks):
        text = normalize_visible_text(block["body"])
        paragraphs = split_markdown_paragraphs(block["body"])
        has_viewpoint = any(word in text for word in _VIEWPOINT_KEYWORDS) or bool(re.search(r"^##\s*(不是|关键|真正|最|别)", block["heading"]))
        has_evidence = any(word in text for word in _EVIDENCE_KEYWORDS) or bool(re.search(r"\d|^\|.+\|", block["body"], flags=re.M))
        has_analysis = any(word in text for word in _ANALYSIS_KEYWORDS) and visible_length(text) >= 80
        is_core = block["heading"] != "开头" or index <= 2
        passed = bool((not is_core) or (visible_length(text) >= 80 and has_viewpoint and has_evidence and has_analysis))
        sections.append(
            {
                "heading": block["heading"],
                "paragraph_count": len(paragraphs),
                "visible_length": visible_length(text),
                "has_viewpoint": has_viewpoint,
                "has_evidence_or_example": has_evidence,
                "has_analysis_progress": has_analysis,
                "core_section": is_core,
                "passed": passed,
            }
        )
    core_sections = [item for item in sections if item.get("core_section")]
    failed = [item for item in core_sections if not item.get("passed")]
    passed = bool(core_sections and not failed)
    return {
        "schema_version": FACTORY_QUALITY_SCHEMA_VERSION,
        "title": title,
        "section_count": len(sections),
        "core_section_count": len(core_sections),
        "failed_core_section_count": len(failed),
        "sections": sections,
        "failed_sections": failed[:10],
        "checks": {
            "has_core_sections": bool(core_sections),
            "all_core_sections_have_viewpoint_evidence_analysis": not failed if core_sections else False,
        },
        "failed_checks": [key for key, ok in {"has_core_sections": bool(core_sections), "all_core_sections_have_viewpoint_evidence_analysis": not failed if core_sections else False}.items() if not ok],
        "passed": passed,
        "generated_at": now_iso(),
    }


def build_share_scene_map(body: str, reader_gate: dict[str, Any] | None = None) -> dict[str, Any]:
    reader_gate = reader_gate or {}
    share_lines = [str(item).strip() for item in reader_gate.get("share_lines") or [] if str(item).strip()]
    comment_seed = _clean(reader_gate.get("comment_seed"))
    takeaway_type = _clean(reader_gate.get("takeaway_module_type"))
    text = normalize_visible_text(body)
    scenes: list[dict[str, str]] = []
    if any(word in text for word in ("同事", "老板", "团队", "公司", "项目", "产品", "客户", "企业")):
        scenes.append({"scene": "转给同事或团队", "reason": "文章含有工作决策、组织协作或业务判断，适合转给相关人讨论。"})
    if share_lines:
        scenes.append({"scene": "发朋友圈表达判断", "reason": "已有可转述句，读者能用一句话表达立场。"})
    if takeaway_type and takeaway_type != "none":
        scenes.append({"scene": "收藏备用", "reason": f"结尾有{takeaway_type}，具备保存价值。"})
    if comment_seed:
        scenes.append({"scene": "评论区争论", "reason": "已有评论引子，能让读者补充自己的判断。"})
    if not scenes and any(word in text for word in ("风险", "代价", "误判", "边界", "分歧")):
        scenes.append({"scene": "转给关心风险的人", "reason": "文章提供了风险或边界判断，适合提醒特定读者。"})
    return {
        "schema_version": FACTORY_QUALITY_SCHEMA_VERSION,
        "scene_count": len(scenes),
        "scenes": scenes[:5],
        "passed": bool(scenes),
    }


def build_topic_heat_pack(workspace: Path, manifest: dict[str, Any], *, discovery: dict[str, Any] | None = None, selected_candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    discovery = discovery or read_json(workspace / _clean(manifest.get("topic_discovery_path") or "topic-discovery.json"), default={}) or {}
    candidates = list(discovery.get("candidates") or [])
    topic = _clean(manifest.get("topic") or manifest.get("selected_title"))
    candidate = selected_candidate or {}
    if not candidate and candidates:
        selected_index = int(manifest.get("topic_selected_index") or 0)
        if 1 <= selected_index <= len(candidates):
            candidate = dict(candidates[selected_index - 1] or {})
        elif topic:
            for item in candidates:
                haystack = " ".join(_clean(item.get(key)) for key in ("recommended_topic", "hot_title", "summary"))
                if topic and topic in haystack:
                    candidate = dict(item)
                    break
    source_items = list(discovery.get("sources") or [])
    urls = [_clean(item.get("link") or item.get("url") or item.get("source_url")) for item in source_items if isinstance(item, dict)]
    domains = sorted({urlparse(url).netloc.lower() for url in urls if url})
    hit_count = int(candidate.get("hit_count") or len(source_items) or 0)
    topic_score_dimensions = dict(candidate.get("topic_score_dimensions") or manifest.get("topic_score_dimensions") or {})
    heat_reason = _clean(candidate.get("heat_reason") or candidate.get("why_now") or candidate.get("hot_reason") or manifest.get("topic_heat_reason"))
    repeat_risk = _clean(candidate.get("repeat_risk") or candidate.get("repeat_risk_score") or manifest.get("repeat_risk"))
    controversy = [
        _clean(value)
        for value in [
            candidate.get("controversy"),
            candidate.get("conflict"),
            candidate.get("spread_reason"),
            candidate.get("discussion_reason"),
        ]
        if _clean(value)
    ]
    rising_score = int(min(20, 6 + min(hit_count, 6) + (4 if heat_reason else 0) + (3 if candidate.get("freshness_score") else 0)))
    multi_source_score = int(min(20, 5 + len(domains) * 3 + min(hit_count, 4)))
    controversy_score = int(min(20, 5 + len(controversy) * 5 + int(candidate.get("spread_potential_score") or 0) // 5))
    audience_score = int(min(20, 5 + int(candidate.get("audience_fit_score") or 0) + (4 if manifest.get("audience") else 0)))
    repeat_safety_score = int(topic_score_dimensions.get("重复风险") or candidate.get("repeat_safety_score") or (16 if repeat_risk and repeat_risk != "high" else 8 if repeat_risk else 0))
    checks = {
        "rising_heat_present": bool(heat_reason or rising_score >= 12),
        "multi_source_coverage_present": bool(len(domains) >= 2 or hit_count >= 2 or manifest.get("source_urls")),
        "controversy_or_reader_relevance_present": bool(controversy or controversy_score >= 10 or candidate.get("reader_value_score") or manifest.get("audience")),
        "repeat_risk_present": bool(repeat_risk or topic_score_dimensions.get("重复风险") is not None),
    }
    failed = [key for key, ok in checks.items() if not ok]
    return {
        "schema_version": FACTORY_QUALITY_SCHEMA_VERSION,
        "topic": topic or _clean(candidate.get("recommended_topic") or candidate.get("hot_title")),
        "provider": discovery.get("provider"),
        "window_hours": discovery.get("window_hours"),
        "hit_count": hit_count,
        "source_domain_count": len(domains),
        "source_domains": domains[:12],
        "heat_reason": heat_reason,
        "controversy_points": controversy[:5],
        "repeat_risk": repeat_risk,
        "scores": {
            "rising_heat": rising_score,
            "multi_source_coverage": multi_source_score,
            "controversy_strength": controversy_score,
            "audience_relevance": audience_score,
            "repeat_safety": repeat_safety_score,
        },
        "checks": checks,
        "failed_checks": failed,
        "passed": not failed,
        "generated_at": now_iso(),
    }


def _title_skeleton(value: str) -> str:
    title = _clean(value)
    title = re.sub(r"\d+(?:\.\d+)?", "0", title)
    title = re.sub(r"[A-Za-z][A-Za-z0-9\.-]+", "A", title)
    title = re.sub(r"[\u4e00-\u9fff]{2,}", "C", title)
    title = re.sub(r"\s+", "", title)
    return title[:32]


def build_topic_viral_bridge(workspace: Path, manifest: dict[str, Any], *, discovery: dict[str, Any] | None = None, selected_candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    discovery = discovery or read_json(workspace / _clean(manifest.get("topic_discovery_path") or "topic-discovery.json"), default={}) or {}
    candidates = [dict(item) for item in (discovery.get("candidates") or []) if isinstance(item, dict)]
    selected = dict(selected_candidate or {})
    selected_index = int(manifest.get("topic_selected_index") or 0)
    if not selected and 1 <= selected_index <= len(candidates):
        selected = candidates[selected_index - 1]
    topic = _clean(manifest.get("topic") or selected.get("recommended_topic") or selected.get("hot_title"))
    selected_tokens = set(_tokens(" ".join([topic, _clean(selected.get("summary")), _clean(selected.get("hot_title"))])))
    similar: list[dict[str, Any]] = []
    for item in candidates:
        title = _clean(item.get("recommended_title") or item.get("hot_title") or item.get("recommended_topic"))
        summary = _clean(item.get("summary") or item.get("heat_reason") or item.get("why_now"))
        tokens = set(_tokens(" ".join([title, summary])))
        overlap = len(selected_tokens & tokens) if selected_tokens else 0
        if item == selected or overlap or len(similar) < 5:
            similar.append(
                {
                    "title": title,
                    "summary": summary[:120],
                    "source_url": _clean(item.get("source_url") or item.get("url")),
                    "heat_reason": _clean(item.get("heat_reason") or item.get("why_now") or item.get("hot_reason")),
                    "spread_reason": _clean(item.get("spread_reason") or item.get("discussion_reason") or item.get("controversy")),
                    "token_overlap": overlap,
                    "title_skeleton": _title_skeleton(title),
                }
            )
        if len(similar) >= 8:
            break
    title_options = [
        _clean(item)
        for item in (
            selected.get("title_direction_candidates")
            or selected.get("title_candidates")
            or selected.get("angles")
            or []
        )
        if _clean(item)
    ]
    if _clean(selected.get("recommended_title")):
        title_options.insert(0, _clean(selected.get("recommended_title")))
    skeleton_counts = Counter(_title_skeleton(item) for item in title_options if item)
    emotion_hints: list[str] = []
    haystack = " ".join(
        _clean(value)
        for value in [
            selected.get("summary"),
            selected.get("spread_reason"),
            selected.get("discussion_reason"),
            selected.get("controversy"),
            selected.get("heat_reason"),
            topic,
        ]
    )
    for label, keywords in (
        ("conflict", ("争议", "冲突", "反对", "质疑", "风险", "代价")),
        ("anxiety", ("焦虑", "担心", "失业", "价格", "成本", "压力")),
        ("utility", ("方法", "清单", "判断", "收藏", "避坑", "指南")),
        ("identity", ("同事", "公司", "团队", "家长", "用户", "老板", "开发者")),
    ):
        if any(word in haystack for word in keywords):
            emotion_hints.append(label)
    if not emotion_hints and (selected.get("spread_potential_score") or selected.get("reader_value_score")):
        emotion_hints.append("reader_value")
    checks = {
        "selected_candidate_present": bool(selected),
        "similar_viral_samples_present": len(similar) >= 2,
        "title_expression_variants_present": len(skeleton_counts) >= 2 or len(title_options) >= 2,
        "comment_emotion_hint_present": bool(emotion_hints),
        "share_angle_hint_present": bool(selected.get("spread_reason") or selected.get("discussion_reason") or selected.get("angles") or title_options),
    }
    failed = [key for key, ok in checks.items() if not ok]
    return {
        "schema_version": FACTORY_QUALITY_SCHEMA_VERSION,
        "topic": topic,
        "selected_title": _clean(manifest.get("selected_title") or selected.get("recommended_title") or selected.get("hot_title")),
        "similar_viral_samples": similar[:8],
        "title_options": title_options[:12],
        "title_skeleton_counts": dict(skeleton_counts),
        "comment_emotion_hints": emotion_hints,
        "checks": checks,
        "failed_checks": failed,
        "passed": not failed,
        "generated_at": now_iso(),
    }


def _read_image_dimensions(path: Path) -> tuple[int, int]:
    try:
        data = path.read_bytes()[:32]
    except OSError:
        return 0, 0
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        try:
            blob = path.read_bytes()
        except OSError:
            return 0, 0
        idx = 2
        while idx + 9 < len(blob):
            if blob[idx] != 0xFF:
                idx += 1
                continue
            marker = blob[idx + 1]
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                return struct.unpack(">HH", blob[idx + 5 : idx + 9])[::-1]
            length = struct.unpack(">H", blob[idx + 2 : idx + 4])[0]
            idx += 2 + length
    return 0, 0


def _file_sha1(path: Path) -> str:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def build_image_asset_audit(workspace: Path, manifest: dict[str, Any], image_plan: dict[str, Any] | None = None) -> dict[str, Any]:
    plan = image_plan or read_json(workspace / _clean(manifest.get("image_plan_path") or "image-plan.json"), default={}) or {}
    items = [dict(item) for item in (plan.get("items") or [])]
    asset_items: list[dict[str, Any]] = []
    missing: list[str] = []
    invalid: list[str] = []
    hashes: Counter[str] = Counter()
    for item in items:
        asset_rel = _clean(item.get("asset_path"))
        item_id = _clean(item.get("id") or item.get("type"))
        if not asset_rel:
            missing.append(f"{item_id} 缺少 asset_path")
            asset_items.append({"id": item_id, "asset_path": "", "exists": False, "passed": False})
            continue
        path = workspace / asset_rel
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        width, height = _read_image_dimensions(path) if exists else (0, 0)
        digest = _file_sha1(path) if exists else ""
        if digest:
            hashes[digest] += 1
        item_failed: list[str] = []
        if not exists:
            item_failed.append("missing_file")
        if exists and size < 4096:
            item_failed.append("file_too_small")
        if exists and (width <= 1 or height <= 1):
            item_failed.append("invalid_dimensions")
        if item_failed:
            invalid.append(f"{item_id}:{','.join(item_failed)}")
        asset_items.append(
            {
                "id": item_id,
                "asset_path": asset_rel,
                "exists": exists,
                "size_bytes": size,
                "width": width,
                "height": height,
                "sha1": digest,
                "failed_checks": item_failed,
                "passed": not item_failed,
            }
        )
    duplicate_hashes = [digest for digest, count in hashes.items() if digest and count > 1]
    duplicate_items = [item for item in asset_items if item.get("sha1") in duplicate_hashes]
    checks = {
        "all_planned_images_have_asset_path": not missing,
        "all_asset_files_exist_and_are_nontrivial": not invalid,
        "no_duplicate_image_hashes_in_article": not duplicate_hashes,
    }
    failed = [key for key, ok in checks.items() if not ok]
    return {
        "schema_version": FACTORY_QUALITY_SCHEMA_VERSION,
        "planned_image_count": len(items),
        "asset_count": len([item for item in asset_items if item.get("exists")]),
        "asset_items": asset_items,
        "missing_assets": missing,
        "invalid_assets": invalid,
        "duplicate_hashes": duplicate_hashes,
        "duplicate_items": duplicate_items,
        "checks": checks,
        "failed_checks": failed,
        "passed": not failed,
        "generated_at": now_iso(),
    }


def build_draft_readability_audit(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    content_path = workspace / "latest-draft-content.html"
    source = "latest-draft-content.html"
    if not content_path.exists():
        content_path = workspace / _clean(manifest.get("wechat_html_path") or "article.wechat.html")
        source = _clean(manifest.get("wechat_html_path") or "article.wechat.html")
    html = read_text(content_path) if content_path.exists() else ""
    text = normalize_visible_text(re.sub(r"<[^>]+>", " ", html))
    collapsed_list = bool(re.search(r"<li[^>]*>[^<]*(?:[-*]\s*[^<]{2,}){2,}</li>", html, flags=re.I | re.S))
    paragraph_lengths = [visible_length(normalize_visible_text(item)) for item in re.findall(r"<p\b[^>]*>(.*?)</p>", html, flags=re.I | re.S)]
    long_paragraphs = [length for length in paragraph_lengths if length >= 180]
    headings = [normalize_visible_text(item) for item in re.findall(r"<h[23]\b[^>]*>(.*?)</h[23]>", html, flags=re.I | re.S)]
    heading_counts = Counter(headings)
    repeated_headings = [heading for heading, count in heading_counts.items() if heading and count > 1]
    first_img = html.lower().find("<img")
    first_h2 = html.lower().find("<h2")
    first_image_before_h2 = first_img == -1 or first_h2 == -1 or first_img < first_h2
    has_sources = bool(manifest.get("source_urls") or (workspace / "references.json").exists() or (workspace / "evidence-report.json").exists())
    source_visible = (not has_sources) or ("data-wx-source-style" in html) or ("参考" in text) or ("来源" in text)
    checks = {
        "draft_content_available": bool(html.strip()),
        "markdown_lists_not_collapsed": not collapsed_list,
        "long_paragraph_pressure_ok": len(long_paragraphs) <= 2,
        "first_image_position_ok": first_image_before_h2,
        "source_block_visible": source_visible,
        "module_labels_not_repeated": not repeated_headings,
    }
    failed = [key for key, ok in checks.items() if not ok]
    return {
        "schema_version": FACTORY_QUALITY_SCHEMA_VERSION,
        "source": source,
        "html_length": len(html),
        "text_length": visible_length(text),
        "image_count": len(re.findall(r"<img\b", html, flags=re.I)),
        "collapsed_list_detected": collapsed_list,
        "long_paragraph_lengths": long_paragraphs[:10],
        "repeated_headings": repeated_headings[:10],
        "first_image_before_first_h2": first_image_before_h2,
        "source_visible": source_visible,
        "checks": checks,
        "failed_checks": failed,
        "passed": not failed,
        "generated_at": now_iso(),
    }


def build_content_version_audit(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    _meta, title, body = _load_article(workspace, manifest)
    current_signature = _article_signature(title, body) if body else ""
    checked: list[dict[str, Any]] = []
    stale: list[str] = []
    for name in ("review-report.json", "score-report.json", "acceptance-report.json", "reader_gate.json", "visual_gate.json", "final_gate.json"):
        payload = read_json(workspace / name, default={}) or {}
        signature = _clean(payload.get("body_signature"))
        if not payload:
            continue
        stale_report = bool(signature and current_signature and signature != current_signature)
        if stale_report:
            stale.append(name)
        checked.append({"artifact": name, "body_signature": signature, "stale": stale_report})
    return {
        "schema_version": FACTORY_QUALITY_SCHEMA_VERSION,
        "current_body_signature": current_signature,
        "checked_artifacts": checked,
        "stale_artifacts": stale,
        "passed": not stale,
        "generated_at": now_iso(),
    }


def build_title_performance_report(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    feedback = read_json(workspace / _clean(manifest.get("performance_feedback_path") or "performance-feedback.json"), default={}) or {}
    title_decision = read_json(workspace / _clean(manifest.get("title_decision_report_path") or "title-decision-report.json"), default={}) or {}
    title = _clean(title_decision.get("selected_title") or manifest.get("selected_title") or manifest.get("topic"))
    entries = list(feedback.get("entries") or [])
    latest = dict(entries[-1]) if entries else {}
    metrics_24h = latest.get("metrics_24h") or {}
    metrics_72h = latest.get("metrics_72h") or {}
    reads = int(metrics_24h.get("read") or metrics_72h.get("read") or 0)
    shares = int(metrics_24h.get("share") or metrics_72h.get("share") or 0)
    favorites = int(metrics_24h.get("favorite") or metrics_72h.get("favorite") or 0)
    comments = int(metrics_24h.get("comment") or metrics_72h.get("comment") or 0)
    title_candidates = list(title_decision.get("candidates") or [])
    selected_candidate = next((item for item in title_candidates if _clean(item.get("title")) == title), {})
    share_rate = round(shares / max(1, reads), 4)
    favorite_rate = round(favorites / max(1, reads), 4)
    comment_rate = round(comments / max(1, reads), 4)
    status = "not_recorded"
    if latest:
        status = "strong" if reads >= 1000 and (share_rate >= 0.02 or favorite_rate >= 0.03 or comment_rate >= 0.01) else "needs_learning"
    return {
        "schema_version": FACTORY_QUALITY_SCHEMA_VERSION,
        "title": title,
        "title_family": _clean(selected_candidate.get("title_family")),
        "title_open_rate_score": selected_candidate.get("title_open_rate_score") or selected_candidate.get("title_score"),
        "candidate_count": len(title_candidates),
        "latest_entry": latest,
        "metrics_24h": metrics_24h,
        "metrics_72h": metrics_72h,
        "rates": {"share": share_rate, "favorite": favorite_rate, "comment": comment_rate},
        "status": status,
        "learning_notes": [str(latest.get("notes") or "").strip()] if latest.get("notes") else [],
        "passed": status in {"not_recorded", "strong", "needs_learning"},
        "generated_at": now_iso(),
    }
