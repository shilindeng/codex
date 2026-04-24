from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.analysis_11d import build_analysis_11d, score_analysis_11d, summarize_analysis_11d
from core.artifacts import extract_summary, now_iso, read_json, read_text, split_frontmatter
from core.quality_checks import cost_signal_present, discussion_trigger_present, scene_signal_present, split_markdown_paragraphs, visible_length
from core.reader_gates import (
    _share_lines,
    _summary_duplicates_opening,
    _takeaway_module_type,
    first_screen_signal_report,
    image_plan_gate_report,
    template_frequency_report,
)
from core.three_layers import build_three_layer_diagnostics

IMAGE_ROLE_LABELS = {
    "click": "点开",
    "explain": "解释",
    "remember": "记住",
    "share": "转发",
}

IMAGE_DENSITY_RANGES: dict[str, tuple[int, int]] = {
    "none": (0, 0),
    "minimal": (0, 1),
    "balanced": (1, 2),
    "dense": (2, 4),
}

AI_LABEL_ALLOWLIST = ("AI", "Agent", "OpenAI", "ChatGPT", "Gemini", "Google", "Meta", "API", "GPU", "Codex")
_UI_STYLE_WORDS = ("UI", "按钮", "界面", "面板", "dashboard", "screen", "app", "icon")

_WEAK_TEXT_PATTERNS = (
    r"值得关注",
    r"很重要",
    r"有变化",
    r"聊一聊",
    r"值得一看",
    r"继续往下看",
    r"欢迎讨论",
)
_SHARE_LINE_PATTERNS = (
    r"不是.{1,24}而是.{1,24}",
    r"问题不在.{1,24}而在.{1,24}",
    r"真正.{0,10}不是.{1,24}而是.{1,24}",
)


def _text_density_limits(image_type: str) -> tuple[int, int]:
    if image_type == "封面图":
        return 2, 14
    if image_type in {"流程图", "信息图", "对比图"}:
        return 3, 12
    return 1, 6


def _looks_like_sentence_fragment(label: str) -> bool:
    value = str(label or "").strip()
    if any(value.startswith(prefix) for prefix in ("这次", "接下来", "很多人", "不只是", "不是", "可能", "会是", "如果")):
        return True
    return len(value) >= 7 and not any(token in value for token in AI_LABEL_ALLOWLIST)


def _has_disallowed_english_label(label: str) -> bool:
    cleaned = str(label or "")
    for token in sorted(AI_LABEL_ALLOWLIST, key=len, reverse=True):
        cleaned = re.sub(re.escape(token), "", cleaned, flags=re.I)
    return bool(re.search(r"[A-Za-z]{2,}", cleaned))

_BLOCKED_TEMPLATE_PHRASES = (
    "真正值得看的是",
    "这也是",
    "最后可以",
    "这张清单值得保存",
    "这份清单值得保存",
)

_ROLE_WORDS = ("家长", "父母", "求职者", "财务", "运营", "产品经理", "企业负责人", "小老板", "工程师", "用户", "普通人", "子女", "老人")
_DETAIL_WORDS = ("现场", "赛道", "会议室", "群里", "工单", "账单", "报价", "订单", "手机号", "药盒", "加油", "船期")
_COMPARISON_WORDS = ("对比", "过去", "现在", "前者", "后者", "相比", "不再", "从", "转向")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_density_mode(value: str) -> str:
    normalized = _clean(value).lower().replace("_", "-")
    if normalized in {"", "auto"}:
        return "auto"
    if normalized in {"rich", "per-section"}:
        return "dense"
    if normalized in {"none", "minimal", "balanced", "dense", "custom"}:
        return normalized
    return "auto"


def _load_article_meta(workspace: Path, manifest: dict[str, Any]) -> tuple[str, str, str]:
    article_rel = str(manifest.get("article_path") or "article.md")
    article_path = workspace / article_rel
    if not article_path.exists():
        return "", "", ""
    meta, body = split_frontmatter(read_text(article_path))
    title = str(manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "").strip()
    summary = str(meta.get("summary") or manifest.get("summary") or extract_summary(body)).strip()
    return title, summary, body


def _analysis_payload(score_report: dict[str, Any], review_report: dict[str, Any]) -> dict[str, Any]:
    return (review_report.get("viral_analysis") or score_report.get("viral_analysis") or {}) if isinstance(review_report, dict) else (score_report.get("viral_analysis") or {})


def _depth_payload(score_report: dict[str, Any], review_report: dict[str, Any]) -> dict[str, Any]:
    return (score_report.get("depth_signals") or review_report.get("depth_signals") or {}) if isinstance(review_report, dict) else (score_report.get("depth_signals") or {})


def _material_payload(score_report: dict[str, Any], review_report: dict[str, Any]) -> dict[str, Any]:
    return (score_report.get("material_signals") or review_report.get("material_signals") or {}) if isinstance(review_report, dict) else (score_report.get("material_signals") or {})


def _analysis_11d_payload(
    title: str,
    summary: str,
    body: str,
    score_report: dict[str, Any],
    review_report: dict[str, Any],
) -> dict[str, Any]:
    existing = (review_report.get("analysis_11d") or score_report.get("analysis_11d") or {}) if isinstance(review_report, dict) else (score_report.get("analysis_11d") or {})
    if existing:
        return existing
    return build_analysis_11d(
        title=title,
        body=body,
        summary=summary,
        analysis=_analysis_payload(score_report, review_report),
        depth=_depth_payload(score_report, review_report),
        material_signals=_material_payload(score_report, review_report),
        humanness_signals=(score_report.get("humanness_signals") or review_report.get("humanness_signals") or {}) if isinstance(review_report, dict) else (score_report.get("humanness_signals") or {}),
    )


def _weak_text(value: str) -> bool:
    text = _clean(value)
    if len(text) < 12:
        return True
    if not re.search(r"[\u4e00-\u9fffA-Za-z0-9]{4,}", text):
        return True
    return any(re.search(pattern, text) for pattern in _WEAK_TEXT_PATTERNS)


def _candidate_sentences(body: str) -> list[str]:
    candidates: list[str] = []
    for paragraph in split_markdown_paragraphs(body):
        for raw in re.split(r"(?<=[。！？!?])", paragraph):
            item = _clean(raw).strip("。！？!? ")
            if 12 <= len(item) <= 48:
                candidates.append(item)
    return candidates


def _table_intro_failures(body: str) -> list[str]:
    lines = str(body or "").splitlines()
    failures: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        if index + 1 < len(lines) and re.match(r"^\s*\|?\s*:?-{2,}:?\s*\|", lines[index + 1]):
            previous = ""
            for back_index in range(index - 1, -1, -1):
                previous = lines[back_index].strip()
                if previous:
                    break
            if not previous or (not cost_signal_present(previous) and not re.search(r"(问题|风险|后果|代价|误判|卡住|失控|冲突)", previous)):
                failures.append("表格前缺少真实问题或代价铺垫")
    return failures[:3]


def _hard_evidence_types(body: str, evidence_items: list[Any]) -> set[str]:
    corpus = "\n".join(split_markdown_paragraphs(body))
    types: set[str] = set()
    if evidence_items:
        types.add("source")
    if re.search(r"\d", corpus):
        types.add("number")
    if any(word in corpus for word in _DETAIL_WORDS) or any(scene_signal_present(item) for item in split_markdown_paragraphs(body)):
        types.add("detail")
    if any(word in corpus for word in _COMPARISON_WORDS):
        types.add("comparison")
    if any(word in corpus for word in _ROLE_WORDS):
        types.add("role")
    if cost_signal_present(corpus):
        types.add("cost")
    return types


def _ending_template_failures(body: str, comment_seed: str) -> list[str]:
    paragraphs = split_markdown_paragraphs(body)
    ending = " ".join(paragraphs[-2:])
    failures: list[str] = []
    if re.search(r"(这[张份]清单值得保存|下次.*问.*问题|最后可以)", ending) and not discussion_trigger_present(ending + " " + comment_seed):
        failures.append("结尾只收成清单或三问，缺少自然分歧点")
    return failures


def _share_line(body: str, analysis: dict[str, Any]) -> str:
    for item in analysis.get("target_quotes") or []:
        text = _clean(str(item))
        if 12 <= len(text) <= 48:
            return text
    ranked = sorted(
        _candidate_sentences(body),
        key=lambda item: (
            any(re.search(pattern, item) for pattern in _SHARE_LINE_PATTERNS),
            any(keyword in item for keyword in ["代价", "成本", "后果", "误判", "真正", "问题"]),
            len(item),
        ),
        reverse=True,
    )
    return ranked[0] if ranked else ""


def _comment_seed(title: str, body: str, analysis: dict[str, Any]) -> str:
    for paragraph in split_markdown_paragraphs(body):
        if discussion_trigger_present(paragraph):
            return _clean(paragraph)[:48]
    viewpoints = [_clean(str(item)) for item in (analysis.get("secondary_viewpoints") or []) if _clean(str(item))]
    if len(viewpoints) >= 2:
        left = viewpoints[0][:18]
        right = viewpoints[1][:18]
        return f"你更认同哪一种：{left}，还是{right}？"
    core = _clean(str(analysis.get("core_viewpoint") or ""))
    if core:
        return f"如果是你，你会先处理“{core[:20]}”吗？"
    if title:
        return f"如果是你，你会怎么处理这件事：{title[:22]}？"
    return ""


def _click_reason(title: str, first_screen: dict[str, Any], analysis: dict[str, Any]) -> str:
    if title and len(title) >= 12:
        if any(keyword in title for keyword in ["代价", "成本", "后果", "误判", "岗位", "风险", "判断"]):
            return f"标题直接点出了读者会在意的代价或判断：{title}"
        return f"标题先把关键冲突挑明了：{title}"
    core = _clean(str(analysis.get("core_viewpoint") or ""))
    if core:
        return f"开头要讲的不是热闹，而是这件事真正会影响什么：{core[:28]}"
    lead = _clean(str(first_screen.get("lead_excerpt") or ""))
    return lead[:32]


def _continue_reason(body: str, first_screen: dict[str, Any]) -> str:
    paragraphs = split_markdown_paragraphs(body)
    lead = " ".join(paragraphs[:2]).strip()
    if lead:
        return lead[:64]
    return _clean(str(first_screen.get("lead_excerpt") or ""))


def _title_consistency_issues(workspace: Path, manifest: dict[str, Any], title: str) -> list[str]:
    expected = _clean(title or manifest.get("selected_title") or "")
    if not expected:
        return []
    sources = {
        "manifest.json": manifest.get("selected_title"),
        "ideation.json": (read_json(workspace / "ideation.json", default={}) or {}).get("selected_title"),
        "title-report.json": (read_json(workspace / "title-report.json", default={}) or {}).get("selected_title"),
        "title-decision-report.json": (read_json(workspace / "title-decision-report.json", default={}) or {}).get("selected_title"),
    }
    article_path = workspace / str(manifest.get("article_path") or "article.md")
    if article_path.exists():
        meta, _body = split_frontmatter(read_text(article_path))
        sources["article.md"] = meta.get("title")
    issues: list[str] = []
    normalized = re.sub(r"\s+", "", expected)
    for source_name, raw in sources.items():
        value = _clean(str(raw or ""))
        if value and re.sub(r"\s+", "", value) != normalized:
            issues.append(f"{source_name} 标题和当前真源不一致")
    return issues


def _infer_image_role(item: dict[str, Any], image_plan: dict[str, Any]) -> tuple[str, str]:
    image_type = str(item.get("type") or "").strip()
    insert_strategy = str(item.get("insert_strategy") or "").strip()
    article_category = str(image_plan.get("article_category") or "").strip()
    visual_route = str((image_plan.get("article_visual_strategy") or {}).get("visual_route") or "").strip()
    if image_type == "封面图" or insert_strategy == "cover_only":
        return "click", "封面图负责让读者先点开。"
    if insert_strategy == "section_end":
        if image_type in {"信息图", "对比图", "流程图"} or visual_route == "conflict-alert":
            return "share", "结尾结构图更适合做可转述、可转发的收束。"
        return "remember", "结尾概念图负责帮助读者记住最后判断。"
    if image_type in {"信息图", "对比图", "流程图"}:
        return "explain", "结构图优先承担解释任务。"
    if image_type == "分隔图":
        return "remember", "分隔图负责帮读者记住节奏与母题。"
    if any(keyword in article_category for keyword in ["分析", "教程", "案例"]):
        return "explain", "这类文章正文图优先帮读者理解。"
    return "remember", "正文概念图优先承担记忆锚点。"


def build_reader_gate(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    title: str,
    summary: str,
    body: str,
    score_report: dict[str, Any],
    review_report: dict[str, Any],
) -> dict[str, Any]:
    first_screen = first_screen_signal_report(body)
    analysis = _analysis_payload(score_report, review_report)
    analysis_11d = _analysis_11d_payload(title, summary, body, score_report, review_report)
    depth = _depth_payload(score_report, review_report)
    paragraphs = split_markdown_paragraphs(body)
    evidence_items = (read_json(workspace / "research.json", default={}) or {}).get("evidence_items") or []
    evidence_count = max(int(depth.get("evidence_paragraph_count") or 0), len(evidence_items))
    evidence_types = _hard_evidence_types(body, evidence_items)
    scene_count = int(depth.get("scene_paragraph_count") or 0) or sum(1 for item in paragraphs if scene_signal_present(item))
    counterpoint_count = int(depth.get("counterpoint_paragraph_count") or 0)
    cost_count = sum(1 for item in paragraphs if cost_signal_present(item))
    click_reason = _click_reason(title, first_screen, analysis)
    continue_reason = _continue_reason(body, first_screen)
    share_line = _clean(((analysis_11d.get("signature_quotes") or [""])[0])) or _share_line(body, analysis)
    share_lines = _share_lines(body, analysis_11d, analysis)
    share_line_score = min(10, len(share_lines) * 3 + (1 if any(visible_length(item) >= 20 for item in share_lines) else 0))
    takeaway_module_type = _takeaway_module_type(body)
    summary_opening_duplicate = _summary_duplicates_opening(summary, body)
    opening_four_factors_passed = bool(first_screen.get("four_question_passed")) and not summary_opening_duplicate
    hooks = analysis_11d.get("interaction_hooks") or {}
    comment_seed = (
        _clean(((hooks.get("comment_triggers") or hooks.get("poll_prompts") or hooks.get("fill_blank_prompts") or [""])[0]))
        or _comment_seed(title, body, analysis)
    )
    fields = {
        "click_reason": click_reason,
        "continue_reason": continue_reason,
        "share_line": share_line,
        "comment_seed": comment_seed,
    }
    weak_fields = [key for key, value in fields.items() if _weak_text(value)]
    failed_checks: list[str] = []
    if evidence_count < 2:
        failed_checks.append("正文证据不足 2 条")
    if len(evidence_types) < 2:
        failed_checks.append("硬证据类型不足，至少需要来源、数字、现场细节、角色、成本或前后对照中的两类")
    if scene_count < 1:
        failed_checks.append("开头缺少具体场景")
    if first_screen and not first_screen.get("four_question_passed", False):
        failed_checks.append("首屏四问未齐：具体人、具体动作、关系/重要性、损失或冲突")
    if summary_opening_duplicate:
        failed_checks.append("副标题或摘要与正文第一句重复，浪费首屏空间")
    if cost_count < 1:
        failed_checks.append("正文缺少真实代价")
    if counterpoint_count < 1:
        failed_checks.append("正文缺少反方或边界")
    if not share_line:
        failed_checks.append("缺少可截图转述的一句话")
    if len(share_lines) < 3:
        failed_checks.append("可截图传播句不足 3 条")
    if takeaway_module_type == "none":
        failed_checks.append("缺少可保存模块：三问卡/四步卡/对比表/判断卡/风险清单")
    if not comment_seed:
        failed_checks.append("缺少自然评论触发点")
    if len(weak_fields) >= 2:
        failed_checks.append("四个读者问题里至少有两项回答过弱")
    failed_checks.extend(_table_intro_failures(body))
    failed_checks.extend(_ending_template_failures(body, comment_seed))
    template_hits = [phrase for phrase in _BLOCKED_TEMPLATE_PHRASES if phrase in body]
    if template_hits:
        failed_checks.append(f"命中模板腔黑名单：{'、'.join(template_hits[:3])}")
    passed = not failed_checks
    return {
        "title": title,
        "summary": summary,
        "click_reason": click_reason,
        "continue_reason": continue_reason,
        "share_line": share_line,
        "share_lines": share_lines,
        "share_line_score": share_line_score,
        "comment_seed": comment_seed,
        "takeaway_module_type": takeaway_module_type,
        "summary_opening_duplicate": summary_opening_duplicate,
        "opening_four_factors_passed": opening_four_factors_passed,
        "weak_fields": weak_fields,
        "evidence_count": evidence_count,
        "hard_evidence_types": sorted(evidence_types),
        "scene_count": scene_count,
        "cost_signal_count": cost_count,
        "counterpoint_count": counterpoint_count,
        "analysis_11d": analysis_11d,
        "first_screen": first_screen,
        "failed_checks": failed_checks,
        "passed": passed,
        "generated_at": now_iso(),
    }


def build_visual_gate(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    image_plan: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = image_plan or {}
    items = [dict(item) for item in (payload.get("items") or [])]
    image_plan_report = image_plan_gate_report(payload, workspace=workspace)
    wechat_html_path = workspace / str(manifest.get("wechat_html_path") or "article.wechat.html")
    wechat_html = read_text(wechat_html_path) if wechat_html_path.exists() else ""
    density_mode = _normalize_density_mode(
        str((payload.get("image_controls") or {}).get("density_mode") or payload.get("density_mode") or (manifest.get("image_controls") or {}).get("density_mode") or "")
    )
    planned_inline_count = int(payload.get("planned_inline_count") or 0)
    inline_items = [item for item in items if str(item.get("insert_strategy") or "") == "section_middle"]
    closing_items = [item for item in items if str(item.get("insert_strategy") or "") == "section_end"]
    inline_range_payload = payload.get("inline_density_range") or {}
    expected_min = int(inline_range_payload.get("min") or 0)
    expected_max = int(inline_range_payload.get("max") or 0)
    if density_mode in IMAGE_DENSITY_RANGES:
        expected_min, expected_max = IMAGE_DENSITY_RANGES[density_mode]
    elif density_mode == "custom":
        expected_min = expected_max = int(payload.get("requested_inline_count") or 0)
    elif density_mode == "auto" and planned_inline_count:
        if planned_inline_count <= 1:
            expected_min, expected_max = 0, 1
        elif planned_inline_count == 2:
            expected_min, expected_max = 1, 2
        else:
            expected_min, expected_max = 2, 4
    allow_closing_image = str((payload.get("closing_image_rule") or {}).get("mode") or (payload.get("image_controls") or {}).get("allow_closing_image") or "auto")
    closing_required = allow_closing_image == "on"
    closing_forbidden = allow_closing_image == "off"
    role_items: list[dict[str, Any]] = []
    missing_roles: list[str] = []
    role_counts: dict[str, int] = {}
    for item in items:
        role = str(item.get("role") or "").strip().lower()
        reason = _clean(str(item.get("role_reason") or ""))
        if role not in IMAGE_ROLE_LABELS:
            role, reason = _infer_image_role(item, payload)
        item["role"] = role
        item["role_label"] = IMAGE_ROLE_LABELS.get(role, "")
        item["role_reason"] = reason
        if role not in IMAGE_ROLE_LABELS:
            missing_roles.append(str(item.get("id") or ""))
        else:
            role_counts[role] = int(role_counts.get(role) or 0) + 1
        role_items.append({"id": item.get("id"), "type": item.get("type"), "role": role, "role_label": item.get("role_label"), "reason": reason})
    article_category = str(payload.get("article_category") or "")
    requires_explain_role = any(keyword in article_category for keyword in ["分析", "教程", "案例"]) or bool(inline_items)
    explain_role_present = role_counts.get("explain", 0) >= 1 if requires_explain_role else True
    density_ok = expected_min <= len(inline_items) <= expected_max if expected_max or expected_min else len(inline_items) == 0
    if density_mode == "auto" and not payload:
        density_ok = False
    closing_ok = True
    if closing_required:
        closing_ok = bool(closing_items)
    elif closing_forbidden:
        closing_ok = not closing_items
    text_policy_failures: list[str] = []
    asset_failures: list[str] = []
    codex_mode = str(payload.get("provider") or "").strip().lower() == "codex"
    for item in items:
        image_type = str(item.get("type") or "")
        policy = str(item.get("text_policy") or "")
        insert_strategy = str(item.get("insert_strategy") or "")
        required_labels = [str(value or "").strip() for value in (item.get("required_text") or []) if str(value or "").strip()]
        suggested_labels = [str(value or "").strip() for value in (item.get("suggested_text") or []) if str(value or "").strip()]
        label_strategy = required_labels or suggested_labels or [str(value or "").strip() for value in (item.get("label_strategy") or []) if str(value or "").strip()]
        asset_path = _clean(str(item.get("asset_path") or ""))
        if asset_path and not (workspace / asset_path).exists():
            asset_failures.append(f"{item.get('id')} 缺少生成图片文件")
        if codex_mode:
            if policy not in {"short-zh", "short-zh-numeric", "short-any"}:
                text_policy_failures.append(f"{item.get('id')} Codex 图片必须配置短字策略")
            if image_type == "封面图" and not required_labels:
                text_policy_failures.append(f"{item.get('id')} Codex 图片缺少 required_text")
            if image_type != "封面图" and required_labels and image_type not in {"流程图", "信息图", "对比图"}:
                text_policy_failures.append(f"{item.get('id')} 正文概念图不应强制 required_text")
            max_count, max_chars = _text_density_limits(image_type)
            if len(label_strategy) > max_count:
                text_policy_failures.append(f"{item.get('id')} 图中文字数量过多")
            if len("".join(label_strategy)) > max_chars:
                text_policy_failures.append(f"{item.get('id')} 图中文字过密")
            if any(_looks_like_sentence_fragment(label) for label in label_strategy):
                text_policy_failures.append(f"{item.get('id')} 图中文字像半句话")
        elif image_type == "封面图" and policy != "none":
            text_policy_failures.append(f"{item.get('id')} 封面图应为无文字")
        elif insert_strategy == "section_middle" and image_type in {"正文插图", "分隔图"} and policy != "none":
            text_policy_failures.append(f"{item.get('id')} 正文概念图应为无文字")
        elif image_type in {"信息图", "流程图"} and policy not in {"short-zh", "short-zh-numeric"}:
            text_policy_failures.append(f"{item.get('id')} 结构图文字策略不对")
        elif image_type == "对比图" and policy not in {"short-zh", "none"}:
            text_policy_failures.append(f"{item.get('id')} 对比图文字策略不对")
        if insert_strategy == "section_middle" and any(_has_disallowed_english_label(label) for label in label_strategy):
            text_policy_failures.append(f"{item.get('id')} 正文图标签里出现英文")
        if insert_strategy == "section_middle" and any(len(label) >= 10 for label in label_strategy):
            text_policy_failures.append(f"{item.get('id')} 正文图标签过长")
        if insert_strategy == "section_middle" and any(any(word in label for word in _UI_STYLE_WORDS) for label in label_strategy):
            text_policy_failures.append(f"{item.get('id')} 正文图标签带 UI 说明词")
    lead_visual_passed = True
    if wechat_html:
        first_img = wechat_html.find("<img")
        first_h2 = wechat_html.find("<h2")
        if first_img != -1 and first_h2 != -1:
            lead_visual_passed = first_img < first_h2
    failed_checks: list[str] = []
    if not payload:
        failed_checks.append("缺少 image-plan.json")
    if not density_ok:
        failed_checks.append("正文配图数量不在配置范围内")
    if missing_roles:
        failed_checks.append("存在未分配图片任务的图片")
    if not explain_role_present:
        failed_checks.append("正文至少要有一张真正承担解释任务的图片")
    if not closing_ok:
        failed_checks.append("结尾图配置和实际产出不一致")
    if text_policy_failures:
        failed_checks.append("图片文字策略不符合当前规则")
    if asset_failures:
        failed_checks.append("图片计划中的生成文件不存在")
    if not image_plan_report.get("passed", True):
        failed_checks.append("图片路线或视觉约束未通过")
    if not lead_visual_passed:
        failed_checks.append("第一张正文图没有提前到首个二级标题前")
    passed = not failed_checks
    return {
        "density_mode": density_mode,
        "cover_excluded_from_density": True,
        "planned_inline_count": len(inline_items),
        "requested_inline_count": int(payload.get("requested_inline_count") or 0),
        "inline_density_range": {"min": expected_min, "max": expected_max},
        "allow_closing_image": allow_closing_image,
        "closing_image_enabled": bool(closing_items),
        "role_items": role_items,
        "role_counts": role_counts,
        "missing_roles": missing_roles,
        "requires_explain_role": requires_explain_role,
        "explain_role_present": explain_role_present,
        "text_policy_failures": text_policy_failures,
        "asset_failures": asset_failures,
        "lead_visual_passed": lead_visual_passed,
        "image_plan_report": image_plan_report,
        "failed_checks": failed_checks,
        "passed": passed,
        "generated_at": now_iso(),
    }


def build_final_gate(
    workspace: Path,
    manifest: dict[str, Any],
    *,
    title: str,
    body: str,
    score_report: dict[str, Any],
    review_report: dict[str, Any],
    acceptance_report: dict[str, Any],
    reader_gate: dict[str, Any],
    visual_gate: dict[str, Any],
) -> dict[str, Any]:
    analysis = _analysis_payload(score_report, review_report)
    analysis_11d = _analysis_11d_payload(title, str(manifest.get("summary") or ""), body, score_report, review_report)
    depth = _depth_payload(score_report, review_report)
    material_signals = _material_payload(score_report, review_report)
    three_layers = (
        acceptance_report.get("three_layer_diagnostics")
        or score_report.get("three_layer_diagnostics")
        or build_three_layer_diagnostics(
            title=title,
            body=body,
            blueprint=manifest.get("viral_blueprint") or {},
            analysis=analysis,
            depth=depth,
            material_signals=material_signals,
            topic=str(manifest.get("topic") or title),
            audience=str(manifest.get("audience") or "公众号读者"),
        )
    )
    hook_score = int((three_layers.get("hook") or {}).get("score") or 0)
    insight_score = int((three_layers.get("insight") or {}).get("score") or 0)
    takeaway_score = int((three_layers.get("takeaway") or {}).get("score") or 0)
    total_score = int(score_report.get("total_score") or 0)
    dimension_11d_scores = score_report.get("dimension_11d_scores") or score_analysis_11d(analysis_11d)
    dimension_11d_summary = score_report.get("dimension_11d_summary") or summarize_analysis_11d(analysis_11d, dimension_11d_scores)
    language_style = analysis_11d.get("language_style") or {}
    interaction_hooks = analysis_11d.get("interaction_hooks") or {}
    title_consistency_issues = _title_consistency_issues(workspace, manifest, title)
    skeleton_report = template_frequency_report(title, body, summary=str(manifest.get("summary") or ""))
    acceptance_gates = acceptance_report.get("gates") or {}
    checks = {
        "score_total_passed": total_score >= 88,
        "hook_passed": hook_score >= 26,
        "insight_passed": insight_score >= 40,
        "takeaway_passed": takeaway_score >= 20,
        "reader_gate_passed": bool(reader_gate.get("passed")),
        "visual_gate_passed": bool(visual_gate.get("passed")),
        "acceptance_passed": bool(acceptance_report.get("passed")),
        "title_consistency_passed": not title_consistency_issues,
        "skeleton_repeat_passed": bool(skeleton_report.get("passed")),
        "batch_uniqueness_passed": bool(acceptance_gates.get("batch_uniqueness_passed", True)),
        "core_viewpoint_passed": bool(analysis_11d.get("core_viewpoint")),
        "emotion_curve_passed": len(analysis_11d.get("emotion_curve") or []) >= 3,
        "argument_diversity_passed": len(analysis_11d.get("argument_diversity") or []) >= 3,
        "language_style_passed": str(language_style.get("rhythm") or "") != "偏平" and len(language_style.get("template_risk_signals") or []) <= 2,
        "interaction_hooks_passed": bool(interaction_hooks.get("comment_triggers") or interaction_hooks.get("share_triggers") or interaction_hooks.get("save_triggers")),
        "opening_four_factors_passed": bool(reader_gate.get("opening_four_factors_passed")),
        "share_lines_passed": int(reader_gate.get("share_line_score") or 0) >= 8 and len(reader_gate.get("share_lines") or []) >= 3,
        "takeaway_module_passed": str(reader_gate.get("takeaway_module_type") or "none") != "none",
    }
    failed_checks = [name for name, ok in checks.items() if not ok]
    return {
        "title": title,
        "total_score": total_score,
        "layer_scores": {
            "hook": hook_score,
            "insight": insight_score,
            "takeaway": takeaway_score,
        },
        "checks": checks,
        "analysis_11d": analysis_11d,
        "dimension_11d_scores": dimension_11d_scores,
        "dimension_11d_summary": dimension_11d_summary,
        "reader_gate": {
            "passed": bool(reader_gate.get("passed")),
            "failed_checks": list(reader_gate.get("failed_checks") or []),
        },
        "visual_gate": {
            "passed": bool(visual_gate.get("passed")),
            "failed_checks": list(visual_gate.get("failed_checks") or []),
        },
        "title_consistency_issues": title_consistency_issues,
        "skeleton_report": skeleton_report,
        "failed_checks": failed_checks,
        "passed": not failed_checks,
        "generated_at": now_iso(),
    }


def collect_gate_publish_blockers(workspace: Path, manifest: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    for key, default_name in (
        ("reader_gate_path", "reader_gate.json"),
        ("visual_gate_path", "visual_gate.json"),
        ("final_gate_path", "final_gate.json"),
    ):
        rel = str(manifest.get(key) or default_name).strip()
        path = workspace / rel
        if not path.exists():
            blockers.append(f"缺少 {rel}")
            continue
        payload = read_json(path, default={}) or {}
        if payload and not bool(payload.get("passed")):
            reasons = payload.get("failed_checks") or payload.get("blockers") or []
            detail = f"：{'、'.join(str(item) for item in reasons[:4])}" if reasons else ""
            blockers.append(f"{rel} 未通过{detail}")
    return blockers
