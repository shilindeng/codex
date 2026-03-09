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
}

ARTIFACT_DEFAULTS = {
    "research_path": "research.json",
    "ideation_path": "ideation.json",
    "article_path": "article.md",
    "review_report_path": "review-report.json",
    "score_report_path": "score-report.json",
    "image_plan_path": "image-plan.json",
    "assembled_path": "assembled.md",
    "html_path": "article.html",
    "wechat_html_path": "article.wechat.html",
    "publish_result_path": "publish-result.json",
    "latest_draft_report_path": "latest-draft-report.json",
}

workspace_path = legacy.workspace_path
ensure_workspace = legacy.ensure_workspace
relative_posix = legacy.relative_posix


def ensure_manifest_schema(manifest: dict[str, Any], workspace: Path | None = None) -> dict[str, Any]:
    manifest = legacy.ensure_manifest_schema(manifest, workspace)
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
