from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from core.artifacts import now_iso, read_json


BOARD_STATUSES = ("选题池", "生产中", "待清理", "已交付")


def _status_from_payload(workspace: Path, manifest: dict[str, Any], delivery: dict[str, Any]) -> str:
    if delivery.get("overall_status") == "passed":
        return "已交付"
    has_topic_discovery = (workspace / str(manifest.get("topic_discovery_path") or "topic-discovery.json")).exists()
    has_article = (workspace / str(manifest.get("article_path") or "article.md")).exists()
    has_score = (workspace / str(manifest.get("score_report_path") or "score-report.json")).exists()
    has_delivery = bool(delivery)
    if has_article or has_score or has_delivery:
        return "生产中"
    if has_topic_discovery:
        return "选题池"
    return "待清理"


def _published(delivery: dict[str, Any]) -> bool:
    return bool(delivery.get("published") or (delivery.get("publish_chain") or {}).get("published"))


def _quality_passed(delivery: dict[str, Any]) -> bool:
    return bool(delivery.get("quality_passed") or (delivery.get("quality_chain") or {}).get("passed"))


def _title_report_missing(delivery: dict[str, Any]) -> bool:
    title_section = (delivery.get("sections") or {}).get("title") or {}
    missing_artifacts = list((delivery.get("quality_chain") or {}).get("missing_artifacts") or [])
    return title_section.get("status") == "missing" or "title-decision-report.json/title-report.json" in missing_artifacts


def build_factory_board(root: Path) -> dict[str, Any]:
    root = Path(root)
    items: list[dict[str, Any]] = []
    for workspace in sorted(path for path in root.iterdir() if path.is_dir()) if root.exists() else []:
        manifest_path = workspace / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = read_json(manifest_path, default={}) or {}
        delivery = read_json(workspace / str(manifest.get("delivery_report_path") or "final-delivery-report.json"), default={}) or {}
        status = str(manifest.get("factory_board_status") or "").strip() or _status_from_payload(workspace, manifest, delivery)
        published = _published(delivery)
        quality_passed = _quality_passed(delivery)
        force_publish = bool(delivery.get("force_publish") or (delivery.get("publish_chain") or {}).get("force_publish"))
        title_report_missing = _title_report_missing(delivery)
        published_but_unqualified = published and not quality_passed
        items.append(
            {
                "workspace": workspace.name,
                "path": str(workspace.resolve()),
                "status": status if status in BOARD_STATUSES else _status_from_payload(workspace, manifest, delivery),
                "topic": manifest.get("topic") or "",
                "selected_title": manifest.get("selected_title") or delivery.get("title") or "",
                "canonical_job_id": manifest.get("canonical_job_id") or workspace.name,
                "batch_id": manifest.get("batch_id") or "",
                "retry_round": int(manifest.get("retry_round") or 0),
                "publish_chain_status": manifest.get("publish_chain_status") or (delivery.get("publish_chain") or {}).get("status") or "unknown",
                "quality_chain_status": manifest.get("quality_chain_status") or (delivery.get("quality_chain") or {}).get("status") or "unknown",
                "batch_chain_status": manifest.get("batch_chain_status") or (delivery.get("batch_chain") or {}).get("status") or "unknown",
                "published": published,
                "quality_passed": quality_passed,
                "force_publish": force_publish,
                "published_but_unqualified": published_but_unqualified,
                "needs_quality_rework": (not quality_passed) and bool(delivery or published),
                "title_report_missing": title_report_missing,
                "completion_status": "合格成品" if quality_passed and (delivery.get("overall_status") == "passed") else ("已发布待返工" if published_but_unqualified else ("生产中待过门" if bool(delivery) else "未完成")),
                "visual_gate_failed": (manifest.get("visual_gate_status") == "failed") or ((delivery.get("quality_chain") or {}).get("visual_gate_passed") is False),
            }
        )
    status_counts = Counter(item["status"] for item in items)
    published_count = sum(1 for item in items if item["published"])
    force_count = sum(1 for item in items if item["force_publish"])
    quality_failed_published = sum(1 for item in items if item["published"] and not item["quality_passed"])
    qualified_count = sum(1 for item in items if item["quality_passed"] and item["batch_chain_status"] == "passed" and item["publish_chain_status"] == "passed")
    needs_rework_count = sum(1 for item in items if item["needs_quality_rework"])
    title_report_missing_count = sum(1 for item in items if item["title_report_missing"])
    visual_failed = sum(1 for item in items if item["visual_gate_failed"])
    retry_rounds = [int(item.get("retry_round") or 0) for item in items]
    return {
        "schema_version": "2026-04-factory-board-v1",
        "root": str(root.resolve()),
        "generated_at": now_iso(),
        "items": items,
        "metrics": {
            "total": len(items),
            "status_counts": {key: int(status_counts.get(key) or 0) for key in BOARD_STATUSES},
            "published_count": published_count,
            "qualified_count": qualified_count,
            "needs_rework_count": needs_rework_count,
            "title_report_missing_count": title_report_missing_count,
            "full_chain_pass_rate": round(status_counts.get("已交付", 0) / max(1, len(items)), 4),
            "delivery_ready_rate": round(qualified_count / max(1, len(items)), 4),
            "force_publish_rate": round(force_count / max(1, published_count), 4),
            "published_quality_failed_rate": round(quality_failed_published / max(1, published_count), 4),
            "title_report_missing_rate": round(title_report_missing_count / max(1, len(items)), 4),
            "manifest_only_backlog": int(status_counts.get("待清理") or 0),
            "average_retry_round": round(sum(retry_rounds) / max(1, len(retry_rounds)), 2),
            "visual_gate_failed_rate": round(visual_failed / max(1, len(items)), 4),
        },
    }
