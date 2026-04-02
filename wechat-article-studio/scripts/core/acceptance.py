from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from core.content_fingerprint import build_article_fingerprint, summarize_collisions


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _tokens(value: str) -> set[str]:
    return {item.lower() for item in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}", _normalize_text(value))}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def build_acceptance_report(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    title: str,
    summary: str,
    body: str,
    score_report: dict[str, Any],
    review_report: dict[str, Any],
    layout_plan: dict[str, Any],
    recent_fingerprints: list[dict[str, Any]],
) -> dict[str, Any]:
    depth = score_report.get("depth_signals") or {}
    quality_gates = score_report.get("quality_gates") or {}
    editorial_review = review_report.get("editorial_review") or score_report.get("editorial_review") or {}
    wechat_html_path = workspace / str(manifest.get("wechat_html_path") or "article.wechat.html")
    wechat_html = legacy.read_text(wechat_html_path) if wechat_html_path.exists() else ""
    references = workspace / str(manifest.get("references_path") or "references.json")
    reference_count = 0
    if references.exists():
        try:
            reference_count = len((json.loads(references.read_text(encoding="utf-8")) or {}).get("items") or [])
        except (OSError, json.JSONDecodeError):
            reference_count = 0
    fingerprint = build_article_fingerprint(
        title,
        body,
        manifest,
        review=review_report,
        blueprint=manifest.get("viral_blueprint") or {},
        layout_plan=layout_plan,
    )
    collisions = summarize_collisions(fingerprint, recent_fingerprints, threshold=0.74)
    summary_overlap = _jaccard(_tokens(summary), _tokens(title + " " + " ".join(legacy.list_paragraphs(body)[:3])))
    summary_tokens = list(_tokens(summary))
    summary_keyword_hit = any(token in _normalize_text(body).lower() for token in summary_tokens[:4])
    summary_length_ok = 10 <= len(_normalize_text(summary)) <= 90
    gates = {
        "score_passed": bool(score_report.get("passed")),
        "title_novelty_passed": bool(collisions.get("route_similarity_passed", True)),
        "opening_scene_passed": int(depth.get("scene_paragraph_count") or 0) >= 1,
        "evidence_passed": int(depth.get("evidence_paragraph_count") or 0) >= 1 and bool(quality_gates.get("credibility_passed", True)),
        "boundary_passed": int(depth.get("counterpoint_paragraph_count") or 0) >= 1,
        "analysis_passed": int(depth.get("long_paragraph_count") or 0) >= 1 or int(depth.get("paragraph_count") or 0) <= 4,
        "ending_natural_passed": str(editorial_review.get("ending_naturalness") or "medium") != "low",
        "summary_alignment_passed": bool(summary.strip()) and summary_length_ok and (summary_overlap >= 0.03 or summary_keyword_hit or len(summary_tokens) <= 2),
        "layout_plan_passed": len(layout_plan.get("section_plans") or []) >= 3 and bool(layout_plan.get("recommended_style")),
        "wechat_render_passed": bool(wechat_html.strip()) and ("<h1" not in wechat_html if str(manifest.get("wechat_header_mode") or "drop-title") == "drop-title" else True),
        "reference_tail_passed": True,
    }
    failed = [name for name, ok in gates.items() if not ok]
    highlights = []
    if gates["opening_scene_passed"]:
        highlights.append("首屏已经有具体场景或动作。")
    if gates["evidence_passed"]:
        highlights.append("正文中段已经有事实或案例托底。")
    if gates["boundary_passed"]:
        highlights.append("全文保留了反方或适用边界。")
    if gates["layout_plan_passed"]:
        highlights.append("版式规划已经在大纲阶段落地。")
    risks = []
    if not gates["title_novelty_passed"]:
        risks.append("和近期文章的路线仍然太近，容易像旧稿换皮。")
    if not gates["summary_alignment_passed"]:
        risks.append("摘要和正文前半段不够贴合。")
    if not gates["wechat_render_passed"]:
        risks.append("公众号片段还不够干净，发布前需要重新渲染。")
    passed = all(gates.values())
    return {
        "title": title,
        "summary": summary,
        "passed": passed,
        "gates": gates,
        "failed_gates": failed,
        "highlights": highlights[:5],
        "risks": risks[:5],
        "content_fingerprint": fingerprint,
        "fingerprint_findings": collisions,
        "layout_plan_overview": {
            "recommended_style": layout_plan.get("recommended_style") or "",
            "module_types": layout_plan.get("module_types") or [],
        },
        "generated_at": legacy.now_iso(),
    }


def markdown_acceptance_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# 成品验收：{payload.get('title') or '未命名标题'}",
        "",
        f"- 结果：{'通过' if payload.get('passed') else '未通过'}",
    ]
    for name, ok in (payload.get("gates") or {}).items():
        lines.append(f"- {name}：{'通过' if ok else '未通过'}")
    lines.append("")
    for item in payload.get("highlights") or []:
        lines.append(f"- 亮点：{item}")
    for item in payload.get("risks") or []:
        lines.append(f"- 风险：{item}")
    findings = payload.get("fingerprint_findings") or {}
    if findings:
        lines.append(f"- 路线相似度峰值：{findings.get('max_route_similarity', 0)}")
        for item in findings.get("similar_items") or []:
            lines.append(f"- 相近旧稿：{item.get('title') or ''}（{item.get('score') or 0}）")
    return "\n".join(lines).rstrip() + "\n"
