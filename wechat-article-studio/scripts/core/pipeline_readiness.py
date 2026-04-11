from __future__ import annotations

from pathlib import Path
from typing import Any


ARTIFACT_REQUIREMENTS: dict[str, tuple[tuple[str, str], ...]] = {
    "score": (("article_path", "article.md"),),
    "render": (
        ("article_path", "article.md"),
        ("score_report_path", "score-report.json"),
        ("acceptance_report_path", "acceptance-report.json"),
    ),
    "publish": (
        ("article_path", "article.md"),
        ("publication_path", "publication.md"),
        ("wechat_html_path", "article.wechat.html"),
        ("score_report_path", "score-report.json"),
        ("acceptance_report_path", "acceptance-report.json"),
    ),
}


def score_dimension_value(report: dict[str, Any], dimension: str) -> int:
    for item in report.get("score_breakdown", []):
        if item.get("dimension") == dimension:
            return int(item.get("score") or 0)
    return 0


def has_score_dimension(report: dict[str, Any], dimension: str) -> bool:
    return any(item.get("dimension") == dimension for item in report.get("score_breakdown", []))


def artifact_contract_report(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    score_report: dict[str, Any] | None = None,
    acceptance_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report: dict[str, Any] = {"score": [], "render": [], "publish": []}
    for stage, specs in ARTIFACT_REQUIREMENTS.items():
        missing: list[str] = []
        for manifest_key, default_name in specs:
            if manifest_key == "score_report_path" and score_report:
                continue
            if manifest_key == "acceptance_report_path" and acceptance_report:
                continue
            rel = str(manifest.get(manifest_key) or default_name).strip()
            if not rel:
                missing.append(default_name)
                continue
            if not (workspace / rel).exists():
                missing.append(rel)
        report[stage] = missing
    acceptance = acceptance_report or {}
    reference_count = int(((acceptance.get("references_summary") or {}).get("reference_count") or 0) if isinstance(acceptance, dict) else 0)
    if reference_count > 0:
        references_rel = str(manifest.get("references_path") or "references.json").strip()
        if not references_rel or not (workspace / references_rel).exists():
            report["publish"].append(references_rel or "references.json")
    image_plan_rel = str(manifest.get("image_plan_path") or "").strip()
    if image_plan_rel and not (workspace / image_plan_rel).exists():
        report["publish"].append(image_plan_rel)
    for stage in report:
        deduped: list[str] = []
        for item in report[stage]:
            if item not in deduped:
                deduped.append(item)
        report[stage] = deduped
    return report


def compute_pipeline_readiness(
    *,
    report: dict[str, Any],
    acceptance: dict[str, Any],
    research_report: dict[str, Any],
    placeholder_issues: list[str],
    stale_blockers: list[str],
    consistency_blockers: list[str],
    title_blockers: list[str],
    similarity_blockers: list[str],
    contract_report: dict[str, Any],
    publish_result_exists: bool,
    min_credibility_score: int,
) -> dict[str, Any]:
    score_blockers: list[str] = []
    if not report:
        score_blockers.append("缺少 score-report.json，无法确认是否过线。")
    else:
        if not bool(report.get("passed")):
            score_blockers.append("当前稿件评分未达阈值。")
        failed_gates = [name for name, ok in (report.get("quality_gates") or {}).items() if not ok]
        if failed_gates:
            score_blockers.append(f"评分硬门槛未通过：{'、'.join(failed_gates)}")
        evidence_dimension = (
            "事实/案例/对比托底"
            if has_score_dimension(report, "事实/案例/对比托底")
            else "可信度与检索支撑"
            if has_score_dimension(report, "可信度与检索支撑")
            else ""
        )
        evidence_score = score_dimension_value(report, evidence_dimension) if evidence_dimension else min_credibility_score
        if evidence_dimension and evidence_score < min_credibility_score:
            score_blockers.append(f"事实/案例/对比托底得分过低（{evidence_score}/{min_credibility_score}）")
    if contract_report.get("score"):
        score_blockers.append(f"工作目录缺少评分所需产物：{'、'.join(contract_report['score'])}")

    render_blockers: list[str] = []
    if research_report.get("requires_evidence") and not research_report.get("passed"):
        render_blockers.append(f"调研门槛未通过：{'；'.join(research_report.get('reasons') or [])}")
    if not acceptance:
        render_blockers.append("缺少 acceptance-report.json，无法确认 render 前置条件。")
    elif not bool((acceptance.get("gates") or {}).get("acceptance_ready_passed", False)):
        render_blockers.append("成品验收前置门槛未通过，当前稿件不满足 render 前置条件。")
    if contract_report.get("render"):
        render_blockers.append(f"工作目录缺少 render 所需产物：{'、'.join(contract_report['render'])}")
    render_blockers.extend(title_blockers)
    render_blockers.extend(similarity_blockers)
    render_blockers.extend(consistency_blockers)

    publish_blockers: list[str] = []
    publish_blockers.extend(placeholder_issues)
    if not acceptance:
        publish_blockers.append("缺少 acceptance-report.json，无法确认成品验收是否通过")
    elif not bool(acceptance.get("passed")):
        failed = acceptance.get("failed_gates") or [name for name, ok in (acceptance.get("gates") or {}).items() if not ok]
        publish_blockers.append(f"成品验收未通过：{'、'.join(str(item) for item in failed)}")
    if contract_report.get("publish"):
        publish_blockers.append(f"工作目录缺少发布所需产物：{'、'.join(contract_report['publish'])}")

    score_ready = not score_blockers and not stale_blockers and not consistency_blockers
    render_ready = score_ready and not render_blockers
    publish_ready = render_ready and not publish_blockers and bool((acceptance.get("gates") or {}).get("publish_ready", False))
    if publish_result_exists and not publish_ready:
        publish_blockers.append("工作目录里已存在历史 publish-result.json，但对应稿件未满足当前发布前置条件。")
    return {
        "score_ready": score_ready,
        "render_ready": render_ready,
        "publish_ready": publish_ready,
        "artifact_contract": contract_report,
        "score_blockers": stale_blockers + consistency_blockers + score_blockers,
        "render_blockers": stale_blockers + consistency_blockers + score_blockers + render_blockers,
        "publish_blockers": stale_blockers + consistency_blockers + score_blockers + render_blockers + publish_blockers,
    }
