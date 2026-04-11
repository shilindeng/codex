from __future__ import annotations

from pathlib import Path
from typing import Any

import legacy_studio as legacy

MANIFEST_STATUS_DEFAULTS = {
    "stage": "initialized",
    "research_status": "not_started",
    "title_status": "not_started",
    "outline_status": "not_started",
    "draft_status": "not_started",
    "review_status": "not_started",
    "score_status": "not_started",
    "image_status": "not_started",
    "render_status": "not_started",
    "publish_status": "not_started",
    "verify_status": "not_started",
    "content_mode": "tech-balanced",
    "wechat_header_mode": "drop-title",
    "metadata_integrity_status": "unknown",
    "batch_uniqueness_status": "unknown",
    "state_consistency_status": "unknown",
    "acceptance_ready_status": "unknown",
}

ARTIFACT_DEFAULTS = {
    "research_path": "research.json",
    "topic_discovery_path": "topic-discovery.json",
    "viral_discovery_path": "viral-discovery.json",
    "source_corpus_path": "source-corpus.json",
    "viral_dna_path": "viral-dna.json",
    "publication_path": "publication.md",
    "publication_report_path": "publication-report.json",
    "ideation_path": "ideation.json",
    "article_path": "article.md",
    "title_report_path": "title-report.json",
    "title_decision_report_path": "title-decision-report.json",
    "review_report_path": "review-report.json",
    "score_report_path": "score-report.json",
    "content_fingerprint_path": "content-fingerprint.json",
    "layout_plan_path": "layout-plan.json",
    "acceptance_report_path": "acceptance-report.json",
    "similarity_report_path": "similarity-report.json",
    "references_path": "references.json",
    "image_plan_path": "image-plan.json",
    "image_outline_path": "image-outline.json",
    "image_outline_markdown_path": "image-outline.md",
    "image_prompt_dir": "prompts/images",
    "assembled_path": "assembled.md",
    "html_path": "article.html",
    "wechat_html_path": "article.wechat.html",
    "versions_manifest_path": "versions/manifest.json",
    "publish_result_path": "publish-result.json",
    "latest_draft_report_path": "latest-draft-report.json",
}

workspace_path = legacy.workspace_path
ensure_workspace = legacy.ensure_workspace
relative_posix = legacy.relative_posix


def ensure_manifest_schema(manifest: dict[str, Any], workspace: Path | None = None) -> dict[str, Any]:
    manifest = legacy.ensure_manifest_schema(manifest, workspace)
    if workspace is not None:
        manifest["workspace"] = str(workspace.resolve())
    manifest.setdefault("artifact_contract_version", 2)
    for key, value in MANIFEST_STATUS_DEFAULTS.items():
        manifest.setdefault(key, value)
    for key, value in ARTIFACT_DEFAULTS.items():
        manifest.setdefault(key, value)
    manifest["updated_at"] = legacy.now_iso()
    return manifest


def load_manifest(workspace: Path) -> dict[str, Any]:
    path = workspace / "manifest.json"
    if path.exists():
        manifest = legacy.read_json(path, default={}) or {}
    else:
        manifest = {}
    return ensure_manifest_schema(manifest, workspace)


def save_manifest(workspace: Path, manifest: dict[str, Any]) -> None:
    legacy.write_json(workspace / "manifest.json", ensure_manifest_schema(manifest, workspace))


def update_stage(manifest: dict[str, Any], stage: str, status_key: str, status_value: str = "done") -> dict[str, Any]:
    manifest["stage"] = stage
    manifest[status_key] = status_value
    manifest["updated_at"] = legacy.now_iso()
    return manifest
