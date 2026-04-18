from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from core.editorial_strategy import ending_pattern_key, heading_pattern_key, opening_pattern_key, title_template_key
from core.quality_checks import discussion_trigger_present, split_markdown_paragraphs
from core.reader_gates import first_screen_signal_report, template_frequency_report

DIMENSION_11D_SPECS: list[tuple[str, str]] = [
    ("core_viewpoint", "核心观点"),
    ("secondary_viewpoints", "副观点"),
    ("persuasion_strategies", "说服策略"),
    ("emotion_triggers", "情绪触发点"),
    ("signature_quotes", "金句"),
    ("emotion_curve", "情感曲线"),
    ("emotion_layers", "情感层次"),
    ("argument_diversity", "论证多样性"),
    ("perspective_shifts", "视角转化"),
    ("language_style", "语言风格"),
    ("interaction_hooks", "互动钩子"),
]

_TEMPLATE_TAIL_RE = re.compile(r"(真正|最先|从今天开始|被改写的是)")
_NOT_BUT_RE = re.compile(r"不是.{1,24}而是.{1,24}")
_EXPLAINER_CONNECTORS = ("首先", "其次", "最后", "换句话说", "说白了", "更重要的是", "需要注意的是", "与此同时")
_COLLOQUIAL_MARKERS = ("你", "我们", "其实", "说白了", "真要说", "别急", "先别", "这事")
_RHYTHM_MARKERS = ("但是", "不过", "同时", "而且", "然后")
_UI_STYLE_WORDS = ("UI", "按钮", "界面", "面板", "dashboard", "screen", "app", "icon")
_CONTROVERSY_MARKERS = ("你更认同", "如果是你", "到底", "该不该", "站队", "哪一种")
_SAVE_MARKERS = ("收藏", "保存", "留着", "下次", "带走", "判断卡", "检查表")
_FILL_BLANK_MARKERS = ("如果把", "如果只允许", "你会先", "空格")


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normalize_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = _clean(item)
        if text and text not in output:
            output.append(text)
    return output


def _sentence_objects_to_texts(value: Any) -> list[str]:
    output: list[str] = []
    for item in value or []:
        if isinstance(item, dict):
            text = _clean(item.get("text") or item.get("sentence") or item.get("quote") or "")
        else:
            text = _clean(item)
        if text and text not in output:
            output.append(text)
    return output


def _clamp(score: int) -> int:
    return max(0, min(10, int(score)))


def _table_count(body: str) -> int:
    return len(re.findall(r"(?m)^\|.+\|\s*\n\|(?:\s*:?-+:?\s*\|)+", body or ""))


def _question_density(body: str) -> float:
    paragraphs = split_markdown_paragraphs(body)
    if not paragraphs:
        return 0.0
    hits = sum(paragraph.count("？") + paragraph.count("?") for paragraph in paragraphs)
    return round(hits / max(1, len(paragraphs)), 2)


def _signature_quotes(body: str, analysis: dict[str, Any]) -> list[str]:
    items = (
        _sentence_objects_to_texts(analysis.get("signature_quotes"))
        + _sentence_objects_to_texts(analysis.get("signature_lines"))
        + _sentence_objects_to_texts(analysis.get("target_quotes"))
    )
    cleaned_items: list[str] = []
    for item in items:
        text = _clean(item).strip("銆傦紒锛?? ")
        if text.startswith("##"):
            continue
        if "|" in text or len(text) > 48 or len(text) < 10:
            continue
        if text not in cleaned_items:
            cleaned_items.append(text)
    if cleaned_items:
        return cleaned_items[:6]
    candidates: list[str] = []
    for paragraph in split_markdown_paragraphs(body):
        for sentence in re.split(r"(?<=[。！？!?])", paragraph):
            text = _clean(sentence).strip("。！？!? ")
            if 10 <= len(text) <= 44 and (_NOT_BUT_RE.search(text) or any(keyword in text for keyword in ("代价", "后果", "误判", "边界", "真正", "问题"))):
                if text not in candidates:
                    candidates.append(text)
    return candidates[:6]


def _normalize_curve(value: Any) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in value or []:
        if isinstance(item, dict):
            stage = _clean(item.get("stage") or item.get("section") or f"阶段 {len(normalized) + 1}")
            emotion = _clean(item.get("emotion") or item.get("value") or stage)
            goal = _clean(item.get("goal") or emotion)
        else:
            text = _clean(item)
            if not text:
                continue
            stage = f"阶段 {len(normalized) + 1}"
            emotion = text
            goal = text
        normalized.append({"stage": stage, "emotion": emotion, "goal": goal})
    return normalized[:6]


def _language_style(title: str, body: str, summary: str, analysis: dict[str, Any], humanness_signals: dict[str, Any] | None = None) -> dict[str, Any]:
    humanness_signals = humanness_signals or {}
    sentences = [item for item in legacy.sentence_split(body or "") if _clean(item)]
    sentence_lengths = [legacy.cjk_len(item) for item in sentences if legacy.cjk_len(item) > 0]
    paragraphs = split_markdown_paragraphs(body)
    paragraph_lengths = [legacy.cjk_len(item) for item in paragraphs if legacy.cjk_len(item) > 0]
    sentence_range = int(humanness_signals.get("sentence_length_range") or (max(sentence_lengths) - min(sentence_lengths) if sentence_lengths else 0))
    paragraph_range = int(humanness_signals.get("paragraph_length_range") or (max(paragraph_lengths) - min(paragraph_lengths) if paragraph_lengths else 0))
    avg_sentence = round(sum(sentence_lengths) / max(1, len(sentence_lengths)), 1) if sentence_lengths else 0.0
    colloquial_hits = sum(body.count(marker) for marker in _COLLOQUIAL_MARKERS)
    rhetoric_hits = (
        len(_NOT_BUT_RE.findall(body))
        + sum(body.count(marker) for marker in ("像", "好比", "就像", "反过来"))
        + body.count("？")
        + body.count("?")
    )
    connector_hits = sum(body.count(marker) for marker in _EXPLAINER_CONNECTORS)
    template_report = template_frequency_report(title, body, summary)
    template_risks: list[str] = []
    if len(_NOT_BUT_RE.findall(title)) >= 1 or _TEMPLATE_TAIL_RE.search(title):
        template_risks.append("标题判断句尾巴偏重")
    if len(_NOT_BUT_RE.findall(body)) >= 3:
        template_risks.append("正文“不是…而是…”句式过多")
    if connector_hits >= 4:
        template_risks.append("解释型连接词偏密")
    if template_report.get("same_family_repeat"):
        template_risks.append("首尾使用了同一类判断模板")
    for pattern in template_report.get("matched_patterns") or []:
        text = _clean(pattern)
        if text and text not in template_risks:
            template_risks.append(text)
    if sentence_range >= 18 and paragraph_range >= 30:
        sentence_length_mix = "长短交替"
    elif avg_sentence <= 18:
        sentence_length_mix = "偏短"
    elif avg_sentence >= 34:
        sentence_length_mix = "偏长"
    else:
        sentence_length_mix = "中等偏稳"
    if colloquial_hits >= 8:
        colloquiality = "高"
    elif colloquial_hits >= 3:
        colloquiality = "中"
    else:
        colloquiality = "低"
    if rhetoric_hits >= 10:
        rhetoric_density = "高"
    elif rhetoric_hits >= 4:
        rhetoric_density = "中"
    else:
        rhetoric_density = "低"
    if sentence_range >= 18 and paragraph_range >= 35:
        rhythm = "有起伏"
    elif sentence_range >= 10:
        rhythm = "基本稳"
    else:
        rhythm = "偏平"
    signature_traits = _normalize_list(analysis.get("style_traits"))[:6]
    if not signature_traits:
        if opening_pattern_key(paragraphs[0]) == "scene-cut" if paragraphs else False:
            signature_traits.append("具体场景起笔")
        if any(marker in body for marker in ("数据", "报告", "官方")):
            signature_traits.append("证据穿插")
        if colloquiality == "高":
            signature_traits.append("对话感")
        if rhetoric_density == "低":
            signature_traits.append("判断克制")
    return {
        "sentence_length_mix": sentence_length_mix,
        "colloquiality": colloquiality,
        "rhetoric_density": rhetoric_density,
        "rhythm": rhythm,
        "signature_traits": signature_traits[:6],
        "template_risk_signals": template_risks[:6],
        "metrics": {
            "avg_sentence_length": avg_sentence,
            "sentence_length_range": sentence_range,
            "paragraph_length_range": paragraph_range,
            "connector_hits": connector_hits,
        },
    }


def _interaction_hooks(body: str, analysis: dict[str, Any], signature_quotes: list[str]) -> dict[str, Any]:
    comment_triggers = _normalize_list(analysis.get("comment_triggers"))
    share_triggers = [item for item in _normalize_list(analysis.get("share_triggers")) if 8 <= len(item) <= 48 and "|" not in item] or signature_quotes[:3]
    save_triggers = _normalize_list(analysis.get("save_triggers")) if analysis.get("save_triggers") else []
    if not save_triggers:
        for paragraph in split_markdown_paragraphs(body)[-3:]:
            if any(marker in paragraph for marker in _SAVE_MARKERS):
                save_triggers.append(_clean(paragraph)[:48])
    controversy_anchors = _normalize_list(analysis.get("controversy_anchors"))
    poll_prompts = [item for item in comment_triggers if any(marker in item for marker in ("哪一个", "哪一种", "站队", "投票", "更认同"))]
    fill_blank_prompts = [item for item in comment_triggers if any(marker in item for marker in _FILL_BLANK_MARKERS)]
    if not fill_blank_prompts:
        fill_blank_prompts = [item for item in _normalize_list(analysis.get("interaction_prompts")) if "____" in item or "如果把" in item][:3]
    if not controversy_anchors:
        controversy_anchors = [item for item in comment_triggers if any(marker in item for marker in _CONTROVERSY_MARKERS)][:3]
    return {
        "comment_triggers": comment_triggers[:4],
        "share_triggers": share_triggers[:4],
        "save_triggers": save_triggers[:4],
        "controversy_anchors": controversy_anchors[:4],
        "poll_prompts": poll_prompts[:3],
        "fill_blank_prompts": fill_blank_prompts[:3],
        "question_density": _question_density(body),
    }


def build_analysis_11d(
    *,
    title: str,
    body: str,
    summary: str = "",
    analysis: dict[str, Any] | None = None,
    depth: dict[str, Any] | None = None,
    material_signals: dict[str, Any] | None = None,
    humanness_signals: dict[str, Any] | None = None,
) -> dict[str, Any]:
    analysis = analysis or {}
    depth = depth or {}
    material_signals = material_signals or {}
    signature_quotes = _signature_quotes(body, analysis)
    language_style = _language_style(title, body, summary, analysis, humanness_signals=humanness_signals)
    interaction_hooks = _interaction_hooks(body, analysis, signature_quotes)
    argument_diversity = _normalize_list(analysis.get("argument_diversity")) or _normalize_list(analysis.get("argument_modes")) or _normalize_list(analysis.get("persuasion_strategies"))
    core_viewpoint = _clean(analysis.get("core_viewpoint") or "")
    clean_title = _clean(title)
    if clean_title and core_viewpoint.startswith(clean_title) and len(core_viewpoint) > len(clean_title) + 8:
        core_viewpoint = _clean(core_viewpoint[len(clean_title) :])
    return {
        "core_viewpoint": core_viewpoint,
        "secondary_viewpoints": _normalize_list(analysis.get("secondary_viewpoints"))[:4],
        "persuasion_strategies": _normalize_list(analysis.get("persuasion_strategies"))[:5],
        "emotion_triggers": _normalize_list(analysis.get("emotion_triggers"))[:5],
        "signature_quotes": signature_quotes[:6],
        "emotion_curve": _normalize_curve(analysis.get("emotion_curve")),
        "emotion_layers": _normalize_list(analysis.get("emotion_layers"))[:5],
        "argument_diversity": argument_diversity[:6],
        "perspective_shifts": _normalize_list(analysis.get("perspective_shifts"))[:5],
        "language_style": language_style,
        "interaction_hooks": interaction_hooks,
        "supporting_signals": {
            "scene_count": int(depth.get("scene_paragraph_count") or 0),
            "evidence_count": int(depth.get("evidence_paragraph_count") or 0),
            "counterpoint_count": int(depth.get("counterpoint_paragraph_count") or 0),
            "table_count": int(material_signals.get("has_table") or 0),
            "analogy_count": int(material_signals.get("analogy_count") or 0),
            "comparison_count": int(material_signals.get("comparison_count") or 0),
        },
    }


def score_analysis_11d(analysis_11d: dict[str, Any]) -> list[dict[str, Any]]:
    language_style = dict(analysis_11d.get("language_style") or {})
    interaction_hooks = dict(analysis_11d.get("interaction_hooks") or {})
    signature_quotes = list(analysis_11d.get("signature_quotes") or [])
    template_risks = list(language_style.get("template_risk_signals") or [])
    scores: list[dict[str, Any]] = []
    score_map = {
        "core_viewpoint": (2 + (4 if analysis_11d.get("core_viewpoint") else 0) + (2 if len(str(analysis_11d.get("core_viewpoint") or "")) >= 14 else 0) + (2 if re.search(r"(代价|后果|边界|误判|风险|判断)", str(analysis_11d.get("core_viewpoint") or "")) else 0), "是否有一个清楚、能落地的主判断"),
        "secondary_viewpoints": (2 + min(8, len(list(analysis_11d.get("secondary_viewpoints") or [])) * 3), "是否有 2-3 个能支撑主观点的侧面"),
        "persuasion_strategies": (2 + min(8, len(list(analysis_11d.get("persuasion_strategies") or [])) * 2), "是否交替使用不同说服方式"),
        "emotion_triggers": (2 + min(8, len(list(analysis_11d.get("emotion_triggers") or [])) * 2), "是否明确知道要触发读者什么情绪"),
        "signature_quotes": (2 + min(8, len(signature_quotes) * 3) - (1 if signature_quotes and all(len(item) > 40 for item in signature_quotes[:2]) else 0), "是否有能脱离上下文传播的金句"),
        "emotion_curve": (2 + min(8, len(list(analysis_11d.get("emotion_curve") or [])) * 2) - (2 if language_style.get("rhythm") == "偏平" else 0), "是否有节奏起伏而不是一路平推"),
        "emotion_layers": (2 + min(8, len(list(analysis_11d.get("emotion_layers") or [])) * 2), "是否从信息层走到价值和身份层"),
        "argument_diversity": (2 + min(8, len(list(analysis_11d.get("argument_diversity") or [])) * 2), "是否有故事、数据、类比、对比交替"),
        "perspective_shifts": (2 + min(8, len(list(analysis_11d.get("perspective_shifts") or [])) * 3), "是否有策略性地切换视角"),
        "language_style": (
            3
            + (3 if language_style.get("rhythm") in {"有起伏", "基本稳"} else 0)
            + (2 if language_style.get("sentence_length_mix") == "长短交替" else 1)
            + (2 if len(template_risks) <= 1 else 0),
            "是否读起来有节奏，不像统一模板",
        ),
        "interaction_hooks": (
            2
            + (2 if interaction_hooks.get("comment_triggers") else 0)
            + (2 if interaction_hooks.get("share_triggers") else 0)
            + (2 if interaction_hooks.get("save_triggers") else 0)
            + (1 if interaction_hooks.get("controversy_anchors") else 0)
            + (1 if float(interaction_hooks.get("question_density") or 0) >= 0.3 else 0),
            "是否自然留下评论、转发、收藏入口",
        ),
    }
    for key, label in DIMENSION_11D_SPECS:
        raw_score, note = score_map[key]
        scores.append({"key": key, "label": label, "score": _clamp(raw_score), "note": note})
    return scores


def summarize_analysis_11d(analysis_11d: dict[str, Any], scores: list[dict[str, Any]]) -> dict[str, Any]:
    sorted_scores = sorted(scores, key=lambda item: (int(item.get("score") or 0), item.get("label") or ""))
    weakest = [{"key": item["key"], "label": item["label"], "score": item["score"]} for item in sorted_scores[:3]]
    strongest = [{"key": item["key"], "label": item["label"], "score": item["score"]} for item in sorted(scores, key=lambda item: (int(item.get("score") or 0), item.get("label") or ""), reverse=True)[:3]]
    missing: list[str] = []
    if not analysis_11d.get("core_viewpoint"):
        missing.append("核心观点")
    if not analysis_11d.get("signature_quotes"):
        missing.append("金句")
    if not (analysis_11d.get("interaction_hooks") or {}).get("comment_triggers"):
        missing.append("互动钩子")
    if len((analysis_11d.get("emotion_curve") or [])) < 3:
        missing.append("情感曲线")
    return {
        "strongest_dimensions": strongest,
        "weakest_dimensions": weakest,
        "missing_dimensions": missing,
        "template_risk_signals": list((analysis_11d.get("language_style") or {}).get("template_risk_signals") or [])[:6],
        "interaction_overview": {
            "comment_count": len((analysis_11d.get("interaction_hooks") or {}).get("comment_triggers") or []),
            "share_count": len((analysis_11d.get("interaction_hooks") or {}).get("share_triggers") or []),
            "save_count": len((analysis_11d.get("interaction_hooks") or {}).get("save_triggers") or []),
        },
    }


def build_analysis_11d_report_payload(
    *,
    title: str,
    analysis_11d: dict[str, Any],
    scores: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "title": title,
        "analysis_11d": analysis_11d,
        "dimension_11d_scores": scores,
        "dimension_11d_summary": summarize_analysis_11d(analysis_11d, scores),
        "generated_at": legacy.now_iso(),
    }


def markdown_analysis_11d_report(payload: dict[str, Any]) -> str:
    analysis_11d = payload.get("analysis_11d") or {}
    summary = payload.get("dimension_11d_summary") or {}
    lines = [f"# 11 维分析：{payload.get('title') or '未命名文章'}", ""]
    for item in payload.get("dimension_11d_scores") or []:
        lines.append(f"- {item.get('label')}：{item.get('score')}/10，{item.get('note')}")
    lines.append("")
    core = _clean(analysis_11d.get("core_viewpoint"))
    if core:
        lines.append(f"- 核心观点：{core}")
    if analysis_11d.get("signature_quotes"):
        lines.append(f"- 金句：{' | '.join((analysis_11d.get('signature_quotes') or [])[:3])}")
    if summary.get("template_risk_signals"):
        lines.append(f"- 模板风险：{' | '.join(summary.get('template_risk_signals') or [])}")
    if summary.get("missing_dimensions"):
        lines.append(f"- 缺项：{'、'.join(summary.get('missing_dimensions') or [])}")
    return "\n".join(lines).rstrip() + "\n"


def _is_single_article_workspace(path: Path, batch_key: str) -> bool:
    name = path.name
    if not name.startswith(f"{batch_key}-"):
        return False
    return "hot-topics" not in name.lower()


def list_batch_workspaces(jobs_root: Path, batch_key: str) -> list[Path]:
    if not jobs_root.exists():
        return []
    output: list[Path] = []
    for item in jobs_root.iterdir():
        if not item.is_dir():
            continue
        if not _is_single_article_workspace(item, batch_key):
            continue
        if (item / "article.md").exists():
            output.append(item.resolve())
    output.sort(key=lambda item: item.name)
    return output


def _workspace_article_snapshot(workspace: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], str, str, str]:
    manifest = legacy.read_json(workspace / "manifest.json", default={}) or {}
    review = legacy.read_json(workspace / "review-report.json", default={}) or {}
    score = legacy.read_json(workspace / "score-report.json", default={}) or {}
    acceptance = legacy.read_json(workspace / "acceptance-report.json", default={}) or {}
    image_plan = legacy.read_json(workspace / "image-plan.json", default={}) or {}
    raw = legacy.read_text(workspace / "article.md")
    meta, body = legacy.split_frontmatter(raw)
    title = _clean(meta.get("title") or manifest.get("selected_title") or workspace.name)
    summary = _clean(meta.get("summary") or manifest.get("summary") or "")
    return manifest, review, score, acceptance, image_plan, title, summary, body


def _ending_action(body: str) -> str:
    paragraphs = split_markdown_paragraphs(body)
    tail = " ".join(paragraphs[-2:])
    tail_headings = re.findall(r"(?m)^\s*##\s+(.+?)\s*$", body or "")
    last_heading = _clean(tail_headings[-1]) if tail_headings else ""
    if any(marker in last_heading + tail for marker in ("带走", "判断卡", "检查表", "清单", "这张表", "这条线")):
        return "judgment_card"
    if any(marker in tail for marker in ("风险", "后果", "别把", "不能", "越过去")):
        return "risk_warning"
    if discussion_trigger_present(tail) or any(marker in tail for marker in ("先问", "下次", "你会怎么")):
        return "reusable_question"
    return "generic"


def _image_roles(image_plan: dict[str, Any]) -> list[str]:
    roles: list[str] = []
    for item in image_plan.get("items") or []:
        role = _clean(item.get("role"))
        if role:
            roles.append(role)
            continue
        image_type = _clean(item.get("type"))
        insert_strategy = _clean(item.get("insert_strategy"))
        if image_type == "封面图" or insert_strategy == "cover_only":
            roles.append("click")
        elif image_type in {"对比图", "流程图", "信息图"}:
            roles.append("explain")
        elif insert_strategy == "section_end":
            roles.append("share")
        else:
            roles.append("remember")
    return roles


def _reader_view(title: str, body: str, acceptance: dict[str, Any], image_plan: dict[str, Any], analysis_11d: dict[str, Any]) -> dict[str, str]:
    paragraphs = split_markdown_paragraphs(body)
    template_risks = list((analysis_11d.get("language_style") or {}).get("template_risk_signals") or [])
    image_roles = _image_roles(image_plan)
    return {
        "title": "标题判断感强，但要看它是不是具体到读者代价。" if title else "标题信息不足。",
        "opening": "开头能不能把人和代价一起立住。" if not (acceptance.get("first_screen") or {}).get("passed") else "开头已经有场景，但还要看是不是足够短够狠。",
        "body": "中段需要真的展开，而不是只堆判断句。" if int((acceptance.get("three_layer_diagnostics") or {}).get("insight", {}).get("score") or 0) < 40 else "中段认知增量基本够，但仍要防同构。",
        "ending": "结尾要么给判断卡，要么给风险提醒，不要只剩一句收束。" if _ending_action(body) == "generic" else "结尾有明确收口动作，但要避免批量复制同一套。", 
        "layout": "表格和图片都要少而准。" if _table_count(body) >= 2 else "结构还算克制，但要注意首屏节奏。",
        "images": "至少一张图要真正承担解释任务。" if "explain" not in image_roles else "图有信息增量，但还要防无效堆图。",
        "template_risk": "；".join(template_risks[:3]) if template_risks else "低",
    }


def build_batch_review_payload(jobs_root: Path, batch_key: str) -> dict[str, Any]:
    workspaces = list_batch_workspaces(jobs_root, batch_key)
    items: list[dict[str, Any]] = []
    opening_counts: dict[str, int] = {}
    ending_counts: dict[str, int] = {}
    title_counts: dict[str, int] = {}
    heading_shapes: dict[str, int] = {}
    table_counts: dict[int, int] = {}
    image_shapes: dict[str, int] = {}
    not_but_scores: dict[str, int] = {}
    explainer_scores: dict[str, int] = {}
    for workspace in workspaces:
        manifest, review, score, acceptance, image_plan, title, summary, body = _workspace_article_snapshot(workspace)
        analysis_11d = dict(review.get("analysis_11d") or {})
        if not analysis_11d:
            analysis_11d = build_analysis_11d(
                title=title,
                body=body,
                summary=summary,
                analysis=review.get("viral_analysis") or score.get("viral_analysis") or {},
                depth=review.get("depth_signals") or score.get("depth_signals") or {},
                material_signals=review.get("material_signals") or score.get("material_signals") or {},
                humanness_signals=review.get("humanness_signals") or score.get("humanness_signals") or {},
            )
        scores = score_analysis_11d(analysis_11d)
        paragraphs = split_markdown_paragraphs(body)
        opening_route = opening_pattern_key(paragraphs[0]) if paragraphs else "none"
        title_pattern = title_template_key(title)
        ending_action = _ending_action(body)
        heading_keys = [heading_pattern_key(item.get("text") or "") for item in legacy.extract_headings(body)[:6]]
        heading_signature = "|".join(item for item in heading_keys if item not in {"", "none", "generic"}) or "generic"
        table_count = _table_count(body)
        image_roles = _image_roles(image_plan)
        image_shape = f"{len(image_plan.get('items') or [])}:{','.join(sorted(image_roles))}"
        not_but_count = len(_NOT_BUT_RE.findall(body))
        connector_count = sum(body.count(marker) for marker in _EXPLAINER_CONNECTORS)
        opening_counts[opening_route] = int(opening_counts.get(opening_route) or 0) + 1
        ending_counts[ending_action] = int(ending_counts.get(ending_action) or 0) + 1
        title_counts[title_pattern] = int(title_counts.get(title_pattern) or 0) + 1
        heading_shapes[heading_signature] = int(heading_shapes.get(heading_signature) or 0) + 1
        table_counts[table_count] = int(table_counts.get(table_count) or 0) + 1
        image_shapes[image_shape] = int(image_shapes.get(image_shape) or 0) + 1
        not_but_scores[str(workspace)] = not_but_count
        explainer_scores[str(workspace)] = connector_count
        items.append(
            {
                "workspace": str(workspace),
                "title": title,
                "analysis_11d": analysis_11d,
                "dimension_11d_scores": scores,
                "dimension_11d_summary": summarize_analysis_11d(analysis_11d, scores),
                "reader_view": _reader_view(title, body, acceptance, image_plan, analysis_11d),
                "batch_shape": {
                    "title_template": title_pattern,
                    "opening_route": opening_route,
                    "heading_signature": heading_signature,
                    "ending_action": ending_action,
                    "table_count": table_count,
                    "image_count": len(image_plan.get("items") or []),
                    "image_roles": image_roles,
                    "not_but_count": not_but_count,
                    "explainer_connector_count": connector_count,
                },
                "scores": {
                    "total": int(score.get("total_score") or 0),
                    "hook": int(score.get("hook_layer_score") or 0),
                    "takeaway": int(score.get("takeaway_layer_score") or 0),
                    "interaction": int(score.get("interaction_score") or 0),
                },
            }
        )
    batch_risks: list[str] = []
    if any(count >= 2 for count in opening_counts.values()):
        batch_risks.append("同批次开头路线重复")
    if any(count >= 2 for count in ending_counts.values() if count and len(workspaces) >= 3):
        batch_risks.append("同批次结尾动作重复")
    if any(count >= 2 for count in title_counts.values()):
        batch_risks.append("同批次标题模板重复")
    if any(count >= 2 for count in heading_shapes.values()):
        batch_risks.append("同批次小标题骨架重复")
    if any(shape.startswith("6:") and count >= 2 for shape, count in image_shapes.items()):
        batch_risks.append("同批次图片数量和角色配置过于接近")
    if int(table_counts.get(2) or 0) >= 2:
        batch_risks.append("同批次使用双表格的稿件过多")
    if sum(1 for value in not_but_scores.values() if value >= 3) >= 2:
        batch_risks.append("同批次“不是……而是……”句式过密")
    if sum(1 for value in explainer_scores.values() if value >= 4) >= 2:
        batch_risks.append("同批次解释型连接词偏密")
    rankings = {
        "best_hook": max(items, key=lambda item: (item["scores"]["hook"], item["scores"]["total"]), default={}),
        "best_save": max(items, key=lambda item: (len((item.get("analysis_11d") or {}).get("interaction_hooks", {}).get("save_triggers") or []), item["scores"]["takeaway"]), default={}),
        "best_share": max(items, key=lambda item: (len((item.get("analysis_11d") or {}).get("interaction_hooks", {}).get("share_triggers") or []), item["scores"]["interaction"]), default={}),
        "heaviest_template": max(items, key=lambda item: len(((item.get("analysis_11d") or {}).get("language_style") or {}).get("template_risk_signals") or []), default={}),
        "weakest_first_screen": min(items, key=lambda item: item["scores"]["hook"] or 999, default={}),
    }
    return {
        "jobs_root": str(jobs_root),
        "batch_key": batch_key,
        "item_count": len(items),
        "items": items,
        "batch_risks": batch_risks,
        "rankings": {key: {"workspace": value.get("workspace"), "title": value.get("title")} for key, value in rankings.items() if value},
        "recommended_actions": [
            "同批次稿件强制错开开头路线、小标题骨架和结尾动作。",
            "默认图片密度降到 balanced，先保留 1 到 2 张解释图。",
            "同批次最多一篇保留 2 张表，其余稿件只留 1 张。",
            "标题优先写谁会先吃亏、谁会先受益、代价落在哪，不要都用抽象判断句。",
        ],
        "generated_at": legacy.now_iso(),
    }


def markdown_batch_review(payload: dict[str, Any]) -> str:
    lines = [f"# 批量复盘：{payload.get('batch_key') or ''}", ""]
    for item in payload.get("items") or []:
        lines.append(f"## {item.get('title')}")
        lines.append(f"- 工作目录：{item.get('workspace')}")
        lines.append(f"- 开头路线：{((item.get('batch_shape') or {}).get('opening_route') or 'none')}")
        lines.append(f"- 结尾动作：{((item.get('batch_shape') or {}).get('ending_action') or 'generic')}")
        lines.append(f"- 表格数：{((item.get('batch_shape') or {}).get('table_count') or 0)}")
        lines.append(f"- 图片角色：{', '.join((item.get('batch_shape') or {}).get('image_roles') or []) or 'none'}")
        weakest = item.get("dimension_11d_summary", {}).get("weakest_dimensions") or []
        if weakest:
            lines.append(f"- 最弱维度：{' / '.join(entry.get('label') or '' for entry in weakest)}")
        reader_view = item.get("reader_view") or {}
        for key in ["title", "opening", "body", "ending", "layout", "images"]:
            if reader_view.get(key):
                lines.append(f"- {key}：{reader_view.get(key)}")
        lines.append("")
    if payload.get("batch_risks"):
        lines.append("## 同批次风险")
        for item in payload.get("batch_risks") or []:
            lines.append(f"- {item}")
        lines.append("")
    if payload.get("recommended_actions"):
        lines.append("## 建议动作")
        for item in payload.get("recommended_actions") or []:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
