from __future__ import annotations

from pathlib import Path
from typing import Any

from core.artifacts import extract_summary, now_iso, read_json, read_text, split_frontmatter


DELIVERY_SCHEMA_VERSION = "2026-04-v1"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _status(passed: bool | None, *, missing: bool = False) -> str:
    if missing:
        return "missing"
    if passed is True:
        return "passed"
    if passed is False:
        return "failed"
    return "unknown"


def _failed_gate_names(payload: dict[str, Any]) -> list[str]:
    if not isinstance(payload, dict) or not payload:
        return []
    if payload.get("failed_checks"):
        return [str(item) for item in payload.get("failed_checks") or []]
    if payload.get("failed_gates"):
        return [str(item) for item in payload.get("failed_gates") or []]
    gates = payload.get("quality_gates") or payload.get("gates") or payload.get("checks") or {}
    return [str(key) for key, ok in gates.items() if not ok]


def _artifact_exists(workspace: Path, manifest: dict[str, Any], key: str, default_name: str) -> tuple[bool, str]:
    rel = _clean(manifest.get(key) or default_name)
    return bool(rel and (workspace / rel).exists()), rel or default_name


def _load_article(workspace: Path, manifest: dict[str, Any]) -> tuple[str, str, str]:
    rel = _clean(manifest.get("article_path") or "article.md")
    path = workspace / rel
    if not path.exists():
        return "", "", ""
    meta, body = split_frontmatter(read_text(path))
    title = _clean(manifest.get("selected_title") or meta.get("title") or manifest.get("topic"))
    summary = _clean(meta.get("summary") or manifest.get("summary") or extract_summary(body))
    return title, summary, body


def _title_section(workspace: Path, manifest: dict[str, Any], title: str) -> dict[str, Any]:
    title_decision = read_json(workspace / _clean(manifest.get("title_decision_report_path") or "title-decision-report.json"), default={}) or {}
    title_report = read_json(workspace / _clean(manifest.get("title_report_path") or "title-report.json"), default={}) or {}
    selected = _clean(title_decision.get("selected_title") or title_report.get("selected_title") or title)
    candidates = title_decision.get("candidates") or []
    selected_candidate = next((item for item in candidates if _clean(item.get("title")) == selected), {})
    risks = list(title_decision.get("selected_title_risks") or selected_candidate.get("selected_title_risks") or [])
    explicit_passed = selected_candidate.get("title_gate_passed")
    if explicit_passed in (None, ""):
        explicit_passed = None if not title_decision and not title_report else not risks and bool(selected)
    return {
        "status": _status(bool(explicit_passed) if explicit_passed is not None else None, missing=not bool(selected)),
        "selected_title": selected,
        "target_reader": _clean(title_decision.get("audience") or manifest.get("audience") or "大众读者"),
        "primary_trigger": _clean(selected_candidate.get("title_family") or ""),
        "secondary_trigger": _clean(selected_candidate.get("title_emotion_mode") or ""),
        "why_click": _clean((title_decision.get("selected_explainer") or {}).get("why_click")),
        "answer_too_complete": "标题说满" in risks or bool(selected_candidate.get("answer_complete_title_penalty")),
        "risks": [str(item) for item in risks],
    }


def build_delivery_report(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    title, summary, body = _load_article(workspace, manifest)
    score_report = read_json(workspace / _clean(manifest.get("score_report_path") or "score-report.json"), default={}) or {}
    acceptance_report = read_json(workspace / _clean(manifest.get("acceptance_report_path") or "acceptance-report.json"), default={}) or {}
    reader_gate = read_json(workspace / _clean(manifest.get("reader_gate_path") or "reader_gate.json"), default={}) or {}
    visual_gate = read_json(workspace / _clean(manifest.get("visual_gate_path") or "visual_gate.json"), default={}) or {}
    final_gate = read_json(workspace / _clean(manifest.get("final_gate_path") or "final_gate.json"), default={}) or {}
    publish_result = read_json(workspace / _clean(manifest.get("publish_result_path") or "publish-result.json"), default={}) or {}
    latest_draft = read_json(workspace / _clean(manifest.get("latest_draft_report_path") or "latest-draft-report.json"), default={}) or {}
    publication_report = read_json(workspace / _clean(manifest.get("publication_report_path") or "publication-report.json"), default={}) or {}

    layout_exists, layout_rel = _artifact_exists(workspace, manifest, "layout_plan_path", "layout-plan.json")
    layout_md_exists = (workspace / "layout-plan.md").exists()
    image_exists, image_rel = _artifact_exists(workspace, manifest, "image_plan_path", "image-plan.json")
    wechat_html_exists, wechat_html_rel = _artifact_exists(workspace, manifest, "wechat_html_path", "article.wechat.html")
    publication_exists, publication_rel = _artifact_exists(workspace, manifest, "publication_path", "publication.md")

    score_passed = bool(score_report.get("passed")) if score_report else None
    acceptance_passed = bool(acceptance_report.get("passed")) if acceptance_report else None
    reader_passed = bool(reader_gate.get("passed")) if reader_gate else None
    visual_passed = bool(visual_gate.get("passed")) if visual_gate else None
    final_passed = bool(final_gate.get("passed")) if final_gate else None
    quality_passed = bool(score_passed and acceptance_passed and reader_passed and visual_passed and final_passed)
    published = bool(publish_result.get("draft_media_id") or (publish_result.get("response") or {}).get("media_id"))
    readback_passed = _clean(latest_draft.get("verify_status") or publish_result.get("verify_status")) == "passed"
    forced = bool(_clean(manifest.get("force_publish_reason")))

    sections = {
        "title": _title_section(workspace, manifest, title),
        "article": {
            "status": _status(bool(body.strip()), missing=not bool(body.strip())),
            "summary": summary,
            "first_screen_status": _status(bool((reader_gate.get("first_screen") or {}).get("passed")) if reader_gate else None),
            "click_reason": _clean(reader_gate.get("click_reason")),
            "continue_reason": _clean(reader_gate.get("continue_reason")),
            "comment_seed": _clean(reader_gate.get("comment_seed")),
            "share_line": _clean(reader_gate.get("share_line")),
            "failed_checks": list(reader_gate.get("failed_checks") or []),
        },
        "quality": {
            "status": _status(quality_passed, missing=not bool(score_report or acceptance_report or final_gate)),
            "score": score_report.get("total_score"),
            "threshold": score_report.get("threshold"),
            "score_passed": score_passed,
            "acceptance_passed": acceptance_passed,
            "reader_gate_passed": reader_passed,
            "visual_gate_passed": visual_passed,
            "final_gate_passed": final_passed,
            "failed_gates": sorted(set(_failed_gate_names(score_report) + _failed_gate_names(acceptance_report) + _failed_gate_names(final_gate))),
        },
        "layout": {
            "status": _status(layout_exists and layout_md_exists, missing=not layout_exists or not layout_md_exists),
            "json_path": layout_rel,
            "markdown_path": "layout-plan.md",
            "lead_paragraph_count": publication_report.get("lead_paragraph_count"),
            "reason": "" if layout_exists and layout_md_exists else "缺少版式规划产物",
        },
        "images": {
            "status": _status(bool(image_exists and visual_passed), missing=not image_exists),
            "image_plan_path": image_rel,
            "planned_inline_count": visual_gate.get("planned_inline_count"),
            "role_counts": visual_gate.get("role_counts") or {},
            "failed_checks": list(visual_gate.get("failed_checks") or []),
        },
        "render": {
            "status": _status(wechat_html_exists and publication_exists, missing=not wechat_html_exists or not publication_exists),
            "publication_path": publication_rel,
            "wechat_html_path": wechat_html_rel,
        },
        "publish": {
            "status": _status(published, missing=not bool(publish_result)),
            "draft_media_id": _clean(publish_result.get("draft_media_id") or (publish_result.get("response") or {}).get("media_id")),
            "force_publish": forced,
            "force_reason": _clean(manifest.get("force_publish_reason")),
            "verify_status_in_publish_result": _clean(publish_result.get("verify_status")),
        },
        "readback": {
            "status": _status(readback_passed, missing=not bool(latest_draft)),
            "verify_status": _clean(latest_draft.get("verify_status") or publish_result.get("verify_status")),
            "expected_inline_count": latest_draft.get("expected_inline_count") or publish_result.get("expected_inline_count"),
            "verified_inline_count": latest_draft.get("verified_inline_count") or publish_result.get("verified_inline_count"),
            "verify_errors": list(latest_draft.get("verify_errors") or publish_result.get("verify_errors") or []),
        },
    }

    warnings: list[str] = []
    publish_blockers: list[str] = []
    if not quality_passed:
        if score_passed is False:
            publish_blockers.append("score-report.json 未通过")
        if acceptance_passed is False:
            publish_blockers.append("acceptance-report.json 未通过")
        if reader_passed is False:
            publish_blockers.extend(f"reader_gate.json：{item}" for item in _failed_gate_names(reader_gate)[:4])
        if visual_passed is False:
            publish_blockers.extend(f"visual_gate.json：{item}" for item in _failed_gate_names(visual_gate)[:4])
        if final_passed is False:
            publish_blockers.extend(f"final_gate.json：{item}" for item in _failed_gate_names(final_gate)[:4])
    if published and readback_passed and not quality_passed:
        warnings.append("草稿箱已发布并回读通过，但质量门未通过。")
    if not published and publish_blockers:
        warnings.append("质量或视觉门未通过，已阻止发布。")
    if forced:
        warnings.append("本次使用了强制发布，需要保留质量风险说明。")
    if not layout_exists or not layout_md_exists:
        warnings.append("缺少版式规划，不能证明首屏和模块层次达标。")
    if not image_exists:
        warnings.append("缺少图片计划，不能证明配图分工达标。")

    overall_passed = quality_passed and (not published or readback_passed)
    return {
        "schema_version": DELIVERY_SCHEMA_VERSION,
        "title": title,
        "summary": summary,
        "overall_status": "passed" if overall_passed else "failed",
        "quality_passed": quality_passed,
        "published": published,
        "readback_passed": readback_passed,
        "force_publish": forced,
        "publish_blockers": publish_blockers,
        "warnings": warnings,
        "sections": sections,
        "generated_at": now_iso(),
    }


def markdown_delivery_report(payload: dict[str, Any]) -> str:
    title = _clean(payload.get("title") or "未命名文章")
    lines = [
        f"# 最终交付报告：{title}",
        "",
        f"- 总体结果：{'通过' if payload.get('overall_status') == 'passed' else '未通过'}",
        f"- 质量结果：{'通过' if payload.get('quality_passed') else '未通过'}",
        f"- 发布结果：{'已发布' if payload.get('published') else '未发布'}",
        f"- 回读结果：{'通过' if payload.get('readback_passed') else '未通过或未执行'}",
    ]
    if payload.get("force_publish"):
        lines.append("- 强制发布：是")
    warnings = [str(item) for item in payload.get("warnings") or [] if str(item).strip()]
    if warnings:
        lines.extend(["", "## 风险提醒", ""])
        lines.extend(f"- {item}" for item in warnings)
    publish_blockers = [str(item) for item in payload.get("publish_blockers") or [] if str(item).strip()]
    if publish_blockers:
        lines.extend(["", "## 未发布原因 / 需要修复", ""])
        lines.extend(f"- {item}" for item in publish_blockers[:12])
    lines.extend(["", "## 分项结果", ""])
    labels = {
        "title": "标题",
        "article": "正文",
        "quality": "质量门",
        "layout": "排版",
        "images": "配图",
        "render": "渲染",
        "publish": "发布",
        "readback": "回读",
    }
    for key, label in labels.items():
        section = (payload.get("sections") or {}).get(key) or {}
        status = section.get("status") or "unknown"
        rendered = {"passed": "通过", "failed": "未通过", "missing": "缺失", "unknown": "未知"}.get(str(status), str(status))
        lines.append(f"- {label}：{rendered}")
    quality = ((payload.get("sections") or {}).get("quality") or {})
    failed_gates = quality.get("failed_gates") or []
    if failed_gates:
        lines.extend(["", "## 未过项", ""])
        lines.extend(f"- {item}" for item in failed_gates[:12])
    return "\n".join(lines).strip() + "\n"
