from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from core.artifacts import now_iso, read_json
from core.factory_acceptance import build_factory_acceptance_report


BOARD_STATUSES = ("选题池", "生产中", "待返工", "已发布但不合格", "真合格成品", "待清理")
FACTORY_STATUS_LABELS = {
    "passed": "真合格成品",
    "force_publish_only": "已发布但不合格",
    "published_but_unqualified": "已发布但不合格",
    "needs_rework": "待返工",
    "incomplete": "生产中",
}


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


def _factory_label(workspace: Path, manifest: dict[str, Any], delivery: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    existing = delivery.get("factory_acceptance") or read_json(workspace / "factory-acceptance-report.json", default={}) or {}
    factory = existing if existing else build_factory_acceptance_report(workspace, manifest, delivery)
    published = _published(delivery) or bool(factory.get("published"))
    if published and factory.get("status") != "passed":
        return "已发布但不合格", factory
    if factory.get("status") == "incomplete":
        return _status_from_payload(workspace, manifest, delivery), factory
    label = FACTORY_STATUS_LABELS.get(str(factory.get("status") or ""), "")
    if label:
        return label, factory
    return _status_from_payload(workspace, manifest, delivery), factory


def build_factory_board(root: Path) -> dict[str, Any]:
    root = Path(root)
    items: list[dict[str, Any]] = []
    for workspace in sorted(path for path in root.iterdir() if path.is_dir()) if root.exists() else []:
        if workspace.name.startswith("edge-profile"):
            continue
        manifest_path = workspace / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = read_json(manifest_path, default={}) or {}
        delivery = read_json(workspace / str(manifest.get("delivery_report_path") or "final-delivery-report.json"), default={}) or {}
        factory_label, factory = _factory_label(workspace, manifest, delivery)
        status = str(manifest.get("factory_board_status") or "").strip() or factory_label
        published = _published(delivery) or bool(factory.get("published"))
        quality_passed = _quality_passed(delivery) or factory.get("status") == "passed"
        force_publish = bool(delivery.get("force_publish") or (delivery.get("publish_chain") or {}).get("force_publish") or factory.get("force_publish"))
        title_report_missing = _title_report_missing(delivery)
        published_but_unqualified = bool(factory.get("status") in {"force_publish_only", "published_but_unqualified"} or (published and factory.get("status") != "passed"))
        true_qualified = factory.get("status") == "passed"
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
                "needs_quality_rework": (not true_qualified) and bool(delivery or published or factory.get("status") == "needs_rework"),
                "title_report_missing": title_report_missing,
                "completion_status": factory.get("grade_label") or ("合格成品" if quality_passed and (delivery.get("overall_status") == "passed") else ("已发布待返工" if published_but_unqualified else ("生产中待过门" if bool(delivery) else "未完成"))),
                "factory_status": factory.get("status") or "unknown",
                "factory_grade_label": factory.get("grade_label") or "",
                "factory_ready": true_qualified,
                "blocking_reasons": list(factory.get("blocking_reasons") or []),
                "top_rework_actions": list(factory.get("top_rework_actions") or [])[:3],
                "visual_gate_failed": (manifest.get("visual_gate_status") == "failed") or ((delivery.get("quality_chain") or {}).get("visual_gate_passed") is False),
            }
        )
    status_counts = Counter(item["status"] for item in items)
    published_count = sum(1 for item in items if item["published"])
    force_count = sum(1 for item in items if item["force_publish"])
    quality_failed_published = sum(1 for item in items if item["published"] and not item["quality_passed"])
    qualified_count = sum(1 for item in items if item.get("factory_ready"))
    needs_rework_count = sum(1 for item in items if item["needs_quality_rework"])
    title_report_missing_count = sum(1 for item in items if item["title_report_missing"])
    visual_failed = sum(1 for item in items if item["visual_gate_failed"])
    retry_rounds = [int(item.get("retry_round") or 0) for item in items]
    reason_counts = Counter(reason for item in items for reason in (item.get("blocking_reasons") or []))
    rework_action_counts = Counter(action for item in items for action in (item.get("top_rework_actions") or []))
    published_unqualified_items = [item for item in items if item.get("published_but_unqualified")]
    true_finished_items = [item for item in items if item.get("factory_ready")]
    return {
        "schema_version": "2026-05-factory-board-v2",
        "root": str(root.resolve()),
        "generated_at": now_iso(),
        "items": items,
        "metrics": {
            "total": len(items),
            "status_counts": {key: int(status_counts.get(key) or 0) for key in BOARD_STATUSES},
            "published_count": published_count,
            "qualified_count": qualified_count,
            "true_qualified_count": qualified_count,
            "needs_rework_count": needs_rework_count,
            "title_report_missing_count": title_report_missing_count,
            "published_unqualified_count": len(published_unqualified_items),
            "full_chain_pass_rate": round(status_counts.get("真合格成品", 0) / max(1, len(items)), 4),
            "delivery_ready_rate": round(qualified_count / max(1, len(items)), 4),
            "force_publish_rate": round(force_count / max(1, published_count), 4),
            "published_quality_failed_rate": round(quality_failed_published / max(1, published_count), 4),
            "title_report_missing_rate": round(title_report_missing_count / max(1, len(items)), 4),
            "manifest_only_backlog": int(status_counts.get("待清理") or 0),
            "average_retry_round": round(sum(retry_rounds) / max(1, len(retry_rounds)), 2),
            "visual_gate_failed_rate": round(visual_failed / max(1, len(items)), 4),
            "top_blocking_reasons": reason_counts.most_common(10),
            "top_rework_actions": rework_action_counts.most_common(10),
        },
        "published_unqualified_items": published_unqualified_items[:20],
        "true_finished_items": true_finished_items[:20],
    }
