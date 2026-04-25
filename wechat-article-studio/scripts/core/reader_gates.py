from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from core.quality_checks import (
    broken_char_ratio,
    cost_signal_present,
    has_broken_char_run,
    lead_paragraph_count,
    metadata_integrity_report,
    normalize_visible_text,
    scene_signal_present,
    split_markdown_paragraphs,
    visible_length,
)
from core.visual_batch import summarize_visual_batch_collisions

_OPENING_ROUTE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("scene-entry", (r"会议室", r"办公室", r"工位", r"白板", r"那天", r"凌晨", r"晚上", r"中午", r"刚坐下", r"头像", r"窗口里")),
    ("counterintuitive-entry", (r"很多人", r"第一反应", r"你以为", r"表面上看", r"看上去", r"误判", r"真正的问题")),
    ("cost-entry", (r"代价", r"成本", r"返工", r"吃亏", r"买单", r"损失", r"后果", r"最贵的一笔")),
    ("news-inversion-entry", (r"\d{1,2}\s*月\s*\d{1,2}\s*日", r"今天", r"本周", r"刚刚", r"消息", r"报道", r"发布", r"披露", r"宣布")),
]

_ENDING_ROUTE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("judgment-close", (r"真正.*(是|该)", r"不是.+而是", r"先问的不是", r"真正会拉开差距", r"最该盯住的")),
    ("stance-question-close", (r"如果是你", r"你会怎么", r"你更认同", r"到底", r"该不该", r"你最想", r"你会先")),
    ("risk-close", (r"风险", r"代价", r"迟早", r"别把", r"会先", r"最先塌掉", r"不能默认")),
    ("action-close", (r"先做", r"第一步", r"从.*开始", r"先把", r"可以先", r"下一步")),
]

_TEMPLATE_PATTERNS: list[tuple[str, str]] = [
    ("not_but", r"不是[^。！？!?；;\n]{1,30}而是[^。！？!?；;\n]{1,30}"),
    ("worth_write_not_but", r"真正值得(?:写|看|聊|警惕|讨论|说明)的不是"),
    ("worth_watch_is", r"真正值得看的是"),
    ("dont_rush", r"先别急着"),
    ("real_problem", r"真正的问题(?:不是|是)"),
    ("this_also_is", r"这也是"),
    ("last_can", r"最后可以"),
    ("save_list_template", r"这[张份]清单值得保存"),
    ("also_dont", r"也别把"),
]

_LEAD_CONFLICT_PATTERNS = (
    r"不是.+而是",
    r"但",
    r"却",
    r"误判",
    r"卡住",
    r"问题",
    r"冲突",
    r"尴尬",
    r"分水岭",
    r"安静下来",
    r"真正的问题",
)

_LEAD_STAKES_PATTERNS = (
    r"这次",
    r"今天",
    r"本周",
    r"刚刚",
    r"发布",
    r"披露",
    r"宣布",
    r"报道",
    r"关键",
    r"代价",
    r"风险",
    r"后果",
    r"影响",
    r"最贵",
    r"最伤",
    r"更累",
    r"拖垮",
    r"真正的问题",
)

_LEAD_PERSON_PATTERNS = (
    r"老板",
    r"团队",
    r"用户",
    r"读者",
    r"父母",
    r"家长",
    r"孩子",
    r"子女",
    r"老人",
    r"求职者",
    r"学生",
    r"小老板",
    r"工程师",
    r"产品经理",
    r"财务",
    r"运营",
    r"平台负责人",
    r"普通人",
    r"同事",
    r"他",
    r"她",
    r"他们",
    r"大家",
)

_LEAD_ACTION_PATTERNS = (
    r"看到",
    r"问",
    r"等",
    r"打开",
    r"搜索",
    r"提醒",
    r"发布",
    r"报价",
    r"下单",
    r"转发",
    r"转",
    r"付款",
    r"回",
    r"盯着",
    r"写",
    r"跑",
    r"摔倒",
    r"联系",
)
_IMAGE_LABEL_ALLOWLIST = ("AI", "Agent", "OpenAI", "ChatGPT", "Gemini", "Google", "Meta", "API", "GPU", "Codex", "Claude", "DeepSeek", "Kimi", "MCP")
_IMAGE_UI_STYLE_WORDS = ("UI", "按钮", "界面", "面板", "dashboard", "screen", "app", "icon")

_SUSPICIOUS_BULLET_RE = re.compile(r"^\s*[-*+]\s+")
_SUSPICIOUS_BULLET_DIGIT_RE = re.compile(r"\d")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dedupe_texts(values: list[str], limit: int = 6) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _normalize_text(raw)
        if not value or len(value) < 12:
            continue
        key = re.sub(r"\W+", "", value.lower())[:40]
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
        if len(output) >= limit:
            break
    return output


def _summary_duplicates_opening(summary: str, body: str) -> bool:
    paragraphs = split_markdown_paragraphs(body)
    if not paragraphs:
        return False
    summary_text = normalize_visible_text(summary)
    opening_text = normalize_visible_text(paragraphs[0])
    if not summary_text or not opening_text:
        return False
    if summary_text[:28] and summary_text[:28] in opening_text:
        return True
    summary_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,4}|[A-Za-z0-9]{3,}", summary_text))
    opening_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,4}|[A-Za-z0-9]{3,}", opening_text))
    if not summary_tokens:
        return False
    return len(summary_tokens & opening_tokens) / max(1, len(summary_tokens)) >= 0.72


def _share_lines(body: str, analysis_11d: dict[str, Any], analysis: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    candidates.extend(str(item) for item in (analysis_11d.get("signature_quotes") or []) if str(item).strip())
    candidates.extend(str(item) for item in (analysis.get("social_currency_points") or []) if str(item).strip())
    candidates.extend(str(item.get("text") or "") for item in (analysis.get("signature_lines") or []) if isinstance(item, dict))
    if len(candidates) < 3:
        for paragraph in split_markdown_paragraphs(body):
            plain = normalize_visible_text(paragraph)
            if 18 <= visible_length(plain) <= 80 and any(word in plain for word in ["不是", "而是", "关键", "代价", "风险", "分水岭", "值钱", "稀缺"]):
                candidates.append(plain)
    return _dedupe_texts(candidates, limit=6)


def _takeaway_module_type(body: str) -> str:
    tail = "\n".join(split_markdown_paragraphs(body)[-8:])
    headings = [match.group(1).strip() for match in re.finditer(r"(?m)^##\s+(.+)$", body or "")]
    corpus = " ".join([tail, headings[-1] if headings else ""])
    if re.search(r"三问|3\s*问|问.*问.*问", corpus):
        return "三问卡"
    if re.search(r"四步|4\s*步|步骤|护栏|清单", corpus):
        return "四步卡"
    if re.search(r"^\|.+\|", tail, flags=re.M) or "对比" in corpus:
        return "对比表"
    if re.search(r"判断卡|判断框架|判断", corpus):
        return "判断卡"
    if re.search(r"风险|边界|责任|避坑", corpus):
        return "风险清单"
    return "none"


def classify_opening_route(text: str) -> str:
    value = _normalize_text(text)
    if not value:
        return "none"
    for key, patterns in _OPENING_ROUTE_PATTERNS:
        if any(re.search(pattern, value) for pattern in patterns):
            return key
    return "generic"


def classify_ending_route(text: str) -> str:
    value = _normalize_text(text)
    if not value:
        return "none"
    for key, patterns in _ENDING_ROUTE_PATTERNS:
        if any(re.search(pattern, value) for pattern in patterns):
            return key
    return "generic"


def first_screen_signal_report(body: str) -> dict[str, Any]:
    paragraphs = split_markdown_paragraphs(body)
    lead = paragraphs[:2]
    lead_text = " ".join(lead)
    opening_route = classify_opening_route(lead[0] if lead else "")
    has_scene = any(scene_signal_present(item) for item in lead) or opening_route in {"scene-entry", "news-inversion-entry"}
    has_person = bool(any(re.search(pattern, lead_text) for pattern in _LEAD_PERSON_PATTERNS))
    has_action = bool(any(re.search(pattern, lead_text) for pattern in _LEAD_ACTION_PATTERNS))
    has_conflict = bool(any(re.search(pattern, lead_text) for pattern in _LEAD_CONFLICT_PATTERNS))
    has_stakes = bool(cost_signal_present(lead_text) or any(re.search(pattern, lead_text) for pattern in _LEAD_STAKES_PATTERNS))
    has_specific_loss = bool(cost_signal_present(lead_text) or re.search(r"(错过|泄露|涨价|延期|返工|失控|误判|风险|后果|买单|成本|更累|疲惫|拖延|混乱)", lead_text))
    pre_h2_paragraphs = lead_paragraph_count(body)
    first_screen_questions = {
        "who": has_person,
        "action": has_action,
        "why_it_matters": has_stakes,
        "loss_or_conflict": bool(has_conflict and has_specific_loss),
    }
    return {
        "opening_route": opening_route,
        "lead_excerpt": lead_text[:220],
        "lead_paragraphs": len(lead),
        "pre_h2_paragraphs": pre_h2_paragraphs,
        "has_scene": has_scene,
        "has_person": has_person,
        "has_action": has_action,
        "has_conflict": has_conflict,
        "has_stakes": has_stakes,
        "has_specific_loss": has_specific_loss,
        "first_screen_questions": first_screen_questions,
        "four_question_passed": sum(1 for ok in first_screen_questions.values() if ok) >= 4,
        "passed": len(lead) >= 2 and has_scene and has_person and has_action and has_conflict and has_stakes and has_specific_loss and pre_h2_paragraphs <= 4,
    }


def template_frequency_report(title: str, body: str, summary: str = "") -> dict[str, Any]:
    corpus = "\n".join([str(title or ""), str(summary or ""), str(body or "")])
    counts = {key: len(re.findall(pattern, corpus)) for key, pattern in _TEMPLATE_PATTERNS}
    paragraphs = split_markdown_paragraphs(body)
    starter_counts: dict[str, int] = {}
    for paragraph in paragraphs[:6]:
        match = re.match(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}", normalize_visible_text(paragraph))
        if not match:
            continue
        token = match.group(0)
        starter_counts[token] = int(starter_counts.get(token) or 0) + 1
    repeated_starters = {key: value for key, value in starter_counts.items() if value >= 2}
    ending_route = classify_ending_route(paragraphs[-1] if paragraphs else "")
    title_not_but = counts["not_but"] >= 1 and bool(re.search(r"不是[^。！？!?]{1,30}而是", str(title or "")))
    ending_not_but = bool(paragraphs and re.search(r"不是[^。！？!?]{1,30}而是", paragraphs[-1]))
    same_family_repeat = title_not_but and ending_not_but and ending_route == "judgment-close"
    matched_patterns = [key for key, value in counts.items() if value]
    if repeated_starters:
        matched_patterns.append("repeated_starters")
    if same_family_repeat:
        matched_patterns.append("title_ending_same_family")
    severe_pattern_hits = counts["worth_write_not_but"] + counts["worth_watch_is"] + counts["save_list_template"] + max(0, counts["not_but"] - 3)
    severe_pattern_hits += max(0, counts["dont_rush"] - 1)
    return {
        "counts": counts,
        "repeated_starters": repeated_starters,
        "same_family_repeat": same_family_repeat,
        "matched_patterns": matched_patterns,
        "passed": severe_pattern_hits <= 0 and len(repeated_starters) <= 1 and not same_family_repeat,
    }


def abnormal_text_report(title: str, summary: str, body: str) -> dict[str, Any]:
    metadata = metadata_integrity_report(title, summary)
    suspicious_bullets: list[str] = []
    suspicious_lines: list[str] = []
    for raw_line in str(body or "").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("|"):
            continue
        compact = normalize_visible_text(stripped)
        if not compact:
            continue
        if _SUSPICIOUS_BULLET_RE.match(stripped):
            bullet_text = _SUSPICIOUS_BULLET_RE.sub("", stripped).strip()
            bullet_compact = normalize_visible_text(bullet_text)
            if (
                has_broken_char_run(bullet_compact)
                or broken_char_ratio(bullet_compact) >= 0.15
                or (
                    visible_length(bullet_compact) <= 12
                    and bool(_SUSPICIOUS_BULLET_DIGIT_RE.search(bullet_compact))
                    and not re.search(r"[。！？!?]$", bullet_text)
                )
            ):
                suspicious_bullets.append(stripped)
            continue
        if has_broken_char_run(compact) or broken_char_ratio(compact) >= 0.3:
            suspicious_lines.append(stripped)
    return {
        "metadata": metadata,
        "suspicious_bullets": suspicious_bullets[:6],
        "suspicious_lines": suspicious_lines[:6],
        "passed": bool(metadata.get("passed")) and not suspicious_bullets and not suspicious_lines,
    }


def _label_language_failures(items: list[dict[str, Any]]) -> list[str]:
    failures: list[str] = []
    for item in items:
        insert_strategy = str(item.get("insert_strategy") or "")
        item_id = str(item.get("id") or "")
        if insert_strategy != "section_middle" and not item_id.startswith("inline-"):
            continue
        labels = [
            str(label or "").strip()
            for label in [
                *(item.get("required_text") or []),
                *(item.get("suggested_text") or []),
                *(item.get("label_strategy") or []),
            ]
            if str(label or "").strip()
        ]
        for label in labels:
            cleaned = label
            for token in sorted(_IMAGE_LABEL_ALLOWLIST, key=len, reverse=True):
                cleaned = re.sub(re.escape(token), "", cleaned, flags=re.I)
            if re.search(r"[A-Za-z]{2,}", cleaned):
                failures.append(f"{item_id} 正文图标签里出现英文")
                break
            if any(word in label for word in _IMAGE_UI_STYLE_WORDS):
                failures.append(f"{item_id} 正文图标签带 UI 说明词")
                break
    return failures


def image_plan_gate_report(image_plan: dict[str, Any] | None, *, workspace: Path | None = None) -> dict[str, Any]:
    payload = image_plan or {}
    items = list(payload.get("items") or [])
    cover = next(
        (
            item
            for item in items
            if str(item.get("insert_strategy") or "") == "cover_only" or str(item.get("id") or "").startswith("cover-")
        ),
        {},
    )
    first_inline = next((item for item in items if str(item.get("id") or "").startswith("inline-")), {})
    inline_items = [
        item
        for item in items
        if str(item.get("insert_strategy") or "") == "section_middle" or str(item.get("id") or "").startswith("inline-")
    ]
    article_strategy = payload.get("article_visual_strategy") or {}
    visual_route = str(article_strategy.get("visual_route") or "")
    per_item_routes = {
        str((item.get("article_visual_strategy") or {}).get("visual_route") or visual_route)
        for item in items
        if str((item.get("article_visual_strategy") or {}).get("visual_route") or visual_route).strip()
    }
    cover_text_policy = str(cover.get("text_policy") or "")
    first_inline_text_policy = str(first_inline.get("text_policy") or "")
    codex_mode = str(payload.get("provider") or "").strip().lower() == "codex"
    cover_policy_ok = (not cover) or (cover_text_policy in {"short-zh", "short-zh-numeric"} if codex_mode else cover_text_policy == "none")
    density_mode = str(
        payload.get("density_mode")
        or (payload.get("image_controls") or {}).get("density_mode")
        or (payload.get("image_controls") or {}).get("density")
        or "auto"
    ).strip().lower()
    inline_range = payload.get("inline_density_range") or {}
    density_min = int(inline_range.get("min") or 0)
    density_max = int(inline_range.get("max") or 0)
    if density_mode == "none":
        density_min = density_max = 0
    elif density_mode == "minimal":
        density_min, density_max = 0, 1
    elif density_mode == "balanced":
        density_min, density_max = 1, 2
    elif density_mode == "dense":
        density_min, density_max = 2, 4
    elif not inline_range:
        density_min = density_max = len(inline_items)
    density_passed = density_min <= len(inline_items) <= density_max if density_max or density_min else len(inline_items) == 0
    valid_roles = {"click", "explain", "remember", "share"}
    inferred_roles = []
    for item in items:
        role = str(item.get("role") or "").strip().lower()
        if role not in valid_roles:
            image_type = str(item.get("type") or "")
            insert_strategy = str(item.get("insert_strategy") or "")
            if image_type == "封面图" or str(item.get("id") or "").startswith("cover-") or insert_strategy == "cover_only":
                role = "click"
            elif image_type in {"信息图", "流程图", "对比图"}:
                role = "explain"
            elif insert_strategy == "section_end":
                role = "share"
            elif str(item.get("id") or "").startswith("inline-"):
                role = "explain"
            else:
                role = "remember"
        inferred_roles.append(role)
    role_assignment_passed = all(role in valid_roles for role in inferred_roles) if items else False
    explain_role_present = any(role == "explain" for role, item in zip(inferred_roles, items) if item in inline_items) if inline_items else True
    batch_visual = summarize_visual_batch_collisions(workspace, payload) if workspace is not None else {"passed": True, "similar_items": []}
    label_language_failures = _label_language_failures(items)
    return {
        "visual_route": visual_route,
        "visual_route_passed": bool(visual_route) and len(per_item_routes) <= 1,
        "visual_batch_uniqueness_passed": bool(batch_visual.get("passed", True)),
        "visual_batch": batch_visual,
        "cover_text_policy_passed": cover_policy_ok,
        "first_inline_text_policy_passed": not first_inline or first_inline_text_policy in {"none", "short-zh", "short-zh-numeric"},
        "density_passed": density_passed,
        "role_assignment_passed": role_assignment_passed,
        "explain_role_present": explain_role_present,
        "label_language_failures": label_language_failures,
        "label_language_passed": not label_language_failures,
        "passed": (
            cover_policy_ok
            and (not first_inline or first_inline_text_policy in {"none", "short-zh", "short-zh-numeric"})
            and density_passed
            and role_assignment_passed
            and explain_role_present
            and not label_language_failures
            and (not visual_route or len(per_item_routes) <= 1)
            and bool(batch_visual.get("passed", True))
        ),
    }
