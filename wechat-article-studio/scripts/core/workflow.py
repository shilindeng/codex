from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
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
from core.acceptance import build_acceptance_report, markdown_acceptance_report
from core.account_strategy import load_account_strategy, research_requirements_status
from core.analysis_11d import build_analysis_11d, build_analysis_11d_report_payload, list_batch_workspaces, markdown_analysis_11d_report, score_analysis_11d
from core.ai_fingerprint import summarize_ai_fingerprints
from core.author_memory import (
    append_lesson_payload,
    build_author_memory_bundle,
    build_playbook_payload,
    compute_edit_lesson_payload,
    write_playbook_artifacts,
)
from core.content_fingerprint import (
    build_article_fingerprint,
    build_outline_fingerprint,
    load_batch_article_items,
    load_fingerprint,
    summarize_batch_collisions,
    summarize_collisions,
)
from core.content_enhancement import (
    build_content_enhancement,
    enhancement_strategy_for_archetype,
    load_content_enhancement,
    write_content_enhancement_artifacts,
)
from core.delivery_report import build_delivery_report, markdown_delivery_report
from core.viral_pipeline import (
    PLATFORM_CHOICES as VIRAL_PLATFORM_CHOICES,
    analyze_source_corpus,
    apply_source_similarity_gate,
    build_source_similarity_report,
    collect_source_corpus,
    discover_viral_candidates,
    markdown_discovery_report,
    markdown_similarity_report,
    markdown_viral_dna_report,
    select_viral_candidates,
    write_discovery_artifacts,
    write_platform_versions,
    write_research_from_viral_analysis,
    write_similarity_artifacts,
    write_source_corpus_artifacts,
)
from core.editorial_anchor import build_editorial_anchor_plan, write_editorial_anchor_artifacts
from core.generation_strategy import build_generation_strategy, ensure_batch_guidance
from core.images import cmd_assemble as legacy_assemble
from core.images import cmd_generate_images as legacy_generate_images
from core.images import cmd_plan_images as legacy_plan_images
from core.layout import INPUT_FORMAT_CHOICES, LAYOUT_STYLE_CHOICES
from core.humanizerai import HumanizerAIClient
from core.layout_skin import LAYOUT_SKIN_CHOICES, normalize_layout_skin_request
from core.layout_plan import build_layout_plan, markdown_layout_plan
from core.manifest import MANIFEST_STATUS_DEFAULTS, ensure_workspace, load_manifest, save_manifest, update_stage, workspace_path
from core.persona import normalize_writing_persona
from core.pipeline_readiness import (
    artifact_contract_report,
    compute_pipeline_readiness,
    has_score_dimension as readiness_has_score_dimension,
    score_dimension_value as readiness_score_dimension_value,
)
from core.quality_gates import build_final_gate, build_reader_gate, build_visual_gate, collect_gate_publish_blockers
from core.batch_review import build_batch_review_payload, markdown_batch_review
from core.publication import (
    apply_reference_policy as publication_apply_reference_policy,
    build_references_payload as publication_build_references_payload,
    normalize_publication_body as publication_normalize_publication_body,
)
from core.publication_cleanup import expand_compact_markdown_lists, strip_ai_label_phrases
from core.quality_checks import build_article_summary, metadata_integrity_report, split_markdown_paragraphs, workspace_batch_key
from core.quality_checks import cost_signal_present, discussion_trigger_present, lead_paragraph_count
from core.editorial_strategy import (
    generate_diverse_title_variants,
    heading_pattern_key,
    normalize_editorial_blueprint,
    opening_pattern_key,
    summarize_recent_corpus,
    title_template_key,
)
from core.render import cmd_render as legacy_render, prepare_publication_artifacts as render_prepare_publication_artifacts
from core.rewrite import generate_revision_candidate
from core.viral import (
    DEFAULT_THRESHOLD as VIRAL_SCORE_THRESHOLD,
    _ai_smell_findings as generation_ai_smell_findings,
    _depth_signals as generation_depth_signals,
    _template_findings as generation_template_findings,
    build_heuristic_review,
    blueprint_complete,
    default_viral_blueprint,
    markdown_review_report,
    normalize_outline_payload,
    normalize_review_payload,
    normalize_viral_blueprint,
    recompute_score_outcome,
)
from core.title_decision import build_title_decision_report, markdown_title_decision_report, title_integrity_report
from providers.text.gemini_web import GeminiWebTextProvider
from providers.text.openai_compatible import OpenAICompatibleTextProvider, placeholder_article, placeholder_outline
from publishers.wechat import cmd_publish as wechat_publish
from publishers.wechat import cmd_verify_draft as wechat_verify_draft

PUBLISH_MIN_CREDIBILITY_SCORE = 6
CONTENT_MODE_CHOICES = ("tech-balanced", "tech-credible", "viral")
WECHAT_HEADER_MODE_CHOICES = ("keep", "drop-title", "drop-title-summary")
RECENT_CORPUS_LIMIT = 20
PIPELINE_SCHEMA_VERSION = "2026-04-v3"
IMAGE_PROVIDER_CHOICES = legacy.IMAGE_PROVIDER_CHOICES
KNOWN_TEMPLATE_PHRASES = [
    "这很正常，你不是一个人",
    "最难受的是",
    "真正值得带走的判断只有一个",
    "如果你最近",
    "别急着把",
    "说白了",
    "以后真正靠谱的 AI，可能不是",
]
_CORPUS_CONTEXT_CACHE: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
_AUTHOR_MEMORY_CACHE: dict[
    tuple[
        str,
        tuple[tuple[str, int], ...],
        tuple[tuple[str, int], ...],
        tuple[tuple[str, int], ...],
    ],
    dict[str, Any],
] = {}
VIRAL_QUERY_RESET_PATHS = [
    "research.json",
    "viral-discovery.json",
    "viral-discovery.md",
    "source-corpus.json",
    "viral-dna.json",
    "viral-dna.md",
    "ideation.json",
    "article.md",
    "title-report.json",
    "title-report.md",
    "title-decision-report.json",
    "title-decision-report.md",
    "content-enhancement.json",
    "content-enhancement.md",
    "editorial-anchor-plan.json",
    "editorial-anchor-plan.md",
    "review-report.json",
    "review-report.md",
    "score-report.json",
    "score-report.md",
    "content-fingerprint.json",
    "layout-plan.json",
    "layout-plan.md",
    "acceptance-report.json",
    "acceptance-report.md",
    "similarity-report.json",
    "similarity-report.md",
    "image-plan.json",
    "image-outline.json",
    "image-outline.md",
    "assembled.md",
    "article.html",
    "article.wechat.html",
    "publish-result.json",
    "latest-draft-report.json",
    "versions",
]


def normalize_content_mode(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in CONTENT_MODE_CHOICES else "tech-balanced"


def normalize_wechat_header_mode(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in WECHAT_HEADER_MODE_CHOICES else "drop-title"


def normalize_layout_style_preference(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    return normalized if normalized in LAYOUT_STYLE_CHOICES else "auto"


def persist_runtime_preferences(manifest: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    manifest["content_mode"] = normalize_content_mode(getattr(args, "content_mode", None) or manifest.get("content_mode"))
    manifest["wechat_header_mode"] = normalize_wechat_header_mode(
        getattr(args, "wechat_header_mode", None) or manifest.get("wechat_header_mode")
    )
    requested_style = getattr(args, "layout_style", None)
    if requested_style is None:
        requested_style = manifest.get("layout_style_preference")
    manifest["layout_style_preference"] = normalize_layout_style_preference(requested_style)
    requested_skin = getattr(args, "layout_skin", None)
    if requested_skin is None:
        requested_skin = manifest.get("layout_skin_preference")
    manifest["layout_skin_preference"] = normalize_layout_skin_request(requested_skin)
    return manifest


def attach_account_strategy(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    strategy = load_account_strategy(workspace, manifest, create_if_missing=True)
    manifest.setdefault("audience", strategy.get("target_reader_label") or "泛科技读者")
    controls = dict(manifest.get("image_controls") or {})
    density_mode = legacy.normalize_image_density_mode(controls.get("density_mode") or controls.get("density") or strategy.get("image_density") or "auto")
    controls.setdefault("density_mode", density_mode)
    controls["density"] = density_mode
    controls.setdefault("allow_closing_image", "auto")
    manifest["image_controls"] = controls
    return manifest


def _normalize_title_value(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def _selected_title_truth(workspace: Path, manifest: dict[str, Any]) -> str:
    candidates = [
        manifest.get("selected_title"),
        (read_json(workspace / "title-decision-report.json", default={}) or {}).get("selected_title"),
        (read_json(workspace / "title-report.json", default={}) or {}).get("selected_title"),
        (read_json(workspace / "ideation.json", default={}) or {}).get("selected_title"),
    ]
    for item in candidates:
        if _normalize_title_value(str(item or "")):
            return str(item).strip()
    return ""


def sync_title_truth(workspace: Path, manifest: dict[str, Any], selected_title: str) -> None:
    title_value = str(selected_title or "").strip()
    if not title_value:
        return
    manifest["selected_title"] = title_value
    ideation = read_json(workspace / "ideation.json", default={}) or {}
    if ideation:
        ideation["selected_title"] = title_value
        write_json(workspace / "ideation.json", ideation)
    title_report = read_json(workspace / "title-report.json", default={}) or {}
    if title_report:
        title_report["selected_title"] = title_value
        write_json(workspace / "title-report.json", title_report)
    decision_report = read_json(workspace / "title-decision-report.json", default={}) or {}
    if decision_report:
        decision_report["selected_title"] = title_value
        write_json(workspace / "title-decision-report.json", decision_report)


def collect_title_consistency_issues(workspace: Path, manifest: dict[str, Any]) -> list[str]:
    expected = _selected_title_truth(workspace, manifest)
    if not expected:
        return []
    normalized_expected = _normalize_title_value(expected)
    sources = {
        "manifest.json": manifest.get("selected_title"),
        "ideation.json": (read_json(workspace / "ideation.json", default={}) or {}).get("selected_title"),
        "title-report.json": (read_json(workspace / "title-report.json", default={}) or {}).get("selected_title"),
        "title-decision-report.json": (read_json(workspace / "title-decision-report.json", default={}) or {}).get("selected_title"),
    }
    article_path = workspace / str(manifest.get("article_path") or "article.md")
    if article_path.exists():
        meta, _ = split_frontmatter(read_text(article_path))
        sources["article.md"] = meta.get("title") or ""
    issues: list[str] = []
    for source_name, raw in sources.items():
        value = str(raw or "").strip()
        if value and _normalize_title_value(value) != normalized_expected:
            issues.append(f"{source_name} 标题与当前真源不一致：{value}")
    return issues


def collect_state_consistency_issues(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    score_report: dict[str, Any] | None = None,
    acceptance_report: dict[str, Any] | None = None,
) -> list[str]:
    issues: list[str] = []
    score_report = score_report or (read_json(workspace / "score-report.json", default={}) or {})
    acceptance_report = acceptance_report or (read_json(workspace / "acceptance-report.json", default={}) or {})
    manifest_title = str(manifest.get("selected_title") or "").strip()
    if score_report:
        report_title = str(score_report.get("title") or "").strip()
        if manifest_title and report_title and manifest_title != report_title:
            issues.append("manifest.json 与 score-report.json 的标题不一致。")
        if "score_passed" in manifest and score_report.get("passed") not in (None, "") and bool(manifest.get("score_passed")) != bool(score_report.get("passed")):
            issues.append("manifest.json 与 score-report.json 的 passed 状态不一致。")
        if str(manifest.get("stage") or "") in {"initialized", "title", "outline", "draft", "review"}:
            issues.append("score-report.json 已存在，但 manifest.stage 仍停在前置阶段。")
    if acceptance_report:
        acceptance_title = str(acceptance_report.get("title") or "").strip()
        if manifest_title and acceptance_title and manifest_title != acceptance_title:
            issues.append("manifest.json 与 acceptance-report.json 的标题不一致。")
        if "acceptance_passed" in manifest and acceptance_report.get("passed") not in (None, "") and bool(manifest.get("acceptance_passed")) != bool(acceptance_report.get("passed")):
            issues.append("manifest.json 与 acceptance-report.json 的 passed 状态不一致。")
        if str(manifest.get("stage") or "") in {"initialized", "title", "outline", "draft", "review"}:
            issues.append("acceptance-report.json 已存在，但 manifest.stage 仍停在前置阶段。")
    publish_result = read_json(workspace / "publish-result.json", default={}) or {}
    if publish_result and str(manifest.get("stage") or "") not in {"publish", "verify"}:
        issues.append("publish-result.json 已存在，但 manifest.stage 不是 publish/verify。")
    deduped: list[str] = []
    for item in issues:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _update_manifest_quality_status(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    title: str,
    summary: str,
    body: str,
    review: dict[str, Any] | None = None,
    layout_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = metadata_integrity_report(title, summary)
    manifest["metadata_integrity_status"] = metadata.get("status") or "failed"
    manifest["metadata_integrity_reasons"] = list(metadata.get("reasons") or [])
    batch_key = workspace_batch_key(workspace)
    manifest["batch_key"] = batch_key
    fingerprint = build_article_fingerprint(
        title,
        body,
        manifest | {"summary": summary, "workspace": str(workspace.resolve())},
        review=review,
        layout_plan=layout_plan or {},
    )
    batch_report = summarize_batch_collisions(
        fingerprint,
        current_title=title,
        current_body=body,
        batch_items=load_batch_article_items(workspace),
        threshold=0.62,
        title_threshold=0.72,
    )
    manifest["batch_uniqueness_status"] = "passed" if batch_report.get("passed", True) else "failed"
    manifest["batch_uniqueness_reasons"] = [
        f"{item.get('title') or item.get('workspace')}: {', '.join(item.get('matched_rules') or [])}"
        for item in (batch_report.get("batch_similar_items") or [])
    ]
    return {"metadata": metadata, "batch": batch_report, "fingerprint": fingerprint}


def research_requirements_report(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    existing = manifest.get("research_requirements")
    if isinstance(existing, dict) and existing:
        return existing
    strategy = load_account_strategy(workspace, manifest, create_if_missing=True)
    research = load_research(workspace)
    report = research_requirements_status(research, manifest, strategy)
    return report


def _update_research_requirements(workspace: Path, manifest: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    strategy = load_account_strategy(workspace, manifest, create_if_missing=True)
    report = research_requirements_status(payload, manifest, strategy)
    payload["minimum_requirements"] = report
    manifest["research_requirements"] = report
    return report


def collect_render_blockers(workspace: Path, manifest: dict[str, Any], score_report: dict[str, Any] | None = None) -> list[str]:
    readiness = build_pipeline_readiness(workspace, manifest, score_report=score_report)
    return list(readiness.get("render_blockers") or [])


def _load_current_article_signature(workspace: Path, manifest: dict[str, Any]) -> str:
    article_path = workspace / str(manifest.get("article_path") or "article.md")
    if not article_path.exists():
        return ""
    meta, body = split_frontmatter(read_text(article_path))
    title = str(manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "").strip()
    return article_body_signature(title, body)


def _stale_report_blockers(workspace: Path, manifest: dict[str, Any]) -> list[str]:
    current_signature = _load_current_article_signature(workspace, manifest)
    if not current_signature:
        return []
    blockers: list[str] = []
    for name in ["review-report.json", "score-report.json", "acceptance-report.json"]:
        payload = read_json(workspace / name, default={}) or {}
        signature = str(payload.get("body_signature") or "").strip()
        if payload and signature and signature != current_signature:
            blockers.append(f"{name} 基于旧正文生成，需要重新生成。")
    return blockers


def build_pipeline_readiness(workspace: Path, manifest: dict[str, Any], *, score_report: dict[str, Any] | None = None, acceptance_report: dict[str, Any] | None = None) -> dict[str, Any]:
    stale_blockers = _stale_report_blockers(workspace, manifest)
    title_blockers = collect_title_consistency_issues(workspace, manifest)
    similarity_blockers = _similarity_blockers(workspace)
    consistency_blockers = collect_state_consistency_issues(workspace, manifest, score_report=score_report, acceptance_report=acceptance_report)
    research_report = research_requirements_report(workspace, manifest)
    report = score_report or (read_json(workspace / "score-report.json", default={}) or {})
    acceptance = acceptance_report or (read_json(workspace / "acceptance-report.json", default={}) or {})
    contract_report = artifact_contract_report(
        workspace,
        manifest,
        score_report=report,
        acceptance_report=acceptance,
    )
    readiness = compute_pipeline_readiness(
        report=report,
        acceptance=acceptance,
        research_report=research_report,
        placeholder_issues=placeholder_reasons(workspace, manifest),
        stale_blockers=stale_blockers,
        consistency_blockers=consistency_blockers,
        title_blockers=title_blockers,
        similarity_blockers=similarity_blockers,
        contract_report=contract_report,
        publish_result_exists=bool(read_json(workspace / "publish-result.json", default={}) or {}),
        min_credibility_score=PUBLISH_MIN_CREDIBILITY_SCORE,
    )
    gate_blockers = collect_gate_publish_blockers(workspace, manifest)
    if gate_blockers:
        merged = list(readiness.get("publish_blockers") or [])
        for item in gate_blockers:
            if item not in merged:
                merged.append(item)
        readiness["publish_blockers"] = merged
        readiness["publish_ready"] = False
    return readiness


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
    if getattr(provider, "provider_name", "") == "gemini-web":
        raise SystemExit(
            f"{command_name} 需要可复用的 gemini-web 登录态。"
            " 请先完成一次 gemini-web 登录，或显式提供 GEMINI_WEB_COOKIE_PATH / GEMINI_WEB_COOKIE。"
        )
    raise SystemExit(
        f"{command_name} 需要已配置的文本 provider。"
        " 请设置 OPENAI_API_KEY 和 ARTICLE_STUDIO_TEXT_MODEL，"
        " 或改用 hosted-run 并先提供 article.md / --article-file。"
    )


def score_dimension_value(report: dict[str, Any], dimension: str) -> int:
    return readiness_score_dimension_value(report, dimension)


def has_score_dimension(report: dict[str, Any], dimension: str) -> bool:
    return readiness_has_score_dimension(report, dimension)


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
    research_requirements = research_requirements_report(workspace, manifest)
    if research_requirements.get("requires_evidence") and not research_requirements.get("passed"):
        reasons.append(f"调研门槛未通过：{'；'.join(research_requirements.get('reasons') or [])}")
    return reasons


def collect_publish_blockers(workspace: Path, manifest: dict[str, Any]) -> list[str]:
    readiness = build_pipeline_readiness(workspace, manifest)
    return list(readiness.get("publish_blockers") or [])


def assert_publish_request_ready(args: argparse.Namespace) -> None:
    if getattr(args, "to", None) != "publish":
        return
    if not getattr(args, "dry_run_publish", False) and not getattr(args, "confirmed_publish", False):
        raise SystemExit("进入正式发布前必须显式传入 --confirmed-publish；未确认时不会写入 publish_intent。")
    if getattr(args, "force_publish", False):
        raise SystemExit("run/hosted-run/viral-run 自动流程不允许 --force-publish；如确需人工应急，请单独运行 publish 并写明 --force-reason。")


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


def detect_corpus_roots(workspace: Path) -> list[Path]:
    candidates: list[Path] = []
    env_roots = [
        (legacy.os.getenv("WECHAT_JOBS_ROOT") or "").strip(),
        (legacy.os.getenv("CODEX_WECHAT_JOBS_ROOT") or "").strip(),
    ]
    for env_root in env_roots:
        if not env_root:
            continue
        for raw in re.split(r"[;,]", env_root):
            item = raw.strip()
            if item:
                candidates.append(Path(item).expanduser())
    parent = workspace
    for _index in range(4):
        parent = parent.parent
        candidates.extend(
            [
                parent / ".wechat-jobs",
                parent / "wechat-jobs",
            ]
        )
    seen: set[str] = set()
    roots: list[Path] = []
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        if resolved.exists() and resolved.is_dir():
            roots.append(resolved)
    return roots


def _normalize_phrase(text: str) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    compact = compact.strip(" -•>\"'“”‘’")
    return compact


def article_body_signature(title: str, body: str) -> str:
    digest = hashlib.sha1()
    digest.update(str(title or "").strip().encode("utf-8"))
    digest.update(b"\n---\n")
    digest.update(str(body or "").strip().encode("utf-8"))
    return digest.hexdigest()


def _existing_path_signature(paths: list[str]) -> tuple[tuple[str, int], ...]:
    signature: list[tuple[str, int]] = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            continue
        try:
            resolved = path.resolve()
            signature.append((str(resolved), int(resolved.stat().st_mtime_ns)))
        except OSError:
            continue
    return tuple(signature)


def recent_article_paths(corpus_roots: list[Path], current_workspace: Path, limit: int = RECENT_CORPUS_LIMIT) -> list[Path]:
    if not corpus_roots:
        return []
    try:
        current_workspace_key = str(current_workspace.resolve())
    except OSError:
        current_workspace_key = str(current_workspace)
    roots_key: list[str] = []
    for root in corpus_roots:
        try:
            roots_key.append(str(root.resolve()))
        except OSError:
            roots_key.append(str(root))
    return [Path(item) for item in _recent_article_paths_cached(tuple(roots_key), current_workspace_key, int(limit))]


@lru_cache(maxsize=8)
def _recent_article_paths_cached(corpus_roots: tuple[str, ...], current_workspace: str, limit: int) -> tuple[str, ...]:
    if not corpus_roots:
        return ()
    current_workspace_path = Path(current_workspace)
    articles: list[Path] = []
    seen: set[str] = set()
    for corpus_root in corpus_roots:
        for path in Path(corpus_root).rglob("article.md"):
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if current_workspace_path in resolved.parents:
                continue
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            articles.append(resolved)
    articles.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    return tuple(str(item) for item in articles[:limit])


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


def collect_recent_fingerprints(workspace: Path, manifest: dict[str, Any], limit: int = RECENT_CORPUS_LIMIT) -> list[dict[str, Any]]:
    fingerprints: list[dict[str, Any]] = []
    for article_path in recent_article_paths(detect_corpus_roots(workspace), workspace, limit=limit):
        fingerprint_path = article_path.parent / "content-fingerprint.json"
        if fingerprint_path.exists():
            payload = load_fingerprint(fingerprint_path)
            if payload:
                fingerprints.append(payload)
                continue
        try:
            raw = read_text(article_path)
        except OSError:
            continue
        other_manifest = read_json(article_path.parent / "manifest.json", default={}) or {}
        other_review = read_json(article_path.parent / "review-report.json", default={}) or {}
        other_layout_plan = read_json(article_path.parent / "layout-plan.json", default={}) or {}
        meta, other_body = split_frontmatter(raw)
        other_title = (
            other_manifest.get("selected_title")
            or meta.get("title")
            or legacy.extract_title_from_body(other_body)
            or article_path.parent.name
        )
        fingerprints.append(
            build_article_fingerprint(
                str(other_title),
                other_body,
                other_manifest,
                review=other_review,
                blueprint=other_manifest.get("viral_blueprint") or {},
                layout_plan=other_layout_plan,
            )
        )
    return fingerprints


def attach_corpus_context(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    corpus_roots = detect_corpus_roots(workspace)
    if not corpus_roots:
        manifest["corpus_root"] = ""
        manifest["corpus_roots"] = []
        manifest["recent_phrase_blacklist"] = []
        manifest["recent_article_titles"] = []
        manifest["recent_corpus_summary"] = {}
        return manifest
    workspace_key = str(workspace.resolve())
    roots_key = tuple(str(item.resolve()) for item in corpus_roots)
    cache_key = (workspace_key, roots_key)
    cached = _CORPUS_CONTEXT_CACHE.get(cache_key)
    if cached:
        manifest.update(copy.deepcopy(cached))
        return manifest
    article_paths = recent_article_paths(corpus_roots, workspace)
    titles: list[str] = []
    for path in article_paths[:8]:
        try:
            raw = read_text(path)
            meta, body = split_frontmatter(raw)
            title = meta.get("title") or legacy.extract_title_from_body(body) or path.parent.name
        except OSError:
            title = path.parent.name
        titles.append(str(title))
    payload = {
        "corpus_root": str(corpus_roots[0]),
        "corpus_roots": [str(item) for item in corpus_roots],
        "recent_phrase_blacklist": collect_recent_phrase_blacklist(article_paths),
        "recent_article_titles": titles,
        "recent_corpus_summary": summarize_recent_corpus(article_paths),
    }
    _CORPUS_CONTEXT_CACHE[cache_key] = copy.deepcopy(payload)
    manifest.update(payload)
    return manifest


def attach_author_memory(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    workspace_key = str(workspace.resolve())
    sample_paths = _existing_path_signature(list(manifest.get("style_sample_paths") or []))
    playbook_paths = _existing_path_signature(list(manifest.get("author_playbook_paths") or []))
    lesson_paths = _existing_path_signature(list(manifest.get("author_lesson_paths") or []))
    cache_key = (workspace_key, sample_paths, playbook_paths, lesson_paths)
    cached = _AUTHOR_MEMORY_CACHE.get(cache_key)
    if cached:
        bundle = copy.deepcopy(cached)
    else:
        bundle = build_author_memory_bundle(workspace, manifest)
        _AUTHOR_MEMORY_CACHE[cache_key] = copy.deepcopy(bundle)
    manifest["author_memory"] = bundle
    manifest["author_playbook_paths"] = bundle.get("playbook_paths") or []
    manifest["author_lesson_paths"] = bundle.get("lesson_paths") or []
    manifest["author_playbook_summary"] = bundle.get("playbook_summary") or []
    manifest["author_voice_fingerprint"] = bundle.get("voice_fingerprint") or []
    manifest["author_phrase_blacklist"] = bundle.get("phrase_blacklist") or []
    manifest["author_sentence_starters_to_avoid"] = bundle.get("sentence_starters_to_avoid") or []
    manifest["author_lesson_patterns"] = bundle.get("lesson_patterns") or []
    manifest["author_lesson_rules"] = bundle.get("lesson_rules") or []
    manifest["author_hard_rules"] = bundle.get("hard_rules") or []
    manifest["author_soft_rules"] = bundle.get("soft_rules") or []
    manifest["author_example_snippets"] = bundle.get("example_snippets") or []
    return manifest


def write_content_fingerprint_artifact(
    workspace: Path,
    title: str,
    body: str,
    manifest: dict[str, Any],
    *,
    review: dict[str, Any] | None = None,
    layout_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_article_fingerprint(
        title,
        body,
        manifest,
        review=review,
        blueprint=manifest.get("viral_blueprint") or {},
        layout_plan=layout_plan or read_json(workspace / "layout-plan.json", default={}) or {},
    )
    write_json(workspace / "content-fingerprint.json", payload)
    manifest["content_fingerprint_path"] = "content-fingerprint.json"
    return payload


def ensure_layout_plan_artifacts(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    title: str = "",
    summary: str = "",
    ideation: dict[str, Any] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    layout_plan_path = workspace / str(manifest.get("layout_plan_path") or "layout-plan.json")
    existing = read_json(layout_plan_path, default={}) or {}
    if existing and not force:
        manifest["layout_plan_path"] = layout_plan_path.name
        return existing
    ideation = ideation or load_ideation(workspace)
    outline_meta = dict(ideation.get("outline_meta") or {})
    if not outline_meta.get("sections"):
        return existing
    title_value = title or manifest.get("selected_title") or ideation.get("selected_title") or manifest.get("topic") or "未命名标题"
    summary_value = summary
    if not summary_value:
        article_path = workspace / str(manifest.get("article_path") or "article.md")
        if article_path.exists():
            meta, body = split_frontmatter(read_text(article_path))
            summary_value = meta.get("summary") or manifest.get("summary") or extract_summary(body)
        else:
            summary_value = manifest.get("summary") or extract_summary(
                "\n".join(str(item.get("goal") or "") for item in (outline_meta.get("sections") or []))
            )
    layout_plan = build_layout_plan(
        title_value,
        summary_value,
        outline_meta,
        manifest | {"viral_blueprint": outline_meta.get("viral_blueprint") or manifest.get("viral_blueprint") or {}},
    )
    write_json(layout_plan_path, layout_plan)
    write_text(workspace / "layout-plan.md", markdown_layout_plan(layout_plan))
    manifest["layout_plan_path"] = layout_plan_path.name
    return layout_plan


def write_acceptance_artifacts(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    article_path = workspace / str(manifest.get("article_path") or "article.md")
    if not article_path.exists():
        return {}
    score_report = read_json(workspace / "score-report.json", default={}) or {}
    review_report = read_json(workspace / "review-report.json", default={}) or {}
    layout_plan = ensure_layout_plan_artifacts(workspace, manifest, force=False)
    if not score_report:
        return {}
    meta, body = split_frontmatter(read_text(article_path))
    title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名标题"
    summary = meta.get("summary") or manifest.get("summary") or extract_summary(body)
    write_content_fingerprint_artifact(workspace, title, body, manifest, review=review_report, layout_plan=layout_plan)
    recent_fingerprints = collect_recent_fingerprints(workspace, manifest)
    image_plan = read_json(workspace / str(manifest.get("image_plan_path") or "image-plan.json"), default={}) or {}
    reader_gate = build_reader_gate(
        workspace,
        manifest,
        title=title,
        summary=summary,
        body=body,
        score_report=score_report,
        review_report=review_report,
    )
    visual_gate = build_visual_gate(
        workspace,
        manifest,
        image_plan=image_plan,
    )
    payload = build_acceptance_report(
        workspace,
        manifest,
        title=title,
        summary=summary,
        body=body,
        score_report=score_report,
        review_report=review_report,
        layout_plan=layout_plan,
        recent_fingerprints=recent_fingerprints,
        reader_gate=reader_gate,
        visual_gate=visual_gate,
    )
    final_gate = build_final_gate(
        workspace,
        manifest,
        title=title,
        body=body,
        score_report=score_report,
        review_report=review_report,
        acceptance_report=payload,
        reader_gate=reader_gate,
        visual_gate=visual_gate,
    )
    write_json(workspace / "reader_gate.json", reader_gate)
    write_json(workspace / "visual_gate.json", visual_gate)
    write_json(workspace / "final_gate.json", final_gate)
    write_json(workspace / "acceptance-report.json", payload)
    write_text(workspace / "acceptance-report.md", markdown_acceptance_report(payload))
    manifest["acceptance_report_path"] = "acceptance-report.json"
    manifest["reader_gate_path"] = "reader_gate.json"
    manifest["visual_gate_path"] = "visual_gate.json"
    manifest["final_gate_path"] = "final_gate.json"
    manifest["acceptance_passed"] = bool(payload.get("passed"))
    manifest["acceptance_ready_status"] = "passed" if (payload.get("gates") or {}).get("acceptance_ready_passed") else "failed"
    manifest["reader_gate_status"] = "passed" if reader_gate.get("passed") else "failed"
    manifest["visual_gate_status"] = "passed" if visual_gate.get("passed") else "failed"
    manifest["final_gate_status"] = "passed" if final_gate.get("passed") else "failed"
    write_delivery_report(workspace, manifest)
    return payload


def write_delivery_report(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    payload = build_delivery_report(workspace, manifest)
    write_json(workspace / "final-delivery-report.json", payload)
    write_text(workspace / "final-delivery-report.md", markdown_delivery_report(payload))
    manifest["delivery_report_path"] = "final-delivery-report.json"
    manifest["delivery_report_markdown_path"] = "final-delivery-report.md"
    manifest["delivery_report_status"] = "passed" if payload.get("overall_status") == "passed" else "failed"
    return payload


def cmd_reader_gate(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace)
    article_path = workspace / str(manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到文章文件：{article_path}")
    score_report = read_json(workspace / "score-report.json", default={}) or {}
    if not score_report:
        raise SystemExit("缺少 score-report.json，请先完成评分。")
    review_report = read_json(workspace / "review-report.json", default={}) or {}
    meta, body = split_frontmatter(read_text(article_path))
    title = str(manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "").strip()
    summary = str(meta.get("summary") or manifest.get("summary") or extract_summary(body)).strip()
    payload = build_reader_gate(
        workspace,
        manifest,
        title=title,
        summary=summary,
        body=body,
        score_report=score_report,
        review_report=review_report,
    )
    write_json(workspace / "reader_gate.json", payload)
    manifest["reader_gate_path"] = "reader_gate.json"
    manifest["reader_gate_status"] = "passed" if payload.get("passed") else "failed"
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_visual_gate(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace)
    image_plan = read_json(workspace / str(manifest.get("image_plan_path") or "image-plan.json"), default={}) or {}
    payload = build_visual_gate(workspace, manifest, image_plan=image_plan)
    write_json(workspace / "visual_gate.json", payload)
    manifest["visual_gate_path"] = "visual_gate.json"
    manifest["visual_gate_status"] = "passed" if payload.get("passed") else "failed"
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_final_gate(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace)
    write_acceptance_artifacts(workspace, manifest)
    save_manifest(workspace, manifest)
    payload = read_json(workspace / "final_gate.json", default={}) or {}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_delivery_report(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace)
    payload = write_delivery_report(workspace, manifest)
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_report_11d(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace)
    article_path = workspace / str(manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到文章文件：{article_path}")
    raw = read_text(article_path)
    meta, body = split_frontmatter(raw)
    title = str(meta.get("title") or manifest.get("selected_title") or manifest.get("topic") or "未命名文章").strip()
    summary = str(meta.get("summary") or manifest.get("summary") or extract_summary(body)).strip()
    review_report = read_json(workspace / "review-report.json", default={}) or {}
    score_report = read_json(workspace / "score-report.json", default={}) or {}
    analysis_11d = (
        review_report.get("analysis_11d")
        or score_report.get("analysis_11d")
        or build_analysis_11d(
            title=title,
            body=body,
            summary=summary,
            analysis=(review_report.get("viral_analysis") or score_report.get("viral_analysis") or {}),
            depth=review_report.get("depth_signals") or score_report.get("depth_signals") or {},
            material_signals=review_report.get("material_signals") or score_report.get("material_signals") or {},
            humanness_signals=review_report.get("humanness_signals") or score_report.get("humanness_signals") or {},
        )
    )
    payload = build_analysis_11d_report_payload(
        title=title,
        analysis_11d=analysis_11d,
        scores=score_report.get("dimension_11d_scores") or [],
    )
    if not payload.get("dimension_11d_scores"):
        payload = build_analysis_11d_report_payload(
            title=title,
            analysis_11d=analysis_11d,
            scores=score_analysis_11d(analysis_11d),
        )
    write_json(workspace / "report-11d.json", payload)
    write_text(workspace / "report-11d.md", markdown_analysis_11d_report(payload))
    manifest["report_11d_path"] = "report-11d.json"
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_review_batch(args: argparse.Namespace) -> int:
    jobs_root = Path(str(args.jobs_root or "")).expanduser().resolve()
    if not jobs_root.exists():
        raise SystemExit(f"找不到批量目录：{jobs_root}")
    batch_key = str(args.batch_key or "").strip()
    if not batch_key:
        raise SystemExit("review-batch 需要传入 --batch-key。")
    payload = build_batch_review_payload(jobs_root, batch_key)
    write_json(jobs_root / "batch-review.json", payload)
    write_text(jobs_root / "batch-review.md", markdown_batch_review(payload))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_learn_performance(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace)
    article_path = workspace / str(manifest.get("article_path") or "article.md")
    title = str(manifest.get("selected_title") or manifest.get("topic") or "未命名文章").strip()
    if article_path.exists():
        meta, _body = split_frontmatter(read_text(article_path))
        title = str(meta.get("title") or title).strip()
    feedback_path = workspace / "performance-feedback.json"
    payload = read_json(feedback_path, default={}) or {}
    entries = list(payload.get("entries") or [])
    entry = {
        "title": title,
        "captured_at": now_iso(),
        "metrics_24h": {
            "read": int(getattr(args, "read_24h", 0) or 0),
            "like": int(getattr(args, "like_24h", 0) or 0),
            "share": int(getattr(args, "share_24h", 0) or 0),
            "comment": int(getattr(args, "comment_24h", 0) or 0),
            "favorite": int(getattr(args, "favorite_24h", 0) or 0),
        },
        "metrics_72h": {
            "read": int(getattr(args, "read_72h", 0) or 0),
            "like": int(getattr(args, "like_72h", 0) or 0),
            "share": int(getattr(args, "share_72h", 0) or 0),
            "comment": int(getattr(args, "comment_72h", 0) or 0),
            "favorite": int(getattr(args, "favorite_72h", 0) or 0),
        },
        "notes": str(getattr(args, "notes", "") or "").strip(),
    }
    entries.append(entry)
    payload["entries"] = entries
    payload["updated_at"] = now_iso()
    write_json(feedback_path, payload)
    manifest["performance_feedback_path"] = "performance-feedback.json"
    save_manifest(workspace, manifest)
    notes = entry["notes"]
    if notes:
        playbook_path = workspace / "performance-playbook.json"
        playbook = read_json(playbook_path, default={}) or {}
        learnings = list(playbook.get("recent_learnings") or [])
        learnings.append({"title": title, "captured_at": entry["captured_at"], "note": notes})
        playbook["recent_learnings"] = learnings[-50:]
        playbook["updated_at"] = now_iso()
        write_json(playbook_path, playbook)
    print(json.dumps(entry, ensure_ascii=False, indent=2))
    return 0


def topic_keyword_tokens(value: str) -> list[str]:
    stop = {
        "今天",
        "最近",
        "这次",
        "真正",
        "为什么",
        "如何",
        "什么",
        "事情",
        "问题",
        "方法",
        "工具",
        "产品",
        "系统",
        "平台",
        "一次",
        "一个",
        "这个",
        "那个",
        "我们",
        "你们",
        "他们",
    }
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9\.-]{1,}|[\u4e00-\u9fff]{2,8}", value or "")
    output: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        cleaned = str(token).strip()
        lowered = cleaned.lower()
        if not cleaned or lowered in seen or cleaned in stop or len(cleaned) < 2:
            continue
        seen.add(lowered)
        output.append(cleaned)
        if re.fullmatch(r"[\u4e00-\u9fff]{5,8}", cleaned):
            for index in range(0, len(cleaned) - 1):
                sub = cleaned[index : index + 2]
                lowered_sub = sub.lower()
                if sub in stop or lowered_sub in seen:
                    continue
                seen.add(lowered_sub)
                output.append(sub)
                if len(output) >= 8:
                    return output[:8]
    return output[:8]


@lru_cache(maxsize=64)
def _load_json_payload_cached(path_value: str, mtime_ns: int) -> Any:
    return read_json(Path(path_value), default={}) or {}


def _load_json_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        resolved = path.resolve()
        mtime_ns = resolved.stat().st_mtime_ns
    except OSError:
        return read_json(path, default={}) or {}
    payload = _load_json_payload_cached(str(resolved), mtime_ns)
    return copy.deepcopy(payload) if isinstance(payload, dict) else {}


def rerank_discovery_candidates(
    candidates: list[dict[str, Any]],
    recent_titles: list[str],
    recent_corpus_summary: dict[str, Any],
    author_memory: dict[str, Any],
    account_strategy: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    strategy = account_strategy or {}
    title_patterns = {str(item.get("key") or "") for item in (recent_corpus_summary.get("overused_title_patterns") or []) if item.get("key")}
    recent_token_counter: Counter[str] = Counter()
    for title in recent_titles:
        for token in topic_keyword_tokens(title):
            recent_token_counter[token.lower()] += 1

    preferred_styles = {
        str(item).strip().lower()
        for item in ((author_memory.get("editorial_preferences") or {}).get("preferred_style_keys") or [])
        if str(item).strip()
    }
    starter_blacklist = {str(item).strip() for item in (author_memory.get("sentence_starters_to_avoid") or []) if str(item).strip()}
    priority_keywords = {str(item).strip() for item in (strategy.get("discovery_priority_keywords") or []) if str(item).strip()}
    deprioritize_keywords = {str(item).strip() for item in (strategy.get("discovery_deprioritize_keywords") or []) if str(item).strip()}

    reranked: list[dict[str, Any]] = []
    for candidate in candidates:
        item = dict(candidate)
        topic = str(item.get("recommended_topic") or item.get("hot_title") or "")
        title = str(item.get("recommended_title") or topic)
        content_kind = str(item.get("content_kind") or "")
        corpus = " ".join(
            [
                topic,
                title,
                " ".join(str(raw).strip() for raw in (item.get("angles") or []) if str(raw).strip()),
                " ".join(str(raw).strip() for raw in (item.get("viewpoints") or []) if str(raw).strip()),
            ]
        )
        candidate_tokens = topic_keyword_tokens(topic)
        repeat_hits = [token for token in candidate_tokens if recent_token_counter.get(token.lower(), 0) > 0]
        repeat_penalty = min(8, sum(min(2, recent_token_counter.get(token.lower(), 0)) for token in repeat_hits))
        if len(repeat_hits) >= 2:
            repeat_penalty += 2
        title_pattern = legacy.title_template_key(title)
        if title_pattern in title_patterns:
            repeat_penalty += 2
        discussion_score = min(10, 3 + len(item.get("angles") or []) + len(item.get("viewpoints") or []))
        if content_kind in {"教程/工具", "事件解读", "趋势观点"}:
            discussion_score += 1
        evidence_score = 4
        if str(item.get("source_tier") or "") == "官方":
            evidence_score += 3
        elif str(item.get("source_tier") or "") == "开源":
            evidence_score += 2
        if int(item.get("hit_count") or 0) >= 2:
            evidence_score += 1
        style_hint_score = 0
        if preferred_styles:
            if "signal-briefing" in preferred_styles and content_kind in {"产品更新", "趋势观点"}:
                style_hint_score += 2
            if "case-memo" in preferred_styles and content_kind in {"事件解读", "产品更新"}:
                style_hint_score += 1
            if "practical-playbook" in preferred_styles and content_kind == "教程/工具":
                style_hint_score += 2
        if any(topic.startswith(starter) for starter in starter_blacklist):
            repeat_penalty += 1
        novelty_score = max(1, 10 - repeat_penalty)
        angle_freshness_score = min(10, 4 + len({str(item).strip() for item in (item.get("angles") or []) if str(item).strip()}))
        if repeat_hits:
            angle_freshness_score = max(1, angle_freshness_score - min(3, len(repeat_hits)))
        reader_value_score = 3
        if content_kind in {"事件解读", "趋势观点"}:
            reader_value_score += 2
        if any(keyword in corpus for keyword in priority_keywords):
            reader_value_score += 3
        if any(keyword in corpus for keyword in {"成本", "代价", "岗位", "影响", "误判", "风险", "谁会先"}):
            reader_value_score += 2
        if any(keyword in corpus for keyword in deprioritize_keywords):
            reader_value_score -= 2
        audience_fit_score = min(10, 4 + style_hint_score + (1 if content_kind in {"教程/工具", "趋势观点"} else 0) + max(0, reader_value_score - 4))
        series_potential_score = min(10, 3 + len({str(raw).strip() for raw in (item.get("angles") or []) if str(raw).strip()}) + (1 if priority_keywords and any(keyword in corpus for keyword in priority_keywords) else 0))
        recommended_archetype = (
            "tutorial"
            if content_kind == "教程/工具"
            else "case-study"
            if content_kind in {"事件解读", "产品更新"}
            else "commentary"
        )
        evidence_potential = min(evidence_score, 10)
        writeability_score = min(10, round((discussion_score + evidence_potential + angle_freshness_score) / 3))
        novelty_reason = (
            f"近期重复词较少，优先从“{(item.get('angles') or ['切口'])[0]}”切入。"
            if not repeat_hits
            else f"近期已有相近词：{'、'.join(repeat_hits[:3])}，建议换成更窄的切口再写。"
        )
        propagation_score = min(
            10,
            max(
                1,
                round(
                    (
                        int(item.get("recommended_title_score") or 0) / max(1, int(item.get("recommended_title_threshold") or legacy.TITLE_SCORE_THRESHOLD))
                    )
                    * 10
                ),
            ),
        )
        differentiation_score = max(1, 10 - min(8, repeat_penalty + (2 if title_pattern in title_patterns else 0)))
        decision_score = (
            propagation_score * 4
            + novelty_score * 4
            + differentiation_score * 3
            + angle_freshness_score * 2
            + min(evidence_score, 10) * 2
            + audience_fit_score * 2
            + max(1, reader_value_score) * 3
            + series_potential_score * 2
            + discussion_score
            - repeat_penalty
        )
        topic_score_dimensions = {
            "时效和证据": min(20, evidence_potential * 2 + min(2, int(item.get("hit_count") or 0)) * 2),
            "冲突和代价": min(20, min(discussion_score, 10) + int(max(1, min(10, reader_value_score))) + (2 if any(keyword in corpus for keyword in {"成本", "代价", "岗位", "影响", "误判", "风险", "谁会先"}) else 0)),
            "目标读者清晰度": min(20, audience_fit_score * 2),
            "判断卡沉淀能力": min(20, writeability_score * 2),
            "互动传播潜力": min(20, propagation_score + min(discussion_score, 10)),
        }
        topic_score_100 = int(sum(topic_score_dimensions.values()))
        item["novelty_score"] = novelty_score
        item["differentiation_score"] = differentiation_score
        item["angle_freshness_score"] = angle_freshness_score
        item["audience_fit_score"] = audience_fit_score
        item["propagation_score"] = propagation_score
        item["discussion_score"] = min(discussion_score, 10)
        item["evidence_score"] = evidence_potential
        item["reader_value_score"] = int(max(1, min(10, reader_value_score)))
        item["series_potential_score"] = int(series_potential_score)
        item["repeat_penalty"] = repeat_penalty
        item["recent_overlap_tokens"] = repeat_hits[:5]
        item["decision_score"] = int(decision_score)
        item["topic_score_100"] = topic_score_100
        item["topic_score_dimensions"] = topic_score_dimensions
        item["topic_gate_passed"] = topic_score_100 >= 70 and min(topic_score_dimensions.values()) >= 10
        item["recommended_archetype"] = recommended_archetype
        item["recommended_enhancement_strategy"] = enhancement_strategy_for_archetype(recommended_archetype, title)
        item["writeability_score"] = int(writeability_score)
        item["evidence_potential"] = int(evidence_potential)
        item["novelty_reason"] = novelty_reason
        reranked.append(item)

    reranked.sort(
        key=lambda item: (
            bool(item.get("recommended_title_gate_passed", False)),
            -int(item.get("repeat_penalty") or 0),
            bool(item.get("topic_gate_passed", False)),
            int(item.get("novelty_score") or 0),
            int(item.get("differentiation_score") or 0),
            int(item.get("decision_score") or 0),
            int(item.get("topic_score_100") or 0),
            int(item.get("hit_count") or 0),
            int(item.get("recommended_title_score") or 0),
        ),
        reverse=True,
    )
    return reranked


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


def normalize_publication_body(title: str, body: str) -> str:
    return publication_normalize_publication_body(title, body)


def build_references_payload(workspace: Path, manifest: dict[str, Any], body: str) -> dict[str, Any]:
    return publication_build_references_payload(workspace, manifest, body)


def apply_reference_policy(workspace: Path, manifest: dict[str, Any], title: str, body: str) -> tuple[str, dict[str, Any]]:
    return publication_apply_reference_policy(workspace, manifest, title, body, keep_inline_citations=True)


def sync_article_reference_policy(workspace: Path, manifest: dict[str, Any]) -> tuple[dict[str, str], str]:
    article_path = workspace / (manifest.get("article_path") or "article.md")
    if not article_path.exists():
        return {}, ""
    raw = read_text(article_path)
    meta, body = split_frontmatter(raw)
    title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名标题"
    body = strip_leading_h1(body, title)
    body = normalize_publication_body(title, body)
    normalized_body, findings = apply_reference_policy(workspace, manifest, title, body)
    summary = meta.get("summary") or manifest.get("summary") or build_article_summary(title, normalized_body)
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
            workspace_candidate = (workspace / path).resolve()
            path = workspace_candidate if workspace_candidate.exists() else path.resolve()
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
    return _load_json_payload(workspace / "research.json")


def load_viral_discovery(workspace: Path) -> dict[str, Any]:
    return _load_json_payload(workspace / "viral-discovery.json")


def load_source_corpus(workspace: Path) -> dict[str, Any]:
    return _load_json_payload(workspace / "source-corpus.json")


def load_viral_dna(workspace: Path) -> dict[str, Any]:
    return _load_json_payload(workspace / "viral-dna.json")


def load_ideation(workspace: Path) -> dict[str, Any]:
    return _load_json_payload(workspace / "ideation.json")


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


def current_editorial_blueprint(workspace: Path, manifest: dict[str, Any], ideation: dict[str, Any] | None = None) -> dict[str, Any]:
    ideation = ideation or load_ideation(workspace)
    outline_meta = ideation.get("outline_meta") or {}
    existing = outline_meta.get("editorial_blueprint") or ideation.get("editorial_blueprint") or manifest.get("editorial_blueprint")
    return normalize_editorial_blueprint(
        existing,
        {
            "topic": manifest.get("topic") or ideation.get("topic") or manifest.get("selected_title") or "",
            "selected_title": ideation.get("selected_title") or manifest.get("selected_title") or "",
            "direction": manifest.get("direction") or ideation.get("direction") or "",
            "audience": manifest.get("audience") or "大众读者",
            "research": load_research(workspace),
            "article_archetype": (current_viral_blueprint(workspace, manifest, ideation).get("article_archetype") or manifest.get("article_archetype") or ""),
            "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
            "content_mode": manifest.get("content_mode") or "tech-balanced",
            "account_strategy": manifest.get("account_strategy") or {},
        },
    )


def current_writing_persona(workspace: Path, manifest: dict[str, Any], ideation: dict[str, Any] | None = None) -> dict[str, Any]:
    ideation = ideation or load_ideation(workspace)
    outline_meta = ideation.get("outline_meta") or {}
    existing = outline_meta.get("writing_persona") or ideation.get("writing_persona") or manifest.get("writing_persona")
    blueprint = current_viral_blueprint(workspace, manifest, ideation)
    return normalize_writing_persona(
        existing,
        {
            "topic": manifest.get("topic") or ideation.get("topic") or manifest.get("selected_title") or "",
            "selected_title": ideation.get("selected_title") or manifest.get("selected_title") or manifest.get("topic") or "",
            "direction": manifest.get("direction") or ideation.get("direction") or "",
            "audience": manifest.get("audience") or "大众读者",
            "content_mode": manifest.get("content_mode") or "tech-balanced",
            "article_archetype": blueprint.get("article_archetype") or manifest.get("article_archetype") or "",
            "author_memory": manifest.get("author_memory") or {},
            "account_strategy": manifest.get("account_strategy") or {},
        },
    )


def ensure_content_enhancement(
    workspace: Path,
    manifest: dict[str, Any],
    ideation: dict[str, Any] | None = None,
    *,
    selected_title: str = "",
    force: bool = False,
) -> dict[str, Any]:
    ideation = ideation or load_ideation(workspace)
    if not force:
        existing = load_content_enhancement(workspace)
        if isinstance(existing, dict) and existing.get("title") == (selected_title or manifest.get("selected_title") or ideation.get("selected_title") or existing.get("title")):
            manifest["content_enhancement_path"] = "content-enhancement.json"
            manifest["humanness_signals"] = manifest.get("humanness_signals") or {}
            return existing
    outline_meta = dict(ideation.get("outline_meta") or {})
    title = selected_title or manifest.get("selected_title") or ideation.get("selected_title") or manifest.get("topic") or "未命名标题"
    research = load_research(workspace)
    evidence_report = read_json(workspace / "evidence-report.json", default={}) or {}
    persona = current_writing_persona(workspace, manifest, ideation)
    payload = build_content_enhancement(
        title=title,
        outline_meta=outline_meta or {"sections": ideation.get("outline") or []},
        manifest=manifest,
        research=research,
        evidence_report=evidence_report,
        author_memory=manifest.get("author_memory") or {},
        writing_persona=persona,
    )
    write_content_enhancement_artifacts(workspace, payload)
    ideation["writing_persona"] = persona
    ideation["content_enhancement"] = payload
    write_json(workspace / "ideation.json", ideation)
    manifest["writing_persona"] = persona
    manifest["content_enhancement_path"] = "content-enhancement.json"
    return payload


def write_editorial_anchor_plan(workspace: Path, manifest: dict[str, Any], *, title: str, review_report: dict[str, Any] | None = None, score_report: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = build_editorial_anchor_plan(
        title=title,
        manifest=manifest,
        review_report=review_report,
        score_report=score_report,
        content_enhancement=load_content_enhancement(workspace),
    )
    write_editorial_anchor_artifacts(workspace, payload)
    manifest["editorial_anchor_plan_path"] = "editorial-anchor-plan.json"
    return payload


def _dedupe_generation_lines(values: list[str]) -> list[str]:
    output: list[str] = []
    for raw in values:
        value = str(raw or "").strip()
        if value and value not in output:
            output.append(value)
    return output


def _has_markdown_table(body: str) -> bool:
    return bool(re.search(r"(?m)^\|.+\|\s*\n\|(?:\s*:?-+:?\s*\|)+", body or ""))


def _analogy_signal_count(body: str) -> int:
    return len(re.findall(r"(像[^。！？!?；;\n]{1,18}一样|就像|好比|相当于|更像一个|像是在)", body or ""))


def _comparison_signal_count(body: str) -> int:
    return len(re.findall(r"(对比|相比之下|一边[^。！？!?；;\n]{0,18}一边|差别在于|差异在于|更像[^。！？!?；;\n]{0,18}不是)", body or ""))


def _table_count(body: str) -> int:
    return len(re.findall(r"(?m)^\|.+\|\s*$", body or "")) // 2


def _takeaway_heading_style(body: str) -> str:
    headings = [str(item.get("text") or "").strip() for item in legacy.extract_headings(body) if int(item.get("level") or 0) == 2]
    if not headings:
        return "generic"
    last_heading = headings[-1]
    if re.search(r"^带走这(?:张|条|句|套)", last_heading):
        return "carry-away"
    if any(keyword in last_heading for keyword in ["判断卡", "检查表", "清单"]):
        return "judgment-card"
    if last_heading.endswith("？") or last_heading.endswith("?"):
        return "question-close"
    return "generic"


def _batch_generation_constraints(title: str, body: str, manifest: dict[str, Any]) -> list[str]:
    workspace_value = str(manifest.get("workspace") or "").strip()
    if not workspace_value:
        return []
    current_workspace = Path(workspace_value)
    batch_key = workspace_batch_key(current_workspace)
    if not batch_key:
        return []
    peers = [path for path in list_batch_workspaces(current_workspace.parent, batch_key) if path.resolve() != current_workspace.resolve()]
    if len(peers) + 1 < 3:
        return []
    paragraphs = split_markdown_paragraphs(body)
    current_opening = opening_pattern_key(paragraphs[0]) if paragraphs else "none"
    current_title_template = title_template_key(title)
    current_takeaway_style = _takeaway_heading_style(body)
    current_heading_keys = [heading_pattern_key(str(item.get("text") or "")) for item in legacy.extract_headings(body)[:6]]
    current_heading_signature = "|".join(item for item in current_heading_keys if item not in {"", "none", "generic"}) or "generic"
    current_table_count = _table_count(body)
    opening_hits = 0
    title_hits = 0
    takeaway_hits = 0
    heading_hits = 0
    double_table_hits = 0
    for peer in peers:
        raw = read_text(peer / "article.md")
        meta, peer_body = split_frontmatter(raw)
        peer_title = str(meta.get("title") or peer.name).strip()
        peer_paragraphs = split_markdown_paragraphs(peer_body)
        if current_opening not in {"none", "generic"} and peer_paragraphs and opening_pattern_key(peer_paragraphs[0]) == current_opening:
            opening_hits += 1
        if current_title_template not in {"", "generic"} and title_template_key(peer_title) == current_title_template:
            title_hits += 1
        if current_takeaway_style == "carry-away" and _takeaway_heading_style(peer_body) == "carry-away":
            takeaway_hits += 1
        peer_heading_keys = [heading_pattern_key(str(item.get("text") or "")) for item in legacy.extract_headings(peer_body)[:6]]
        peer_heading_signature = "|".join(item for item in peer_heading_keys if item not in {"", "none", "generic"}) or "generic"
        if current_heading_signature != "generic" and peer_heading_signature == current_heading_signature:
            heading_hits += 1
        if current_table_count >= 2 and _table_count(peer_body) >= 2:
            double_table_hits += 1
    constraints: list[str] = []
    if opening_hits >= 1:
        constraints.append("同批次稿件已经重复这种开头路线，需要换一种进入方式。")
    if title_hits >= 1:
        constraints.append("同批次稿件已经出现这类标题模板，需要换一种标题句法。")
    if takeaway_hits >= 1:
        constraints.append("同批次稿件不要再用“带走这张/这条”式结尾标题。")
    if heading_hits >= 1:
        constraints.append("同批次稿件的小标题骨架已经太像，需要换一种结构推进。")
    if double_table_hits >= 1:
        constraints.append("同批次已经有其他稿件用了 2 张表，当前稿件应压回到 1 张。")
    return constraints


def build_generation_preflight_report(
    title: str,
    body: str,
    manifest: dict[str, Any],
    outline_meta: dict[str, Any] | None = None,
    content_enhancement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blueprint = dict((outline_meta or {}).get("viral_blueprint") or manifest.get("viral_blueprint") or {})
    depth = generation_depth_signals(body, blueprint)
    ai_smell = generation_ai_smell_findings(body, manifest)
    ai_fingerprint_summary = summarize_ai_fingerprints(ai_smell)
    template_findings = generation_template_findings(title, body, manifest)
    enhancement = content_enhancement or manifest.get("content_enhancement") or {}
    section_enhancements = list(enhancement.get("section_enhancements") or []) if isinstance(enhancement, dict) else []
    has_table = _has_markdown_table(body)
    analogy_count = _analogy_signal_count(body)
    comparison_count = _comparison_signal_count(body)
    lead_paras = lead_paragraph_count(body)
    has_cost_signal = cost_signal_present(body)
    has_discussion_trigger = discussion_trigger_present(body)
    batch_constraints = _batch_generation_constraints(title, body, manifest)
    title_tail_template = bool(re.search(r"(真正|最先|从今天开始|被改写的是)", title or ""))
    not_but_count = len(re.findall(r"不是.{1,24}而是.{1,24}", body or ""))
    explainer_connector_count = sum((body or "").count(marker) for marker in ["首先", "其次", "最后", "换句话说", "说白了", "更重要的是", "需要注意的是"])
    missing_elements: list[str] = []
    if depth.get("scene_paragraph_count", 0) < 1:
        missing_elements.append("开头缺少具体场景、动作或瞬间。")
    if depth.get("evidence_paragraph_count", 0) < 1:
        missing_elements.append("中段缺少案例、数据或事实托底。")
    if not has_table:
        missing_elements.append("正文缺少一张服务判断的数据表格或对比表。")
    if analogy_count < 1:
        missing_elements.append("正文缺少类比分析，抽象问题还没被讲直白。")
    if comparison_count < 1:
        missing_elements.append("正文缺少明确对比分析，差异还没被讲透。")
    if depth.get("counterpoint_paragraph_count", 0) < 1:
        missing_elements.append("全文缺少反方、误判或适用边界。")
    if depth.get("long_paragraph_count", 0) < 1 and depth.get("paragraph_count", 0) > 4:
        missing_elements.append("缺少真正展开的分析段，段落太碎。")
    if lead_paras > 4:
        missing_elements.append("第一个小标题前铺垫过长，首屏还没尽快切题。")
    if not has_cost_signal:
        missing_elements.append("正文缺少现实代价，读者还感受不到后果。")
    if not has_discussion_trigger:
        missing_elements.append("正文缺少可讨论的分歧点，评论和转发入口还不够。")
    missing_elements.extend(batch_constraints)
    if title_tail_template:
        missing_elements.append("标题还在用“真正/最先/从今天开始/被改写的是”这类判断句尾巴。")
    if not_but_count >= 3:
        missing_elements.append("正文“不是……而是……”句式过密，模板味太重。")
    if explainer_connector_count >= 4:
        missing_elements.append("解释型连接词偏密，读起来像说明书。")
    if section_enhancements:
        if depth.get("evidence_paragraph_count", 0) < 1 and any(item.get("support_quotes") or item.get("support_sources") for item in section_enhancements):
            missing_elements.append("写前增强已经准备了来源材料，但正文还没把证据真正写进去。")
        if depth.get("scene_paragraph_count", 0) < 1 and any(item.get("detail_anchors") for item in section_enhancements):
            missing_elements.append("写前增强已经规划了场景细节，但首屏还没真正落下现场。")
        if not has_table and any(item.get("table_targets") for item in section_enhancements):
            missing_elements.append("写前增强已经要求表格，但正文还没有真正把表格写出来。")
        if analogy_count < 1 and any(item.get("analogy_targets") for item in section_enhancements):
            missing_elements.append("写前增强已经要求类比分析，但正文还没有把抽象问题讲直白。")
        if comparison_count < 1 and any(item.get("comparison_targets") for item in section_enhancements):
            missing_elements.append("写前增强已经要求对比分析，但正文还没有把差异讲透。")
        if depth.get("evidence_paragraph_count", 0) < 2 and any(item.get("citation_targets") for item in section_enhancements):
            missing_elements.append("写前增强已经要求引用或来源化表达，但正文里还不够。")
        if depth.get("counterpoint_paragraph_count", 0) < 1 and any(item.get("counterpoint_targets") for item in section_enhancements):
            missing_elements.append("写前增强已经给了边界提醒，但正文还没把反方或适用边界写进去。")

    if any(str(item.get("type") or "") == "prompt_leak" for item in ai_smell):
        missing_elements.append("正文里泄漏了内部提示语或写作说明。")
    severe_types = {
        "author_phrase",
        "author_starter",
        "repeated_starter",
        "repeated_sentence_opener",
        "heading_monotony",
        "outline_like",
        "prompt_leak",
        "reader_strawman",
        "opening_triad",
        "dead_opening_self_intro",
        "body_feeling_answer",
        "blessing_close",
        "fake_precision_emotion",
    }
    severe_findings = [
        item
        for item in ai_smell
        if str(item.get("type") or "") in severe_types or str(item.get("severity") or "").lower() == "strong"
    ]
    if any(str(item.get("pattern") or "").startswith(("ending-pattern:", "heading-pattern:", "author-starter:")) for item in template_findings):
        severe_findings.extend(
            [
                {"type": "template_collision", "evidence": str(item.get("evidence") or item.get("pattern") or "")}
                for item in template_findings
                if str(item.get("pattern") or "").startswith(("ending-pattern:", "heading-pattern:", "author-starter:"))
            ]
        )
    rewrite_focus = _dedupe_generation_lines(
        [
            "重写重复起手，打散段落句法。" if depth.get("repeated_starter_count", 0) or depth.get("repeated_sentence_opener_count", 0) else "",
            "重写小标题，至少用两种不同句法。" if depth.get("heading_monotony") else "",
            "补一个开头场景或动作瞬间。" if depth.get("scene_paragraph_count", 0) < 1 else "",
            "补一处案例、数据或事实支撑。" if depth.get("evidence_paragraph_count", 0) < 1 else "",
            "补一张能帮助读者看清差异、趋势或成本的 Markdown 表格。" if not has_table else "",
            "补一段类比分析，把抽象问题讲成人一看就懂的画面。" if analogy_count < 1 else "",
            "补一段对比分析，讲清楚表面像什么、实际差在哪。" if comparison_count < 1 else "",
            "补一处反方、误判或适用边界。" if depth.get("counterpoint_paragraph_count", 0) < 1 else "",
            "把卡片段落合并成至少一段真正展开的分析。" if depth.get("long_paragraph_count", 0) < 1 and depth.get("paragraph_count", 0) > 4 else "",
            "把首屏压到 4 段内，尽快给出主判断和第一个小标题。" if lead_paras > 4 else "",
            "补一段现实代价，写清谁在付、付在哪里、后果是什么。" if not has_cost_signal else "",
            "补一个可讨论的分歧点，让读者有理由接话或转发。" if not has_discussion_trigger else "",
            "删除内部提示语、写作说明和蓝图口吻。" if any(str(item.get("type") or "") == "prompt_leak" for item in ai_smell) else "",
            (
                f"优先把这一条来源材料写进正文：{((section_enhancements[0].get('support_quotes') or [{}])[0].get('text') or (section_enhancements[0].get('support_sources') or [{}])[0].get('title') or '')}"
                if section_enhancements and (section_enhancements[0].get("support_quotes") or section_enhancements[0].get("support_sources")) and depth.get("evidence_paragraph_count", 0) < 1
                else ""
            ),
            (
                f"优先把这一节的现场写出来：{(section_enhancements[0].get('detail_anchors') or [''])[0]}"
                if section_enhancements and section_enhancements[0].get("detail_anchors") and depth.get("scene_paragraph_count", 0) < 1
                else ""
            ),
            (
                f"优先把这一节需要的表格写出来：{(section_enhancements[0].get('table_targets') or [''])[0]}"
                if section_enhancements and section_enhancements[0].get("table_targets") and not has_table
                else ""
            ),
            (
                f"优先把这一节的类比补出来：{(section_enhancements[0].get('analogy_targets') or [''])[0]}"
                if section_enhancements and section_enhancements[0].get("analogy_targets") and analogy_count < 1
                else ""
            ),
            (
                f"优先把这一节的对比写透：{(section_enhancements[0].get('comparison_targets') or [''])[0]}"
                if section_enhancements and section_enhancements[0].get("comparison_targets") and comparison_count < 1
                else ""
            ),
        ]
        + [f"删掉作者明确避开的句式：{item.get('pattern')}" for item in ai_smell if str(item.get("type") or "") in {"author_phrase", "author_starter"}]
        + list(ai_fingerprint_summary.get("rewrite_hints") or [])
    )
    rewrite_focus = _dedupe_generation_lines(
        rewrite_focus
        + (["同批次强制换开头路线、小标题骨架或结尾动作，别再按同一模子展开。"] if batch_constraints else [])
        + (["把标题从抽象判断句改成更具体的对象、动作和代价。"] if title_tail_template else [])
        + (["删掉多余的“不是……而是……”句式，保留一处最值钱的就够了。"] if not_but_count >= 3 else [])
        + (["压低“首先/其次/最后/换句话说/说白了”这类解释型连接词密度。"] if explainer_connector_count >= 4 else [])
    )
    issue_score = (
        len(severe_findings) * 2
        + len(missing_elements)
        + len(template_findings)
        + int(ai_fingerprint_summary.get("strong_count") or 0) * 2
        + int(ai_fingerprint_summary.get("medium_count") or 0)
    )
    needs_hardening = bool(severe_findings or len(missing_elements) >= 2)
    return {
        "title": title,
        "generated_at": now_iso(),
        "ai_smell_findings": ai_smell,
        "ai_fingerprint_summary": ai_fingerprint_summary,
        "template_findings": template_findings,
        "depth_signals": depth,
        "lead_paragraph_count": lead_paras,
        "cost_signal_present": has_cost_signal,
        "discussion_trigger_present": has_discussion_trigger,
        "batch_constraints": batch_constraints,
        "title_tail_template": title_tail_template,
        "not_but_count": not_but_count,
        "explainer_connector_count": explainer_connector_count,
        "missing_elements": missing_elements,
        "severe_findings": severe_findings,
        "rewrite_focus": rewrite_focus,
        "needs_hardening": needs_hardening,
        "issue_score": issue_score,
    }


def write_generation_preflight_report(workspace: Path, report: dict[str, Any]) -> None:
    write_json(workspace / "generation-preflight.json", report)
    lines = [
        f"标题：{report.get('title') or '未命名标题'}",
        f"是否需要预修：{'是' if report.get('needs_hardening') else '否'}",
        f"问题分：{report.get('issue_score') or 0}",
    ]
    for item in report.get("missing_elements") or []:
        lines.append(f"缺失：{item}")
    for item in report.get("severe_findings") or []:
        lines.append(f"严重信号：{item.get('evidence') or item.get('type')}")
    for item in report.get("rewrite_focus") or []:
        lines.append(f"预修重点：{item}")
    ensure_text_report(workspace / "generation-preflight.md", "生成预检报告", lines)


def harden_generated_article_body(
    workspace: Path,
    manifest: dict[str, Any],
    title: str,
    summary: str,
    body: str,
    *,
    outline_meta: dict[str, Any] | None = None,
    allow_model_repair: bool = True,
) -> tuple[str, dict[str, Any]]:
    enhancement = load_content_enhancement(workspace)
    if enhancement:
        manifest["content_enhancement"] = enhancement
    initial_report = build_generation_preflight_report(title, body, manifest, outline_meta, content_enhancement=enhancement)
    final_body = body.strip()
    actions: list[str] = []
    final_report = initial_report
    if initial_report.get("needs_hardening"):
        cleaned = legacy.cleanup_rewrite_markdown(final_body) or final_body
        if cleaned.strip() and cleaned.strip() != final_body.strip():
            final_body = cleaned.strip()
            actions.append("规则预修：清理模板连接词并压缩重复句式")
        if allow_model_repair:
            provider = active_text_provider()
            if provider.configured():
                context = {
                    "mode": "generation-preflight",
                    "title": title,
                    "audience": manifest.get("audience") or "公众号读者",
                    "direction": manifest.get("direction") or "",
                    "summary": summary or manifest.get("summary") or extract_summary(final_body),
                    "article_body": final_body,
                    "rewrite_goal": (
                        "生成阶段预修：\n"
                        "- 先修重复起手、重复小标题、模板结尾和假人味连接词。\n"
                        "- 必须补足这篇稿子缺的内容：具体场景、案例/数据/事实、反方或适用边界、展开分析段。\n"
                        "- 不要重写成另一种模板；保持原题和主判断不变，只把文章拉回真人作者写作状态。\n"
                        "- 删除作者记忆里明确避开的句式与起手。\n"
                        "- 保持 Markdown 结构，不要输出解释。\n"
                    ),
                    "mandatory_revisions": initial_report.get("rewrite_focus") or [],
                    "weaknesses": initial_report.get("missing_elements") or [],
                    "suggestions": {"generation_preflight": initial_report.get("rewrite_focus") or []},
                    "score_breakdown": [],
                    "viral_blueprint": dict((outline_meta or {}).get("viral_blueprint") or manifest.get("viral_blueprint") or {}),
                    "viral_analysis": {},
                    "emotion_value_sentences": [],
                    "pain_point_sentences": [],
                    "ai_smell_findings": initial_report.get("ai_smell_findings") or [],
                    "quality_gates": {},
                    "style_samples": manifest.get("style_sample_paths") or [],
                    "style_signals": manifest.get("style_signals") or [],
                    "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
                    "recent_article_titles": manifest.get("recent_article_titles") or [],
                    "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
                    "corpus_root": manifest.get("corpus_root") or "",
                    "editorial_blueprint": dict((outline_meta or {}).get("editorial_blueprint") or manifest.get("editorial_blueprint") or {}),
                    "author_memory": manifest.get("author_memory") or {},
                    "writing_persona": manifest.get("writing_persona") or {},
                    "content_enhancement": load_content_enhancement(workspace),
                    "generation_preflight": initial_report,
                }
                result = provider.revise_article(context)
                revised = strip_leading_h1(str(result.payload or ""), title).strip()
                if revised:
                    final_body = revised
                    actions.append("模型预修：先处理生成阶段的模板风险")
        final_report = build_generation_preflight_report(title, final_body, manifest, outline_meta, content_enhancement=enhancement)
    report = {
        "title": title,
        "generated_at": now_iso(),
        "initial": initial_report,
        "final": final_report,
        "actions": actions,
        "used_repaired_body": bool(actions),
    }
    write_generation_preflight_report(workspace, report)
    return final_body, report


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
    threshold = max((int(item.get("title_score_threshold") or 0) for item in ranked_titles), default=legacy.TITLE_SCORE_THRESHOLD)
    payload = {
        "topic": topic,
        "selected_title": selected_title,
        "threshold": threshold,
        "candidates": ranked_titles,
        "generated_at": now_iso(),
    }
    write_json(workspace / "title-report.json", payload)
    lines = [f"原始主题：{topic}", f"最终标题：{selected_title}", f"准入阈值：{threshold}"]
    for item in ranked_titles[:5]:
        lines.append(f"{item['title']}｜得分 {item['title_score']}｜{'通过' if item['title_gate_passed'] else '未通过'}")
    ensure_text_report(workspace / "title-report.md", "标题评分报告", lines)


def write_title_decision_artifacts(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(workspace / "title-decision-report.json", payload)
    write_text(workspace / "title-decision-report.md", markdown_title_decision_report(payload))


def _apply_batch_title_constraints(decision_report: dict[str, Any], batch_guidance: dict[str, Any]) -> dict[str, Any]:
    candidates = list(decision_report.get("candidates") or [])
    forbidden_patterns = {str(item).strip() for item in (batch_guidance.get("forbidden_title_patterns") or []) if str(item).strip()}
    title_tail_re = re.compile(r"(真正|最先|从今天开始|被改写的是)")
    for item in candidates:
        title = str(item.get("title") or "").strip()
        risks = list(item.get("selected_title_risks") or [])
        blocked = False
        reasons = []
        if str(item.get("title_template_key") or "").strip() in forbidden_patterns:
            blocked = True
            reasons.append("撞上同批次高频标题模板")
        if title_tail_re.search(title):
            reasons.append("标题判断句尾巴过重")
            item["title_score"] = max(0, int(item.get("title_score") or 0) - 3)
            item["title_open_rate_score"] = int(item.get("title_score") or 0)
        if reasons:
            item["batch_collision_reasons"] = reasons
            for reason in reasons:
                if reason not in risks:
                    risks.append(reason)
        if blocked:
            item["title_gate_passed"] = False
        item["selected_title_risks"] = risks
        if reasons:
            item["title_gate_reason"] = "；".join(reasons[:3])
    candidates.sort(
        key=lambda item: (
            bool(item.get("title_gate_passed")),
            int(item.get("title_score") or 0),
            float(item.get("hook_strength_score") or 0),
            -float(item.get("recent_title_overlap") or 0),
        ),
        reverse=True,
    )
    updated = dict(decision_report)
    updated["candidates"] = candidates
    if candidates:
        updated["selected_title"] = str(candidates[0].get("title") or updated.get("selected_title") or "")
    return updated


def _title_rewrite_hints(candidates: list[dict[str, Any]]) -> list[str]:
    counter: Counter[str] = Counter()
    for item in candidates[:3]:
        for detail in (item.get("title_score_breakdown") or []):
            try:
                score = float(detail.get("score") or 0)
            except (TypeError, ValueError):
                score = 0
            if score < 6:
                counter[str(detail.get("dimension") or "").strip()] += 1
    mapping = {
        "普遍痛点": "加强普遍痛点",
        "信息差": "加强信息差",
        "反常识": "加强反常识",
        "低门槛理解": "压缩标题长度",
        "高预期": "加强高预期",
        "情绪共鸣": "加强情绪共鸣",
        "传播性": "加强传播性",
        "可信度": "加强可信度",
        "新鲜度": "避开旧模板",
    }
    return [mapping[key] for key, _count in counter.most_common(4) if key in mapping]


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
    research = load_research(workspace)
    batch_guidance = manifest.get("batch_guidance") or ensure_batch_guidance(workspace, manifest, force=False)
    recent_corpus_summary = manifest.get("recent_corpus_summary") or {}
    decision_report = build_title_decision_report(
        topic=topic,
        audience=audience,
        angle=angle,
        candidates=candidates,
        manifest=manifest,
        research=research,
        editorial_blueprint=manifest.get("editorial_blueprint") or {},
        selected_title=selected_title,
        account_strategy=manifest.get("account_strategy") or {},
        title_rewrite_round=0,
    )
    decision_report = _apply_batch_title_constraints(decision_report, batch_guidance)
    ranked_titles = list(decision_report.get("candidates") or [])
    selected = ranked_titles[0] if ranked_titles else None
    top3 = ranked_titles[:3]
    if not selected or (top3 and all(not item.get("title_gate_passed", False) for item in top3)):
        weakness_hints = _title_rewrite_hints(ranked_titles)
        boosted_candidates = candidates + generate_diverse_title_variants(
            topic,
            angle,
            audience,
            editorial_blueprint=manifest.get("editorial_blueprint") or {},
            recent_titles=manifest.get("recent_article_titles") or [],
            recent_corpus_summary=recent_corpus_summary if isinstance(recent_corpus_summary, dict) else {},
            writing_persona=manifest.get("writing_persona") or {},
            account_strategy=manifest.get("account_strategy") or {},
            count=10,
            boost_round=1,
            weakness_hints=weakness_hints,
        )
        decision_report = build_title_decision_report(
            topic=topic,
            audience=audience,
            angle=angle,
            candidates=boosted_candidates,
            manifest=manifest,
            research=research,
            editorial_blueprint=manifest.get("editorial_blueprint") or {},
            selected_title=selected_title,
            account_strategy=manifest.get("account_strategy") or {},
            title_rewrite_round=1,
        )
        decision_report = _apply_batch_title_constraints(decision_report, batch_guidance)
        ranked_titles = list(decision_report.get("candidates") or [])
        selected = ranked_titles[0] if ranked_titles else None
    chosen_title = selected.get("title") if selected else topic
    if selected_title:
        selected_candidate = next((item for item in ranked_titles if str(item.get("title") or "") == selected_title), None)
        integrity = title_integrity_report(selected_title, topic=topic, account_strategy=manifest.get("account_strategy") or {})
        if selected_candidate and selected_candidate.get("title_gate_passed", False):
            chosen_title = selected_title
            ideation["selected_title_score"] = selected_candidate.get("title_score", 0)
            ideation["selected_title_gate_passed"] = selected_candidate.get("title_gate_passed", False)
        elif selected_candidate:
            ideation["selected_title_score"] = selected_candidate.get("title_score", 0)
            ideation["selected_title_gate_passed"] = False
        else:
            ideation["selected_title_score"] = int((integrity.get("score") or 0) * 10)
            ideation["selected_title_gate_passed"] = bool(integrity.get("passed"))
    elif selected:
        chosen_title = selected["title"]
        ideation["selected_title_score"] = selected.get("title_score", 0)
        ideation["selected_title_gate_passed"] = selected.get("title_gate_passed", False)
    else:
        ideation["selected_title_score"] = 0
        ideation["selected_title_gate_passed"] = False
    ideation["selected_title"] = chosen_title
    ideation["title_threshold"] = decision_report.get("threshold") or legacy.TITLE_SCORE_THRESHOLD
    ideation["titles"] = ranked_titles
    write_title_report(workspace, topic, chosen_title, ranked_titles)
    decision_report["selected_title"] = chosen_title
    write_title_decision_artifacts(workspace, decision_report)
    manifest["selected_title"] = chosen_title
    manifest["title_report_path"] = "title-report.json"
    manifest["title_decision_report_path"] = "title-decision-report.json"
    manifest["title_gate_threshold"] = ideation.get("title_threshold") or legacy.TITLE_SCORE_THRESHOLD
    manifest["title_gate_passed"] = ideation.get("selected_title_gate_passed", False)
    manifest["title_score"] = ideation.get("selected_title_score", 0)
    sync_title_truth(workspace, manifest, chosen_title)
    return ideation, selected


def _resolve_selected_title(
    manifest: dict[str, Any],
    ideation: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
    requested_title: str = "",
    *,
    fallback: str = "未命名标题",
) -> str:
    ideation = ideation or {}
    research = research or {}
    return requested_title or manifest.get("selected_title") or ideation.get("selected_title") or research.get("topic") or manifest.get("topic") or fallback


def _build_outline_generation_contexts(
    workspace: Path,
    manifest: dict[str, Any],
    ideation: dict[str, Any],
    research: dict[str, Any],
    selected_title: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    editorial_blueprint = current_editorial_blueprint(workspace, manifest, ideation)
    batch_guidance = manifest.get("batch_guidance") or ensure_batch_guidance(workspace, manifest, force=False)
    generation_strategy = build_generation_strategy(
        title=selected_title,
        manifest=manifest,
        batch_guidance=batch_guidance,
    )
    editorial_blueprint = {
        **editorial_blueprint,
        "blocked_opening_patterns": list(dict.fromkeys(list(editorial_blueprint.get("blocked_opening_patterns") or []) + list(batch_guidance.get("forbidden_opening_routes") or []))),
    }
    writing_persona = current_writing_persona(workspace, manifest, ideation)
    outline_context = {
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
        "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
        "corpus_root": manifest.get("corpus_root") or "",
        "content_mode": manifest.get("content_mode") or "tech-balanced",
        "editorial_blueprint": editorial_blueprint,
        "author_memory": manifest.get("author_memory") or {},
        "writing_persona": writing_persona,
        "account_strategy": manifest.get("account_strategy") or {},
        "batch_guidance": batch_guidance,
        "generation_strategy": generation_strategy,
    }
    normalize_context = {
        "topic": manifest.get("topic") or research.get("topic") or selected_title,
        "selected_title": selected_title,
        "audience": manifest.get("audience") or research.get("audience") or "大众读者",
        "direction": manifest.get("direction") or research.get("angle") or "",
        "research": research,
        "style_signals": manifest.get("style_signals") or [],
        "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
        "content_mode": manifest.get("content_mode") or "tech-balanced",
        "editorial_blueprint": editorial_blueprint,
        "author_memory": manifest.get("author_memory") or {},
        "writing_persona": writing_persona,
        "account_strategy": manifest.get("account_strategy") or {},
        "batch_guidance": batch_guidance,
        "generation_strategy": generation_strategy,
    }
    return outline_context, normalize_context, editorial_blueprint, writing_persona


def _generate_outline_with_collision_retry(
    provider: Any,
    workspace: Path,
    manifest: dict[str, Any],
    selected_title: str,
    outline_context: dict[str, Any],
    normalize_context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    result = provider.generate_outline(outline_context)
    outline = normalize_outline_payload(dict(result.payload), normalize_context)
    recent_fingerprints = collect_recent_fingerprints(workspace, manifest)
    outline_fingerprint = build_outline_fingerprint(selected_title, outline, manifest | {"viral_blueprint": outline.get("viral_blueprint") or {}})
    fingerprint_findings = summarize_collisions(outline_fingerprint, recent_fingerprints, threshold=0.74)
    if not fingerprint_findings.get("route_similarity_passed"):
        retry_context = dict(outline_context)
        retry_context["fingerprint_collision_notes"] = [
            f"当前大纲和旧稿《{item.get('title') or '未命名'}》过近（{item.get('score') or 0}），请主动换开头路径、证据组织和结尾收束。"
            for item in (fingerprint_findings.get("similar_items") or [])[:3]
        ]
        retry_result = provider.generate_outline(retry_context)
        retry_outline = normalize_outline_payload(
            dict(retry_result.payload),
            normalize_context | {"fingerprint_collision_notes": retry_context["fingerprint_collision_notes"]},
        )
        retry_fingerprint = build_outline_fingerprint(
            selected_title,
            retry_outline,
            manifest | {"viral_blueprint": retry_outline.get("viral_blueprint") or {}},
        )
        retry_findings = summarize_collisions(retry_fingerprint, recent_fingerprints, threshold=0.74)
        if float(retry_findings.get("max_route_similarity") or 1) < float(fingerprint_findings.get("max_route_similarity") or 1):
            outline = retry_outline
            outline_fingerprint = retry_fingerprint
            fingerprint_findings = retry_findings
    return outline, outline_fingerprint, fingerprint_findings


def _persist_outline_result(
    workspace: Path,
    manifest: dict[str, Any],
    ideation: dict[str, Any],
    research: dict[str, Any],
    selected_title: str,
    outline: dict[str, Any],
    outline_fingerprint: dict[str, Any],
    fingerprint_findings: dict[str, Any],
    writing_persona: dict[str, Any],
) -> None:
    outline.setdefault("title", selected_title)
    outline["content_fingerprint_preview"] = outline_fingerprint
    outline["fingerprint_similarity_preview"] = fingerprint_findings
    layout_plan = build_layout_plan(
        selected_title,
        extract_summary("\n".join(str(item.get("goal") or "") for item in (outline.get("sections") or []))),
        outline,
        manifest | {"viral_blueprint": outline.get("viral_blueprint") or {}},
    )
    write_json(workspace / "layout-plan.json", layout_plan)
    write_text(workspace / "layout-plan.md", markdown_layout_plan(layout_plan))
    outline["layout_plan_path"] = "layout-plan.json"
    ideation["selected_title"] = selected_title
    ideation["outline"] = outline.get("sections") or []
    ideation["outline_meta"] = outline
    ideation["viral_blueprint"] = outline.get("viral_blueprint") or {}
    ideation["editorial_blueprint"] = outline.get("editorial_blueprint") or {}
    ideation["generation_strategy"] = build_generation_strategy(
        title=selected_title,
        manifest=manifest,
        batch_guidance=manifest.get("batch_guidance") or {},
        outline_meta=outline,
    )
    ideation["writing_persona"] = normalize_writing_persona(
        writing_persona,
        {
            "topic": manifest.get("topic") or selected_title,
            "selected_title": selected_title,
            "audience": manifest.get("audience") or research.get("audience") or "大众读者",
            "direction": manifest.get("direction") or research.get("angle") or "",
            "content_mode": manifest.get("content_mode") or "tech-balanced",
            "article_archetype": (outline.get("viral_blueprint") or {}).get("article_archetype") or "",
            "author_memory": manifest.get("author_memory") or {},
        },
    )
    ideation["updated_at"] = now_iso()
    write_json(workspace / "ideation.json", ideation)
    manifest["selected_title"] = selected_title
    manifest["outline"] = [item.get("heading", "") for item in outline.get("sections") or []]
    manifest["viral_blueprint"] = outline.get("viral_blueprint") or {}
    manifest["editorial_blueprint"] = outline.get("editorial_blueprint") or {}
    manifest["writing_persona"] = ideation.get("writing_persona") or writing_persona
    manifest["layout_plan_path"] = "layout-plan.json"
    manifest["batch_guidance_path"] = "batch-guidance.json"
    update_stage(manifest, "outline", "outline_status")
    save_manifest(workspace, manifest)


def _normalize_write_outline_meta(
    workspace: Path,
    manifest: dict[str, Any],
    ideation: dict[str, Any],
    research: dict[str, Any],
    selected_title: str,
    outline_file: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    outline_meta = dict(ideation.get("outline_meta") or {})
    layout_plan = read_json(workspace / "layout-plan.json", default={}) or {}
    batch_guidance = manifest.get("batch_guidance") or ensure_batch_guidance(workspace, manifest, force=False)
    if outline_file:
        outline_lines = [line.strip("- ").strip() for line in read_input_file(outline_file).splitlines() if line.strip()]
        outline_meta["sections"] = [{"heading": line, "goal": "展开该章节", "evidence_need": "按需补证据"} for line in outline_lines]
    editorial_blueprint = current_editorial_blueprint(workspace, manifest, ideation)
    writing_persona = current_writing_persona(workspace, manifest, ideation)
    outline_meta = normalize_outline_payload(
        outline_meta,
        {
            "topic": manifest.get("topic") or research.get("topic") or selected_title,
            "selected_title": selected_title,
            "audience": manifest.get("audience") or research.get("audience") or "大众读者",
            "direction": manifest.get("direction") or research.get("angle") or "",
            "research": research,
            "style_signals": manifest.get("style_signals") or [],
            "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
            "content_mode": manifest.get("content_mode") or "tech-balanced",
            "editorial_blueprint": editorial_blueprint,
            "author_memory": manifest.get("author_memory") or {},
            "writing_persona": writing_persona,
            "batch_guidance": batch_guidance,
            "generation_strategy": build_generation_strategy(
                title=selected_title,
                manifest=manifest,
                batch_guidance=batch_guidance,
                outline_meta=outline_meta,
            ),
        },
    )
    ideation["outline_meta"] = outline_meta
    ideation["generation_strategy"] = build_generation_strategy(
        title=selected_title,
        manifest=manifest,
        batch_guidance=batch_guidance,
        outline_meta=outline_meta,
    )
    ideation["writing_persona"] = normalize_writing_persona(
        writing_persona,
        {
            "topic": manifest.get("topic") or research.get("topic") or selected_title,
            "selected_title": selected_title,
            "audience": manifest.get("audience") or research.get("audience") or "大众读者",
            "direction": manifest.get("direction") or research.get("angle") or "",
            "content_mode": manifest.get("content_mode") or "tech-balanced",
            "article_archetype": (outline_meta.get("viral_blueprint") or {}).get("article_archetype") or "",
            "author_memory": manifest.get("author_memory") or {},
        },
    )
    return outline_meta, layout_plan, editorial_blueprint, writing_persona


def apply_research_credibility_boost(report: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
    sources = normalize_string_list(research.get("sources"))
    evidence_items = normalize_string_list(research.get("evidence_items"))
    if not report or (not sources and not evidence_items):
        return report
    boosted = json.loads(json.dumps(report, ensure_ascii=False))
    target = None
    for item in boosted.get("score_breakdown", []):
        if item.get("dimension") in {"事实/案例/对比托底", "可信度与检索支撑"}:
            target = item
            break
    if target is None:
        return boosted
    weight = int(target.get("weight") or 10) or 10
    bonus = min(weight, max(int(target.get("score", 0) or 0), min(4, len(sources)) + min(4, len(evidence_items)) + 2))
    target["score"] = bonus
    quality_gates = boosted.get("quality_gates") or {}
    quality_gates["credibility_passed"] = bonus >= PUBLISH_MIN_CREDIBILITY_SCORE
    boosted["quality_gates"] = quality_gates
    weaknesses = normalize_string_list(boosted.get("weaknesses"))
    if bonus >= 6:
        weaknesses = [item for item in weaknesses if not item.startswith("可信度与检索支撑") and not item.startswith("事实/案例/对比托底")]
    boosted["weaknesses"] = weaknesses
    return recompute_score_outcome(boosted)


def cmd_research(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = attach_account_strategy(workspace, manifest)
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
            "account_strategy": manifest.get("account_strategy") or {},
        }
    )
    payload = dict(result.payload)
    payload.setdefault("topic", topic)
    payload.setdefault("angle", angle)
    payload.setdefault("audience", audience)
    payload["provider"] = result.provider
    payload["model"] = result.model
    payload["generated_at"] = now_iso()
    _update_research_requirements(workspace, manifest, payload)
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
    manifest = _prepare_content_manifest(workspace)
    batch_guidance = ensure_batch_guidance(workspace, manifest, force=True)
    provider = require_live_text_provider("titles")
    research = load_research(workspace)
    topic = manifest.get("topic") or research.get("topic") or "未命名主题"
    audience = manifest.get("audience") or research.get("audience") or "大众读者"
    count = args.count or 10
    writing_persona = current_writing_persona(workspace, manifest)
    result = provider.generate_titles(
        {
            "topic": topic,
            "audience": audience,
            "angle": manifest.get("direction") or research.get("angle") or "",
            "count": count,
            "research": research,
            "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
            "recent_article_titles": manifest.get("recent_article_titles") or [],
            "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
            "editorial_blueprint": current_editorial_blueprint(workspace, manifest),
            "author_memory": manifest.get("author_memory") or {},
            "writing_persona": writing_persona,
            "account_strategy": manifest.get("account_strategy") or {},
            "batch_guidance": batch_guidance,
            "generation_strategy": build_generation_strategy(
                title=str(manifest.get("selected_title") or topic),
                manifest=manifest,
                batch_guidance=batch_guidance,
            ),
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
    ideation["generation_strategy"] = build_generation_strategy(
        title=str(ideation.get("selected_title") or topic),
        manifest=manifest,
        batch_guidance=batch_guidance,
    )
    write_json(workspace / "ideation.json", ideation)
    manifest["selected_title"] = ideation.get("selected_title") or manifest.get("selected_title", "")
    manifest["writing_persona"] = writing_persona
    manifest["ideation_path"] = "ideation.json"
    manifest["batch_guidance_path"] = "batch-guidance.json"
    update_stage(manifest, "titles", "title_status")
    save_manifest(workspace, manifest)
    print(json.dumps(ideation, ensure_ascii=False, indent=2))
    return 0


def cmd_outline(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace, args)
    batch_guidance = ensure_batch_guidance(workspace, manifest, force=True)
    provider = require_live_text_provider("outline")
    research = load_research(workspace)
    ideation = load_ideation(workspace)
    selected_title = _resolve_selected_title(manifest, ideation, research, args.title)
    outline_context, normalize_context, _editorial_blueprint, writing_persona = _build_outline_generation_contexts(
        workspace,
        manifest,
        ideation,
        research,
        selected_title,
    )
    outline, outline_fingerprint, fingerprint_findings = _generate_outline_with_collision_retry(
        provider,
        workspace,
        manifest,
        selected_title,
        outline_context,
        normalize_context,
    )
    _persist_outline_result(
        workspace,
        manifest,
        ideation,
        research,
        selected_title,
        outline,
        outline_fingerprint,
        fingerprint_findings,
        writing_persona,
    )
    print(json.dumps(outline, ensure_ascii=False, indent=2))
    return 0


def cmd_enhance(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace, args)
    ideation = load_ideation(workspace)
    selected_title = args.title or manifest.get("selected_title") or ideation.get("selected_title") or manifest.get("topic") or "未命名标题"
    if not ideation.get("outline_meta"):
        editorial_blueprint = current_editorial_blueprint(workspace, manifest, ideation)
        ideation["outline_meta"] = normalize_outline_payload(
            {
                "title": selected_title,
                "sections": ideation.get("outline") or [],
                "viral_blueprint": ideation.get("viral_blueprint") or manifest.get("viral_blueprint") or {},
                "editorial_blueprint": ideation.get("editorial_blueprint") or editorial_blueprint,
            },
            {
                "topic": manifest.get("topic") or selected_title,
                "selected_title": selected_title,
                "audience": manifest.get("audience") or "大众读者",
                "direction": manifest.get("direction") or "",
                "research": load_research(workspace),
                "style_signals": manifest.get("style_signals") or [],
                "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
                "content_mode": manifest.get("content_mode") or "tech-balanced",
                "editorial_blueprint": editorial_blueprint,
                "author_memory": manifest.get("author_memory") or {},
            },
        )
        write_json(workspace / "ideation.json", ideation)
    payload = ensure_content_enhancement(workspace, manifest, ideation, selected_title=selected_title, force=True)
    manifest["writing_persona"] = current_writing_persona(workspace, manifest, ideation)
    manifest["content_enhancement_path"] = "content-enhancement.json"
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace, args)
    batch_guidance = ensure_batch_guidance(workspace, manifest, force=True)
    provider = require_live_text_provider("write")
    research = load_research(workspace)
    ideation = load_ideation(workspace)
    selected_title = _resolve_selected_title(manifest, ideation, research, args.title)
    outline_meta, layout_plan, editorial_blueprint, writing_persona = _normalize_write_outline_meta(
        workspace,
        manifest,
        ideation,
        research,
        selected_title,
        args.outline_file,
    )
    write_json(workspace / "ideation.json", ideation)
    content_enhancement = ensure_content_enhancement(workspace, manifest, ideation, selected_title=selected_title, force=True)
    manifest["content_enhancement"] = content_enhancement
    generation_strategy = ideation.get("generation_strategy") or build_generation_strategy(
        title=selected_title,
        manifest=manifest,
        batch_guidance=batch_guidance,
        outline_meta=outline_meta,
    )
    ideation["generation_strategy"] = generation_strategy
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
            "style_samples": manifest.get("style_sample_paths") or [],
            "style_signals": manifest.get("style_signals") or [],
            "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
            "recent_article_titles": manifest.get("recent_article_titles") or [],
            "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
            "corpus_root": manifest.get("corpus_root") or "",
            "content_mode": manifest.get("content_mode") or "tech-balanced",
            "editorial_blueprint": outline_meta.get("editorial_blueprint") or editorial_blueprint,
            "author_memory": manifest.get("author_memory") or {},
            "layout_plan": layout_plan,
            "writing_persona": ideation.get("writing_persona") or writing_persona,
            "content_enhancement": content_enhancement,
            "account_strategy": manifest.get("account_strategy") or {},
            "batch_guidance": batch_guidance,
            "generation_strategy": generation_strategy,
        }
    )
    body = str(result.payload).strip()
    body = strip_leading_h1(body, selected_title)
    body, preflight = harden_generated_article_body(
        workspace,
        manifest,
        selected_title,
        build_article_summary(selected_title, body),
        body,
        outline_meta=outline_meta,
        allow_model_repair=True,
    )
    article_path = workspace / "article.md"
    write_text(article_path, join_frontmatter({"title": selected_title, "summary": build_article_summary(selected_title, body)}, body))
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    summary = synced_meta.get("summary") or build_article_summary(selected_title, synced_body or body)
    manifest.update(
        {
            "selected_title": selected_title,
            "summary": summary,
            "article_path": "article.md",
            "outline": [item.get("heading", "") for item in (outline_meta.get("sections") or [])],
            "viral_blueprint": outline_meta.get("viral_blueprint") or {},
            "editorial_blueprint": outline_meta.get("editorial_blueprint") or {},
            "writing_persona": ideation.get("writing_persona") or writing_persona,
            "text_provider": result.provider,
            "text_model": result.model,
            "generation_preflight_path": "generation-preflight.json",
            "generation_preflight_status": "fixed" if preflight.get("used_repaired_body") else "passed",
            "content_enhancement_path": "content-enhancement.json",
        }
    )
    _apply_article_quality_status(
        workspace,
        manifest,
        title=selected_title,
        summary=summary,
        body=synced_body or body,
        layout_plan=layout_plan,
    )
    write_content_fingerprint_artifact(workspace, selected_title, synced_body or body, manifest, layout_plan=layout_plan)
    update_stage(manifest, "draft", "draft_status")
    save_manifest(workspace, manifest)
    print(str(article_path))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace, args)
    batch_guidance = ensure_batch_guidance(workspace, manifest, force=True)
    runtime = _prepare_article_runtime(workspace, manifest)
    article = runtime.article
    meta, body, title = article.meta, article.body, article.title
    blueprint = current_viral_blueprint(workspace, manifest)
    content_enhancement = runtime.content_enhancement
    layout_plan = runtime.layout_plan
    manifest["content_enhancement"] = content_enhancement
    writing_persona = runtime.writing_persona
    generation_strategy = build_generation_strategy(
        title=title,
        manifest=manifest,
        batch_guidance=batch_guidance,
        body=body,
    )
    provider = active_text_provider()
    if provider.configured():
        result = provider.review_article(
            {
                "title": title,
                "audience": manifest.get("audience") or "大众读者",
                "direction": manifest.get("direction") or "",
                "summary": article.summary,
                "article_body": body,
                "viral_blueprint": blueprint,
                "editorial_blueprint": current_editorial_blueprint(workspace, manifest),
                "style_samples": manifest.get("style_sample_paths") or [],
                "style_signals": manifest.get("style_signals") or [],
                "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
                "recent_article_titles": manifest.get("recent_article_titles") or [],
                "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
                "corpus_root": manifest.get("corpus_root") or "",
                "revision_round": int(manifest.get("revision_round") or 1),
                "content_mode": manifest.get("content_mode") or "tech-balanced",
                "author_memory": manifest.get("author_memory") or {},
                "layout_plan": layout_plan,
                "writing_persona": writing_persona,
                "content_enhancement": content_enhancement,
                "account_strategy": manifest.get("account_strategy") or {},
                "batch_guidance": batch_guidance,
                "generation_strategy": generation_strategy,
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
    payload["generation_strategy"] = build_generation_strategy(
        title=title,
        manifest=manifest,
        batch_guidance=batch_guidance,
        body=body,
        analysis_11d=payload.get("analysis_11d") or {},
    )
    payload["schema_version"] = PIPELINE_SCHEMA_VERSION
    payload["body_signature"] = article_body_signature(title, body)
    payload["generated_at"] = now_iso()
    write_editorial_anchor_plan(workspace, manifest, title=title, review_report=payload, score_report=read_json(workspace / "score-report.json", default={}) or {})
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
        "analysis_11d": report.get("analysis_11d") or {},
        "generation_strategy": build_generation_strategy(
            title=title,
            manifest=manifest,
            analysis_11d=report.get("analysis_11d") or {},
            batch_guidance=manifest.get("batch_guidance") or {},
        ),
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


def _apply_article_quality_status(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    title: str,
    summary: str,
    body: str,
    review: dict[str, Any] | None = None,
    layout_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    status = _update_manifest_quality_status(
        workspace,
        manifest,
        title=title,
        summary=summary,
        body=body,
        review=review,
        layout_plan=layout_plan,
    )
    return status


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
    manifest = _prepare_content_manifest(workspace, args)
    runtime = _prepare_article_runtime(workspace, manifest)
    article = runtime.article
    meta, body, title = article.meta, article.body, article.title
    manifest["writing_persona"] = runtime.writing_persona
    manifest["content_enhancement"] = runtime.content_enhancement
    report = read_json(workspace / "score-report.json", default={}) or {}
    current_signature = article_body_signature(title, body)
    if report and str(report.get("body_signature") or "").strip() not in {"", current_signature}:
        report = {}
    if not report:
        threshold = manifest.get("score_threshold") or legacy.DEFAULT_THRESHOLD
        report = legacy.build_score_report(title, body, manifest, threshold)
    report = apply_research_credibility_boost(report, load_research(workspace))
    report["schema_version"] = PIPELINE_SCHEMA_VERSION
    report["body_signature"] = current_signature
    write_json(workspace / "score-report.json", report)
    legacy.write_text(workspace / "score-report.md", legacy.markdown_report(report))
    manifest["score_report_path"] = "score-report.json"
    manifest["score_total"] = report["total_score"]
    manifest["score_passed"] = report["passed"]
    mode = (getattr(args, "mode", None) or "improve-score").strip().lower().replace("_", "-")
    if mode == "explosive-score":
        mode = "stage-1"
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
    manifest = _prepare_content_manifest(workspace, include_corpus=True, include_author_memory=False)
    raw = read_input_file(args.input)
    meta, body = split_frontmatter(raw)
    title = args.selected_title or manifest.get("selected_title") or meta.get("title") or legacy.extract_title_from_body(body) or manifest.get("topic") or "未命名文章"
    body = strip_leading_h1(body, title)
    summary = args.summary or meta.get("summary") or manifest.get("summary") or build_article_summary(title, body)
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
    _apply_article_quality_status(
        workspace,
        manifest,
        title=title,
        summary=str(manifest.get("summary") or summary),
        body=synced_body or body,
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
        write_acceptance_artifacts(workspace, manifest)
        write_delivery_report(workspace, manifest)
        save_manifest(workspace, manifest)
        blockers = collect_publish_blockers(workspace, manifest)
        force_publish = bool(getattr(args, "force_publish", False))
        force_reason = str(getattr(args, "force_reason", "") or "").strip()
        if blockers and not force_publish:
            detail = "\n".join(f"- {item}" for item in blockers)
            raise SystemExit(f"当前稿件不满足正式发布条件：\n{detail}")
        if blockers and force_publish:
            if not force_reason:
                raise SystemExit("强制发布需要同时传入 --force-reason，说明为什么仍要继续发布。")
            manifest["force_publish_reason"] = force_reason
            manifest["force_publish_at"] = now_iso()
            save_manifest(workspace, manifest)
        _mark_publish_intent(workspace)
    rc = wechat_publish(args)
    manifest = load_manifest(workspace)
    write_delivery_report(workspace, manifest)
    save_manifest(workspace, manifest)
    return rc


def cmd_verify_draft(args: argparse.Namespace) -> int:
    rc = wechat_verify_draft(args)
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    write_delivery_report(workspace, manifest)
    save_manifest(workspace, manifest)
    return rc


def cmd_doctor(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve()
    provider = active_text_provider()
    humanizer = HumanizerAIClient.from_env()
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
            "gemini-web": legacy.doctor_provider_status("gemini-web"),
            "codex": legacy.doctor_provider_status("codex"),
            "gemini-api": legacy.doctor_provider_status("gemini-api"),
            "openai-image": legacy.doctor_provider_status("openai-image"),
        },
        "de_ai_bridge": {
            "humanizerai": humanizer.doctor_status(),
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
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = attach_account_strategy(workspace, manifest)
    manifest = attach_corpus_context(workspace, manifest)
    manifest = attach_author_memory(workspace, manifest)
    window_hours = int(args.window_hours or 24)
    limit = int(args.limit or legacy.DISCOVERY_TOPIC_LIMIT)
    provider = getattr(args, "provider", None)
    focus = getattr(args, "focus", None)
    rss_urls = list(getattr(args, "rss_url", None) or [])
    payload = legacy.discover_recent_topics(
        window_hours=window_hours,
        limit=limit,
        provider=provider,
        focus=focus,
        rss_urls=rss_urls,
    )
    payload["candidates"] = rerank_discovery_candidates(
        list(payload.get("candidates") or []),
        manifest.get("recent_article_titles") or [],
        manifest.get("recent_corpus_summary") or {},
        manifest.get("author_memory") or {},
        manifest.get("account_strategy") or {},
    )[:limit]
    legacy.write_topic_discovery_artifacts(workspace, payload)
    manifest["topic_discovery_path"] = "topic-discovery.json"
    manifest["topic_discovery_provider"] = payload.get("provider") or legacy.normalize_discovery_provider(provider)
    manifest["topic_discovery_focus"] = payload.get("focus") or legacy.normalize_discovery_focus(focus)
    controls = dict(manifest.get("image_controls") or {})
    strategy = manifest.get("account_strategy") or {}
    controls.setdefault("density", str(strategy.get("image_density") or "balanced"))
    controls.setdefault("layout_family", str(strategy.get("image_layout_family") or "editorial"))
    manifest["image_controls"] = controls
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _reset_manifest_progress(manifest: dict[str, Any]) -> None:
    manifest["stage"] = "initialized"
    for key in MANIFEST_STATUS_DEFAULTS:
        if key == "stage":
            continue
        manifest[key] = "not_started"
    # Reset revision-related state on topic change.
    for key in [
        "revision_round",
        "revision_rounds",
        "stop_reason",
        "best_round",
        "viral_blueprint",
        "editorial_blueprint",
        "writing_persona",
        "content_enhancement_path",
        "humanness_signals",
        "viral_selection",
        "viral_query",
        "viral_selected_count",
        "viral_discovery_path",
        "source_corpus_path",
        "viral_dna_path",
        "similarity_report_path",
        "versions_manifest_path",
    ]:
        manifest.pop(key, None)


def _recommended_viral_indexes(discovery: dict[str, Any]) -> list[int]:
    recommended = list(discovery.get("recommended_selection") or [])
    if recommended:
        ids = [str(item.get("source_id") or "") for item in recommended]
        indexes: list[int] = []
        for idx, candidate in enumerate(discovery.get("candidates") or [], start=1):
            if str(candidate.get("source_id") or "") in ids:
                indexes.append(idx)
        if indexes:
            return indexes[:5]
    return list(range(1, min(5, len(discovery.get("candidates") or [])) + 1))


def _selected_viral_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    items = manifest.get("viral_selection") or []
    return list(items) if isinstance(items, list) else []


def _clear_workspace_paths(workspace: Path, rel_paths: list[str]) -> None:
    for rel in rel_paths:
        target = workspace / rel
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            try:
                target.unlink()
            except OSError:
                pass


def _viral_query_changed(workspace: Path, manifest: dict[str, Any], query: str) -> bool:
    query_text = str(query or "").strip()
    if not query_text:
        return False
    existing_query = str(manifest.get("viral_query") or "").strip()
    existing_topic = str(manifest.get("topic") or "").strip()
    if existing_query and existing_query != query_text:
        return True
    if existing_topic and existing_topic != query_text:
        for rel in ["source-corpus.json", "viral-dna.json", "article.md", "score-report.json", "versions"]:
            if (workspace / rel).exists():
                return True
    return False


def _reset_for_new_viral_query(workspace: Path, manifest: dict[str, Any], query: str) -> None:
    _reset_manifest_progress(manifest)
    _clear_workspace_paths(workspace, VIRAL_QUERY_RESET_PATHS)
    manifest.update(
        {
            "topic": str(query or "").strip(),
            "direction": "",
            "selected_title": "",
            "source_urls": [],
        }
    )
    for key in [
        "viral_query",
        "viral_selection",
        "viral_selected_count",
        "research_requirements",
        "title_score",
        "title_gate_passed",
        "score_total",
        "score_passed",
        "rewrite_path",
        "rewrite_preview_score",
        "rewrite_preview_passed",
        "evidence_report_path",
        "evidence_used_count",
        "versions_manifest_path",
    ]:
        manifest.pop(key, None)


def _similarity_blockers(workspace: Path) -> list[str]:
    report = read_json(workspace / "similarity-report.json", default={}) or {}
    if report.get("available") and not bool(report.get("passed")):
        failed = list(report.get("failed_items") or [])
        if failed:
            details = "；".join(
                f"{item.get('title')}({', '.join(item.get('failures') or [])})" for item in failed[:3]
            )
            return [f"与爆款样本相似度未通过：{details}"]
        return ["与爆款样本相似度未通过"]
    return []


def _write_viral_analysis_payload(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    topic: str,
    angle: str,
    audience: str,
    content_mode: str,
) -> dict[str, Any]:
    corpus = load_source_corpus(workspace)
    payload = analyze_source_corpus(
        corpus,
        topic=topic,
        angle=angle,
        audience=audience,
        content_mode=content_mode,
        account_strategy=manifest.get("account_strategy") or {},
    )
    _update_research_requirements(workspace, manifest, payload["research"])
    write_research_from_viral_analysis(workspace, payload)
    manifest.update(
        {
            "topic": payload["research"].get("topic") or topic,
            "direction": payload["research"].get("angle") or angle,
            "audience": payload["research"].get("audience") or audience,
            "source_urls": [str(item.get("url") or "").strip() for item in (payload["research"].get("sources") or []) if str(item.get("url") or "").strip()],
            "research_path": "research.json",
            "source_corpus_path": "source-corpus.json",
            "viral_dna_path": "viral-dna.json",
            "text_provider": "viral-pipeline",
            "text_model": "heuristic",
            "viral_blueprint": payload["dna"].get("viral_blueprint") or manifest.get("viral_blueprint") or {},
            "editorial_blueprint": payload["dna"].get("editorial_blueprint") or manifest.get("editorial_blueprint") or {},
            "writing_persona": payload["dna"].get("writing_persona") or manifest.get("writing_persona") or {},
        }
    )
    update_stage(manifest, "research", "research_status")
    save_manifest(workspace, manifest)
    return payload


def cmd_select_topic(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = attach_account_strategy(workspace, manifest)

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
    recommended_archetype = str(candidate.get("recommended_archetype") or "").strip()
    recommended_enhancement_strategy = str(candidate.get("recommended_enhancement_strategy") or "").strip()

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
            "article_archetype": recommended_archetype or manifest.get("article_archetype") or "",
            "recommended_enhancement_strategy": recommended_enhancement_strategy or manifest.get("recommended_enhancement_strategy") or "",
            "writeability_score": candidate.get("writeability_score"),
            "evidence_potential": candidate.get("evidence_potential"),
            "topic_score_100": candidate.get("topic_score_100"),
            "topic_score_dimensions": candidate.get("topic_score_dimensions") or {},
            "topic_gate_passed": candidate.get("topic_gate_passed"),
            "topic_novelty_reason": candidate.get("novelty_reason") or "",
        }
    )

    ideation = read_json(workspace / "ideation.json", default={}) or {}
    ideation.update(
        {
            "topic": new_topic,
            "direction": angle,
            "selected_title": selected_title,
            "updated_at": now_iso(),
            "recommended_archetype": recommended_archetype,
            "recommended_enhancement_strategy": recommended_enhancement_strategy,
            "topic_score_100": candidate.get("topic_score_100"),
            "topic_score_dimensions": candidate.get("topic_score_dimensions") or {},
            "topic_gate_passed": candidate.get("topic_gate_passed"),
        }
    )
    write_json(workspace / "ideation.json", ideation)
    sync_title_truth(workspace, manifest, selected_title)
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


def cmd_discover_viral(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = attach_account_strategy(workspace, manifest)
    query = str(getattr(args, "query", "") or getattr(args, "topic", "") or manifest.get("topic") or manifest.get("selected_title") or "").strip()
    if not query:
        raise SystemExit("discover-viral 需要 --query，或当前工作目录里已有 topic。")
    if _viral_query_changed(workspace, manifest, query):
        _reset_for_new_viral_query(workspace, manifest, query)
    platforms = list(getattr(args, "platform", None) or VIRAL_PLATFORM_CHOICES)
    payload = discover_viral_candidates(
        query,
        platforms=platforms,
        limit_per_platform=int(getattr(args, "limit_per_platform", 6) or 6),
        account_strategy=manifest.get("account_strategy") or {},
    )
    write_discovery_artifacts(workspace, payload)
    manifest["viral_query"] = query
    manifest["topic"] = query
    manifest["viral_discovery_path"] = "viral-discovery.json"
    manifest["source_urls"] = [str(item.get("url") or "").strip() for item in (payload.get("recommended_selection") or []) if str(item.get("url") or "").strip()]
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_select_viral(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = attach_account_strategy(workspace, manifest)
    discovery = load_viral_discovery(workspace)
    if not discovery:
        raise SystemExit("找不到 viral-discovery.json，请先运行 discover-viral。")
    indexes = list(getattr(args, "index", None) or [])
    if not indexes:
        indexes = _recommended_viral_indexes(discovery)
    selected = select_viral_candidates(discovery, [int(item) for item in indexes])
    query = str(discovery.get("query") or manifest.get("viral_query") or manifest.get("topic") or "").strip()
    if str(manifest.get("viral_query") or "").strip() and str(manifest.get("viral_query") or "").strip() != query:
        _reset_manifest_progress(manifest)
    source_urls = [str(item.get("url") or "").strip() for item in selected if str(item.get("url") or "").strip()]
    manifest.update(
        {
            "viral_query": query,
            "viral_selection": selected,
            "viral_selected_count": len(selected),
            "viral_discovery_path": "viral-discovery.json",
            "source_urls": source_urls,
        }
    )
    if not str(manifest.get("topic") or "").strip():
        manifest["topic"] = query
    save_manifest(workspace, manifest)
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "query": query,
                "selected_indexes": indexes,
                "selected_count": len(selected),
                "source_urls": source_urls,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_collect_viral(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = attach_account_strategy(workspace, manifest)
    selected = _selected_viral_from_manifest(manifest)
    if not selected and list(getattr(args, "index", None) or []):
        discovery = load_viral_discovery(workspace)
        selected = select_viral_candidates(discovery, [int(item) for item in list(getattr(args, "index", None) or [])])
        manifest["viral_selection"] = selected
    if not selected:
        raise SystemExit("collect-viral 找不到已选样本。请先运行 select-viral。")
    payload = collect_source_corpus(selected)
    write_source_corpus_artifacts(workspace, payload)
    manifest["source_corpus_path"] = "source-corpus.json"
    manifest["source_urls"] = [str(item.get("url") or "").strip() for item in (payload.get("items") or []) if str(item.get("url") or "").strip()]
    manifest["viral_selection"] = list(payload.get("items") or [])
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_analyze_viral(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace, args, include_corpus=False, include_author_memory=True)
    corpus = load_source_corpus(workspace)
    if not corpus:
        raise SystemExit("analyze-viral 找不到 source-corpus.json，请先运行 collect-viral。")
    topic = str(getattr(args, "topic", "") or manifest.get("topic") or manifest.get("viral_query") or "").strip()
    if not topic:
        raise SystemExit("analyze-viral 需要 topic；请传 --topic 或先在工作目录里设好 topic。")
    angle = str(getattr(args, "angle", "") or manifest.get("direction") or "").strip()
    audience = str(getattr(args, "audience", "") or manifest.get("audience") or "大众读者").strip()
    payload = _write_viral_analysis_payload(
        workspace,
        manifest,
        topic=topic,
        angle=angle,
        audience=audience,
        content_mode=manifest.get("content_mode") or "tech-balanced",
    )
    print(json.dumps(payload["dna"], ensure_ascii=False, indent=2))
    return 0


def cmd_adapt_platforms(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace, args)
    article_path = workspace / str(manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到正文：{article_path}")
    raw_article = read_text(article_path)
    meta, body = split_frontmatter(raw_article)
    selected_title = str(getattr(args, "title", "") or manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名标题").strip()
    summary = str(getattr(args, "summary", "") or meta.get("summary") or manifest.get("summary") or extract_summary(body)).strip()
    versions_manifest = write_platform_versions(
        workspace,
        article_text=raw_article,
        selected_title=selected_title,
        summary=summary,
        dna_payload=load_viral_dna(workspace),
    )
    manifest["versions_manifest_path"] = "versions/manifest.json"
    save_manifest(workspace, manifest)
    print(json.dumps(versions_manifest, ensure_ascii=False, indent=2))
    return 0


def cmd_viral_run(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest, style_sample = _prepare_run_manifest(workspace, args)
    topic = str(getattr(args, "topic", "") or manifest.get("topic") or manifest.get("selected_title") or "").strip()
    query = str(getattr(args, "query", "") or topic).strip()
    if not query:
        raise SystemExit("viral-run 需要 --query 或 --topic。")
    cmd_discover_viral(
        argparse.Namespace(
            workspace=str(workspace),
            query=query,
            topic=topic,
            platform=list(getattr(args, "platform", None) or VIRAL_PLATFORM_CHOICES),
            limit_per_platform=int(getattr(args, "limit_per_platform", 6) or 6),
        )
    )
    discovery = load_viral_discovery(workspace)
    indexes = list(getattr(args, "index", None) or []) or _recommended_viral_indexes(discovery)
    cmd_select_viral(argparse.Namespace(workspace=str(workspace), index=indexes))
    cmd_collect_viral(argparse.Namespace(workspace=str(workspace), index=[]))
    cmd_analyze_viral(
        argparse.Namespace(
            workspace=str(workspace),
            topic=topic or query,
            angle=getattr(args, "angle", None),
            audience=getattr(args, "audience", None),
            style_sample=style_sample,
            content_mode=manifest.get("content_mode") or "tech-balanced",
            wechat_header_mode=manifest.get("wechat_header_mode") or "drop-title",
        )
    )

    if not (workspace / "ideation.json").exists() or not load_ideation(workspace).get("titles"):
        cmd_titles(argparse.Namespace(workspace=str(workspace), count=args.title_count, selected_title=None))
    ideation = load_ideation(workspace)
    if not ideation.get("outline"):
        cmd_outline(argparse.Namespace(workspace=str(workspace), title=args.title or ideation.get("selected_title"), style_sample=style_sample))
        ideation = load_ideation(workspace)
    current_title = args.title or ideation.get("selected_title")
    cmd_enhance(
        argparse.Namespace(
            workspace=str(workspace),
            title=current_title,
            style_sample=style_sample,
            content_mode=manifest.get("content_mode") or "tech-balanced",
            wechat_header_mode=manifest.get("wechat_header_mode") or "drop-title",
        )
    )
    if not (workspace / "article.md").exists():
        cmd_write(argparse.Namespace(workspace=str(workspace), title=current_title, outline_file=None, style_sample=style_sample))
    score_report = _run_revision_loop(workspace, max_rounds=int(getattr(args, "max_revision_rounds", 3) or 3), style_sample=style_sample)
    manifest = load_manifest(workspace)
    _finalize_after_score(workspace, manifest, manifest.get("selected_title") or topic or query, score_report)
    render_blockers = collect_render_blockers(workspace, manifest, score_report)
    if render_blockers:
        detail = "\n".join(f"- {item}" for item in render_blockers)
        raise SystemExit(f"当前稿件不满足 render 前置条件：\n{detail}")
    _run_image_render_pipeline(workspace, manifest, args)
    cmd_adapt_platforms(argparse.Namespace(workspace=str(workspace), title=None, summary=None, style_sample=[]))
    return 0


def _merge_url_list(base: list[str], extra: list[str]) -> list[str]:
    merged = normalize_urls([*base, *extra])
    return merged


def cmd_prepare_publication(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace, args, include_corpus=False, include_author_memory=False)
    payload = render_prepare_publication_artifacts(workspace, manifest, input_rel=getattr(args, "input", None))
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_evidence(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = attach_account_strategy(workspace, manifest)

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
    _update_research_requirements(workspace, manifest, research)
    write_json(research_path, research)
    save_manifest(workspace, manifest)

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


def cmd_build_playbook(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    manifest = persist_style_samples(workspace, manifest, getattr(args, "style_sample", None))
    explicit_samples = [Path(path) for path in (manifest.get("style_sample_paths") or []) if Path(path).exists()]
    article_paths = explicit_samples[:]
    if getattr(args, "include_recent_corpus", False):
        manifest = attach_corpus_context(workspace, manifest)
        article_paths.extend(recent_article_paths(detect_corpus_roots(workspace), workspace))
    lesson_patterns = manifest.get("author_lesson_patterns") or []
    payload = build_playbook_payload(article_paths, lesson_patterns=lesson_patterns)
    if int(payload.get("source_count") or 0) <= 0:
        raise SystemExit("build-playbook 没读到任何有效样本。请传入可访问的 --style-sample，或加上 --include-recent-corpus。")
    output_base = (workspace / "style-playbook").resolve()
    write_playbook_artifacts(output_base, payload)
    manifest["author_playbook_paths"] = [str(output_base.with_suffix(".json"))]
    manifest = attach_author_memory(workspace, manifest)
    save_manifest(workspace, manifest)
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "source_count": payload.get("source_count") or 0,
                "playbook_json": str(output_base.with_suffix(".json")),
                "playbook_md": str(output_base.with_suffix(".md")),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_learn_edits(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    draft_path = Path(args.draft).resolve()
    final_path = Path(args.final).resolve()
    if not draft_path.exists():
        raise SystemExit(f"找不到 draft 文件：{draft_path}")
    if not final_path.exists():
        raise SystemExit(f"找不到 final 文件：{final_path}")
    payload = compute_edit_lesson_payload(read_text(draft_path), read_text(final_path))
    lesson_path = workspace / "author-lessons.json"
    summary = append_lesson_payload(lesson_path, payload)
    manifest["author_lesson_paths"] = [str(lesson_path.resolve())]
    manifest = attach_author_memory(workspace, manifest)
    save_manifest(workspace, manifest)
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "lesson_file": str(lesson_path),
                "patterns": payload.get("patterns") or [],
                "total_patterns": summary.get("patterns") or [],
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
    return None


def _sync_image_controls(workspace: Path, args: argparse.Namespace) -> None:
    manifest = load_manifest(workspace)
    manifest = attach_account_strategy(workspace, manifest)
    controls = legacy.resolve_image_controls(manifest.get("image_controls"), args)
    strategy = manifest.get("account_strategy") or {}
    density_mode = legacy.normalize_image_density_mode(controls.get("density_mode") or controls.get("density") or strategy.get("image_density") or "auto")
    controls.setdefault("density_mode", density_mode)
    controls["density"] = density_mode
    controls.setdefault("allow_closing_image", "auto")
    manifest["image_controls"] = controls
    save_manifest(workspace, manifest)


def _write_hosted_research(workspace: Path, manifest: dict[str, Any], topic: str, angle: str, audience: str, source_urls: list[str]) -> None:
    manifest = attach_account_strategy(workspace, manifest)
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
    _update_research_requirements(workspace, manifest, payload)
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
    manifest = attach_account_strategy(workspace, manifest)
    manifest = attach_corpus_context(workspace, manifest)
    manifest = attach_author_memory(workspace, manifest)
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
                "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
                "content_mode": manifest.get("content_mode") or "tech-balanced",
                "editorial_blueprint": current_editorial_blueprint(workspace, manifest, ideation),
                "author_memory": manifest.get("author_memory") or {},
            },
        )
        ideation["outline_meta"] = outline_meta
        ideation["viral_blueprint"] = outline_meta.get("viral_blueprint") or {}
        ideation["editorial_blueprint"] = outline_meta.get("editorial_blueprint") or {}
        manifest["viral_blueprint"] = outline_meta.get("viral_blueprint") or {}
        manifest["editorial_blueprint"] = outline_meta.get("editorial_blueprint") or {}
        layout_plan = build_layout_plan(
            title,
            extract_summary("\n".join(str(item.get("goal") or "") for item in (outline_meta.get("sections") or []))),
            outline_meta,
            manifest | {"viral_blueprint": outline_meta.get("viral_blueprint") or {}},
        )
        write_json(workspace / "layout-plan.json", layout_plan)
        write_text(workspace / "layout-plan.md", markdown_layout_plan(layout_plan))
        manifest["layout_plan_path"] = "layout-plan.json"
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
        editorial_blueprint = current_editorial_blueprint(workspace, manifest, ideation)
        ideation["editorial_blueprint"] = editorial_blueprint
        manifest["editorial_blueprint"] = editorial_blueprint
    write_json(workspace / "ideation.json", ideation)
    manifest["selected_title"] = title
    sync_title_truth(workspace, manifest, title)
    manifest["content_mode"] = manifest.get("content_mode") or "tech-balanced"
    if outline_items:
        manifest["outline"] = outline_items
        update_stage(manifest, "outline", "outline_status")
    update_stage(manifest, "titles", "title_status")


def _ensure_hosted_titles(workspace: Path, manifest: dict[str, Any], topic: str, audience: str, angle: str, requested_title: str = "") -> None:
    manifest = attach_account_strategy(workspace, manifest)
    ideation = load_ideation(workspace)
    writing_persona = current_writing_persona(workspace, manifest, ideation)
    if not ideation.get("titles"):
        provider = active_text_provider()
        research = load_research(workspace)
        if provider.configured():
            result = provider.generate_titles(
                {
                    "topic": topic,
                    "audience": audience,
                    "angle": angle,
                    "count": 10,
                    "research": research,
                    "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
                    "recent_article_titles": manifest.get("recent_article_titles") or [],
                    "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
                    "editorial_blueprint": current_editorial_blueprint(workspace, manifest, ideation),
                    "author_memory": manifest.get("author_memory") or {},
                    "writing_persona": writing_persona,
                    "account_strategy": manifest.get("account_strategy") or {},
                }
            )
            if isinstance(result.payload, list):
                titles = result.payload[:10]
            elif isinstance(result.payload, dict):
                titles = (result.payload.get("candidates") or result.payload.get("titles") or [])[:10]
            else:
                titles = []
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
                    "titles": generate_diverse_title_variants(
                        topic,
                        angle,
                        audience,
                        editorial_blueprint=current_editorial_blueprint(workspace, manifest, ideation),
                        recent_titles=manifest.get("recent_article_titles") or [],
                        recent_corpus_summary=manifest.get("recent_corpus_summary") or {},
                        writing_persona=writing_persona,
                        account_strategy=manifest.get("account_strategy") or {},
                        count=10,
                    ),
                    "updated_at": now_iso(),
                    "provider": "local-heuristic",
                    "model": "builtin",
                }
            )
    ideation["writing_persona"] = writing_persona
    manifest["writing_persona"] = writing_persona
    ideation, _ = select_scored_title(workspace, manifest, ideation, topic, audience, angle, requested_title)
    write_json(workspace / "ideation.json", ideation)


def _bootstrap_hosted_article(workspace: Path, manifest: dict[str, Any], topic: str, title: str, angle: str, audience: str) -> str:
    manifest = attach_account_strategy(workspace, manifest)
    manifest = attach_corpus_context(workspace, manifest)
    manifest = attach_author_memory(workspace, manifest)
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
                "account_strategy": manifest.get("account_strategy") or {},
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
        default_editorial_blueprint = current_editorial_blueprint(workspace, manifest, ideation)
        writing_persona = current_writing_persona(workspace, manifest, ideation)
        title_result = provider.generate_titles(
            {
                "topic": topic,
                "audience": audience,
                "angle": angle,
                "count": 10,
                "research": research,
                "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
                "recent_article_titles": manifest.get("recent_article_titles") or [],
                "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
                "editorial_blueprint": default_editorial_blueprint,
                "author_memory": manifest.get("author_memory") or {},
                "writing_persona": writing_persona,
                "account_strategy": manifest.get("account_strategy") or {},
            }
        )
        if isinstance(title_result.payload, list):
            titles = title_result.payload[:10]
        elif isinstance(title_result.payload, dict):
            titles = (title_result.payload.get("candidates") or title_result.payload.get("titles") or [])[:10]
        else:
            titles = []
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
        ideation, _ = select_scored_title(workspace, manifest, ideation, topic, audience, angle, title)
        write_json(workspace / "ideation.json", ideation)
        manifest["selected_title"] = ideation.get("selected_title") or title
        manifest["writing_persona"] = writing_persona
        update_stage(manifest, "titles", "title_status")
    title = title or ideation.get("selected_title") or manifest.get("selected_title") or topic

    outline_meta = dict(ideation.get("outline_meta") or {})
    if not outline_meta.get("sections"):
        default_editorial_blueprint = current_editorial_blueprint(workspace, manifest, ideation)
        writing_persona = current_writing_persona(workspace, manifest, ideation)
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
                "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
                "corpus_root": manifest.get("corpus_root") or "",
                "content_mode": manifest.get("content_mode") or "tech-balanced",
                "editorial_blueprint": default_editorial_blueprint,
                "author_memory": manifest.get("author_memory") or {},
                "writing_persona": writing_persona,
                "account_strategy": manifest.get("account_strategy") or {},
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
                "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
                "content_mode": manifest.get("content_mode") or "tech-balanced",
                "editorial_blueprint": default_editorial_blueprint,
                "author_memory": manifest.get("author_memory") or {},
                "writing_persona": writing_persona,
                "account_strategy": manifest.get("account_strategy") or {},
            },
        )
        if not outline_meta.get("sections"):
            outline_meta = placeholder_outline(title)
        ideation["selected_title"] = title
        ideation["outline"] = outline_meta.get("sections") or []
        ideation["outline_meta"] = outline_meta
        ideation["viral_blueprint"] = outline_meta.get("viral_blueprint") or {}
        ideation["editorial_blueprint"] = outline_meta.get("editorial_blueprint") or {}
        ideation["writing_persona"] = normalize_writing_persona(
            writing_persona,
            {
                "topic": topic,
                "selected_title": title,
                "audience": audience,
                "direction": angle,
                "content_mode": manifest.get("content_mode") or "tech-balanced",
                "article_archetype": (outline_meta.get("viral_blueprint") or {}).get("article_archetype") or "",
                "author_memory": manifest.get("author_memory") or {},
            },
        )
        ideation["updated_at"] = now_iso()
        ideation["provider"] = outline_result.provider
        ideation["model"] = outline_result.model
        write_json(workspace / "ideation.json", ideation)
        manifest["outline"] = [item.get("heading", "") for item in outline_meta.get("sections") or []]
        manifest["viral_blueprint"] = outline_meta.get("viral_blueprint") or {}
        manifest["editorial_blueprint"] = outline_meta.get("editorial_blueprint") or {}
        manifest["writing_persona"] = ideation.get("writing_persona") or writing_persona
        update_stage(manifest, "outline", "outline_status")
    content_enhancement = ensure_content_enhancement(workspace, manifest, ideation, selected_title=title, force=True)

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
            "style_samples": manifest.get("style_sample_paths") or [],
            "style_signals": manifest.get("style_signals") or [],
            "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
            "recent_article_titles": manifest.get("recent_article_titles") or [],
            "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
            "corpus_root": manifest.get("corpus_root") or "",
            "content_mode": manifest.get("content_mode") or "tech-balanced",
            "editorial_blueprint": outline_meta.get("editorial_blueprint") or current_editorial_blueprint(workspace, manifest, ideation),
            "author_memory": manifest.get("author_memory") or {},
            "writing_persona": ideation.get("writing_persona") or current_writing_persona(workspace, manifest, ideation),
            "content_enhancement": content_enhancement,
            "account_strategy": manifest.get("account_strategy") or {},
        }
    )
    body = str(article_result.payload).strip()
    if not body:
        body = placeholder_article(title, outline_meta or placeholder_outline(title), audience)
    body = strip_leading_h1(body, title)
    body, preflight = harden_generated_article_body(
        workspace,
        manifest,
        title,
        build_article_summary(title, body),
        body,
        outline_meta=outline_meta,
        allow_model_repair=True,
    )
    write_text(workspace / "article.md", join_frontmatter({"title": title, "summary": build_article_summary(title, body)}, body))
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    summary = synced_meta.get("summary") or build_article_summary(title, synced_body or body)
    manifest.update(
        {
            "selected_title": title,
            "summary": summary,
            "article_path": "article.md",
            "text_provider": article_result.provider,
            "text_model": article_result.model,
            "generation_preflight_path": "generation-preflight.json",
            "generation_preflight_status": "fixed" if preflight.get("used_repaired_body") else "passed",
            "content_enhancement_path": "content-enhancement.json",
        }
    )
    _apply_article_quality_status(
        workspace,
        manifest,
        title=title,
        summary=summary,
        body=synced_body or body,
        layout_plan=layout_plan,
    )
    sync_title_truth(workspace, manifest, title)
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
    manifest = attach_account_strategy(workspace, manifest)
    manifest = attach_corpus_context(workspace, manifest)
    manifest = attach_author_memory(workspace, manifest)
    manifest["writing_persona"] = current_writing_persona(workspace, manifest)
    article_path = workspace / "article.md"
    if article_file:
        raw = read_input_file(article_file)
        meta, body = split_frontmatter(raw)
        title = title_hint or meta.get("title") or manifest.get("selected_title") or manifest.get("topic") or "未命名标题"
        body = strip_leading_h1(body, title)
        summary = summary_hint or meta.get("summary") or build_article_summary(title, body)
        write_text(article_path, join_frontmatter({"title": title, "summary": summary}, body))
    elif not article_path.exists():
        title = title_hint or manifest.get("selected_title") or manifest.get("topic") or "未命名标题"
        return _bootstrap_hosted_article(workspace, manifest, manifest.get("topic") or title, title, angle, audience)
    meta, body = split_frontmatter(read_text(article_path))
    title = title_hint or meta.get("title") or manifest.get("selected_title") or manifest.get("topic") or "未命名标题"
    summary = summary_hint or meta.get("summary") or build_article_summary(title, body)
    ensure_content_enhancement(workspace, manifest, load_ideation(workspace), selected_title=title, force=True)
    hardened_body, preflight = harden_generated_article_body(
        workspace,
        manifest,
        title,
        summary,
        strip_leading_h1(body, title),
        outline_meta=load_ideation(workspace).get("outline_meta") or {},
        allow_model_repair=True,
    )
    summary = summary_hint or build_article_summary(title, hardened_body)
    write_text(article_path, join_frontmatter({"title": title, "summary": summary}, hardened_body))
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    manifest.update(
        {
            "selected_title": title,
            "summary": synced_meta.get("summary") or summary,
            "article_path": "article.md",
            "text_provider": "host-agent",
            "text_model": "session",
            "generation_preflight_path": "generation-preflight.json",
            "generation_preflight_status": "fixed" if preflight.get("used_repaired_body") else "passed",
            "content_enhancement_path": "content-enhancement.json",
        }
    )
    _apply_article_quality_status(
        workspace,
        manifest,
        title=title,
        summary=str(manifest.get("summary") or summary),
        body=synced_body or hardened_body,
    )
    update_stage(manifest, "draft", "draft_status")
    return title


def _finalize_after_score(workspace: Path, manifest: dict[str, Any], title: str, score_report: dict[str, Any]) -> dict[str, Any]:
    manifest["score_status"] = "done"
    manifest["score_report_path"] = "score-report.json"
    manifest["score_total"] = score_report.get("total_score")
    manifest["score_passed"] = score_report.get("passed")
    manifest["humanness_signals"] = score_report.get("humanness_signals") or {}
    manifest["stage"] = "score"
    ensure_layout_plan_artifacts(workspace, manifest, title=title, force=True)
    review_payload = read_json(workspace / "review-report.json", default={}) or {}
    # Prefer the structured, real review if present; only fall back to score-derived review when missing.
    if not (isinstance(review_payload, dict) and review_payload.get("viral_analysis")):
        review_payload = build_review_from_score(title, score_report, manifest)
        write_review_report(workspace, manifest, review_payload)
    write_editorial_anchor_plan(workspace, manifest, title=title, review_report=review_payload, score_report=score_report)
    write_acceptance_artifacts(workspace, manifest)
    save_manifest(workspace, manifest)
    return review_payload


def _prepare_run_manifest(workspace: Path, args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    manifest = _prepare_content_manifest(workspace, args, include_corpus=False, include_author_memory=True)
    style_sample = list(manifest.get("style_sample_paths") or [])
    save_manifest(workspace, manifest)
    assert_publish_request_ready(args)
    return manifest, style_sample


def _run_image_render_pipeline(workspace: Path, manifest: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    _sync_image_controls(workspace, args)
    manifest = load_manifest(workspace)
    publication_report = render_prepare_publication_artifacts(workspace, manifest)
    original_article_path = str(manifest.get("article_path") or "article.md")
    publication_path = str(manifest.get("publication_path") or publication_report.get("output_path") or "publication.md")
    requested_inline_count = int(getattr(args, "inline_count", 0) or 0)
    inline_count = requested_inline_count or int(publication_report.get("inline_image_limit") or 0)
    ensure_layout_plan_artifacts(workspace, manifest, force=True)
    image_provider = _effective_image_provider(args)
    manifest["article_path"] = publication_path
    save_manifest(workspace, manifest)
    try:
        legacy_plan_images(
            argparse.Namespace(
                workspace=str(workspace),
                provider=image_provider,
                inline_count=inline_count,
                image_density=getattr(args, "image_density", None),
                allow_closing_image=getattr(args, "allow_closing_image", None),
            )
        )
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
    finally:
        manifest = load_manifest(workspace)
        manifest["article_path"] = original_article_path
        save_manifest(workspace, manifest)
    legacy_render(
        argparse.Namespace(
            workspace=str(workspace),
            input=None,
            output="article.html",
            accent_color=args.accent_color,
            layout_style=getattr(args, "layout_style", None),
            layout_skin=getattr(args, "layout_skin", None),
            input_format=getattr(args, "input_format", "auto"),
            wechat_header_mode=getattr(args, "wechat_header_mode", "drop-title"),
        )
    )
    manifest = load_manifest(workspace)
    manifest["image_status"] = "done"
    manifest["render_status"] = "done"
    manifest["stage"] = "render"
    write_acceptance_artifacts(workspace, manifest)
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
                force_publish=getattr(args, "force_publish", False),
                force_reason=getattr(args, "force_reason", None),
            )
        )
        if not args.dry_run_publish:
            cmd_verify_draft(argparse.Namespace(workspace=str(workspace), media_id=None))
    return manifest


def cmd_score(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = _prepare_content_manifest(workspace, args)
    runtime = _prepare_article_runtime(workspace, manifest, input_value=args.input)
    article = runtime.article
    meta, body, title = article.meta, article.body, article.title
    manifest["writing_persona"] = runtime.writing_persona
    manifest["content_enhancement"] = runtime.content_enhancement
    threshold = args.threshold or manifest.get("score_threshold")
    review = read_json(workspace / "review-report.json", default={}) or {}
    current_signature = article_body_signature(title, body)
    if review and str(review.get("body_signature") or "").strip() not in {"", current_signature}:
        review = {}
    layout_plan = runtime.layout_plan
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
    similarity_report = build_source_similarity_report(title, body, manifest, load_source_corpus(workspace))
    write_similarity_artifacts(workspace, similarity_report)
    manifest["similarity_report_path"] = "similarity-report.json"
    report = apply_source_similarity_gate(report, similarity_report)
    report["schema_version"] = PIPELINE_SCHEMA_VERSION
    report["body_signature"] = current_signature

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
    write_content_fingerprint_artifact(workspace, title, body, manifest, review=review, layout_plan=layout_plan)
    manifest["score_breakdown"] = report["score_breakdown"]
    manifest["score_total"] = report["total_score"]
    manifest["score_passed"] = report["passed"]
    manifest["humanness_signals"] = report.get("humanness_signals") or {}
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


@dataclass(frozen=True)
class LoadedArticleContext:
    article_path: Path
    meta: dict[str, Any]
    body: str
    title: str
    summary: str
    synced_meta: dict[str, str]
    synced_body: str


def _load_workspace_article(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    input_value: str | None = None,
) -> LoadedArticleContext:
    synced_meta, synced_body = sync_article_reference_policy(workspace, manifest)
    article_rel = input_value or str(manifest.get("article_path") or "article.md")
    article_path = workspace / article_rel
    if not article_path.exists():
        raise SystemExit(f"找不到待处理文章：{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
    if synced_body:
        meta.update({key: value for key, value in synced_meta.items() if value})
        body = synced_body
    body = legacy.strip_image_directives(body)
    title = legacy.infer_title(manifest, meta, body)
    summary = meta.get("summary") or manifest.get("summary") or extract_summary(body)
    return LoadedArticleContext(
        article_path=article_path,
        meta=meta,
        body=body,
        title=title,
        summary=summary,
        synced_meta=synced_meta,
        synced_body=synced_body,
    )


@dataclass(frozen=True)
class PreparedArticleRuntime:
    article: LoadedArticleContext
    ideation: dict[str, Any]
    content_enhancement: dict[str, Any]
    writing_persona: dict[str, Any]
    layout_plan: dict[str, Any]


def _prepare_article_runtime(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    input_value: str | None = None,
    enhancement_force: bool = False,
) -> PreparedArticleRuntime:
    article = _load_workspace_article(workspace, manifest, input_value=input_value)
    ideation = load_ideation(workspace)
    writing_persona = current_writing_persona(workspace, manifest, ideation)
    content_enhancement = ensure_content_enhancement(
        workspace,
        manifest,
        ideation,
        selected_title=article.title,
        force=enhancement_force,
    )
    layout_plan = read_json(workspace / "layout-plan.json", default={}) or {}
    return PreparedArticleRuntime(
        article=article,
        ideation=ideation,
        content_enhancement=content_enhancement,
        writing_persona=writing_persona,
        layout_plan=layout_plan,
    )


def _prepare_content_manifest(
    workspace: Path,
    args: argparse.Namespace | None = None,
    *,
    include_corpus: bool = True,
    include_author_memory: bool = True,
) -> dict[str, Any]:
    manifest = load_manifest(workspace)
    manifest = attach_account_strategy(workspace, manifest)
    if args is not None:
        manifest = persist_runtime_preferences(manifest, args)
        manifest = persist_style_samples(workspace, manifest, getattr(args, "style_sample", None))
    if include_corpus:
        manifest = attach_corpus_context(workspace, manifest)
    if include_author_memory:
        manifest = attach_author_memory(workspace, manifest)
    return manifest


def _run_revision_loop(workspace: Path, *, max_rounds: int, style_sample: list[str] | None = None) -> dict[str, Any]:
    max_rounds = max(1, int(max_rounds or 1))
    manifest = load_manifest(workspace)
    manifest["revision_rounds"] = []
    manifest["revision_round"] = 0
    manifest["stop_reason"] = ""
    manifest["best_round"] = 0
    save_manifest(workspace, manifest)

    best_rank = (-1, -1, -1)
    best_round = 0
    best_article_path = str(manifest.get("article_path") or "article.md")
    scores: list[int] = []
    stop_reason = ""
    stage_modes = ["stage-1", "stage-2", "stage-3"]

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
            "stage": stage_modes[min(round_index - 1, len(stage_modes) - 1)],
            "virality_score": int(score_report.get("virality_score") or 0),
            "article_path": str(manifest.get("article_path") or "article.md"),
            "review_report_path": str(manifest.get("review_report_path") or "review-report.json"),
            "score_report_path": str(manifest.get("score_report_path") or "score-report.json"),
        }
        revision_rounds = list(manifest.get("revision_rounds") or [])
        revision_rounds.append(record)
        manifest["revision_rounds"] = revision_rounds
        save_manifest(workspace, manifest)

        hard_gate_count = sum(
            1
            for name in ["naturalness_floor_passed", "reading_flow_passed", "hook_quality_passed", "ending_naturalness_passed"]
            if (score_report.get("quality_gates") or {}).get(name)
        )
        current_rank = (hard_gate_count, int(score_report.get("virality_score") or 0), score_value)
        if current_rank > best_rank:
            best_rank = current_rank
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
        next_mode = stage_modes[min(round_index - 1, len(stage_modes) - 1)]
        cmd_revise(
            argparse.Namespace(
                workspace=str(workspace),
                promote=True,
                mode=next_mode,
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
    manifest, style_sample = _prepare_run_manifest(workspace, args)
    raw_topic = (args.topic or manifest.get("topic") or "").strip()
    if raw_topic.lower() in legacy.START_TOPIC_TOKENS:
        return cmd_discover_topics(
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
        ideation = load_ideation(workspace)
    current_title = args.title or ideation.get("selected_title")
    cmd_enhance(argparse.Namespace(workspace=str(workspace), title=current_title, style_sample=style_sample, content_mode=manifest.get("content_mode") or "tech-balanced", wechat_header_mode=manifest.get("wechat_header_mode") or "drop-title"))
    if not (workspace / "article.md").exists():
        cmd_write(argparse.Namespace(workspace=str(workspace), title=current_title, outline_file=None, style_sample=style_sample))
    score_report = _run_revision_loop(workspace, max_rounds=int(getattr(args, "max_revision_rounds", 3) or 3), style_sample=style_sample)
    manifest = load_manifest(workspace)
    _finalize_after_score(workspace, manifest, manifest.get("selected_title") or topic, score_report)
    render_blockers = collect_render_blockers(workspace, manifest, score_report)
    if render_blockers:
        detail = "\n".join(f"- {item}" for item in render_blockers)
        raise SystemExit(f"当前稿件不满足 render 前置条件：\n{detail}")
    _run_image_render_pipeline(workspace, manifest, args)
    return 0


def cmd_hosted_run(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest, style_sample = _prepare_run_manifest(workspace, args)
    raw_topic = (args.topic or manifest.get("topic") or "").strip()
    if raw_topic.lower() in legacy.START_TOPIC_TOKENS:
        return cmd_discover_topics(
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
    cmd_enhance(argparse.Namespace(workspace=str(workspace), title=title, style_sample=style_sample, content_mode=manifest.get("content_mode") or "tech-balanced", wechat_header_mode=manifest.get("wechat_header_mode") or "drop-title"))
    title = _import_hosted_article(workspace, manifest, args.article_file, title, args.summary, angle, audience)
    save_manifest(workspace, manifest)
    score_report = _run_revision_loop(workspace, max_rounds=int(getattr(args, "max_revision_rounds", 3) or 3), style_sample=style_sample)
    manifest = load_manifest(workspace)
    _finalize_after_score(workspace, manifest, title, score_report)
    render_blockers = collect_render_blockers(workspace, manifest, score_report)
    if render_blockers:
        detail = "\n".join(f"- {item}" for item in render_blockers)
        raise SystemExit(f"当前稿件不满足 render 前置条件：\n{detail}")

    _run_image_render_pipeline(workspace, manifest, args)
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
            title_count=10,
            content_mode=args.content_mode,
            wechat_header_mode=args.wechat_header_mode,
            image_provider=args.provider,
            image_preset=args.image_preset,
            image_style_mode=getattr(args, "image_style_mode", None),
            image_preset_cover=getattr(args, "image_preset_cover", None),
            image_preset_infographic=getattr(args, "image_preset_infographic", None),
            image_preset_inline=getattr(args, "image_preset_inline", None),
            image_density=args.image_density,
            allow_closing_image=getattr(args, "allow_closing_image", None),
            image_layout_family=args.image_layout_family,
            image_theme=args.image_theme,
            image_style=args.image_style,
            image_type=args.image_type,
            image_mood=args.image_mood,
            image_text_policy=getattr(args, "image_text_policy", None),
            image_label_language=getattr(args, "image_label_language", None),
            custom_visual_brief=args.custom_visual_brief,
            inline_count=args.inline_count,
            dry_run_images=args.dry_run_images,
            dry_run_publish=args.dry_run_publish,
            confirmed_publish=args.confirmed_publish,
            force_publish=getattr(args, "force_publish", False),
            force_reason=getattr(args, "force_reason", None),
            gemini_model=args.gemini_model,
            openai_model=args.openai_model,
            accent_color=args.accent_color,
            layout_style=getattr(args, "layout_style", None),
            layout_skin=getattr(args, "layout_skin", None),
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

    titles = subparsers.add_parser("titles", help="生成 10 个左右标题候选并写入 ideation.json")
    titles.add_argument("--workspace", required=True)
    titles.add_argument("--count", type=int, default=10)
    titles.add_argument("--selected-title")
    titles.set_defaults(func=cmd_titles)

    outline = subparsers.add_parser("outline", help="基于 research 和标题生成大纲")
    outline.add_argument("--workspace", required=True)
    outline.add_argument("--title")
    outline.add_argument("--style-sample", action="append", default=[], help="可选：提供高表现文章/风格样本文件路径（可重复）")
    outline.set_defaults(func=cmd_outline)

    enhance = subparsers.add_parser("enhance", help="在正式写作前补角度、细节、证据和写作人格")
    enhance.add_argument("--workspace", required=True)
    enhance.add_argument("--title")
    enhance.add_argument("--style-sample", action="append", default=[], help="可选：提供高表现文章/风格样本文件路径（可重复）")
    enhance.set_defaults(func=cmd_enhance)

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
        choices=["improve-score", "explosive-score", "de-ai", "stage-1", "stage-2", "stage-3"],
        default="improve-score",
        help="改写模式：综合提分（improve-score）、阶段化回炉（stage-1/2/3）、爆点增强别名（explosive-score）或去 AI 味（de-ai）",
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
    run.add_argument("--title-count", type=int, default=10)
    run.add_argument("--content-mode", choices=CONTENT_MODE_CHOICES, default="tech-balanced")
    run.add_argument("--wechat-header-mode", choices=WECHAT_HEADER_MODE_CHOICES, default="drop-title")
    run.add_argument("--max-revision-rounds", type=int, default=3, help="多轮修正上限（默认 3）")
    run.add_argument("--style-sample", action="append", default=[], help="可选：提供高表现文章/风格样本文件路径（可重复）")
    run.add_argument("--to", choices=["render", "publish"], default="render")
    run.add_argument("--image-provider", choices=IMAGE_PROVIDER_CHOICES)
    run.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    run.add_argument("--image-style-mode", choices=["uniform", "mixed-by-type"])
    run.add_argument("--image-preset-cover", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    run.add_argument("--image-preset-infographic", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    run.add_argument("--image-preset-inline", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    run.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default=None)
    run.add_argument("--allow-closing-image", choices=legacy.ALLOW_CLOSING_IMAGE_CHOICES, default=None)
    run.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    run.add_argument("--image-theme")
    run.add_argument("--image-style")
    run.add_argument("--image-type")
    run.add_argument("--image-mood")
    run.add_argument("--image-text-policy", choices=legacy.IMAGE_TEXT_POLICY_CHOICES)
    run.add_argument("--image-label-language", choices=legacy.IMAGE_LABEL_LANGUAGE_CHOICES)
    run.add_argument("--custom-visual-brief")
    run.add_argument("--inline-count", type=int, default=0)
    run.add_argument("--dry-run-images", action="store_true")
    run.add_argument("--dry-run-publish", action="store_true")
    run.add_argument("--confirmed-publish", action="store_true")
    run.add_argument("--force-publish", action="store_true")
    run.add_argument("--force-reason")
    run.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    run.add_argument("--openai-model", default="gpt-image-1")
    run.add_argument("--accent-color", default="#0F766E")
    run.add_argument("--layout-style", choices=LAYOUT_STYLE_CHOICES)
    run.add_argument("--layout-skin", choices=LAYOUT_SKIN_CHOICES, default=None)
    run.add_argument("--input-format", choices=INPUT_FORMAT_CHOICES, default="auto")
    run.set_defaults(func=cmd_run)

    viral_run = subparsers.add_parser("viral-run", help="一键跑爆款发现、采集、拆解、原创改写与公众号版本输出")
    viral_run.add_argument("--workspace", required=True)
    viral_run.add_argument("--query")
    viral_run.add_argument("--topic")
    viral_run.add_argument("--angle")
    viral_run.add_argument("--audience")
    viral_run.add_argument("--title")
    viral_run.add_argument("--title-count", type=int, default=10)
    viral_run.add_argument("--index", action="append", type=int, default=[])
    viral_run.add_argument("--platform", action="append", choices=VIRAL_PLATFORM_CHOICES, default=[])
    viral_run.add_argument("--limit-per-platform", type=int, default=6)
    viral_run.add_argument("--content-mode", choices=CONTENT_MODE_CHOICES, default="tech-balanced")
    viral_run.add_argument("--wechat-header-mode", choices=WECHAT_HEADER_MODE_CHOICES, default="drop-title")
    viral_run.add_argument("--max-revision-rounds", type=int, default=3)
    viral_run.add_argument("--style-sample", action="append", default=[])
    viral_run.add_argument("--to", choices=["render", "publish"], default="render")
    viral_run.add_argument("--image-provider", choices=IMAGE_PROVIDER_CHOICES)
    viral_run.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    viral_run.add_argument("--image-style-mode", choices=["uniform", "mixed-by-type"])
    viral_run.add_argument("--image-preset-cover", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    viral_run.add_argument("--image-preset-infographic", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    viral_run.add_argument("--image-preset-inline", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    viral_run.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default=None)
    viral_run.add_argument("--allow-closing-image", choices=legacy.ALLOW_CLOSING_IMAGE_CHOICES, default=None)
    viral_run.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    viral_run.add_argument("--image-theme")
    viral_run.add_argument("--image-style")
    viral_run.add_argument("--image-type")
    viral_run.add_argument("--image-mood")
    viral_run.add_argument("--image-text-policy", choices=legacy.IMAGE_TEXT_POLICY_CHOICES)
    viral_run.add_argument("--image-label-language", choices=legacy.IMAGE_LABEL_LANGUAGE_CHOICES)
    viral_run.add_argument("--custom-visual-brief")
    viral_run.add_argument("--inline-count", type=int, default=0)
    viral_run.add_argument("--dry-run-images", action="store_true")
    viral_run.add_argument("--dry-run-publish", action="store_true")
    viral_run.add_argument("--confirmed-publish", action="store_true")
    viral_run.add_argument("--force-publish", action="store_true")
    viral_run.add_argument("--force-reason")
    viral_run.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    viral_run.add_argument("--openai-model", default="gpt-image-1")
    viral_run.add_argument("--accent-color", default="#0F766E")
    viral_run.add_argument("--layout-style", choices=LAYOUT_STYLE_CHOICES)
    viral_run.add_argument("--layout-skin", choices=LAYOUT_SKIN_CHOICES, default=None)
    viral_run.add_argument("--input-format", choices=INPUT_FORMAT_CHOICES, default="auto")
    viral_run.set_defaults(func=cmd_viral_run)

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

    discover_viral = subparsers.add_parser("discover-viral", help="多平台搜索适合公众号二次创作的爆款样本")
    discover_viral.add_argument("--workspace", required=True)
    discover_viral.add_argument("--query")
    discover_viral.add_argument("--topic")
    discover_viral.add_argument("--platform", action="append", choices=VIRAL_PLATFORM_CHOICES, default=[])
    discover_viral.add_argument("--limit-per-platform", type=int, default=6)
    discover_viral.set_defaults(func=cmd_discover_viral)

    select_viral = subparsers.add_parser("select-viral", help="从 viral-discovery.json 里选中 1~5 篇爆款样本")
    select_viral.add_argument("--workspace", required=True)
    select_viral.add_argument("--index", action="append", type=int, default=[])
    select_viral.set_defaults(func=cmd_select_viral)

    collect_viral = subparsers.add_parser("collect-viral", help="批量抓取已选样本的全文、字幕、评论和互动数据")
    collect_viral.add_argument("--workspace", required=True)
    collect_viral.add_argument("--index", action="append", type=int, default=[])
    collect_viral.set_defaults(func=cmd_collect_viral)

    analyze_viral = subparsers.add_parser("analyze-viral", help="自动拆解爆款基因，并写回 research/blueprint")
    analyze_viral.add_argument("--workspace", required=True)
    analyze_viral.add_argument("--topic")
    analyze_viral.add_argument("--angle")
    analyze_viral.add_argument("--audience")
    analyze_viral.add_argument("--style-sample", action="append", default=[])
    analyze_viral.set_defaults(func=cmd_analyze_viral)

    adapt_platforms = subparsers.add_parser("adapt-platforms", help="输出公众号版本")
    adapt_platforms.add_argument("--workspace", required=True)
    adapt_platforms.add_argument("--title")
    adapt_platforms.add_argument("--summary")
    adapt_platforms.set_defaults(func=cmd_adapt_platforms)

    evidence = subparsers.add_parser("evidence", help="抽取/补齐来源证据句并回写 research.json/source_urls（默认不联网）")
    evidence.add_argument("--workspace", required=True)
    evidence.add_argument("--source-url", action="append", default=[], help="补充来源 URL（可重复）")
    evidence.add_argument("--limit", type=int, default=6, help="最多保留的来源 URL 数")
    evidence.add_argument("--max-items", type=int, default=6, help="最多抽取的证据句条数")
    evidence.add_argument("--auto-search", action="store_true", help="启用 Tavily 自动搜索补来源（需要 TAVILY_API_KEY）")
    evidence.set_defaults(func=cmd_evidence)

    prepare_publication = subparsers.add_parser("prepare-publication", help="在发布前整理 Markdown 成品，生成 publication.md")
    prepare_publication.add_argument("--workspace", required=True)
    prepare_publication.add_argument("--input")
    prepare_publication.set_defaults(func=cmd_prepare_publication)

    build_playbook = subparsers.add_parser("build-playbook", help="从风格样本构建可复用的作者风格作战卡")
    build_playbook.add_argument("--workspace", required=True)
    build_playbook.add_argument("--style-sample", action="append", default=[], help="风格样本 Markdown 路径（可重复）")
    build_playbook.add_argument("--include-recent-corpus", action="store_true", help="把最近工作区语料也纳入分析")
    build_playbook.set_defaults(func=cmd_build_playbook)

    learn_edits = subparsers.add_parser("learn-edits", help="比较初稿和人工终稿，沉淀为作者偏好")
    learn_edits.add_argument("--workspace", required=True)
    learn_edits.add_argument("--draft", required=True)
    learn_edits.add_argument("--final", required=True)
    learn_edits.set_defaults(func=cmd_learn_edits)

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
    hosted_run.add_argument("--image-provider", choices=IMAGE_PROVIDER_CHOICES)
    hosted_run.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    hosted_run.add_argument("--image-style-mode", choices=["uniform", "mixed-by-type"])
    hosted_run.add_argument("--image-preset-cover", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    hosted_run.add_argument("--image-preset-infographic", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    hosted_run.add_argument("--image-preset-inline", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    hosted_run.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default=None)
    hosted_run.add_argument("--allow-closing-image", choices=legacy.ALLOW_CLOSING_IMAGE_CHOICES, default=None)
    hosted_run.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    hosted_run.add_argument("--image-theme")
    hosted_run.add_argument("--image-style")
    hosted_run.add_argument("--image-type")
    hosted_run.add_argument("--image-mood")
    hosted_run.add_argument("--image-text-policy", choices=legacy.IMAGE_TEXT_POLICY_CHOICES)
    hosted_run.add_argument("--image-label-language", choices=legacy.IMAGE_LABEL_LANGUAGE_CHOICES)
    hosted_run.add_argument("--custom-visual-brief")
    hosted_run.add_argument("--inline-count", type=int, default=0)
    hosted_run.add_argument("--dry-run-images", action="store_true")
    hosted_run.add_argument("--dry-run-publish", action="store_true")
    hosted_run.add_argument("--confirmed-publish", action="store_true")
    hosted_run.add_argument("--force-publish", action="store_true")
    hosted_run.add_argument("--force-reason")
    hosted_run.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    hosted_run.add_argument("--openai-model", default="gpt-image-1")
    hosted_run.add_argument("--accent-color", default="#0F766E")
    hosted_run.add_argument("--layout-style", choices=LAYOUT_STYLE_CHOICES)
    hosted_run.add_argument("--layout-skin", choices=LAYOUT_SKIN_CHOICES, default=None)
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
    plan_images.add_argument("--provider", choices=IMAGE_PROVIDER_CHOICES)
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
    plan_images.add_argument("--image-text-policy", choices=legacy.IMAGE_TEXT_POLICY_CHOICES)
    plan_images.add_argument("--image-label-language", choices=legacy.IMAGE_LABEL_LANGUAGE_CHOICES)
    plan_images.add_argument("--custom-visual-brief")
    plan_images.add_argument("--inline-count", type=int, default=0)
    plan_images.set_defaults(func=legacy_plan_images)

    generate_images = subparsers.add_parser("generate-images", help="执行 image-plan.json 中的图片生成")
    generate_images.add_argument("--workspace", required=True)
    generate_images.add_argument("--provider", choices=IMAGE_PROVIDER_CHOICES)
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
    render.add_argument("--layout-style", choices=LAYOUT_STYLE_CHOICES)
    render.add_argument("--layout-skin", choices=LAYOUT_SKIN_CHOICES, default=None)
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
    publish.add_argument("--force-publish", action="store_true")
    publish.add_argument("--force-reason")
    publish.set_defaults(func=cmd_publish)

    verify_draft = subparsers.add_parser("verify-draft", help="回读草稿箱内容，校验图片与 thumb_media_id")
    verify_draft.add_argument("--workspace", required=True)
    verify_draft.add_argument("--media-id")
    verify_draft.set_defaults(func=cmd_verify_draft)

    doctor = subparsers.add_parser("doctor", help="检查 Python、文本 provider、图片 provider、去 AI 外部桥接、微信凭证")
    doctor.add_argument("--workspace")
    doctor.set_defaults(func=cmd_doctor)

    consent = subparsers.add_parser("consent", help="管理 gemini-web 的显式同意状态")
    consent.add_argument("--accept", action="store_true")
    consent.add_argument("--revoke", action="store_true")
    consent.set_defaults(func=cmd_consent)

    all_cmd = subparsers.add_parser("all", help="兼容别名：等价于 run")
    all_cmd.add_argument("--workspace", required=True)
    all_cmd.add_argument("--provider", choices=IMAGE_PROVIDER_CHOICES)
    all_cmd.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    all_cmd.add_argument("--image-style-mode", choices=["uniform", "mixed-by-type"])
    all_cmd.add_argument("--image-preset-cover", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    all_cmd.add_argument("--image-preset-infographic", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    all_cmd.add_argument("--image-preset-inline", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    all_cmd.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default=None)
    all_cmd.add_argument("--allow-closing-image", choices=legacy.ALLOW_CLOSING_IMAGE_CHOICES, default=None)
    all_cmd.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    all_cmd.add_argument("--image-theme")
    all_cmd.add_argument("--image-style")
    all_cmd.add_argument("--image-type")
    all_cmd.add_argument("--image-mood")
    all_cmd.add_argument("--image-text-policy", choices=legacy.IMAGE_TEXT_POLICY_CHOICES)
    all_cmd.add_argument("--image-label-language", choices=legacy.IMAGE_LABEL_LANGUAGE_CHOICES)
    all_cmd.add_argument("--custom-visual-brief")
    all_cmd.add_argument("--inline-count", type=int, default=0)
    all_cmd.add_argument("--threshold", type=int)
    all_cmd.add_argument("--content-mode", choices=CONTENT_MODE_CHOICES, default="tech-balanced")
    all_cmd.add_argument("--wechat-header-mode", choices=WECHAT_HEADER_MODE_CHOICES, default="drop-title")
    all_cmd.add_argument("--dry-run-images", action="store_true")
    all_cmd.add_argument("--publish", action="store_true")
    all_cmd.add_argument("--dry-run-publish", action="store_true")
    all_cmd.add_argument("--confirmed-publish", action="store_true")
    all_cmd.add_argument("--force-publish", action="store_true")
    all_cmd.add_argument("--force-reason")
    all_cmd.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    all_cmd.add_argument("--openai-model", default="gpt-image-1")
    all_cmd.add_argument("--accent-color", default="#0F766E")
    all_cmd.add_argument("--layout-style", choices=LAYOUT_STYLE_CHOICES)
    all_cmd.add_argument("--layout-skin", choices=LAYOUT_SKIN_CHOICES, default=None)
    all_cmd.add_argument("--input-format", choices=INPUT_FORMAT_CHOICES, default="auto")
    all_cmd.set_defaults(func=cmd_all)

    reader_gate = subparsers.add_parser("reader-gate", help="生成 reader_gate.json")
    reader_gate.add_argument("--workspace", required=True)
    reader_gate.set_defaults(func=cmd_reader_gate)

    visual_gate = subparsers.add_parser("visual-gate", help="生成 visual_gate.json")
    visual_gate.add_argument("--workspace", required=True)
    visual_gate.set_defaults(func=cmd_visual_gate)

    final_gate = subparsers.add_parser("final-gate", help="生成 final_gate.json")
    final_gate.add_argument("--workspace", required=True)
    final_gate.set_defaults(func=cmd_final_gate)

    delivery_report = subparsers.add_parser("delivery-report", help="生成最终交付报告，汇总质量、配图、发布和回读状态")
    delivery_report.add_argument("--workspace", required=True)
    delivery_report.set_defaults(func=cmd_delivery_report)

    learn_performance = subparsers.add_parser("learn-performance", help="记录 24h / 72h 的真实表现")
    learn_performance.add_argument("--workspace", required=True)
    learn_performance.add_argument("--read-24h", type=int, default=0)
    learn_performance.add_argument("--like-24h", type=int, default=0)
    learn_performance.add_argument("--share-24h", type=int, default=0)
    learn_performance.add_argument("--comment-24h", type=int, default=0)
    learn_performance.add_argument("--favorite-24h", type=int, default=0)
    learn_performance.add_argument("--read-72h", type=int, default=0)
    learn_performance.add_argument("--like-72h", type=int, default=0)
    learn_performance.add_argument("--share-72h", type=int, default=0)
    learn_performance.add_argument("--comment-72h", type=int, default=0)
    learn_performance.add_argument("--favorite-72h", type=int, default=0)
    learn_performance.add_argument("--notes")
    learn_performance.set_defaults(func=cmd_learn_performance)

    report_11d = subparsers.add_parser("report-11d", help="生成单篇 11 维分析报告")
    report_11d.add_argument("--workspace", required=True)
    report_11d.set_defaults(func=cmd_report_11d)

    review_batch = subparsers.add_parser("review-batch", help="批量复盘同一批次目录")
    review_batch.add_argument("--jobs-root", required=True)
    review_batch.add_argument("--batch-key", required=True)
    review_batch.set_defaults(func=cmd_review_batch)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))
