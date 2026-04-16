from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from core.content_fingerprint import build_article_fingerprint, load_batch_article_items, summarize_batch_collisions, summarize_collisions
from core.quality_checks import discussion_trigger_present, lead_paragraph_count, metadata_integrity_report
from core.reader_gates import abnormal_text_report, first_screen_signal_report, image_plan_gate_report
from core.three_layers import build_three_layer_diagnostics

ACCEPTANCE_SCHEMA_VERSION = "2026-04-v3"


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


def _body_signature(title: str, body: str) -> str:
    digest = hashlib.sha1()
    digest.update(str(title or "").strip().encode("utf-8"))
    digest.update(b"\n---\n")
    digest.update(str(body or "").strip().encode("utf-8"))
    return digest.hexdigest()


def _selected_title_issues(workspace: Path, manifest: dict[str, Any], body_title: str) -> list[str]:
    expected = str(manifest.get("selected_title") or body_title or "").strip()
    if not expected:
        return []
    normalized_expected = _normalize_text(expected)
    sources = {
        "manifest.json": manifest.get("selected_title"),
        "ideation.json": (legacy.read_json(workspace / "ideation.json", default={}) or {}).get("selected_title"),
        "title-report.json": (legacy.read_json(workspace / "title-report.json", default={}) or {}).get("selected_title"),
        "title-decision-report.json": (legacy.read_json(workspace / "title-decision-report.json", default={}) or {}).get("selected_title"),
    }
    issues: list[str] = []
    for source_name, raw in sources.items():
        value = str(raw or "").strip()
        if value and _normalize_text(value) != normalized_expected:
            issues.append(f"{source_name} 的标题和当前真源不一致")
    return issues


def _state_consistency_issues(workspace: Path, manifest: dict[str, Any], title: str, score_report: dict[str, Any], acceptance_passed: bool) -> list[str]:
    issues: list[str] = []
    manifest_title = str(manifest.get("selected_title") or "").strip()
    score_title = str(score_report.get("title") or "").strip()
    if manifest_title and manifest_title != title:
        issues.append("manifest.json 和当前验收标题不一致")
    if score_title and score_title != title:
        issues.append("score-report.json 和当前验收标题不一致")
    if score_report.get("passed") not in (None, "") and manifest.get("score_passed") not in (None, ""):
        if bool(score_report.get("passed")) != bool(manifest.get("score_passed")):
            issues.append("manifest.json 和 score-report.json 的通过状态不一致")
    if manifest.get("acceptance_passed") not in (None, "") and bool(manifest.get("acceptance_passed")) != bool(acceptance_passed):
        issues.append("manifest.json 里的 acceptance_passed 与当前验收结果不一致")
    return issues


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
    publication_path = workspace / str(manifest.get("publication_path") or "publication.md")
    publication_meta, publication_body = ({}, "")
    if publication_path.exists():
        publication_meta, publication_body = legacy.split_frontmatter(legacy.read_text(publication_path))
    references = workspace / str(manifest.get("references_path") or "references.json")
    reference_count = 0
    if references.exists():
        try:
            reference_count = len((json.loads(references.read_text(encoding="utf-8")) or {}).get("items") or [])
        except (OSError, json.JSONDecodeError):
            reference_count = 0
    image_plan = legacy.read_json(workspace / str(manifest.get("image_plan_path") or "image-plan.json"), default={}) or {}
    fingerprint = build_article_fingerprint(
        title,
        body,
        manifest,
        review=review_report,
        blueprint=manifest.get("viral_blueprint") or {},
        layout_plan=layout_plan,
    )
    collisions = summarize_collisions(fingerprint, recent_fingerprints, threshold=0.74)
    batch_collisions = summarize_batch_collisions(
        fingerprint,
        current_title=title,
        current_body=body,
        batch_items=load_batch_article_items(workspace),
        threshold=0.62,
        title_threshold=0.72,
    )
    metadata = metadata_integrity_report(title, summary)
    first_screen = first_screen_signal_report(body)
    abnormal_text = abnormal_text_report(title, summary, body)
    three_layers = (
        score_report.get("three_layer_diagnostics")
        or review_report.get("three_layer_diagnostics")
        or build_three_layer_diagnostics(
            title=title,
            body=body,
            blueprint=manifest.get("viral_blueprint") or {},
            analysis=(review_report.get("viral_analysis") or score_report.get("viral_analysis") or {}),
            depth=score_report.get("depth_signals") or review_report.get("depth_signals") or {},
            material_signals=score_report.get("material_signals") or review_report.get("material_signals") or {},
            topic=str(manifest.get("topic") or title),
            audience=str(manifest.get("audience") or "大众读者"),
        )
    )
    publication_text = abnormal_text_report(
        str(publication_meta.get("title") or title),
        str(publication_meta.get("summary") or summary),
        publication_body,
    ) if publication_body.strip() else {"passed": True, "suspicious_bullets": [], "suspicious_lines": []}
    rendered_text_integrity_passed = ("????" not in wechat_html) and ("\uFFFD" not in wechat_html)
    image_plan_report = image_plan_gate_report(image_plan, workspace=workspace)
    summary_overlap = _jaccard(_tokens(summary), _tokens(title + " " + " ".join(legacy.list_paragraphs(body)[:3])))
    summary_tokens = list(_tokens(summary))
    summary_keyword_hit = any(token in _normalize_text(body).lower() for token in summary_tokens[:4])
    summary_length_ok = 45 <= len(_normalize_text(summary)) <= 90
    research_requirements = (
        manifest.get("research_requirements")
        or (legacy.read_json(workspace / "research.json", default={}) or {}).get("minimum_requirements")
        or {}
    )
    title_consistency_issues = _selected_title_issues(workspace, manifest, title)
    reference_tail_present = 'data-wx-role="reference-card"' in wechat_html or 'data-wx-role="reference-list"' in wechat_html
    compare_block_present = any(marker in wechat_html for marker in ['data-wx-role="compare-grid"', 'data-wx-role="compare-header"', '<table'])
    code_block_present = "<pre" in wechat_html or "<code" in wechat_html
    first_h2_match = re.search(r"(?m)^\s*##\s+", body)
    h3_count = len(re.findall(r"(?m)^\s*###\s+", body))
    h2_count = len(re.findall(r"(?m)^\s*##\s+", body))
    lead_visual_passed = True
    if "<img" in wechat_html and re.search(r"<h2\b", wechat_html):
        first_img = wechat_html.find("<img")
        first_h2 = wechat_html.find("<h2")
        lead_visual_passed = first_img != -1 and (first_h2 == -1 or first_img < first_h2)
    lead_visual_deadline_ratio = float(layout_plan.get("lead_visual_deadline_ratio") or 0.25)
    lead_visual_window_passed = True
    if "<img" in wechat_html:
        first_img = wechat_html.find("<img")
        lead_visual_window_passed = first_img != -1 and (first_img / max(1, len(wechat_html))) <= lead_visual_deadline_ratio
    score_failed_gates = [name for name, ok in quality_gates.items() if not ok]
    state_consistency_issues = _state_consistency_issues(workspace, manifest, title, score_report, False)
    gates = {
        "metadata_integrity_passed": bool(metadata.get("passed")),
        "body_integrity_passed": bool(abnormal_text.get("passed")) and bool(publication_text.get("passed", True)) and rendered_text_integrity_passed,
        "batch_uniqueness_passed": bool(batch_collisions.get("passed", True)),
        "state_consistency_passed": not state_consistency_issues,
        "score_passed": bool(score_report.get("passed")),
        "title_novelty_passed": bool(collisions.get("route_similarity_passed", True)),
        "title_consistency_passed": not title_consistency_issues,
        "evidence_minimum_passed": bool(research_requirements.get("passed", True)),
        "first_screen_passed": bool(first_screen.get("passed")),
        "hook_layer_passed": bool((three_layers.get("hook") or {}).get("passed")),
        "insight_layer_passed": bool((three_layers.get("insight") or {}).get("passed")),
        "takeaway_layer_passed": bool((three_layers.get("takeaway") or {}).get("passed")),
        "opening_scene_passed": int(depth.get("scene_paragraph_count") or 0) >= 1,
        "evidence_passed": int(depth.get("evidence_paragraph_count") or 0) >= 1 and bool(quality_gates.get("credibility_passed", True)),
        "boundary_passed": int(depth.get("counterpoint_paragraph_count") or 0) >= 1,
        "analysis_passed": int(depth.get("long_paragraph_count") or 0) >= 1 or int(depth.get("paragraph_count") or 0) <= 4,
        "ending_natural_passed": str(editorial_review.get("ending_naturalness") or "medium") != "low",
        "summary_integrity_passed": not metadata.get("summary_issues"),
        "summary_alignment_passed": bool(summary.strip()) and summary_length_ok and (summary_overlap >= 0.03 or summary_keyword_hit or len(summary_tokens) <= 2),
        "layout_plan_passed": len(layout_plan.get("section_plans") or []) >= 3 and bool(layout_plan.get("recommended_style")),
        "pre_h2_length_passed": lead_paragraph_count(body) <= 4,
        "layout_hierarchy_passed": not (h2_count >= 4 and h3_count == 0 and int(depth.get("paragraph_count") or 0) >= 18),
        "lead_visual_passed": lead_visual_passed,
        "lead_visual_window_passed": lead_visual_window_passed,
        "image_text_density_passed": bool(image_plan_report.get("passed", True)),
        "visual_batch_uniqueness_passed": bool(image_plan_report.get("visual_batch_uniqueness_passed", True)),
        "wechat_render_passed": bool(wechat_html.strip()) and ("<h1" not in wechat_html if str(manifest.get("wechat_header_mode") or "drop-title") == "drop-title" else True) and bool(compare_block_present or code_block_present or "<p" in wechat_html),
        "reference_tail_passed": reference_count == 0 or reference_tail_present,
        "source_block_visible_passed": reference_count == 0 or reference_tail_present,
        "quality_gates_passed": not score_failed_gates,
    }
    gates["acceptance_ready_passed"] = bool(
        gates["metadata_integrity_passed"]
        and gates["batch_uniqueness_passed"]
        and gates["state_consistency_passed"]
        and gates["title_novelty_passed"]
        and gates["title_consistency_passed"]
        and gates["evidence_minimum_passed"]
        and gates["body_integrity_passed"]
        and gates["first_screen_passed"]
        and gates["hook_layer_passed"]
        and gates["insight_layer_passed"]
        and gates["takeaway_layer_passed"]
        and gates["opening_scene_passed"]
        and gates["boundary_passed"]
        and gates["analysis_passed"]
        and gates["summary_integrity_passed"]
        and gates["summary_alignment_passed"]
        and gates["layout_plan_passed"]
        and gates["pre_h2_length_passed"]
        and gates["layout_hierarchy_passed"]
        and gates["quality_gates_passed"]
    )
    gates["score_ready"] = bool(gates["score_passed"] and gates["quality_gates_passed"])
    gates["render_ready"] = bool(
        gates["score_ready"] and gates["acceptance_ready_passed"]
    )
    gates["publish_ready"] = bool(
        gates["render_ready"]
        and gates["wechat_render_passed"]
        and gates["source_block_visible_passed"]
        and gates["reference_tail_passed"]
        and gates["lead_visual_passed"]
        and gates["lead_visual_window_passed"]
        and gates["image_text_density_passed"]
        and gates["visual_batch_uniqueness_passed"]
        and gates["summary_alignment_passed"]
    )
    gates["publish_chain_ready"] = bool(gates["publish_ready"])
    failed = [name for name, ok in gates.items() if not ok]
    highlights = []
    if gates["opening_scene_passed"]:
        highlights.append("首屏已经有具体场景或动作。")
    if gates["first_screen_passed"]:
        highlights.append("前两段已经同时给出场景、冲突和继续读下去的理由。")
    if gates["hook_layer_passed"]:
        highlights.append("钩子层已经成立，标题和首屏能把人停下来。")
    if gates["insight_layer_passed"]:
        highlights.append("认知增量层已经成立，中段有新判断和迁移价值。")
    if gates["takeaway_layer_passed"]:
        highlights.append("文末已经有可收藏、可复用的 takeaway。")
    if gates["title_consistency_passed"]:
        highlights.append("标题真源已经统一到同一个结果。")
    if gates["evidence_passed"]:
        highlights.append("正文中段已经有事实或案例托底。")
    if gates["boundary_passed"]:
        highlights.append("全文保留了反方或适用边界。")
    if gates["layout_plan_passed"]:
        highlights.append("版式规划已经在大纲阶段落地。")
    risks = []
    if not gates["title_novelty_passed"]:
        risks.append("和近期文章的路线仍然太近，容易像旧稿换皮。")
    if not gates["metadata_integrity_passed"]:
        risks.append("标题或摘要本身存在乱码、问号替换或空值。")
    if not gates["body_integrity_passed"]:
        risks.append("正文里还有异常字符、坏字或可疑 bullet。")
    if not gates["batch_uniqueness_passed"]:
        risks.append("同批次里已经有结构或正文高度相近的稿子，当前稿件像换皮重写。")
    if not gates["state_consistency_passed"]:
        risks.append("状态单、评分单和验收结果没有对齐，当前工作目录不可信。")
    if not gates["title_consistency_passed"]:
        risks.append("标题在多个产物之间不一致，后续容易出现选题、成稿和渲染错位。")
    if not gates["evidence_minimum_passed"]:
        risks.append("评论/案例类稿件还没满足最小证据门槛。")
    if not gates["first_screen_passed"]:
        risks.append("前两段还没同时把场景、冲突和阅读代价交代清楚。")
    if not gates["hook_layer_passed"]:
        risks.append("只有开头，没有真正站住钩子层。")
    if not gates["insight_layer_passed"]:
        risks.append("有信息，但没有稳定交付认知增量。")
    if not gates["takeaway_layer_passed"]:
        risks.append("结尾还能看，但没有值得收藏和复用的 takeaway。")
    if not gates["summary_alignment_passed"]:
        risks.append("摘要和正文前半段不够贴合。")
    if not gates["pre_h2_length_passed"]:
        risks.append("首屏铺垫过长，第一个二级标题前的段落太多。")
    if not gates["layout_hierarchy_passed"]:
        risks.append("层级过于扁平，长文扫读路径不够清楚。")
    if not gates["wechat_render_passed"]:
        risks.append("公众号片段还不够干净，发布前需要重新渲染。")
    if not gates["reference_tail_passed"] or not gates["source_block_visible_passed"]:
        risks.append("来源卡片没有真正落到公众号成品里。")
    if not gates["lead_visual_passed"]:
        risks.append("有图片但没有在首屏形成视觉锚点。")
    if not gates["lead_visual_window_passed"]:
        risks.append("第一张图出现太晚，没有落在前四分之一阅读区间。")
    if not gates["image_text_density_passed"]:
        risks.append("图片计划里的文字密度或视觉路线还不够克制，容易把配图做成海报。")
    if not gates["visual_batch_uniqueness_passed"]:
        risks.append("同批文章的图片方案过于接近，读者会觉得只是换题不换视觉。")
    if score_failed_gates:
        risks.append("评分硬门槛和成品验收还没有完全对齐。")
    passed = all(gates.values())
    if passed:
        state_consistency_issues = _state_consistency_issues(workspace, manifest, title, score_report, True)
        gates["state_consistency_passed"] = not state_consistency_issues
        passed = all(gates.values())
    return {
        "schema_version": ACCEPTANCE_SCHEMA_VERSION,
        "title": title,
        "summary": summary,
        "body_signature": _body_signature(title, body),
        "passed": passed,
        "gates": gates,
        "failed_gates": failed,
        "blockers": failed,
        "highlights": highlights[:5],
        "risks": risks[:5],
        "metadata_integrity": metadata,
        "first_screen": first_screen,
        "three_layer_diagnostics": three_layers,
        "abnormal_text": abnormal_text,
        "publication_text": publication_text,
        "rendered_text_integrity_passed": rendered_text_integrity_passed,
        "image_plan_report": image_plan_report,
        "content_fingerprint": fingerprint,
        "fingerprint_findings": collisions,
        "batch_uniqueness": batch_collisions,
        "state_consistency_issues": state_consistency_issues,
        "title_consistency_issues": title_consistency_issues,
        "research_requirements": research_requirements,
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
