from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import legacy_studio as legacy
from core.artifacts import (
    ensure_text_report,
    extract_summary,
    join_frontmatter,
    now_iso,
    read_input_file,
    read_json,
    read_text,
    split_frontmatter,
    strip_leading_h1,
    write_json,
    write_text,
)
from core.images import cmd_assemble as legacy_assemble
from core.images import cmd_generate_images as legacy_generate_images
from core.images import cmd_plan_images as legacy_plan_images
from core.layout import INPUT_FORMAT_CHOICES, LAYOUT_STYLE_CHOICES
from core.manifest import MANIFEST_STATUS_DEFAULTS, ensure_workspace, load_manifest, save_manifest, update_stage, workspace_path
from core.render import cmd_render as legacy_render
from core.rewrite import generate_revision_candidate
from core.viral import (
    DEFAULT_THRESHOLD as VIRAL_SCORE_THRESHOLD,
    build_heuristic_review,
    blueprint_complete,
    default_viral_blueprint,
    markdown_review_report,
    normalize_outline_payload,
    normalize_review_payload,
    normalize_viral_blueprint,
)
from providers.text.gemini_web import GeminiWebTextProvider
from providers.text.openai_compatible import OpenAICompatibleTextProvider, placeholder_article, placeholder_outline
from publishers.wechat import cmd_publish as wechat_publish
from publishers.wechat import cmd_verify_draft as wechat_verify_draft

PUBLISH_MIN_CREDIBILITY_SCORE = 5
CONTENT_MODE_CHOICES = ("tech-balanced", "tech-credible", "viral")
WECHAT_HEADER_MODE_CHOICES = ("keep", "drop-title", "drop-title-summary")
RECENT_CORPUS_LIMIT = 20
KNOWN_TEMPLATE_PHRASES = [
    "这很正常，你不是一个人",
    "最难受的是",
    "真正值得带走的判断只有一个",
    "如果你最近",
    "别急着把",
    "说白了",
    "以后真正靠谱的 AI，可能不是",
]


def normalize_content_mode(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in CONTENT_MODE_CHOICES else "tech-balanced"


def normalize_wechat_header_mode(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in WECHAT_HEADER_MODE_CHOICES else "drop-title"


def persist_runtime_preferences(manifest: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    manifest["content_mode"] = normalize_content_mode(getattr(args, "content_mode", None) or manifest.get("content_mode"))
    manifest["wechat_header_mode"] = normalize_wechat_header_mode(
        getattr(args, "wechat_header_mode", None) or manifest.get("wechat_header_mode")
    )
    return manifest


def active_text_provider():
    provider_name = (legacy.os.getenv("ARTICLE_STUDIO_TEXT_PROVIDER") or "openai-compatible").strip().lower()
    if provider_name in {"gemini-web", "gemini_web"}:
        return GeminiWebTextProvider()
    if provider_name not in {"openai-compatible", "openai_compatible", ""}:
        raise SystemExit(f"暂不支持的文本 provider：{provider_name}")
    return OpenAICompatibleTextProvider()


def require_live_text_provider(command_name: str):
    provider = active_text_provider()
    if provider.configured():
        return provider
    raise SystemExit(
        f"{command_name} 需要已配置的文本 provider。"
        " 请设置 OPENAI_API_KEY 和 ARTICLE_STUDIO_TEXT_MODEL，"
        " 或改用 hosted-run 并先提供 article.md / --article-file。"
    )


def score_dimension_value(report: dict[str, Any], dimension: str) -> int:
    for item in report.get("score_breakdown", []):
        if item.get("dimension") == dimension:
            return int(item.get("score") or 0)
    return 0


def placeholder_reasons(workspace: Path, manifest: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if str(manifest.get("text_model") or "").strip().lower() == "placeholder":
        reasons.append("当前正文仍来自 placeholder 文本回退")
    research = load_research(workspace)
    if research.get("placeholder"):
        reasons.append("research.json 仍是 placeholder 调研结果")
    review = read_json(workspace / "review-report.json", default={}) or {}
    if review.get("placeholder"):
        reasons.append("review-report.json 仍是 placeholder 评审结果")
    return reasons


def collect_publish_blockers(workspace: Path, manifest: dict[str, Any]) -> list[str]:
    blockers = placeholder_reasons(workspace, manifest)
    report = read_json(workspace / "score-report.json", default={}) or {}
    if not report:
        blockers.append("缺少 score-report.json，无法确认是否可发布")
        return blockers
    if not bool(report.get("passed", manifest.get("score_passed"))):
        blockers.append("当前稿件评分未达发布阈值")
    quality_gates = report.get("quality_gates") or {}
    failed_gates = [name for name, ok in quality_gates.items() if not ok]
    if failed_gates:
        blockers.append(f"质量门槛未通过：{'、'.join(failed_gates)}")
    if str(report.get("score_profile") or "") in {"tech-balanced", "tech-credible"}:
        evidence_score = score_dimension_value(report, "技术准确与证据")
        min_score = 12 if str(report.get("score_profile")) == "tech-balanced" else 14
        if evidence_score < min_score:
            blockers.append(f"技术准确与证据得分过低（{evidence_score}/{min_score}）")
    else:
        credibility_score = score_dimension_value(report, "可信度与检索支撑")
        if credibility_score < PUBLISH_MIN_CREDIBILITY_SCORE:
            blockers.append(f"可信度与检索支撑得分过低（{credibility_score}/{PUBLISH_MIN_CREDIBILITY_SCORE}）")
    return blockers


def assert_publish_request_ready(args: argparse.Namespace) -> None:
    if getattr(args, "to", None) != "publish":
        return
    if not getattr(args, "dry_run_publish", False) and not getattr(args, "confirmed_publish", False):
        raise SystemExit("进入正式发布前必须显式传入 --confirmed-publish；未确认时不会写入 publish_intent。")


def normalize_urls(values: list[str]) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for raw in values:
        value = (raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        urls.append(value)
    return urls


def detect_corpus_root(workspace: Path) -> Path | None:
    env_root = (legacy.os.getenv("WECHAT_JOBS_ROOT") or "").strip()
    candidates: list[Path] = []
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve())
    candidates.append(Path(r"D:\vibe-coding\codex\wechat-jobs"))
    candidates.append(workspace.parent / "wechat-jobs")
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_dir():
            return resolved
    return None


def _normalize_phrase(text: str) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    compact = compact.strip(" -•>\"'“”‘’")
    return compact


def recent_article_paths(corpus_root: Path | None, current_workspace: Path, limit: int = RECENT_CORPUS_LIMIT) -> list[Path]:
    if corpus_root is None or not corpus_root.exists():
        return []
    current_workspace = current_workspace.resolve()
    articles: list[Path] = []
    for path in corpus_root.rglob("article.md"):
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if current_workspace in resolved.parents:
            continue
        articles.append(resolved)
    articles.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    return articles[:limit]


def collect_recent_phrase_blacklist(paths: list[Path]) -> list[str]:
    counter: Counter[str] = Counter()
    for path in paths:
        try:
            raw = read_text(path)
        except OSError:
            continue
        _, body = split_frontmatter(raw)
        paragraphs = [block.strip() for block in legacy.list_paragraphs(body) if block.strip()]
        candidates = paragraphs[:2] + paragraphs[-2:]
        headings = [item.get("text", "") for item in legacy.extract_headings(body)[:4]]
        candidates.extend(headings)
        for item in candidates:
            normalized = _normalize_phrase(item)
            if 8 <= legacy.cjk_len(normalized) <= 36:
                counter[normalized] += 1
    for phrase in KNOWN_TEMPLATE_PHRASES:
        counter[_normalize_phrase(phrase)] += 2
    return [item for item, count in counter.most_common(20) if count >= 2]


def attach_corpus_context(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    corpus_root = detect_corpus_root(workspace)
    if corpus_root is None:
        manifest["corpus_root"] = ""
        manifest["recent_phrase_blacklist"] = []
        manifest["recent_article_titles"] = []
        return manifest
    article_paths = recent_article_paths(corpus_root, workspace)
    titles: list[str] = []
    for path in article_paths[:8]:
        try:
            raw = read_text(path)
            meta, body = split_frontmatter(raw)
            title = meta.get("title") or legacy.extract_title_from_body(body) or path.parent.name
        except OSError:
            title = path.parent.name
        titles.append(str(title))
    manifest["corpus_root"] = str(corpus_root)
    manifest["recent_phrase_blacklist"] = collect_recent_phrase_blacklist(article_paths)
    manifest["recent_article_titles"] = titles
    return manifest


def _reference_domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "") or url


def _reference_label(url: str) -> str:
    domain = _reference_domain(url)
    path = (urlparse(url).path or "").strip("/")
    if path:
        parts = [part for part in path.split("/") if part]
        return f"{domain} / {parts[-1][:36]}"
    return domain


def _extract_body_urls(body: str) -> list[str]:
    urls = re.findall(r"https?://[^\s)>\]]+", body or "")
    return normalize_urls(urls)


def build_references_payload(workspace: Path, manifest: dict[str, Any], body: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    evidence_report = read_json(workspace / "evidence-report.json", default={}) or {}
    for entry in (evidence_report.get("items") or []):
        url = str(entry.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "url": url,
                "title": str(entry.get("page_title") or entry.get("title") or _reference_label(url)).strip(),
                "domain": _reference_domain(url),
                "note": extract_summary(str(entry.get("sentence") or entry.get("description") or ""), 72),
                "source_type": "evidence",
            }
        )
    research = load_research(workspace)
    for entry in (research.get("sources") or []):
        if isinstance(entry, dict):
            url = str(entry.get("url") or entry.get("link") or "").strip()
            title = str(entry.get("title") or entry.get("name") or "").strip()
        else:
            url = str(entry or "").strip()
            title = ""
        if not url or url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "url": url,
                "title": title or _reference_label(url),
                "domain": _reference_domain(url),
                "note": "",
                "source_type": "research",
            }
        )
    for url in normalize_urls(list(manifest.get("source_urls") or []) + _extract_body_urls(body)):
        if not url or url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "url": url,
                "title": _reference_label(url),
                "domain": _reference_domain(url),
                "note": "",
                "source_type": "manifest",
            }
        )
    normalized_items = []
    for index, item in enumerate(items, start=1):
        normalized_items.append({**item, "index": index})
    payload = {"items": normalized_items, "generated_at": now_iso()}
    write_json(workspace / "references.json", payload)
    manifest["references_path"] = "references.json"
    return payload


def apply_reference_policy(workspace: Path, manifest: dict[str, Any], title: str, body: str) -> tuple[str, dict[str, Any]]:
    payload = build_references_payload(workspace, manifest, body)
    items = payload.get("items") or []
    body_urls = _extract_body_urls(body)
    body_citation_urls = body_urls[:4]
    marker_map = {url: f"[{index + 1}]" for index, url in enumerate(body_citation_urls)}
    title_map = {item["url"]: item["title"] for item in items}

    def replace_markdown_link(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        url = match.group(2).strip()
        if url in marker_map:
            return f"{label} {marker_map[url]}"
        return label or title_map.get(url, _reference_label(url))

    normalized_body = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", replace_markdown_link, body)

    def replace_raw_url(match: re.Match[str]) -> str:
        url = match.group(0).strip()
        return marker_map.get(url, title_map.get(url, _reference_label(url)))

    normalized_body = re.sub(r"https?://[^\s)>\]]+", replace_raw_url, normalized_body)
    if not re.search(r"\[\d+\]", normalized_body) and items:
        paragraphs = [block for block in re.split(r"\n\s*\n", normalized_body) if block.strip()]
        injected = 0
        rebuilt: list[str] = []
        for block in paragraphs:
            candidate = block
            if injected < min(4, len(items)) and not candidate.lstrip().startswith("#") and legacy.cjk_len(candidate) >= 35:
                if re.search(r"\d{4}年|\d+(?:\.\d+)?%|官方|研究|报告|数据显示|文档|发布|上线|Stars|release", candidate):
                    candidate = candidate.rstrip() + f" [{items[injected]['index']}]"
                    injected += 1
            rebuilt.append(candidate)
        normalized_body = "\n\n".join(rebuilt)
    findings = {
        "raw_urls_before": len(body_urls),
        "raw_urls_after": len(_extract_body_urls(normalized_body)),
        "body_citation_count": len(re.findall(r"\[\d+\]", normalized_body)),
        "reference_count": len(items),
        "citation_policy_passed": len(_extract_body_urls(normalized_body)) == 0,
    }
    return normalized_body, findings


def sync_article_reference_policy(workspace: Path, manifest: dict[str, Any]) -> tuple[dict[str, str], str]:
    article_path = workspace / (manifest.get("article_path") or "article.md")
    if not article_path.exists():
        return {}, ""
    raw = read_text(article_path)
    meta, body = split_frontmatter(raw)
    title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名标题"
    body = strip_leading_h1(body, title)
    normalized_body, findings = apply_reference_policy(workspace, manifest, title, body)
    summary = meta.get("summary") or manifest.get("summary") or extract_summary(normalized_body)
    if normalized_body != body or not (workspace / "references.json").exists():
        write_text(article_path, join_frontmatter({"title": title, "summary": summary}, normalized_body))
    manifest["references_path"] = "references.json"
    manifest["citation_policy_findings"] = findings
    return {"title": title, "summary": summary}, normalized_body


def normalize_style_samples(values: list[str], workspace: Path | None = None) -> list[str]:
    seen: set[str] = set()
    samples: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute() and workspace is not None:
            path = (workspace / path).resolve()
        else:
            path = path.resolve()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        samples.append(key)
    return samples


def extract_style_signals(sample_paths: list[str]) -> list[str]:
    signals: list[str] = []
    for raw in sample_paths[:3]:
        path = Path(raw)
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            continue
        paragraphs = [block.strip() for block in legacy.list_paragraphs(content)[:3] if block.strip()]
        compact = "\n".join(paragraphs)
        if not compact:
            continue
        if any(word in compact for word in ["你", "我们", "别急", "说白了"]):
            signals.append("对话感")
        if re.search(r"不是.+而是|但|却|反而", compact):
            signals.append("强对比")
        if len(paragraphs) >= 2:
            signals.append("短段落")
        if any(word in compact for word in ["案例", "比如", "例如", "故事"]):
            signals.append("案例推进")
        if any(word in compact for word in ["某天", "那一刻", "刷到", "看到", "消息", "细节"]):
            signals.append("场景切口")
        if any(word in compact for word in ["判断", "信号", "分水岭", "趋势", "误判"]):
            signals.append("判断递进")
        if any(word in compact for word in ["官方", "报告", "数据", "文档", "来源", "研究"]):
            signals.append("证据穿插")
    return list(dict.fromkeys(signals))


def load_research(workspace: Path) -> dict[str, Any]:
    return read_json(workspace / "research.json", default={}) or {}


def load_ideation(workspace: Path) -> dict[str, Any]:
    return read_json(workspace / "ideation.json", default={}) or {}


def current_viral_blueprint(workspace: Path, manifest: dict[str, Any], ideation: dict[str, Any] | None = None) -> dict[str, Any]:
    ideation = ideation or load_ideation(workspace)
    outline_meta = ideation.get("outline_meta") or {}
    blueprint = outline_meta.get("viral_blueprint") or ideation.get("viral_blueprint") or manifest.get("viral_blueprint")
    return normalize_viral_blueprint(
        blueprint,
        {
            "topic": manifest.get("topic") or ideation.get("topic") or manifest.get("selected_title") or "",
            "selected_title": ideation.get("selected_title") or manifest.get("selected_title") or "",
            "direction": manifest.get("direction") or ideation.get("direction") or "",
            "audience": manifest.get("audience") or "大众读者",
            "research": load_research(workspace),
            "style_signals": manifest.get("style_signals") or [],
        },
    )


def persist_style_samples(workspace: Path, manifest: dict[str, Any], sample_values: list[str] | None) -> dict[str, Any]:
    merged = list(manifest.get("style_sample_paths") or [])
    merged.extend(sample_values or [])
    normalized = normalize_style_samples(merged, workspace)
    manifest["style_sample_paths"] = normalized
    manifest["style_signals"] = extract_style_signals(normalized)
    return manifest


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        candidates = []
        for line in raw.splitlines():
            cleaned = line.strip()
            cleaned = cleaned.lstrip("-*").strip()
            cleaned = cleaned.removeprefix("•").strip()
            if cleaned:
                candidates.append(cleaned)
        if len(candidates) <= 1:
            parts = [part.strip() for part in raw.split("。") if part.strip()]
            if len(parts) > 1:
                candidates = [part if part.endswith("。") else f"{part}。" for part in parts]
        normalized = []
        for item in candidates:
            item = item.strip()
            item = item[2:].strip() if len(item) > 2 and item[0].isdigit() and item[1] in {".", "、"} else item
            if item:
                normalized.append(item)
        return normalized
    return []


def looks_like_issue(text: str) -> bool:
    markers = ["不足", "偏弱", "问题", "缺少", "需要", "建议补", "可再", "不够", "避免", "警惕", "修正"]
    value = (text or "").strip()
    return any(marker in value for marker in markers)


def split_review_points(value: Any) -> tuple[list[str], list[str]]:
    raw_items = normalize_string_list(value)
    strengths: list[str] = []
    issues: list[str] = []
    for item in raw_items:
        if looks_like_issue(item):
            issues.append(item)
        else:
            strengths.append(item)
    return strengths, issues


def write_title_report(workspace: Path, topic: str, selected_title: str, ranked_titles: list[dict[str, Any]]) -> None:
    payload = {
        "topic": topic,
        "selected_title": selected_title,
        "threshold": legacy.TITLE_SCORE_THRESHOLD,
        "candidates": ranked_titles,
        "generated_at": now_iso(),
    }
    write_json(workspace / "title-report.json", payload)
    lines = [f"原始主题：{topic}", f"最终标题：{selected_title}", f"准入阈值：{legacy.TITLE_SCORE_THRESHOLD}"]
    for item in ranked_titles[:5]:
        lines.append(f"{item['title']}｜得分 {item['title_score']}｜{'通过' if item['title_gate_passed'] else '未通过'}")
    ensure_text_report(workspace / "title-report.md", "标题评分报告", lines)


def select_scored_title(
    workspace: Path,
    manifest: dict[str, Any],
    ideation: dict[str, Any],
    topic: str,
    audience: str,
    angle: str,
    selected_title: str = "",
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    candidates = list(ideation.get("titles") or [])
    ranked_titles, selected = legacy.rank_title_candidates(candidates, topic, audience, angle, selected_title)
    if not selected or not selected.get("title_gate_passed", False):
        boosted_candidates = candidates + legacy.generate_hot_title_variants(topic, angle, audience)
        ranked_titles, selected = legacy.rank_title_candidates(boosted_candidates, topic, audience, angle, selected_title)
    chosen_title = selected_title or (selected.get("title") if selected else topic)
    if selected_title:
        selected_report = legacy.title_dimension_score(selected_title, audience, angle)
        ideation["selected_title_score"] = selected_report["total_score"]
        ideation["selected_title_gate_passed"] = selected_report["passed"]
    elif selected:
        chosen_title = selected["title"]
        ideation["selected_title_score"] = selected.get("title_score", 0)
        ideation["selected_title_gate_passed"] = selected.get("title_gate_passed", False)
    else:
        ideation["selected_title_score"] = 0
        ideation["selected_title_gate_passed"] = False
    ideation["selected_title"] = chosen_title
    ideation["title_threshold"] = legacy.TITLE_SCORE_THRESHOLD
    ideation["titles"] = ranked_titles
    write_title_report(workspace, topic, chosen_title, ranked_titles)
    manifest["selected_title"] = chosen_title
    manifest["title_report_path"] = "title-report.json"
    manifest["title_gate_threshold"] = legacy.TITLE_SCORE_THRESHOLD
    manifest["title_gate_passed"] = ideation.get("selected_title_gate_passed", False)
    manifest["title_score"] = ideation.get("selected_title_score", 0)
    return ideation, selected


def apply_research_credibility_boost(report: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
    sources = normalize_string_list(research.get("sources"))
    evidence_items = normalize_string_list(research.get("evidence_items"))
    if not report or (not sources and not evidence_items):
        return report
    boosted = json.loads(json.dumps(report, ensure_ascii=False))
    target = None
    for item in boosted.get("score_breakdown", []):
        if item.get("dimension") == "可信度与检索支撑":
            target = item
            break
    if target is None:
        return boosted
    weight = int(target.get("weight") or 8) or 8
    bonus = min(weight, max(target.get("score", 0), min(4, len(sources)) + min(4, len(evidence_items))))
    target["score"] = bonus
    boosted["total_score"] = sum(item.get("score", 0) for item in boosted.get("score_breakdown", []))
    quality_gates = boosted.get("quality_gates") or {}
    quality_gates["credibility_passed"] = bonus >= PUBLISH_MIN_CREDIBILITY_SCORE
    boosted["quality_gates"] = quality_gates
    boosted["passed"] = boosted["total_score"] >= boosted.get("threshold", legacy.DEFAULT_THRESHOLD) and all(quality_gates.values())
    weaknesses = normalize_string_list(boosted.get("weaknesses"))
    if bonus >= 4:
        weaknesses = [item for item in weaknesses if not item.startswith("可信度与检索支撑")]
    boosted["weaknesses"] = weaknesses
    return boosted


def cmd_research(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    provider = require_live_text_provider("research")
    source_urls = normalize_urls(args.source_url or manifest.get("source_urls") or [])
    topic = args.topic or manifest.get("topic") or "未命名主题"
    audience = args.audience or manifest.get("audience") or "大众读者"
    angle = args.angle or manifest.get("direction") or ""
    result = provider.generate_research_pack(
        {
            "topic": topic,
            "angle": angle,
            "audience": audience,
            "source_urls": source_urls,
        }
    )
    payload = dict(result.payload)
    payload.setdefault("topic", topic)
    payload.setdefault("angle", angle)
    payload.setdefault("audience", audience)
    payload["provider"] = result.provider
    payload["model"] = result.model
    payload["generated_at"] = now_iso()
    write_json(workspace / "research.json", payload)
    manifest.update(
        {
            "topic": topic,
            "direction": angle,
            "audience": audience,
            "source_urls": source_urls,
            "research_path": "research.json",
            "text_provider": result.provider,
            "text_model": result.model,
        }
    )
    update_stage(manifest, "research", "research_status")
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_titles(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    provider = require_live_text_provider("titles")
    research = load_research(workspace)
    topic = manifest.get("topic") or research.get("topic") or "未命名主题"
    audience = manifest.get("audience") or research.get("audience") or "大众读者"
    count = args.count or 3
    result = provider.generate_titles(
        {
            "topic": topic,
            "audience": audience,
            "angle": manifest.get("direction") or research.get("angle") or "",
            "count": count,
            "research": research,
        }
    )
    ideation = load_ideation(workspace)
    payload = result.payload
    if isinstance(payload, list):
        titles = payload
    elif isinstance(payload, dict):
        titles = payload.get("candidates") or payload.get("titles") or []
    else:
        titles = []
    if not isinstance(titles, list):
        titles = []
    titles = titles[:count]
    ideation.update(
        {
            "topic": topic,
            "direction": manifest.get("direction") or research.get("angle") or "",
            "titles": titles,
            "updated_at": now_iso(),
            "provider": result.provider,
            "model": result.model,
        }
    )
    ideation, _ = select_scored_title(
        workspace,
        manifest,
        ideation,
        topic,
        audience,
        manifest.get("direction") or research.get("angle") or "",
        args.selected_title or "",
    )
    write_json(workspace / "ideation.json", ideation)
    manifest["selected_title"] = ideation.get("selected_title") or manifest.get("selected_title", "")
    manifest["ideation_path"] = "ideation.json"
    update_stage(manifest, "titles", "title_status")
    save_manifest(workspace, manifest)
    print(json.dumps(ideation, ensure_ascii=False, indent=2))
    return 0


def cmd_outline(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = persist_runtime_preferences(manifest, args)
    manifest = persist_style_samples(workspace, manifest, getattr(args, "style_sample", None))
    manifest = attach_corpus_context(workspace, manifest)
    provider = require_live_text_provider("outline")
    research = load_research(workspace)
    ideation = load_ideation(workspace)
    selected_title = args.title or manifest.get("selected_title") or ideation.get("selected_title") or manifest.get("topic") or "未命名标题"
    result = provider.generate_outline(
        {
            "topic": manifest.get("topic") or research.get("topic") or "",
            "selected_title": selected_title,
            "audience": manifest.get("audience") or research.get("audience") or "大众读者",
            "direction": manifest.get("direction") or research.get("angle") or "",
            "research": research,
            "titles": ideation.get("titles") or [],
            "style_samples": manifest.get("style_sample_paths") or [],
            "style_signals": manifest.get("style_signals") or [],
            "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
            "recent_article_titles": manifest.get("recent_article_titles") or [],
            "corpus_root": manifest.get("corpus_root") or "",
            "content_mode": manifest.get("content_mode") or "tech-balanced",
        }
    )
    outline = normalize_outline_payload(
        dict(result.payload),
        {
            "topic": manifest.get("topic") or research.get("topic") or selected_title,
            "selected_title": selected_title,
            "audience": manifest.get("audience") or research.get("audience") or "大众读者",
            "direction": manifest.get("direction") or research.get("angle") or "",
            "research": research,
            "style_signals": manifest.get("style_signals") or [],
            "content_mode": manifest.get("content_mode") or "tech-balanced",
        },
    )
    outline.setdefault("title", selected_title)
    ideation["selected_title"] = selected_title
    ideation["outline"] = outline.get("sections") or []
    ideation["outline_meta"] = outline
    ideation["viral_blueprint"] = outline.get("viral_blueprint") or {}
    ideation["editorial_blueprint"] = outline.get("editorial_blueprint") or {}
    ideation["updated_at"] = now_iso()
    write_json(workspace / "ideation.json", ideation)
    manifest["selected_title"] = selected_title
    manifest["outline"] = [item.get("heading", "") for item in outline.get("sections") or []]
    manifest["viral_blueprint"] = outline.get("viral_blueprint") or {}
    manifest["editorial_blueprint"] = outline.get("editorial_blueprint") or {}
    update_stage(manifest, "outline", "outline_status")
    save_manifest(workspace, manifest)
    print(json.dumps(outline, ensure_ascii=False, indent=2))
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = persist_runtime_preferences(manifest, args)
    manifest = persist_style_samples(workspace, manifest, getattr(args, "style_sample", None))
    manifest = attach_corpus_context(workspace, manifest)
    provider = require_live_text_provider("write")
    research = load_research(workspace)
    ideation = load_ideation(workspace)
    outline_meta = dict(ideation.get("outline_meta") or {})
    if args.outline_file:
        outline_lines = [line.strip("- ").strip() for line in read_input_file(args.outline_file).splitlines() if line.strip()]
        outline_meta["sections"] = [{"heading": line, "goal": "展开该章节", "evidence_need": "按需补证据"} for line in outline_lines]
    selected_title = args.title or manifest.get("selected_title") or ideation.get("selected_title") or manifest.get("topic") or "未命名标题"
    outline_meta = normalize_outline_payload(
        outline_meta,
        {
            "topic": manifest.get("topic") or research.get("topic") or selected_title,
            "selected_title": selected_title,
            "audience": manifest.get("audience") or research.get("audience") or "大众读者",
            "direction": manifest.get("direction") or research.get("angle") or "",
            "research": research,
            "style_signals": manifest.get("style_signals") or [],
            "content_mode": manifest.get("content_mode") or "tech-balanced",
        },
    )
    result = provider.generate_article(
        {
            "topic": manifest.get("topic") or research.get("topic") or selected_title,
            "title": selected_title,
            "selected_title": selected_title,
            "audience": manifest.get("audience") or research.get("audience") or "大众读者",
            "direction": manifest.get("direction") or research.get("angle") or "",
            "research": research,
            "outline": outline_meta or {"sections": ideation.get("outline") or []},
            "viral_blueprint": outline_meta.get("viral_blueprint") or current_viral_blueprint(workspace, manifest, ideation),
            "editorial_blueprint": outline_meta.get("editorial_blueprint") or {},
            "style_samples": manifest.get("style_sample_paths") or [],
            "style_signals": manifest.get("style_signals") or [],
            "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
            "recent_article_titles": manifest.get("recent_article_titles") or [],
            "corpus_root": manifest.get("corpus_root") or "",
            "content_mode": manifest.get("content_mode") or "tech-balanced",
        }
    )
    body = str(result.payload).strip()
    body = strip_leading_h1(body, selected_title)
    article_path = workspace / "article.md"
    write_text(article_path, join_frontmatter({"title": selected_title, "summary": extract_summary(body)}, body))
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    summary = synced_meta.get("summary") or extract_summary(synced_body or body)
    manifest.update(
        {
            "selected_title": selected_title,
            "summary": summary,
            "article_path": "article.md",
            "outline": [item.get("heading", "") for item in (outline_meta.get("sections") or [])],
            "viral_blueprint": outline_meta.get("viral_blueprint") or {},
            "editorial_blueprint": outline_meta.get("editorial_blueprint") or {},
            "text_provider": result.provider,
            "text_model": result.model,
        }
    )
    update_stage(manifest, "draft", "draft_status")
    save_manifest(workspace, manifest)
    print(str(article_path))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = persist_runtime_preferences(manifest, args)
    manifest = persist_style_samples(workspace, manifest, getattr(args, "style_sample", None))
    manifest = attach_corpus_context(workspace, manifest)
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    article_path = workspace / (manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到待评审文章：{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
    if synced_body:
        meta.update({key: value for key, value in synced_meta.items() if value})
        body = synced_body
    body = legacy.strip_image_directives(body)
    title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名标题"
    blueprint = current_viral_blueprint(workspace, manifest)
    provider = active_text_provider()
    if provider.configured():
        result = provider.review_article(
            {
                "title": title,
                "audience": manifest.get("audience") or "大众读者",
                "direction": manifest.get("direction") or "",
                "summary": meta.get("summary") or manifest.get("summary") or extract_summary(body),
                "article_body": body,
                "viral_blueprint": blueprint,
                "editorial_blueprint": (load_ideation(workspace).get("outline_meta") or {}).get("editorial_blueprint") or {},
                "style_samples": manifest.get("style_sample_paths") or [],
                "style_signals": manifest.get("style_signals") or [],
                "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
                "recent_article_titles": manifest.get("recent_article_titles") or [],
                "corpus_root": manifest.get("corpus_root") or "",
                "revision_round": int(manifest.get("revision_round") or 1),
                "content_mode": manifest.get("content_mode") or "tech-balanced",
            }
        )
        review_source = result.provider
        model_name = result.model
        raw_payload: Any = result.payload
    else:
        review_source = "local-heuristic"
        model_name = "builtin"
        raw_payload = build_heuristic_review(
            title,
            body,
            manifest,
            blueprint=blueprint,
            revision_round=int(manifest.get("revision_round") or 1),
            review_source=review_source,
            confidence=0.58,
        )
    payload = normalize_review_payload(
        raw_payload,
        title=title,
        body=body,
        manifest=manifest,
        blueprint=blueprint,
        revision_round=int(manifest.get("revision_round") or 1),
        review_source=review_source,
    )
    strengths, issues = split_review_points(payload.get("findings"))
    payload["findings"] = strengths + issues
    payload["strengths"] = strengths or payload.get("strengths") or []
    payload["issues"] = issues or payload.get("issues") or []
    payload["platform_notes"] = normalize_string_list(payload.get("platform_notes"))
    payload["title"] = title
    payload["provider"] = review_source
    payload["model"] = model_name
    payload["generated_at"] = now_iso()
    write_json(workspace / "review-report.json", payload)
    write_text(workspace / "review-report.md", markdown_review_report(payload))
    manifest["review_report_path"] = "review-report.json"
    update_stage(manifest, "review", "review_status")
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_review_from_score(title: str, report: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    total = int(report.get("total_score") or 0)
    threshold = int(report.get("threshold") or legacy.DEFAULT_THRESHOLD)
    delta = total - threshold
    if delta >= 0:
        summary = f"《{title}》当前版本已达到发布阈值（{total}/{threshold}），可以进入配图与排版阶段。"
    else:
        summary = f"《{title}》当前版本暂未达到发布阈值（{total}/{threshold}），建议先按问题清单补强后再出图排版。"
    strengths = normalize_string_list(report.get("strengths"))[:4]
    issues = normalize_string_list(report.get("weaknesses"))[:4]
    mandatory = normalize_string_list(report.get("mandatory_revisions"))
    for item in mandatory:
        if item not in issues:
            issues.append(item)
    platform_notes = [
        "微信公众号优先短段落、小标题和重点句，避免连续大段文字。",
        "事实型内容在发布前应自行核验关键表述，但最终正文不自动附加来源区。",
    ]
    if manifest.get("score_passed"):
        platform_notes.append("当前稿件已过线，进入出图前可再检查封面标题和摘要是否适合转发。")
    return {
        "summary": summary,
        "findings": strengths + issues,
        "strengths": strengths,
        "issues": issues,
        "platform_notes": platform_notes,
        "title": title,
        "provider": "host-agent",
        "model": "session",
        "generated_at": now_iso(),
        "hosted": True,
    }


def write_review_report(workspace: Path, manifest: dict[str, Any], payload: dict[str, Any]) -> None:
    write_json(workspace / "review-report.json", payload)
    lines = [payload.get("summary", "")]
    lines.extend(f"亮点：{item}" for item in payload.get("strengths", []))
    lines.extend(f"问题：{item}" for item in payload.get("issues", []))
    lines.extend(f"平台建议：{item}" for item in payload.get("platform_notes", []))
    ensure_text_report(workspace / "review-report.md", "编辑评审报告", lines)
    manifest["review_report_path"] = "review-report.json"
    update_stage(manifest, "review", "review_status")


def _mark_publish_intent(workspace: Path) -> None:
    manifest = load_manifest(workspace)
    if manifest.get("publish_intent"):
        return
    manifest["publish_intent"] = True
    save_manifest(workspace, manifest)


def _maybe_promote_rewrite(manifest: dict[str, Any], rewrite: dict[str, Any]) -> None:
    output_path = str(rewrite.get("output_path") or "").strip()
    if not output_path:
        return
    current_path = str(manifest.get("article_path") or "article.md")
    if current_path != output_path:
        manifest["draft_source_path"] = current_path
    manifest["article_path"] = output_path
    manifest["active_article_variant"] = "rewrite"


def cmd_revise(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = persist_runtime_preferences(manifest, args)
    manifest = persist_style_samples(workspace, manifest, getattr(args, "style_sample", None))
    manifest = attach_corpus_context(workspace, manifest)
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    article_path = workspace / (manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到待改写文章：{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
    if synced_body:
        meta.update({key: value for key, value in synced_meta.items() if value})
        body = synced_body
    body = legacy.strip_image_directives(body)
    title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名标题"
    report = read_json(workspace / "score-report.json", default={}) or {}
    if not report:
        threshold = manifest.get("score_threshold") or legacy.DEFAULT_THRESHOLD
        report = legacy.build_score_report(title, body, manifest, threshold)
    report = apply_research_credibility_boost(report, load_research(workspace))
    write_json(workspace / "score-report.json", report)
    legacy.write_text(workspace / "score-report.md", legacy.markdown_report(report))
    manifest["score_report_path"] = "score-report.json"
    manifest["score_total"] = report["total_score"]
    manifest["score_passed"] = report["passed"]
    mode = (getattr(args, "mode", None) or "improve-score").strip().lower().replace("_", "-")
    if mode == "explosive-score":
        mode = "improve-score"
    revision_round = int(manifest.get("revision_round") or 0)
    output_name = f"article-rewrite-r{revision_round}.md" if revision_round >= 1 else "article-rewrite.md"
    rewrite = generate_revision_candidate(
        workspace,
        title,
        meta,
        body,
        report,
        manifest,
        output_name=output_name,
        mode=mode,
    )
    # Keep a stable latest filename for humans while preserving per-round artifacts.
    if output_name != "article-rewrite.md":
        try:
            write_text(workspace / "article-rewrite.md", read_text(workspace / output_name))
        except OSError:
            pass
    manifest["rewrite_path"] = rewrite["output_path"]
    manifest["rewrite_preview_score"] = rewrite.get("preview_score")
    manifest["rewrite_preview_passed"] = rewrite.get("preview_passed")
    if rewrite.get("evidence_report_path"):
        manifest["evidence_report_path"] = rewrite["evidence_report_path"]
        manifest["evidence_used_count"] = rewrite.get("evidence_used_count", 0)
    if getattr(args, "promote", False):
        _maybe_promote_rewrite(manifest, rewrite)
    update_stage(manifest, "revise", "draft_status")
    save_manifest(workspace, manifest)
    print(json.dumps(rewrite, ensure_ascii=False, indent=2))
    return 0


def cmd_ideate(args: argparse.Namespace) -> int:
    return legacy.cmd_ideate(args)


def cmd_draft(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = attach_corpus_context(workspace, manifest)
    raw = read_input_file(args.input)
    meta, body = split_frontmatter(raw)
    title = args.selected_title or manifest.get("selected_title") or meta.get("title") or legacy.extract_title_from_body(body) or manifest.get("topic") or "未命名文章"
    body = strip_leading_h1(body, title)
    summary = args.summary or meta.get("summary") or manifest.get("summary") or extract_summary(body)
    author = args.author or meta.get("author") or manifest.get("author") or ""
    article_meta = {"title": title, "summary": summary}
    if author:
        article_meta["author"] = author
    article_path = workspace / "article.md"
    write_text(article_path, join_frontmatter(article_meta, body))
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    manifest.update(
        {
            "selected_title": title,
            "summary": synced_meta.get("summary") or summary,
            "author": author,
            "article_path": "article.md",
            "outline": [item["text"] for item in legacy.extract_headings(synced_body or body)] or manifest.get("outline") or [],
        }
    )
    save_manifest(workspace, manifest)
    print(str(article_path))
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    if not getattr(args, "dry_run", False):
        if not getattr(args, "confirmed_publish", False):
            raise SystemExit("正式发布前必须显式传入 --confirmed-publish。")
        blockers = collect_publish_blockers(workspace, manifest)
        if blockers:
            detail = "\n".join(f"- {item}" for item in blockers)
            raise SystemExit(f"当前稿件不满足正式发布条件：\n{detail}")
        _mark_publish_intent(workspace)
    return wechat_publish(args)


def cmd_verify_draft(args: argparse.Namespace) -> int:
    return wechat_verify_draft(args)


def cmd_doctor(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve()
    provider = active_text_provider()
    wechat_app_id, wechat_app_secret, _ = legacy.resolve_wechat_credentials(required=False)
    report = {
        "python": {"version": legacy.sys.version.split()[0], "ok": legacy.sys.version_info >= (3, 10)},
        "workspace": {
            "path": str(workspace),
            "exists": workspace.exists(),
            "writable": legacy.can_write_directory(workspace if workspace.exists() else workspace.parent),
        },
        "text_provider": {
            "default_mode": "hosted-agent",
            "hosted_agent_ready": True,
            "api_provider": provider.provider_name,
            "api_configured": provider.configured(),
            "model": getattr(provider, "model", ""),
            "required_env": ["ARTICLE_STUDIO_TEXT_MODEL", "OPENAI_API_KEY"],
            "notes": [
                "在 Codex / ClaudeCode / OpenClaw 中默认不要求文本环境变量，由宿主 agent 负责文本生成。",
                "只有脱离宿主、单独运行 run / research / titles / outline / write / review 等文本命令时，才需要配置文本 API。",
            ],
        },
        "image_providers": {
            "gemini-api": legacy.doctor_provider_status("gemini-api"),
            "openai-image": legacy.doctor_provider_status("openai-image"),
            "gemini-web": legacy.doctor_provider_status("gemini-web"),
        },
        "wechat": {
            "has_app_id": bool(wechat_app_id),
            "has_app_secret": bool(wechat_app_secret),
            "credential_path": str(getattr(legacy, "wechat_credential_path", lambda: "")()),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_consent(args: argparse.Namespace) -> int:
    return legacy.cmd_consent(args)


def cmd_discover_topics(args: argparse.Namespace) -> int:
    return legacy.cmd_discover_topics(args)


def _reset_manifest_progress(manifest: dict[str, Any]) -> None:
    manifest["stage"] = "initialized"
    for key in MANIFEST_STATUS_DEFAULTS:
        if key == "stage":
            continue
        manifest[key] = "not_started"
    # Reset revision-related state on topic change.
    for key in ["revision_round", "revision_rounds", "stop_reason", "best_round", "viral_blueprint"]:
        manifest.pop(key, None)


def cmd_select_topic(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)

    discovery_rel = str(manifest.get("topic_discovery_path") or "topic-discovery.json")
    discovery_path = workspace / discovery_rel
    if not discovery_path.exists():
        raise SystemExit(f"找不到热点选题发现结果：{discovery_path}")
    discovery = read_json(discovery_path, default={}) or {}
    candidates = list(discovery.get("candidates") or [])
    if not candidates:
        raise SystemExit("topic-discovery.json 中没有 candidates，无法选择。请先运行 discover-topics。")

    index = int(args.index or 0)
    if index < 1 or index > len(candidates):
        raise SystemExit(f"--index 超出范围：{index}（可选 1~{len(candidates)}）")

    candidate = candidates[index - 1] or {}
    new_topic = str(candidate.get("recommended_topic") or candidate.get("hot_title") or "").strip()
    if not new_topic:
        raise SystemExit("候选条目缺少 recommended_topic/hot_title，无法写入 manifest。")

    angles = list(candidate.get("angles") or [])
    angle = str(getattr(args, "angle", "") or "").strip()
    if not angle:
        angle_index = int(getattr(args, "angle_index", 1) or 1)
        if angle_index < 1:
            angle_index = 1
        if angles and 1 <= angle_index <= len(angles):
            angle = str(angles[angle_index - 1] or "").strip()
        else:
            angle = str(manifest.get("direction") or "").strip()

    audience = str(getattr(args, "audience", "") or "").strip() or str(manifest.get("audience") or "大众读者")
    selected_title = str(candidate.get("recommended_title") or candidate.get("hot_title") or new_topic).strip()
    source_url = str(candidate.get("source_url") or "").strip()
    source_urls = [source_url] if source_url else []

    previous_topic = str(manifest.get("topic") or "").strip()
    research = read_json(workspace / "research.json", default={}) or {}
    research_topic = str(research.get("topic") or "").strip()
    mismatch = (previous_topic and previous_topic != new_topic) or (research_topic and research_topic != new_topic)
    if mismatch:
        _reset_manifest_progress(manifest)

    manifest.update(
        {
            "topic": new_topic,
            "direction": angle,
            "audience": audience,
            "selected_title": selected_title,
            "source_urls": source_urls,
            "topic_selected_from": discovery_rel,
            "topic_selected_index": index,
            "topic_selected_at": now_iso(),
        }
    )

    ideation = read_json(workspace / "ideation.json", default={}) or {}
    ideation.update(
        {
            "topic": new_topic,
            "direction": angle,
            "selected_title": selected_title,
            "updated_at": now_iso(),
        }
    )
    write_json(workspace / "ideation.json", ideation)
    save_manifest(workspace, manifest)
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "selected_index": index,
                "topic": new_topic,
                "direction": angle,
                "selected_title": selected_title,
                "source_urls": source_urls,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _merge_url_list(base: list[str], extra: list[str]) -> list[str]:
    merged = normalize_urls([*base, *extra])
    return merged


def cmd_evidence(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)

    max_urls = int(getattr(args, "limit", 6) or 6)
    max_items = int(getattr(args, "max_items", 6) or 6)
    auto_search = bool(getattr(args, "auto_search", False))

    source_urls = _merge_url_list(list(manifest.get("source_urls") or []), list(getattr(args, "source_url", []) or []))

    if auto_search and legacy.tavily_api_key():
        topic = str(manifest.get("topic") or "").strip()
        angle = str(manifest.get("direction") or "").strip()
        seed = " ".join(part for part in [topic, angle] if part).strip() or "AI 科技 热点"
        query = f"{seed} 官方 文档 开源"
        try:
            discovered = legacy.tavily_search_urls(query, max_results=max_urls)
        except Exception as exc:
            discovered = []
            print(f"evidence 自动搜索失败（已忽略，继续用现有来源）：{exc}")
        source_urls = _merge_url_list(source_urls, discovered)

    source_urls = source_urls[:max_urls]

    article_path = workspace / (manifest.get("article_path") or "article.md")
    if article_path.exists():
        meta, body = split_frontmatter(read_text(article_path))
        body = legacy.strip_image_directives(body)
        title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名标题"
    else:
        title = str(manifest.get("selected_title") or manifest.get("topic") or "未命名标题")
        body = ""

    if not source_urls:
        raise SystemExit("当前未提供任何 source_url。请先传入 --source-url 或先选中热点条目后再运行 evidence。")

    report = legacy.collect_online_evidence(title, body, source_urls, workspace, max_items=max_items)

    evidence_lines = [f"# 证据与来源（最多 {max_items} 条证据句）", "", f"- 来源数：`{len(source_urls)}`", ""]
    for item in report.get("items") or []:
        evidence_lines.append(f"- 《{item.get('page_title') or ''}》：{item.get('sentence') or ''}")
        evidence_lines.append(f"  - {item.get('url') or ''}")
    if not (report.get("items") or []):
        evidence_lines.append("- 未能从来源中抽取到可用证据句；建议更换为官方发布、文档或权威媒体来源。")
    evidence_md_path = workspace / "evidence.md"
    write_text(evidence_md_path, "\n".join(evidence_lines).rstrip() + "\n")

    # Update manifest source urls + evidence pointers (best-effort; does not gate publish by itself).
    manifest["source_urls"] = source_urls
    manifest["evidence_report_path"] = "evidence-report.json"
    manifest["evidence_used_count"] = len(report.get("items") or [])
    save_manifest(workspace, manifest)

    # Merge into research.json (create stub if missing).
    research_path = workspace / "research.json"
    research_exists = research_path.exists()
    research = read_json(research_path, default={}) or {}
    research.setdefault("topic", manifest.get("topic") or title)
    research.setdefault("angle", manifest.get("direction") or "")
    research.setdefault("audience", manifest.get("audience") or "大众读者")
    existing_sources = research.get("sources") or []
    if isinstance(existing_sources, list) and existing_sources and isinstance(existing_sources[0], dict):
        seen = {str(item.get("url") or "").strip() for item in existing_sources if str(item.get("url") or "").strip()}
        for url in source_urls:
            if url not in seen:
                existing_sources.append({"url": url, "credibility": "evidence"})
                seen.add(url)
        research["sources"] = existing_sources
    else:
        research["sources"] = _merge_url_list([str(item).strip() for item in existing_sources if str(item).strip()], source_urls)
    research["evidence_items"] = report.get("items") or []
    research.setdefault("information_gaps", [])
    research.setdefault("forbidden_claims", ["不要把未验证信息写成确定事实。"])
    research["updated_at"] = now_iso()
    if "provider" not in research:
        research["provider"] = "evidence"
    if "model" not in research:
        research["model"] = "session"
    if research_exists and (research.get("sources") or research.get("evidence_items")):
        research["placeholder"] = False
    elif "placeholder" not in research:
        research["placeholder"] = False if research_exists else True
    write_json(research_path, research)

    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "source_urls": source_urls,
                "evidence_report_path": "evidence-report.json",
                "evidence_md_path": "evidence.md",
                "evidence_items": len(report.get("items") or []),
                "auto_search": auto_search,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _run_score(workspace: str) -> dict[str, Any]:
    cmd_score(
        argparse.Namespace(
            workspace=workspace,
            input=None,
            threshold=None,
            fail_below=False,
            no_rewrite=False,
            rewrite_output=None,
        )
    )
    return read_json(Path(workspace) / "score-report.json", default={}) or {}


def _effective_image_provider(args: argparse.Namespace) -> str | None:
    explicit = getattr(args, "image_provider", None)
    if explicit:
        return explicit
    if getattr(args, "dry_run_images", False):
        return "openai-image"
    return None


def _sync_image_controls(workspace: Path, args: argparse.Namespace) -> None:
    manifest = load_manifest(workspace)
    manifest["image_controls"] = legacy.resolve_image_controls(manifest.get("image_controls"), args)
    save_manifest(workspace, manifest)


def _write_hosted_research(workspace: Path, manifest: dict[str, Any], topic: str, angle: str, audience: str, source_urls: list[str]) -> None:
    payload = {
        "topic": topic,
        "angle": angle,
        "audience": audience,
        "sources": source_urls,
        "evidence_items": [],
        "information_gaps": ["正文由宿主 agent 直接生成；如含事实断言，请在发布前补充来源与证据。"],
        "forbidden_claims": ["不要把未验证信息写成确定事实。"],
        "provider": "host-agent",
        "model": "session",
        "generated_at": now_iso(),
        "hosted": True,
    }
    write_json(workspace / "research.json", payload)
    manifest.update(
        {
            "topic": topic,
            "direction": angle,
            "audience": audience,
            "source_urls": source_urls,
            "research_path": "research.json",
            "text_provider": "host-agent",
            "text_model": "session",
        }
    )
    update_stage(manifest, "research", "research_status")


def _write_hosted_ideation(workspace: Path, manifest: dict[str, Any], title: str, outline_file: str | None) -> None:
    manifest = attach_corpus_context(workspace, manifest)
    ideation = load_ideation(workspace)
    ideation["topic"] = manifest.get("topic") or title
    ideation["direction"] = manifest.get("direction") or ""
    ideation["selected_title"] = title
    ideation["updated_at"] = now_iso()
    ideation["provider"] = "host-agent"
    ideation["model"] = "session"
    if not ideation.get("titles"):
        ideation["titles"] = [
            {
                "title": title,
                "strategy": "宿主 agent 直出",
                "audience_fit": manifest.get("audience") or "大众读者",
                "risk_note": "",
            }
        ]
    outline_items: list[str] = []
    if outline_file:
        outline_items = [line.strip("- ").strip() for line in read_input_file(outline_file).splitlines() if line.strip()]
    elif ideation.get("outline"):
        outline_items = [str(item).strip() for item in ideation.get("outline") if str(item).strip()]
    if outline_items:
        ideation["outline"] = outline_items
        outline_meta = {
            "title": title,
            "angle": manifest.get("direction") or "",
            "sections": [{"heading": item, "goal": "宿主 agent 已生成正文", "evidence_need": "按需补充"} for item in outline_items],
        }
        outline_meta = normalize_outline_payload(
            outline_meta,
            {
                "topic": manifest.get("topic") or title,
                "selected_title": title,
                "audience": manifest.get("audience") or "大众读者",
                "direction": manifest.get("direction") or "",
                "research": load_research(workspace),
                "style_signals": manifest.get("style_signals") or [],
                "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
                "recent_article_titles": manifest.get("recent_article_titles") or [],
                "content_mode": manifest.get("content_mode") or "tech-balanced",
            },
        )
        ideation["outline_meta"] = outline_meta
        ideation["viral_blueprint"] = outline_meta.get("viral_blueprint") or {}
        ideation["editorial_blueprint"] = outline_meta.get("editorial_blueprint") or {}
        manifest["viral_blueprint"] = outline_meta.get("viral_blueprint") or {}
        manifest["editorial_blueprint"] = outline_meta.get("editorial_blueprint") or {}
    elif not ideation.get("viral_blueprint") and not manifest.get("viral_blueprint"):
        blueprint = default_viral_blueprint(
            topic=str(manifest.get("topic") or title),
            title=title,
            angle=str(manifest.get("direction") or ""),
            audience=str(manifest.get("audience") or "大众读者"),
            research=load_research(workspace),
            style_signals=manifest.get("style_signals") or [],
        )
        ideation["viral_blueprint"] = blueprint
        manifest["viral_blueprint"] = blueprint
    write_json(workspace / "ideation.json", ideation)
    manifest["selected_title"] = title
    manifest["content_mode"] = manifest.get("content_mode") or "tech-balanced"
    if outline_items:
        manifest["outline"] = outline_items
        update_stage(manifest, "outline", "outline_status")
    update_stage(manifest, "titles", "title_status")


def _ensure_hosted_titles(workspace: Path, manifest: dict[str, Any], topic: str, audience: str, angle: str, requested_title: str = "") -> None:
    ideation = load_ideation(workspace)
    if not ideation.get("titles"):
        provider = active_text_provider()
        research = load_research(workspace)
        if provider.configured():
            result = provider.generate_titles(
                {
                    "topic": topic,
                    "audience": audience,
                    "angle": angle,
                    "count": 4,
                    "research": research,
                }
            )
            titles = result.payload[:4] if isinstance(result.payload, list) else result.payload.get("titles", [])
            ideation.update(
                {
                    "topic": topic,
                    "direction": angle,
                    "titles": titles,
                    "updated_at": now_iso(),
                    "provider": result.provider,
                    "model": result.model,
                }
            )
        else:
            ideation.update(
                {
                    "topic": topic,
                    "direction": angle,
                    "titles": legacy.generate_hot_title_variants(topic, angle, audience),
                    "updated_at": now_iso(),
                    "provider": "local-heuristic",
                    "model": "builtin",
                }
            )
    ideation, _ = select_scored_title(workspace, manifest, ideation, topic, audience, angle, requested_title)
    write_json(workspace / "ideation.json", ideation)


def _bootstrap_hosted_article(workspace: Path, manifest: dict[str, Any], topic: str, title: str, angle: str, audience: str) -> str:
    manifest = attach_corpus_context(workspace, manifest)
    provider = require_live_text_provider("hosted-run 自动补正文")
    source_urls = normalize_urls(manifest.get("source_urls") or [])
    research = load_research(workspace)
    if not research:
        result = provider.generate_research_pack(
            {
                "topic": topic,
                "angle": angle,
                "audience": audience,
                "source_urls": source_urls,
            }
        )
        payload = dict(result.payload)
        payload.setdefault("topic", topic)
        payload.setdefault("angle", angle)
        payload.setdefault("audience", audience)
        payload["provider"] = result.provider
        payload["model"] = result.model
        payload["generated_at"] = now_iso()
        write_json(workspace / "research.json", payload)
        manifest["research_path"] = "research.json"
        manifest["text_provider"] = result.provider
        manifest["text_model"] = result.model
        update_stage(manifest, "research", "research_status")
        research = payload

    ideation = load_ideation(workspace)
    if not ideation.get("titles"):
        title_result = provider.generate_titles(
            {
                "topic": topic,
                "audience": audience,
                "angle": angle,
                "count": 3,
                "research": research,
                "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
                "recent_article_titles": manifest.get("recent_article_titles") or [],
            }
        )
        titles = title_result.payload[:3] if isinstance(title_result.payload, list) else title_result.payload.get("titles", [])
        ideation.update(
            {
                "topic": topic,
                "direction": angle,
                "titles": titles,
                "selected_title": title or (titles[0]["title"] if titles else topic),
                "updated_at": now_iso(),
                "provider": title_result.provider,
                "model": title_result.model,
            }
        )
        write_json(workspace / "ideation.json", ideation)
        manifest["selected_title"] = ideation.get("selected_title") or title
        update_stage(manifest, "titles", "title_status")
    title = title or ideation.get("selected_title") or manifest.get("selected_title") or topic

    outline_meta = dict(ideation.get("outline_meta") or {})
    if not outline_meta.get("sections"):
        outline_result = provider.generate_outline(
            {
                "topic": topic,
                "selected_title": title,
                "audience": audience,
                "direction": angle,
                "research": research,
                "titles": ideation.get("titles") or [],
                "style_samples": manifest.get("style_sample_paths") or [],
                "style_signals": manifest.get("style_signals") or [],
                "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
                "recent_article_titles": manifest.get("recent_article_titles") or [],
                "corpus_root": manifest.get("corpus_root") or "",
                "content_mode": manifest.get("content_mode") or "tech-balanced",
            }
        )
        outline_meta = normalize_outline_payload(
            dict(outline_result.payload),
            {
                "topic": topic,
                "selected_title": title,
                "audience": audience,
                "direction": angle,
                "research": research,
                "style_signals": manifest.get("style_signals") or [],
                "content_mode": manifest.get("content_mode") or "tech-balanced",
            },
        )
        if not outline_meta.get("sections"):
            outline_meta = placeholder_outline(title)
        ideation["selected_title"] = title
        ideation["outline"] = outline_meta.get("sections") or []
        ideation["outline_meta"] = outline_meta
        ideation["viral_blueprint"] = outline_meta.get("viral_blueprint") or {}
        ideation["editorial_blueprint"] = outline_meta.get("editorial_blueprint") or {}
        ideation["updated_at"] = now_iso()
        ideation["provider"] = outline_result.provider
        ideation["model"] = outline_result.model
        write_json(workspace / "ideation.json", ideation)
        manifest["outline"] = [item.get("heading", "") for item in outline_meta.get("sections") or []]
        manifest["viral_blueprint"] = outline_meta.get("viral_blueprint") or {}
        manifest["editorial_blueprint"] = outline_meta.get("editorial_blueprint") or {}
        update_stage(manifest, "outline", "outline_status")

    article_result = provider.generate_article(
        {
            "topic": topic,
            "title": title,
            "selected_title": title,
            "audience": audience,
            "direction": angle,
            "research": research,
            "outline": outline_meta or {"sections": ideation.get("outline") or []},
            "viral_blueprint": outline_meta.get("viral_blueprint") or current_viral_blueprint(workspace, manifest, ideation),
            "editorial_blueprint": outline_meta.get("editorial_blueprint") or {},
            "style_samples": manifest.get("style_sample_paths") or [],
            "style_signals": manifest.get("style_signals") or [],
            "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
            "recent_article_titles": manifest.get("recent_article_titles") or [],
            "corpus_root": manifest.get("corpus_root") or "",
            "content_mode": manifest.get("content_mode") or "tech-balanced",
        }
    )
    body = str(article_result.payload).strip()
    if not body:
        body = placeholder_article(title, outline_meta or placeholder_outline(title), audience)
    body = strip_leading_h1(body, title)
    write_text(workspace / "article.md", join_frontmatter({"title": title, "summary": extract_summary(body)}, body))
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    summary = synced_meta.get("summary") or extract_summary(synced_body or body)
    manifest.update(
        {
            "selected_title": title,
            "summary": summary,
            "article_path": "article.md",
            "text_provider": article_result.provider,
            "text_model": article_result.model,
        }
    )
    update_stage(manifest, "draft", "draft_status")
    return title


def _import_hosted_article(
    workspace: Path,
    manifest: dict[str, Any],
    article_file: str | None,
    title_hint: str | None,
    summary_hint: str | None,
    angle: str,
    audience: str,
) -> str:
    manifest = attach_corpus_context(workspace, manifest)
    article_path = workspace / "article.md"
    if article_file:
        raw = read_input_file(article_file)
        meta, body = split_frontmatter(raw)
        title = title_hint or meta.get("title") or manifest.get("selected_title") or manifest.get("topic") or "未命名标题"
        body = strip_leading_h1(body, title)
        summary = summary_hint or meta.get("summary") or extract_summary(body)
        write_text(article_path, join_frontmatter({"title": title, "summary": summary}, body))
    elif not article_path.exists():
        title = title_hint or manifest.get("selected_title") or manifest.get("topic") or "未命名标题"
        return _bootstrap_hosted_article(workspace, manifest, manifest.get("topic") or title, title, angle, audience)
    meta, body = split_frontmatter(read_text(article_path))
    title = title_hint or meta.get("title") or manifest.get("selected_title") or manifest.get("topic") or "未命名标题"
    summary = summary_hint or meta.get("summary") or extract_summary(body)
    write_text(article_path, join_frontmatter({"title": title, "summary": summary}, strip_leading_h1(body, title)))
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    manifest.update(
        {
            "selected_title": title,
            "summary": synced_meta.get("summary") or summary,
            "article_path": "article.md",
            "text_provider": "host-agent",
            "text_model": "session",
        }
    )
    update_stage(manifest, "draft", "draft_status")
    return title


def _finalize_after_score(workspace: Path, manifest: dict[str, Any], title: str, score_report: dict[str, Any]) -> dict[str, Any]:
    manifest["score_status"] = "done"
    manifest["score_report_path"] = "score-report.json"
    manifest["score_total"] = score_report.get("total_score")
    manifest["score_passed"] = score_report.get("passed")
    manifest["stage"] = "score"
    review_payload = read_json(workspace / "review-report.json", default={}) or {}
    # Prefer the structured, real review if present; only fall back to score-derived review when missing.
    if not (isinstance(review_payload, dict) and review_payload.get("viral_analysis")):
        review_payload = build_review_from_score(title, score_report, manifest)
        write_review_report(workspace, manifest, review_payload)
    save_manifest(workspace, manifest)
    return review_payload


def cmd_score(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = persist_runtime_preferences(manifest, args)
    manifest = persist_style_samples(workspace, manifest, getattr(args, "style_sample", None))
    manifest = attach_corpus_context(workspace, manifest)
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    article_path = workspace / (args.input or manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到待评分文章：{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
    if synced_body:
        meta.update({key: value for key, value in synced_meta.items() if value})
        body = synced_body
    body = legacy.strip_image_directives(body)
    title = legacy.infer_title(manifest, meta, body)
    threshold = args.threshold or manifest.get("score_threshold")
    review = read_json(workspace / "review-report.json", default={}) or {}
    if not review:
        blueprint = current_viral_blueprint(workspace, manifest)
        review = build_heuristic_review(title, body, manifest, blueprint=blueprint, revision_round=int(manifest.get("revision_round") or 1))
        write_json(workspace / "review-report.json", review)
        write_text(workspace / "review-report.md", markdown_review_report(review))
        manifest["review_report_path"] = "review-report.json"
        update_stage(manifest, "review", "review_status")

    revision_rounds = list(manifest.get("revision_rounds") or [])
    report = legacy.build_score_report(
        title,
        body,
        manifest,
        int(threshold) if threshold is not None else None,
        review=review,
        revision_rounds=revision_rounds,
        stop_reason=str(manifest.get("stop_reason") or ""),
    )
    report = apply_research_credibility_boost(report, load_research(workspace))

    if not report.get("passed") and not args.no_rewrite:
        if args.rewrite_output:
            rewrite_path = Path(args.rewrite_output)
            if not rewrite_path.is_absolute():
                rewrite_path = workspace / rewrite_path
        else:
            rewrite_path = workspace / "article-rewrite.md"
        rewrite = generate_revision_candidate(workspace, title, meta, body, report, manifest, rewrite_path.name, mode="improve-score")
        report["rewrite"] = rewrite
        manifest["rewrite_path"] = rewrite["output_path"]
        manifest["rewrite_preview_score"] = rewrite.get("preview_score")
        manifest["rewrite_preview_passed"] = rewrite.get("preview_passed")
        if rewrite.get("evidence_report_path"):
            manifest["evidence_report_path"] = rewrite["evidence_report_path"]
            manifest["evidence_used_count"] = rewrite.get("evidence_used_count", 0)

    write_json(workspace / "score-report.json", report)
    legacy.write_text(workspace / "score-report.md", legacy.markdown_report(report))
    manifest["score_breakdown"] = report["score_breakdown"]
    manifest["score_total"] = report["total_score"]
    manifest["score_passed"] = report["passed"]
    manifest["score_report_path"] = "score-report.json"
    manifest["score_status"] = "done"
    save_manifest(workspace, manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_below and report["total_score"] < int(report.get("threshold") or VIRAL_SCORE_THRESHOLD):
        return 2
    return 0


def _run_score_only(workspace: Path, *, threshold: int | None = None, style_sample: list[str] | None = None) -> dict[str, Any]:
    cmd_score(
        argparse.Namespace(
            workspace=str(workspace),
            input=None,
            threshold=threshold,
            fail_below=False,
            no_rewrite=True,
            rewrite_output=None,
            style_sample=style_sample or [],
        )
    )
    return read_json(workspace / "score-report.json", default={}) or {}


def _run_review_only(workspace: Path, *, style_sample: list[str] | None = None) -> dict[str, Any]:
    cmd_review(argparse.Namespace(workspace=str(workspace), style_sample=style_sample or []))
    return read_json(workspace / "review-report.json", default={}) or {}


def _run_revision_loop(workspace: Path, *, max_rounds: int, style_sample: list[str] | None = None) -> dict[str, Any]:
    max_rounds = max(1, int(max_rounds or 1))
    manifest = load_manifest(workspace)
    manifest["revision_rounds"] = []
    manifest["revision_round"] = 0
    manifest["stop_reason"] = ""
    manifest["best_round"] = 0
    save_manifest(workspace, manifest)

    best_score = -1
    best_round = 0
    best_article_path = str(manifest.get("article_path") or "article.md")
    scores: list[int] = []
    stop_reason = ""

    for round_index in range(1, max_rounds + 1):
        manifest = load_manifest(workspace)
        manifest["revision_round"] = round_index
        save_manifest(workspace, manifest)

        _run_review_only(workspace, style_sample=style_sample)
        score_report = _run_score_only(workspace, threshold=None, style_sample=style_sample)
        manifest = load_manifest(workspace)

        score_value = int(score_report.get("total_score") or 0)
        passed = bool(score_report.get("passed"))
        record = {
            "round": round_index,
            "score": score_value,
            "passed": passed,
            "article_path": str(manifest.get("article_path") or "article.md"),
            "review_report_path": str(manifest.get("review_report_path") or "review-report.json"),
            "score_report_path": str(manifest.get("score_report_path") or "score-report.json"),
        }
        revision_rounds = list(manifest.get("revision_rounds") or [])
        revision_rounds.append(record)
        manifest["revision_rounds"] = revision_rounds
        save_manifest(workspace, manifest)

        if score_value > best_score:
            best_score = score_value
            best_round = round_index
            best_article_path = record["article_path"]

        scores.append(score_value)
        if passed:
            stop_reason = "passed"
            break
        if round_index >= max_rounds:
            stop_reason = "max_rounds_reached"
            break
        if len(scores) >= 3:
            if (scores[-1] - scores[-2]) < 2 and (scores[-2] - scores[-3]) < 2:
                stop_reason = "plateau"
                break

        # Next round rewrite: keep per-round artifact via revision_round in manifest.
        cmd_revise(
            argparse.Namespace(
                workspace=str(workspace),
                promote=True,
                mode="explosive-score",
                style_sample=style_sample or [],
            )
        )

    # Switch to best-performing round before continuing.
    manifest = load_manifest(workspace)
    manifest["stop_reason"] = stop_reason or "unknown"
    manifest["best_round"] = best_round
    manifest["article_path"] = best_article_path
    manifest["revision_round"] = best_round
    save_manifest(workspace, manifest)

    # Re-generate final review/score for the selected best variant, and stamp stop_reason in score report.
    _run_review_only(workspace, style_sample=style_sample)
    manifest = load_manifest(workspace)
    manifest["stop_reason"] = stop_reason or "unknown"
    manifest["best_round"] = best_round
    save_manifest(workspace, manifest)
    return _run_score_only(workspace, threshold=None, style_sample=style_sample)


def cmd_run(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = persist_runtime_preferences(manifest, args)
    style_sample = list(getattr(args, "style_sample", []) or [])
    manifest = persist_style_samples(workspace, manifest, style_sample)
    save_manifest(workspace, manifest)
    assert_publish_request_ready(args)
    raw_topic = (args.topic or manifest.get("topic") or "").strip()
    if raw_topic.lower() in legacy.START_TOPIC_TOKENS:
        return legacy.cmd_discover_topics(
            argparse.Namespace(
                workspace=str(workspace),
                window_hours=24,
                limit=legacy.DISCOVERY_TOPIC_LIMIT,
                provider="auto",
                focus="ai-tech",
                rss_url=[],
            )
        )
    require_live_text_provider("run")
    topic = raw_topic or "未命名主题"
    if not (workspace / "research.json").exists():
        cmd_research(
            argparse.Namespace(
                workspace=str(workspace),
                topic=topic,
                angle=args.angle or manifest.get("direction") or "",
                audience=args.audience or manifest.get("audience") or "大众读者",
                source_url=args.source_url or manifest.get("source_urls") or [],
            )
        )
    if not (workspace / "ideation.json").exists() or not load_ideation(workspace).get("titles"):
        cmd_titles(argparse.Namespace(workspace=str(workspace), count=args.title_count, selected_title=None))
    ideation = load_ideation(workspace)
    if not ideation.get("outline"):
        cmd_outline(argparse.Namespace(workspace=str(workspace), title=args.title or ideation.get("selected_title"), style_sample=style_sample))
    if not (workspace / "article.md").exists():
        cmd_write(argparse.Namespace(workspace=str(workspace), title=args.title or ideation.get("selected_title"), outline_file=None, style_sample=style_sample))
    score_report = _run_revision_loop(workspace, max_rounds=int(getattr(args, "max_revision_rounds", 3) or 3), style_sample=style_sample)
    manifest = load_manifest(workspace)
    _finalize_after_score(workspace, manifest, manifest.get("selected_title") or topic, score_report)
    _sync_image_controls(workspace, args)
    image_provider = _effective_image_provider(args)
    legacy_plan_images(argparse.Namespace(workspace=str(workspace), provider=image_provider, inline_count=args.inline_count))
    manifest = load_manifest(workspace)
    manifest["image_status"] = "planned"
    save_manifest(workspace, manifest)
    legacy_generate_images(
        argparse.Namespace(
            workspace=str(workspace),
            provider=image_provider,
            dry_run=args.dry_run_images,
            gemini_model=args.gemini_model,
            openai_model=args.openai_model,
        )
    )
    legacy_assemble(argparse.Namespace(workspace=str(workspace)))
    legacy_render(
        argparse.Namespace(
            workspace=str(workspace),
            input=None,
            output="article.html",
            accent_color=args.accent_color,
            layout_style=getattr(args, "layout_style", "auto"),
            input_format=getattr(args, "input_format", "auto"),
            wechat_header_mode=getattr(args, "wechat_header_mode", "drop-title"),
        )
    )
    manifest = load_manifest(workspace)
    manifest["image_status"] = "done"
    manifest["render_status"] = "done"
    manifest["stage"] = "render"
    save_manifest(workspace, manifest)
    if args.to == "publish":
        cmd_publish(
            argparse.Namespace(
                workspace=str(workspace),
                input=None,
                digest=None,
                author=None,
                cover=None,
                dry_run=args.dry_run_publish,
                confirmed_publish=args.confirmed_publish,
            )
        )
        if not args.dry_run_publish:
            cmd_verify_draft(argparse.Namespace(workspace=str(workspace), media_id=None))
    return 0


def cmd_hosted_run(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = persist_runtime_preferences(manifest, args)
    style_sample = list(getattr(args, "style_sample", []) or [])
    manifest = persist_style_samples(workspace, manifest, style_sample)
    save_manifest(workspace, manifest)
    assert_publish_request_ready(args)
    raw_topic = (args.topic or manifest.get("topic") or "").strip()
    if raw_topic.lower() in legacy.START_TOPIC_TOKENS:
        return legacy.cmd_discover_topics(
            argparse.Namespace(
                workspace=str(workspace),
                window_hours=24,
                limit=legacy.DISCOVERY_TOPIC_LIMIT,
                provider="auto",
                focus="ai-tech",
                rss_url=[],
            )
        )
    topic = raw_topic or "未命名主题"
    angle = args.angle or manifest.get("direction") or ""
    audience = args.audience or manifest.get("audience") or "大众读者"
    source_urls = normalize_urls(args.source_url or manifest.get("source_urls") or [])
    _write_hosted_research(workspace, manifest, topic, angle, audience, source_urls)
    _ensure_hosted_titles(workspace, manifest, topic, audience, angle, args.title or "")
    refreshed = load_ideation(workspace)
    title = args.title or refreshed.get("selected_title") or manifest.get("selected_title") or topic
    _write_hosted_ideation(workspace, manifest, title, args.outline_file)
    title = _import_hosted_article(workspace, manifest, args.article_file, title, args.summary, angle, audience)
    save_manifest(workspace, manifest)
    score_report = _run_revision_loop(workspace, max_rounds=int(getattr(args, "max_revision_rounds", 3) or 3), style_sample=style_sample)
    manifest = load_manifest(workspace)
    _finalize_after_score(workspace, manifest, title, score_report)

    _sync_image_controls(workspace, args)
    image_provider = _effective_image_provider(args)
    legacy_plan_images(argparse.Namespace(workspace=str(workspace), provider=image_provider, inline_count=args.inline_count))
    manifest = load_manifest(workspace)
    manifest["image_status"] = "planned"
    save_manifest(workspace, manifest)
    legacy_generate_images(
        argparse.Namespace(
            workspace=str(workspace),
            provider=image_provider,
            dry_run=args.dry_run_images,
            gemini_model=args.gemini_model,
            openai_model=args.openai_model,
        )
    )
    legacy_assemble(argparse.Namespace(workspace=str(workspace)))
    legacy_render(
        argparse.Namespace(
            workspace=str(workspace),
            input=None,
            output="article.html",
            accent_color=args.accent_color,
            layout_style=getattr(args, "layout_style", "auto"),
            input_format=getattr(args, "input_format", "auto"),
            wechat_header_mode=getattr(args, "wechat_header_mode", "drop-title"),
        )
    )
    manifest = load_manifest(workspace)
    manifest["image_status"] = "done"
    manifest["render_status"] = "done"
    manifest["stage"] = "render"
    save_manifest(workspace, manifest)
    if args.to == "publish":
        cmd_publish(
            argparse.Namespace(
                workspace=str(workspace),
                input=None,
                digest=None,
                author=None,
                cover=None,
                dry_run=args.dry_run_publish,
                confirmed_publish=args.confirmed_publish,
            )
        )
        if not args.dry_run_publish:
            cmd_verify_draft(argparse.Namespace(workspace=str(workspace), media_id=None))
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    return cmd_run(
        argparse.Namespace(
            workspace=args.workspace,
            topic=None,
            angle=None,
            audience=None,
            source_url=[],
            title=None,
            title_count=3,
            content_mode=args.content_mode,
            wechat_header_mode=args.wechat_header_mode,
            image_provider=args.provider,
            image_preset=args.image_preset,
            image_style_mode=getattr(args, "image_style_mode", None),
            image_preset_cover=getattr(args, "image_preset_cover", None),
            image_preset_infographic=getattr(args, "image_preset_infographic", None),
            image_preset_inline=getattr(args, "image_preset_inline", None),
            image_density=args.image_density,
            image_layout_family=args.image_layout_family,
            image_theme=args.image_theme,
            image_style=args.image_style,
            image_type=args.image_type,
            image_mood=args.image_mood,
            custom_visual_brief=args.custom_visual_brief,
            inline_count=args.inline_count,
            dry_run_images=args.dry_run_images,
            dry_run_publish=args.dry_run_publish,
            confirmed_publish=args.confirmed_publish,
            gemini_model=args.gemini_model,
            openai_model=args.openai_model,
            accent_color=args.accent_color,
            layout_style=getattr(args, "layout_style", "auto"),
            input_format=getattr(args, "input_format", "auto"),
            to="publish" if args.publish else "render",
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studio.py", description="微信公众号图文工作流 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    research = subparsers.add_parser("research", help="初始化 research.json，沉淀调研输入与来源清单")
    research.add_argument("--workspace", required=True)
    research.add_argument("--topic", required=True)
    research.add_argument("--angle")
    research.add_argument("--audience")
    research.add_argument("--source-url", action="append", default=[])
    research.set_defaults(func=cmd_research)

    titles = subparsers.add_parser("titles", help="生成 3 个左右标题候选并写入 ideation.json")
    titles.add_argument("--workspace", required=True)
    titles.add_argument("--count", type=int, default=3)
    titles.add_argument("--selected-title")
    titles.set_defaults(func=cmd_titles)

    outline = subparsers.add_parser("outline", help="基于 research 和标题生成大纲")
    outline.add_argument("--workspace", required=True)
    outline.add_argument("--title")
    outline.add_argument("--style-sample", action="append", default=[], help="可选：提供高表现文章/风格样本文件路径（可重复）")
    outline.set_defaults(func=cmd_outline)

    write = subparsers.add_parser("write", help="基于 research + ideation 产出 article.md 初稿")
    write.add_argument("--workspace", required=True)
    write.add_argument("--title")
    write.add_argument("--outline-file")
    write.add_argument("--style-sample", action="append", default=[], help="可选：提供高表现文章/风格样本文件路径（可重复）")
    write.set_defaults(func=cmd_write)

    review = subparsers.add_parser("review", help="生成独立的编辑评审报告，不替代 score")
    review.add_argument("--workspace", required=True)
    review.add_argument("--style-sample", action="append", default=[], help="可选：提供高表现文章/风格样本文件路径（可重复）")
    review.set_defaults(func=cmd_review)

    revise = subparsers.add_parser("revise", help="基于 score/report 生成 article-rewrite.md 候选稿")
    revise.add_argument("--workspace", required=True)
    revise.add_argument("--promote", action="store_true", help="将改写稿切换为后续流程默认正文")
    revise.add_argument(
        "--mode",
        choices=["improve-score", "explosive-score", "de-ai"],
        default="improve-score",
        help="改写模式：爆款提分改写（explosive-score/improve-score）或去 AI 味（de-ai）",
    )
    revise.add_argument("--style-sample", action="append", default=[], help="可选：提供高表现文章/风格样本文件路径（可重复）")
    revise.set_defaults(func=cmd_revise)

    run = subparsers.add_parser("run", help="从 research 串到 render；显式要求时才继续 publish")
    run.add_argument("--workspace", required=True)
    run.add_argument("--topic")
    run.add_argument("--angle")
    run.add_argument("--audience")
    run.add_argument("--source-url", action="append", default=[])
    run.add_argument("--title")
    run.add_argument("--title-count", type=int, default=3)
    run.add_argument("--content-mode", choices=CONTENT_MODE_CHOICES, default="tech-balanced")
    run.add_argument("--wechat-header-mode", choices=WECHAT_HEADER_MODE_CHOICES, default="drop-title")
    run.add_argument("--max-revision-rounds", type=int, default=3, help="多轮修正上限（默认 3）")
    run.add_argument("--style-sample", action="append", default=[], help="可选：提供高表现文章/风格样本文件路径（可重复）")
    run.add_argument("--to", choices=["render", "publish"], default="render")
    run.add_argument("--image-provider", choices=["gemini-web", "gemini-api", "openai-image"])
    run.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    run.add_argument("--image-style-mode", choices=["uniform", "mixed-by-type"])
    run.add_argument("--image-preset-cover", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    run.add_argument("--image-preset-infographic", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    run.add_argument("--image-preset-inline", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    run.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default="balanced")
    run.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    run.add_argument("--image-theme")
    run.add_argument("--image-style")
    run.add_argument("--image-type")
    run.add_argument("--image-mood")
    run.add_argument("--custom-visual-brief")
    run.add_argument("--inline-count", type=int, default=0)
    run.add_argument("--dry-run-images", action="store_true")
    run.add_argument("--dry-run-publish", action="store_true")
    run.add_argument("--confirmed-publish", action="store_true")
    run.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    run.add_argument("--openai-model", default="gpt-image-1")
    run.add_argument("--accent-color", default="#0F766E")
    run.add_argument("--layout-style", choices=LAYOUT_STYLE_CHOICES, default="auto")
    run.add_argument("--input-format", choices=INPUT_FORMAT_CHOICES, default="auto")
    run.set_defaults(func=cmd_run)

    discover_topics = subparsers.add_parser("discover-topics", help="联网发现最近 12/24 小时的热点新闻与可写选题")
    discover_topics.add_argument("--workspace", required=True)
    discover_topics.add_argument("--window-hours", type=int, choices=[12, 24], default=24)
    discover_topics.add_argument("--limit", type=int, default=legacy.DISCOVERY_TOPIC_LIMIT)
    discover_topics.add_argument("--provider", choices=legacy.DISCOVERY_PROVIDER_CHOICES, default="auto")
    discover_topics.add_argument("--rss-url", action="append", default=[], help="自定义 RSS 源（可重复；用于 provider=custom-rss 或 auto 回退）")
    discover_topics.add_argument("--focus", choices=["ai-tech", "all"], default="ai-tech")
    discover_topics.set_defaults(func=cmd_discover_topics)

    select_topic = subparsers.add_parser("select-topic", help="从 topic-discovery.json 选择候选方向并写入 manifest")
    select_topic.add_argument("--workspace", required=True)
    select_topic.add_argument("--index", type=int, required=True, help="候选编号（1-based）")
    select_topic.add_argument("--angle-index", type=int, default=1, help="角度编号（1-based；默认 1）")
    select_topic.add_argument("--angle", help="显式指定切入角度（优先级高于 --angle-index）")
    select_topic.add_argument("--audience", help="显式指定读者画像（缺省沿用 manifest）")
    select_topic.set_defaults(func=cmd_select_topic)

    evidence = subparsers.add_parser("evidence", help="抽取/补齐来源证据句并回写 research.json/source_urls（默认不联网）")
    evidence.add_argument("--workspace", required=True)
    evidence.add_argument("--source-url", action="append", default=[], help="补充来源 URL（可重复）")
    evidence.add_argument("--limit", type=int, default=6, help="最多保留的来源 URL 数")
    evidence.add_argument("--max-items", type=int, default=6, help="最多抽取的证据句条数")
    evidence.add_argument("--auto-search", action="store_true", help="启用 Tavily 自动搜索补来源（需要 TAVILY_API_KEY）")
    evidence.set_defaults(func=cmd_evidence)

    hosted_run = subparsers.add_parser("hosted-run", help="由宿主 agent 负责文本生成，再继续评分、配图、渲染与发布")
    hosted_run.add_argument("--workspace", required=True)
    hosted_run.add_argument("--topic")
    hosted_run.add_argument("--angle")
    hosted_run.add_argument("--audience")
    hosted_run.add_argument("--source-url", action="append", default=[])
    hosted_run.add_argument("--title")
    hosted_run.add_argument("--outline-file")
    hosted_run.add_argument("--article-file")
    hosted_run.add_argument("--summary")
    hosted_run.add_argument("--content-mode", choices=CONTENT_MODE_CHOICES, default="tech-balanced")
    hosted_run.add_argument("--wechat-header-mode", choices=WECHAT_HEADER_MODE_CHOICES, default="drop-title")
    hosted_run.add_argument("--max-revision-rounds", type=int, default=3, help="多轮修正上限（默认 3）")
    hosted_run.add_argument("--style-sample", action="append", default=[], help="可选：提供高表现文章/风格样本文件路径（可重复）")
    hosted_run.add_argument("--to", choices=["render", "publish"], default="render")
    hosted_run.add_argument("--image-provider", choices=["gemini-web", "gemini-api", "openai-image"])
    hosted_run.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    hosted_run.add_argument("--image-style-mode", choices=["uniform", "mixed-by-type"])
    hosted_run.add_argument("--image-preset-cover", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    hosted_run.add_argument("--image-preset-infographic", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    hosted_run.add_argument("--image-preset-inline", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    hosted_run.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default="balanced")
    hosted_run.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    hosted_run.add_argument("--image-theme")
    hosted_run.add_argument("--image-style")
    hosted_run.add_argument("--image-type")
    hosted_run.add_argument("--image-mood")
    hosted_run.add_argument("--custom-visual-brief")
    hosted_run.add_argument("--inline-count", type=int, default=0)
    hosted_run.add_argument("--dry-run-images", action="store_true")
    hosted_run.add_argument("--dry-run-publish", action="store_true")
    hosted_run.add_argument("--confirmed-publish", action="store_true")
    hosted_run.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    hosted_run.add_argument("--openai-model", default="gpt-image-1")
    hosted_run.add_argument("--accent-color", default="#0F766E")
    hosted_run.add_argument("--layout-style", choices=LAYOUT_STYLE_CHOICES, default="auto")
    hosted_run.add_argument("--input-format", choices=INPUT_FORMAT_CHOICES, default="auto")
    hosted_run.set_defaults(func=cmd_hosted_run)

    ideate = subparsers.add_parser("ideate", help="兼容模式入口：保存选题元信息到工作目录")
    ideate.add_argument("--workspace")
    ideate.add_argument("--topic", required=True)
    ideate.add_argument("--direction", default="")
    ideate.add_argument("--audience", default="大众读者")
    ideate.add_argument("--goal", default="公众号爆款图文")
    ideate.add_argument("--score-threshold", type=int, default=legacy.DEFAULT_THRESHOLD)
    ideate.add_argument("--source-url", action="append", default=[])
    ideate.add_argument("--title", action="append", default=[])
    ideate.add_argument("--selected-title")
    ideate.add_argument("--outline-file")
    ideate.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    ideate.add_argument("--image-style-mode", choices=["uniform", "mixed-by-type"])
    ideate.add_argument("--image-preset-cover", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    ideate.add_argument("--image-preset-infographic", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    ideate.add_argument("--image-preset-inline", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    ideate.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default="balanced")
    ideate.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    ideate.add_argument("--image-theme")
    ideate.add_argument("--image-style")
    ideate.add_argument("--image-type")
    ideate.add_argument("--image-mood")
    ideate.add_argument("--custom-visual-brief")
    ideate.add_argument("--publish-intent", action="store_true")
    ideate.set_defaults(func=cmd_ideate)

    draft = subparsers.add_parser("draft", help="兼容模式入口：把现成 Markdown 落盘为 article.md")
    draft.add_argument("--workspace", required=True)
    draft.add_argument("--input", required=True)
    draft.add_argument("--selected-title")
    draft.add_argument("--summary")
    draft.add_argument("--author")
    draft.set_defaults(func=cmd_draft)

    score = subparsers.add_parser("score", help="运行启发式 lint + score，并在低分时生成改写候选")
    score.add_argument("--workspace", required=True)
    score.add_argument("--input")
    score.add_argument("--threshold", type=int)
    score.add_argument("--fail-below", action="store_true")
    score.add_argument("--no-rewrite", action="store_true")
    score.add_argument("--rewrite-output")
    score.add_argument("--style-sample", action="append", default=[], help="可选：提供高表现文章/风格样本文件路径（可重复）")
    score.set_defaults(func=cmd_score)

    plan_images = subparsers.add_parser("plan-images", help="按章节权重生成 image-plan.json")
    plan_images.add_argument("--workspace", required=True)
    plan_images.add_argument("--provider", choices=["gemini-web", "gemini-api", "openai-image"])
    plan_images.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    plan_images.add_argument("--image-style-mode", choices=["uniform", "mixed-by-type"])
    plan_images.add_argument("--image-preset-cover", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    plan_images.add_argument("--image-preset-infographic", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    plan_images.add_argument("--image-preset-inline", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    plan_images.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default="balanced")
    plan_images.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    plan_images.add_argument("--image-theme")
    plan_images.add_argument("--image-style")
    plan_images.add_argument("--image-type")
    plan_images.add_argument("--image-mood")
    plan_images.add_argument("--custom-visual-brief")
    plan_images.add_argument("--inline-count", type=int, default=0)
    plan_images.set_defaults(func=legacy_plan_images)

    generate_images = subparsers.add_parser("generate-images", help="执行 image-plan.json 中的图片生成")
    generate_images.add_argument("--workspace", required=True)
    generate_images.add_argument("--provider", choices=["gemini-web", "gemini-api", "openai-image"])
    generate_images.add_argument("--dry-run", action="store_true")
    generate_images.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    generate_images.add_argument("--openai-model", default="gpt-image-1")
    generate_images.set_defaults(func=legacy_generate_images)

    assemble = subparsers.add_parser("assemble", help="把图片插回 Markdown，生成 assembled.md")
    assemble.add_argument("--workspace", required=True)
    assemble.set_defaults(func=legacy_assemble)

    render = subparsers.add_parser("render", help="渲染 article.html 和 article.wechat.html")
    render.add_argument("--workspace", required=True)
    render.add_argument("--input")
    render.add_argument("--output", default="article.html")
    render.add_argument("--accent-color", default="#0F766E")
    render.add_argument("--layout-style", choices=LAYOUT_STYLE_CHOICES, default="auto")
    render.add_argument("--input-format", choices=INPUT_FORMAT_CHOICES, default="auto")
    render.add_argument("--wechat-header-mode", choices=WECHAT_HEADER_MODE_CHOICES, default="drop-title")
    render.set_defaults(func=legacy_render)

    publish = subparsers.add_parser("publish", help="发布到微信公众号草稿箱；正式发布需显式确认")
    publish.add_argument("--workspace", required=True)
    publish.add_argument("--input")
    publish.add_argument("--digest")
    publish.add_argument("--author")
    publish.add_argument("--cover")
    publish.add_argument("--dry-run", action="store_true")
    publish.add_argument("--confirmed-publish", action="store_true")
    publish.set_defaults(func=cmd_publish)

    verify_draft = subparsers.add_parser("verify-draft", help="回读草稿箱内容，校验图片与 thumb_media_id")
    verify_draft.add_argument("--workspace", required=True)
    verify_draft.add_argument("--media-id")
    verify_draft.set_defaults(func=cmd_verify_draft)

    doctor = subparsers.add_parser("doctor", help="检查 Python、文本 provider、图片 provider、微信凭证")
    doctor.add_argument("--workspace")
    doctor.set_defaults(func=cmd_doctor)

    consent = subparsers.add_parser("consent", help="管理 gemini-web 的显式同意状态")
    consent.add_argument("--accept", action="store_true")
    consent.add_argument("--revoke", action="store_true")
    consent.set_defaults(func=cmd_consent)

    all_cmd = subparsers.add_parser("all", help="兼容别名：等价于 run")
    all_cmd.add_argument("--workspace", required=True)
    all_cmd.add_argument("--provider", choices=["gemini-web", "gemini-api", "openai-image"])
    all_cmd.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    all_cmd.add_argument("--image-style-mode", choices=["uniform", "mixed-by-type"])
    all_cmd.add_argument("--image-preset-cover", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    all_cmd.add_argument("--image-preset-infographic", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    all_cmd.add_argument("--image-preset-inline", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    all_cmd.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default="balanced")
    all_cmd.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    all_cmd.add_argument("--image-theme")
    all_cmd.add_argument("--image-style")
    all_cmd.add_argument("--image-type")
    all_cmd.add_argument("--image-mood")
    all_cmd.add_argument("--custom-visual-brief")
    all_cmd.add_argument("--inline-count", type=int, default=0)
    all_cmd.add_argument("--threshold", type=int)
    all_cmd.add_argument("--content-mode", choices=CONTENT_MODE_CHOICES, default="tech-balanced")
    all_cmd.add_argument("--wechat-header-mode", choices=WECHAT_HEADER_MODE_CHOICES, default="drop-title")
    all_cmd.add_argument("--dry-run-images", action="store_true")
    all_cmd.add_argument("--publish", action="store_true")
    all_cmd.add_argument("--dry-run-publish", action="store_true")
    all_cmd.add_argument("--confirmed-publish", action="store_true")
    all_cmd.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    all_cmd.add_argument("--openai-model", default="gpt-image-1")
    all_cmd.add_argument("--accent-color", default="#0F766E")
    all_cmd.add_argument("--layout-style", choices=LAYOUT_STYLE_CHOICES, default="auto")
    all_cmd.add_argument("--input-format", choices=INPUT_FORMAT_CHOICES, default="auto")
    all_cmd.set_defaults(func=cmd_all)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))
