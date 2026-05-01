from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from core.artifacts import extract_summary, now_iso, read_json, read_text, split_frontmatter


FACTORY_ACCEPTANCE_SCHEMA_VERSION = "2026-05-factory-acceptance-v1"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _load_json(workspace: Path, manifest: dict[str, Any], key: str, default_name: str) -> dict[str, Any]:
    rel = _clean(manifest.get(key) or default_name)
    return read_json(workspace / rel, default={}) or {}


def _artifact_exists(workspace: Path, manifest: dict[str, Any], key: str, default_name: str) -> bool:
    rel = _clean(manifest.get(key) or default_name)
    return bool(rel and (workspace / rel).exists())


def _load_article(workspace: Path, manifest: dict[str, Any]) -> tuple[dict[str, Any], str]:
    article_rel = _clean(manifest.get("article_path") or "article.md")
    article_path = workspace / article_rel
    if not article_path.exists():
        return {}, ""
    meta, body = split_frontmatter(read_text(article_path))
    return meta, body


def _bool(value: Any) -> bool:
    return bool(value is True or str(value).strip().lower() == "true")


def _count_patterns(body: str, patterns: list[str]) -> int:
    return sum(len(re.findall(pattern, body or "", flags=re.I)) for pattern in patterns)


def _failed_checks(payload: dict[str, Any]) -> list[str]:
    if not payload:
        return []
    if payload.get("failed_checks"):
        return [str(item) for item in payload.get("failed_checks") or []]
    if payload.get("failed_gates"):
        return [str(item) for item in payload.get("failed_gates") or []]
    checks = payload.get("checks") or payload.get("quality_gates") or payload.get("gates") or {}
    return [str(key) for key, value in checks.items() if value is False]


def build_topic_package(workspace: Path, manifest: dict[str, Any], *, delivery_report: dict[str, Any] | None = None) -> dict[str, Any]:
    delivery_report = delivery_report or {}
    meta, body = _load_article(workspace, manifest)
    topic_discovery = _load_json(workspace, manifest, "topic_discovery_path", "topic-discovery.json")
    score_report = _load_json(workspace, manifest, "score_report_path", "score-report.json")
    reader_gate = _load_json(workspace, manifest, "reader_gate_path", "reader_gate.json")
    title = _clean(manifest.get("selected_title") or delivery_report.get("title") or score_report.get("title") or meta.get("title") or manifest.get("topic"))
    summary = _clean(manifest.get("summary") or delivery_report.get("summary") or meta.get("summary") or extract_summary(body))
    topic = _clean(manifest.get("topic") or title)
    candidates = topic_discovery.get("candidates") or topic_discovery.get("items") or []
    topic_score = (
        manifest.get("topic_score_100")
        or topic_discovery.get("topic_score_100")
        or topic_discovery.get("selected_topic_score")
        or score_report.get("topic_score_100")
    )
    selected_candidate = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        text = " ".join(str(candidate.get(key) or "") for key in ("title", "topic", "summary", "name"))
        if topic and topic in text:
            selected_candidate = candidate
            break
    heat_reason = _clean(
        selected_candidate.get("heat_reason")
        or selected_candidate.get("why_now")
        or selected_candidate.get("hot_reason")
        or manifest.get("topic_heat_reason")
    )
    controversy_points = [
        item
        for item in [
            _clean(selected_candidate.get("controversy")),
            _clean(selected_candidate.get("conflict")),
            _clean(reader_gate.get("comment_seed")),
        ]
        if item
    ]
    audience_identity = _clean(manifest.get("audience") or reader_gate.get("target_reader") or "公众号读者")
    material_potential = {
        "source_url_count": len(manifest.get("source_urls") or []),
        "topic_candidates": len(candidates),
        "has_summary": bool(summary),
        "has_comment_seed": bool(reader_gate.get("comment_seed")),
    }
    repeat_risk = _clean(selected_candidate.get("repeat_risk") or selected_candidate.get("repeat_risk_score") or manifest.get("repeat_risk"))
    missing = [
        name
        for name, ok in [
            ("热点理由", bool(heat_reason or topic_score)),
            ("争议点", bool(controversy_points)),
            ("受众身份", bool(audience_identity)),
            ("素材潜力", any(material_potential.values())),
            ("重复风险", bool(repeat_risk or candidates)),
        ]
        if not ok
    ]
    return {
        "schema_version": "2026-05-topic-package-v1",
        "topic": topic,
        "title": title,
        "summary": summary,
        "topic_score_100": topic_score,
        "heat_reason": heat_reason,
        "controversy_points": controversy_points[:3],
        "audience_identity": audience_identity,
        "material_potential": material_potential,
        "repeat_risk": repeat_risk,
        "missing_fields": missing,
        "passed": not missing,
    }


def build_material_pack(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    meta, body = _load_article(workspace, manifest)
    reader_gate = _load_json(workspace, manifest, "reader_gate_path", "reader_gate.json")
    references = _load_json(workspace, manifest, "references_path", "references.json")
    evidence_report = _load_json(workspace, manifest, "evidence_report_path", "evidence-report.json")
    source_count = len(references.get("items") or []) + len(evidence_report.get("items") or []) + len(manifest.get("source_urls") or [])
    quote_count = len(re.findall(r"[“”\"「」]", body or "")) // 2 + len(re.findall(r"\[\d{1,2}]", body or ""))
    table_count = len(re.findall(r"(?m)^\s*\|.+\|\s*$", body or ""))
    comparison_count = int(reader_gate.get("counterpoint_count") or 0) + _count_patterns(body, [r"不是.+而是", r"相比", r"对比", r"差异", r"另一面"])
    analogy_count = _count_patterns(body, [r"像是", r"好比", r"类似", r"可以理解为", r"打个比方"])
    case_count = _count_patterns(body, [r"比如", r"例如", r"案例", r"公开报道", r"数据显示", r"提到"])
    counterpoint_count = int(reader_gate.get("counterpoint_count") or 0) + _count_patterns(body, [r"反过来", r"边界", r"不是所有", r"但也", r"风险"])
    hard_evidence_types = list(reader_gate.get("hard_evidence_types") or [])
    checks = {
        "source_or_reference_passed": source_count >= 2 or "source" in hard_evidence_types,
        "case_or_quote_passed": case_count >= 1 or quote_count >= 2,
        "comparison_passed": comparison_count >= 1,
        "analogy_passed": analogy_count >= 1,
        "counterpoint_passed": counterpoint_count >= 1,
        "judgment_table_passed": table_count >= 2,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "2026-05-material-pack-v1",
        "title": _clean(manifest.get("selected_title") or meta.get("title")),
        "source_count": source_count,
        "quote_count": quote_count,
        "table_row_count": table_count,
        "case_count": case_count,
        "comparison_count": comparison_count,
        "analogy_count": analogy_count,
        "counterpoint_count": counterpoint_count,
        "hard_evidence_types": hard_evidence_types,
        "checks": checks,
        "failed_checks": failed,
        "passed": not failed,
    }


def build_viral_moment_map(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    reader_gate = _load_json(workspace, manifest, "reader_gate_path", "reader_gate.json")
    final_gate = _load_json(workspace, manifest, "final_gate_path", "final_gate.json")
    score_report = _load_json(workspace, manifest, "score_report_path", "score-report.json")
    share_lines = [str(item).strip() for item in reader_gate.get("share_lines") or [] if str(item).strip()]
    takeaway_module = _clean(reader_gate.get("takeaway_module_type"))
    checks = {
        "opening_four_factors_passed": _bool(reader_gate.get("opening_four_factors_passed")) or _bool((final_gate.get("checks") or {}).get("opening_four_factors_passed")),
        "share_lines_passed": len(share_lines) >= 3 and int(reader_gate.get("share_line_score") or 0) >= 8,
        "comment_seed_passed": bool(_clean(reader_gate.get("comment_seed"))),
        "takeaway_module_passed": bool(takeaway_module) and _bool((final_gate.get("checks") or {}).get("takeaway_module_passed") if final_gate else True),
        "template_control_passed": _bool((score_report.get("quality_gates") or {}).get("template_penalty_passed")) or not any("模板腔" in item for item in _failed_checks(reader_gate)),
        "batch_uniqueness_passed": _bool((final_gate.get("checks") or {}).get("batch_uniqueness_passed")),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "2026-05-viral-moment-map-v1",
        "click_reason": _clean(reader_gate.get("click_reason")),
        "continue_reason": _clean(reader_gate.get("continue_reason")),
        "share_line": _clean(reader_gate.get("share_line")),
        "share_lines": share_lines[:8],
        "share_line_score": int(reader_gate.get("share_line_score") or 0),
        "comment_seed": _clean(reader_gate.get("comment_seed")),
        "takeaway_module_type": takeaway_module,
        "checks": checks,
        "failed_checks": failed,
        "passed": not failed,
    }


def build_layout_render_audit(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    meta, body = _load_article(workspace, manifest)
    html_path = workspace / _clean(manifest.get("wechat_html_path") or "article.wechat.html")
    html = read_text(html_path) if html_path.exists() else ""
    layout_json = _artifact_exists(workspace, manifest, "layout_plan_path", "layout-plan.json")
    layout_md = (workspace / "layout-plan.md").exists()
    image_plan = _load_json(workspace, manifest, "image_plan_path", "image-plan.json")
    image_items = list(image_plan.get("items") or [])
    expected_inline = int(image_plan.get("planned_inline_count") or manifest.get("expected_inline_count") or 0)
    html_img_count = len(re.findall(r"<img\b", html, flags=re.I))
    html_h2_count = len(re.findall(r"<h2\b", html, flags=re.I))
    table_rows = len(re.findall(r"(?m)^\s*\|.+\|\s*$", body or ""))
    has_sources = bool(manifest.get("source_urls") or (workspace / "references.json").exists() or (workspace / "evidence-report.json").exists())
    source_visible = (not has_sources) or ("data-wx-source-style" in html) or ("参考" in html) or ("来源" in html)
    first_image_before_h2 = True
    first_img = html.lower().find("<img")
    first_h2 = html.lower().find("<h2")
    if first_img >= 0 and first_h2 >= 0:
        first_image_before_h2 = first_img < first_h2
    checks = {
        "layout_plan_present": layout_json and layout_md,
        "wechat_html_present": html_path.exists() and bool(html.strip()),
        "inline_image_count_passed": html_img_count >= max(1, expected_inline) if image_items else html_img_count > 0,
        "first_image_before_first_h2": first_image_before_h2,
        "heading_hierarchy_passed": html_h2_count >= 3,
        "judgment_table_present": table_rows >= 2 or "<table" in html.lower(),
        "source_block_visible": source_visible,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "2026-05-layout-render-audit-v1",
        "html_image_count": html_img_count,
        "expected_inline_count": expected_inline,
        "html_h2_count": html_h2_count,
        "table_row_count": table_rows,
        "has_sources": has_sources,
        "checks": checks,
        "failed_checks": failed,
        "passed": not failed,
    }


REWORK_ACTIONS = {
    "title_report_missing": "补齐标题决策报告，保留候选、评分、重写理由和最终选择证据。",
    "first_screen_failed": "重写标题下方和前两段，补具体场景、动作、关系和损失/冲突。",
    "material_coverage_failed": "补素材包：至少加入引用/来源、案例、对比、类比、反方边界和服务判断的表格。",
    "viral_moment_failed": "补传播模块：可转述金句、评论引子、朋友圈分享句、收藏模块和自然结尾。",
    "layout_render_failed": "补 layout-plan 并重渲染，检查首图、标题层级、表格铺垫、来源区块和移动端阅读节奏。",
    "image_policy_failed": "重做图片计划，确保图片承担点击、解释、记忆或转发角色，并避免同批视觉重复。",
    "batch_uniqueness_failed": "换角度重写，拉开标题结构、开头方式、正文骨架、结尾模块和视觉路线。",
    "force_publish_used": "标记为强制发布，不得计入真合格成品。",
    "quality_chain_failed": "继续走针对性回炉，直到评分、读者门、视觉门和最终门同时通过。",
    "topic_package_failed": "补齐选题包：热点理由、争议点、受众身份、素材潜力和重复风险。",
}


def build_factory_acceptance_report(workspace: Path, manifest: dict[str, Any], delivery_report: dict[str, Any] | None = None) -> dict[str, Any]:
    delivery_report = delivery_report or _load_json(workspace, manifest, "delivery_report_path", "final-delivery-report.json")
    has_content_artifacts = bool(delivery_report) or any((workspace / name).exists() for name in ("article.md", "score-report.json", "reader_gate.json", "visual_gate.json", "final_gate.json", "article.wechat.html"))
    topic_package = build_topic_package(workspace, manifest, delivery_report=delivery_report)
    material_pack = build_material_pack(workspace, manifest)
    viral_moment_map = build_viral_moment_map(workspace, manifest)
    layout_render_audit = build_layout_render_audit(workspace, manifest)
    visual_gate = _load_json(workspace, manifest, "visual_gate_path", "visual_gate.json")
    final_gate = _load_json(workspace, manifest, "final_gate_path", "final_gate.json")
    title_report_present = (workspace / _clean(manifest.get("title_decision_report_path") or "title-decision-report.json")).exists() or (workspace / _clean(manifest.get("title_report_path") or "title-report.json")).exists()
    quality_chain = delivery_report.get("quality_chain") or {}
    publish_chain = delivery_report.get("publish_chain") or {}
    batch_chain = delivery_report.get("batch_chain") or {}
    force_publish = bool(delivery_report.get("force_publish") or publish_chain.get("force_publish") or manifest.get("force_publish_reason"))
    published = bool(delivery_report.get("published") or publish_chain.get("published"))
    readback = bool(delivery_report.get("readback_passed") or publish_chain.get("readback_passed"))
    blocking_reasons: list[str] = []
    if not title_report_present:
        blocking_reasons.append("title_report_missing")
    if not topic_package.get("passed"):
        blocking_reasons.append("topic_package_failed")
    if not viral_moment_map["checks"].get("opening_four_factors_passed"):
        blocking_reasons.append("first_screen_failed")
    if not material_pack.get("passed"):
        blocking_reasons.append("material_coverage_failed")
    if not viral_moment_map.get("passed"):
        blocking_reasons.append("viral_moment_failed")
    if not layout_render_audit.get("passed"):
        blocking_reasons.append("layout_render_failed")
    if visual_gate and not visual_gate.get("passed"):
        blocking_reasons.append("image_policy_failed")
    if (final_gate.get("checks") or {}).get("batch_uniqueness_passed") is False or batch_chain.get("status") == "failed":
        blocking_reasons.append("batch_uniqueness_failed")
    if force_publish:
        blocking_reasons.append("force_publish_used")
    if quality_chain and not quality_chain.get("passed"):
        blocking_reasons.append("quality_chain_failed")
    if not has_content_artifacts:
        blocking_reasons = []
    blocking_reasons = sorted(set(blocking_reasons))
    viral_ready = not blocking_reasons and topic_package.get("passed") and material_pack.get("passed") and viral_moment_map.get("passed")
    quality_ready = bool((delivery_report.get("quality_passed") or quality_chain.get("passed")) and viral_ready)
    publish_ready = bool(quality_ready and readback and published and not force_publish)
    if publish_ready:
        status = "passed"
        grade_label = "真合格成品"
    elif published and readback:
        status = "force_publish_only" if force_publish else "published_but_unqualified"
        grade_label = "已发布但不合格"
    elif has_content_artifacts:
        status = "needs_rework"
        grade_label = "待返工"
    else:
        status = "incomplete"
        grade_label = "生产中"
    top_rework_actions = [REWORK_ACTIONS[key] for key in blocking_reasons if key in REWORK_ACTIONS][:3]
    return {
        "schema_version": FACTORY_ACCEPTANCE_SCHEMA_VERSION,
        "workspace": workspace.name,
        "generated_at": now_iso(),
        "status": status,
        "grade_label": grade_label,
        "factory_mode": "viral_quality",
        "quality_ready": quality_ready,
        "publish_ready": publish_ready,
        "viral_ready": viral_ready,
        "published": published,
        "readback_passed": readback,
        "force_publish": force_publish,
        "blocking_reasons": blocking_reasons,
        "top_rework_actions": top_rework_actions,
        "topic_package": topic_package,
        "material_pack": material_pack,
        "viral_moment_map": viral_moment_map,
        "layout_render_audit": layout_render_audit,
    }


def markdown_factory_acceptance_report(payload: dict[str, Any]) -> str:
    lines = [
        f"# 工厂验收报告：{payload.get('workspace') or '未命名工作区'}",
        "",
        f"- 工厂结果：{payload.get('grade_label')}",
        f"- 是否真合格：{'是' if payload.get('status') == 'passed' else '否'}",
        f"- 是否强制发布：{'是' if payload.get('force_publish') else '否'}",
        f"- 是否已发布回读：{'是' if payload.get('published') and payload.get('readback_passed') else '否'}",
    ]
    blockers = [str(item) for item in payload.get("blocking_reasons") or []]
    if blockers:
        lines.extend(["", "## 阻塞原因", ""])
        lines.extend(f"- {item}" for item in blockers)
    actions = [str(item) for item in payload.get("top_rework_actions") or []]
    if actions:
        lines.extend(["", "## 优先返工", ""])
        lines.extend(f"- {item}" for item in actions)
    return "\n".join(lines).strip() + "\n"


def build_factory_audit(root: Path) -> dict[str, Any]:
    root = Path(root)
    items: list[dict[str, Any]] = []
    reason_counter: Counter[str] = Counter()
    artifact_counter: Counter[str] = Counter()
    quality_gate_counter: Counter[str] = Counter()
    reader_counter: Counter[str] = Counter()
    visual_counter: Counter[str] = Counter()
    for workspace in sorted(path for path in root.iterdir() if path.is_dir()) if root.exists() else []:
        if workspace.name.startswith("edge-profile"):
            continue
        manifest_path = workspace / "manifest.json"
        if not manifest_path.exists():
            continue
        manifest = read_json(manifest_path, default={}) or {}
        delivery = _load_json(workspace, manifest, "delivery_report_path", "final-delivery-report.json")
        acceptance = build_factory_acceptance_report(workspace, manifest, delivery)
        for reason in acceptance.get("blocking_reasons") or []:
            reason_counter[str(reason)] += 1
        for name in ("title-decision-report.json", "layout-plan.json", "layout-plan.md", "score-report.json", "reader_gate.json", "visual_gate.json", "final_gate.json"):
            if not (workspace / name).exists():
                artifact_counter[name] += 1
        final_gate = _load_json(workspace, manifest, "final_gate_path", "final_gate.json")
        reader_gate = _load_json(workspace, manifest, "reader_gate_path", "reader_gate.json")
        visual_gate = _load_json(workspace, manifest, "visual_gate_path", "visual_gate.json")
        for item in _failed_checks(final_gate):
            quality_gate_counter[item] += 1
        for item in _failed_checks(reader_gate):
            reader_counter[item] += 1
        for item in _failed_checks(visual_gate):
            visual_counter[item] += 1
        items.append(
            {
                "workspace": workspace.name,
                "status": acceptance.get("status"),
                "grade_label": acceptance.get("grade_label"),
                "published": acceptance.get("published"),
                "readback_passed": acceptance.get("readback_passed"),
                "force_publish": acceptance.get("force_publish"),
                "blocking_reasons": acceptance.get("blocking_reasons") or [],
                "top_rework_actions": acceptance.get("top_rework_actions") or [],
            }
        )
    published_count = sum(1 for item in items if item.get("published"))
    readback_count = sum(1 for item in items if item.get("readback_passed"))
    force_count = sum(1 for item in items if item.get("force_publish"))
    published_force_count = sum(1 for item in items if item.get("published") and item.get("force_publish"))
    true_qualified = sum(1 for item in items if item.get("status") == "passed")
    published_unqualified = sum(1 for item in items if item.get("published") and item.get("status") != "passed")
    status_counts = Counter(str(item.get("grade_label") or item.get("status")) for item in items)
    return {
        "schema_version": "2026-05-factory-audit-v1",
        "root": str(root.resolve()),
        "generated_at": now_iso(),
        "metrics": {
            "total": len(items),
            "status_counts": dict(status_counts),
            "published_count": published_count,
            "readback_count": readback_count,
            "force_publish_count": force_count,
            "published_force_publish_count": published_force_count,
            "true_qualified_count": true_qualified,
            "published_unqualified_count": published_unqualified,
            "force_publish_rate": round(published_force_count / max(1, published_count), 4),
            "published_unqualified_rate": round(published_unqualified / max(1, published_count), 4),
        },
        "top_blocking_reasons": reason_counter.most_common(20),
        "missing_artifact_counts": artifact_counter.most_common(20),
        "top_quality_failed_gates": quality_gate_counter.most_common(20),
        "top_reader_failed_checks": reader_counter.most_common(20),
        "top_visual_failed_checks": visual_counter.most_common(20),
        "items": items,
    }
