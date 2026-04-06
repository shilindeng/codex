from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ImagePromptingConfig:
    image_type_prompt_modules: dict[str, str]
    image_differentiation_modules: list[str]
    image_text_policy_defaults: dict[str, str]
    image_text_policy_labels: dict[str, str]
    image_label_bad_prefixes: tuple[str, ...]
    extract_summary: Callable[[str, int], str]
    cjk_len: Callable[[str], int]
    sentence_split: Callable[[str], list[str]]
    is_generated_section_heading: Callable[[str], bool]


def image_position_label(item: dict[str, Any]) -> str:
    if item.get("type") == "封面图":
        return "cover"
    if item.get("insert_strategy") == "section_end":
        return "closing-summary"
    target = item.get("target_section") or f"section-{item.get('target_section_index', -1)}"
    return f"{target}@block-{item.get('placement_block_index', 0)}"


def cleaned_image_signal_text(text: str, limit: int, *, cfg: ImagePromptingConfig) -> str:
    value = re.sub(r"(?<!\w)\[(\d{1,2})\](?!\()", "", text or "")
    value = re.sub(r"【\s*\d{1,2}\s*】", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return ""
    return cfg.extract_summary(value, limit)


def image_section_focus(item: dict[str, Any], limit: int, *, cfg: ImagePromptingConfig) -> str:
    heading = str(item.get("section_heading") or item.get("target_section") or "").strip()
    if cfg.is_generated_section_heading(heading):
        heading = ""
    excerpt = cleaned_image_signal_text(
        str(item.get("anchor_block_excerpt") or item.get("section_excerpt") or item.get("semantic_focus") or ""),
        limit,
        cfg=cfg,
    )
    heading_focus = cleaned_image_signal_text(heading, min(limit, 28), cfg=cfg) if heading else ""
    if heading_focus and cfg.cjk_len(heading_focus) >= 4:
        return cfg.extract_summary(heading_focus, min(limit, 28))
    focus = excerpt or heading_focus
    if focus:
        return cfg.extract_summary(focus, limit)
    return cleaned_image_signal_text(str(item.get("alt") or ""), limit, cfg=cfg) or "current section"


def image_anchor_excerpt(item: dict[str, Any], limit: int, *, cfg: ImagePromptingConfig) -> str:
    return cleaned_image_signal_text(str(item.get("anchor_block_excerpt") or ""), limit, cfg=cfg)


def image_section_excerpt(item: dict[str, Any], limit: int, *, cfg: ImagePromptingConfig) -> str:
    excerpt = cleaned_image_signal_text(str(item.get("section_excerpt") or ""), limit, cfg=cfg)
    anchor = image_anchor_excerpt(item, limit, cfg=cfg)
    if excerpt and anchor and (excerpt.startswith(anchor) or anchor.startswith(excerpt)):
        return ""
    return excerpt


def image_purpose_label(item: dict[str, Any]) -> str:
    mapping = {
        "封面图": "建立整篇文章的第一视觉印象",
        "信息图": "把结论、框架或清单压缩成可扫读的信息结构",
        "流程图": "把步骤、路径和节点关系讲清楚",
        "对比图": "把两种方案或两侧观点的差异可视化",
        "分隔图": "给长段落提供节奏变化并保持主题连续",
        "正文插图": "为附近段落提供更直观的概念锚点",
    }
    return mapping.get(item.get("type", "正文插图"), "辅助读者理解附近段落")


def short_sentence_chunks(text: str, limit: int = 4, max_len: int = 18, *, cfg: ImagePromptingConfig) -> list[str]:
    candidates: list[str] = []
    for sentence in cfg.sentence_split(text):
        cleaned = re.sub(r"\s+", "", sentence).strip("，。；：:、 ")
        if not cleaned:
            continue
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len]
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)
        if len(candidates) >= limit:
            break
    return candidates


def image_text_budget(item: dict[str, Any]) -> str:
    image_type = item.get("type", "正文插图")
    if image_type in {"封面图", "正文插图", "分隔图"}:
        return "none-to-minimal"
    if image_type == "流程图":
        return "up to 3 very short step labels"
    if image_type == "对比图":
        return "up to 4 very short contrast labels"
    if image_type == "信息图":
        return "up to 4 short labels or numeric callouts"
    return "minimal"


def image_label_strategy(item: dict[str, Any], *, cfg: ImagePromptingConfig) -> list[str]:
    heading = item.get("section_heading") or item.get("target_section") or ""
    excerpt = item.get("section_excerpt") or ""
    image_type = item.get("type", "正文插图")
    if image_type in {"封面图", "正文插图", "分隔图"}:
        return []
    labels = short_sentence_chunks(excerpt, limit=4, max_len=8, cfg=cfg)
    if image_type == "流程图" and not labels:
        labels = [heading, "步骤一", "步骤二"]
    elif image_type == "对比图" and len(labels) < 2:
        labels = [heading, "方案甲", "方案乙"]
    elif image_type == "信息图" and not labels:
        labels = [heading]
    normalized: list[str] = []
    for label in labels:
        compact = re.sub(r"^[一二三四五六七八九十0-9]+\W*", "", str(label or "")).strip()
        compact = compact.strip("，。；：:、- ")
        if any(compact.startswith(prefix) for prefix in cfg.image_label_bad_prefixes):
            continue
        if compact and compact not in normalized:
            normalized.append(compact)
    if image_type == "流程图" and not normalized:
        normalized = ["步骤一", "步骤二", "步骤三"]
    elif image_type == "对比图" and len(normalized) < 2:
        normalized = ["方案甲", "方案乙"]
    elif image_type == "信息图" and not normalized and heading:
        normalized = [cfg.extract_summary(str(heading), 8)]
    return normalized[:4]


def normalize_image_text_policy(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    alias_map = {
        "": "auto",
        "auto": "auto",
        "none": "none",
        "no-text": "none",
        "no-readable-text": "none",
        "short-zh": "short-zh",
        "short-chinese": "short-zh",
        "zh-short": "short-zh",
        "short-zh-numeric": "short-zh-numeric",
        "short-chinese-numeric": "short-zh-numeric",
        "short-any": "short-any",
        "minimal": "short-any",
    }
    return alias_map.get(normalized, "auto")


def normalize_label_language(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized.lower() in {"any", "auto"}:
        return "any"
    return "zh-CN"


def compact_label_strategy(values: Any, *, limit: int = 4, max_len: int = 6) -> list[str]:
    candidates = values or []
    if isinstance(candidates, str):
        candidates = [part.strip() for part in re.split(r"[/,|]", candidates) if part.strip()]
    output: list[str] = []
    for raw in candidates:
        compact = re.sub(r"\s+", "", str(raw or "")).strip("，。；：:、 ")
        if not compact:
            continue
        if compact.lower() in {"none", "no-label", "无"}:
            continue
        if len(compact) > max_len:
            compact = compact[:max_len]
        if compact not in output:
            output.append(compact)
        if len(output) >= limit:
            break
    return output


def image_text_policy_variant_instruction(policy: str, label_language: str, allowed_labels: Any = None) -> str:
    normalized = normalize_image_text_policy(policy)
    language = normalize_label_language(label_language)
    labels = compact_label_strategy(allowed_labels)
    if normalized == "none":
        return "Do not include any readable Chinese or English text, letters, numbers, UI copy, or labels in the final image."
    if normalized == "short-zh":
        base = "If labels are necessary, use only 2 to 4 very short Simplified Chinese labels."
    elif normalized == "short-zh-numeric":
        base = "If structure requires labels, use only a few very short Simplified Chinese labels or compact Arabic numerals."
    else:
        base = "If labels are necessary, keep them extremely short and sparse."
        if language == "zh-CN":
            base += " Prefer Simplified Chinese for this Chinese WeChat article."
    if labels and normalized != "none":
        base += " Prefer labels such as: " + " / ".join(labels) + "."
    return base


def resolve_image_text_policy(controls: dict[str, Any], item: dict[str, Any], *, cfg: ImagePromptingConfig) -> dict[str, Any]:
    image_type = str(item.get("type") or "正文插图").strip() or "正文插图"
    strategy = dict(controls.get("text_policy_overrides") or {})
    explicit_mode = normalize_image_text_policy(str(item.get("text_policy") or controls.get("text_policy") or ""))
    if explicit_mode != "auto":
        mode = explicit_mode
        reason = "图片文字策略来自显式配置。"
    else:
        configured_mode = normalize_image_text_policy(str(strategy.get(image_type) or strategy.get("default") or "auto"))
        mode = cfg.image_text_policy_defaults.get(image_type, "none") if configured_mode == "auto" else configured_mode
        reason = "图片文字策略按图片类型和账号策略自动决定。"
    label_language = normalize_label_language(str(item.get("label_language") or controls.get("label_language") or strategy.get("label_language") or "zh-CN"))
    label_strategy = compact_label_strategy(item.get("label_strategy") or image_label_strategy(item, cfg=cfg))
    text_budget = str(item.get("text_budget") or image_text_budget(item)).strip() or image_text_budget(item)
    prompt_lines = [image_text_policy_variant_instruction(mode, label_language, label_strategy)]
    if mode == "none":
        prompt_lines.append("Prefer pure imagery, symbols, objects, and composition over words.")
    elif mode in {"short-zh", "short-zh-numeric"}:
        prompt_lines.append("No English labels, no copied paragraphs, and no dense text blocks inside the image.")
    else:
        prompt_lines.append("Do not turn the image into a slide, spreadsheet, or UI card filled with text.")
    return {
        "mode": mode,
        "label": cfg.image_text_policy_labels.get(mode, cfg.image_text_policy_labels["auto"]),
        "reason": reason,
        "label_language": label_language,
        "label_strategy": label_strategy,
        "text_budget": text_budget,
        "prompt_lines": prompt_lines,
    }


def image_visual_content(item: dict[str, Any], *, cfg: ImagePromptingConfig) -> str:
    layout = item.get("layout_variant_label") or "默认构图"
    focus = image_section_focus(item, 96, cfg=cfg)
    return f"{focus}；采用{layout}，并保持与全文统一主题一致。"


def image_visual_elements(item: dict[str, Any], *, cfg: ImagePromptingConfig) -> list[str]:
    image_type = item.get("type", "正文插图")
    focus = image_section_focus(item, 72, cfg=cfg)
    if image_type == "封面图":
        return ["单一主视觉物件", "高识别度背景氛围", f"围绕“{focus}”的象征隐喻"]
    if image_type == "流程图":
        return ["步骤节点", "方向箭头或连接路径", f"与“{focus}”相关的操作符号"]
    if image_type == "对比图":
        return ["左右或双栏对照结构", "两组对立图标/物件", f"围绕“{focus}”的差异化视觉线索"]
    if image_type == "信息图":
        return ["分组卡片或结构模块", "图标与层级关系", f"压缩表达“{focus}”的框架元素"]
    if image_type == "分隔图":
        return ["节奏切换用主题母题", "情绪化背景", f"与“{focus}”关联的单一象征元素"]
    return ["概念性主物件", "辅助环境线索", f"服务“{focus}”的局部视觉隐喻"]


def image_layout_spec(item: dict[str, Any]) -> dict[str, str]:
    image_type = item.get("type", "正文插图")
    return {
        "variant_key": item.get("layout_variant_key", "default"),
        "variant_label": item.get("layout_variant_label", "默认构图"),
        "instruction": item.get("layout_variant_instruction", "Use a distinct composition."),
        "composition_goal": {
            "封面图": "先建立第一眼记忆点，再留出可用于封面裁切的安全区。",
            "信息图": "先让结构一眼可扫读，再让局部层级能被快速理解。",
            "流程图": "先看懂路径顺序，再看懂节点关系。",
            "对比图": "先看见对立关系，再看清差异细节。",
            "分隔图": "先切换节奏，再保持主题连续。",
        }.get(image_type, "先看见主题，再看懂附近段落的概念隐喻。"),
    }


def image_aspect_policy(item: dict[str, Any]) -> str:
    image_type = item.get("type", "正文插图")
    aspect = item.get("aspect_ratio", "16:9")
    mapping = {
        "封面图": f"{aspect} 宽画幅，兼容公众号封面和文章头图裁切。",
        "信息图": f"{aspect} 纵向信息密度优先，适合结尾收束和长图浏览。",
        "流程图": f"{aspect} 横向流程展开优先，保证路径和节点有呼吸空间。",
        "对比图": f"{aspect} 横向对照优先，保证左右两侧平衡。",
        "分隔图": f"{aspect} 横向节奏切换优先，适合作为段落分隔。",
    }
    return mapping.get(image_type, f"{aspect} 通用正文配图比例，兼顾正文阅读宽度。")


def compose_prompt(
    title: str,
    summary: str,
    controls: dict[str, Any],
    item: dict[str, Any],
    audience: str,
    *,
    cfg: ImagePromptingConfig,
    style_family_modules: dict[str, str],
    content_mode_modules: dict[str, str],
) -> str:
    section = image_section_focus(item, 56, cfg=cfg)
    style_mode = item.get("style_mode") or controls.get("style_mode") or "uniform"
    theme = item.get("visual_theme") or controls.get("theme", "") or "content-led visual direction"
    style = item.get("visual_style") or controls.get("style", "") or "distinctive editorial illustration"
    mood = item.get("visual_mood") or controls.get("mood", "") or "clear and restrained"
    brief = item.get("visual_brief") or controls.get("custom_visual_brief") or "highlight the core insight without clutter"
    article_strategy = item.get("article_visual_strategy") or {}
    profile_key = controls.get("profile_key") or article_strategy.get("profile_key") or ""
    content_mode = article_strategy.get("content_mode") or "conceptual"
    content_summary = cleaned_image_signal_text(summary, 96, cfg=cfg) or cleaned_image_signal_text(title, 72, cfg=cfg)
    anchor_excerpt = image_anchor_excerpt(item, 72, cfg=cfg)
    section_excerpt = image_section_excerpt(item, 84, cfg=cfg)
    scene_hint = section_excerpt or anchor_excerpt or content_summary
    text_policy = resolve_image_text_policy(controls, item, cfg=cfg)
    instructions = [
        "Create a polished visual for a Chinese WeChat Official Account article.",
        f"Article title: {title}",
        f"Purpose: {item['type']}",
        f"Audience: {audience or 'general readers'}",
        f"Theme: {theme}",
        f"Style: {style}",
        f"Mood: {mood}",
        f"Visual brief: {brief}",
    ]
    style_family_module = style_family_modules.get(profile_key, "")
    if style_family_module:
        instructions.append("Style family guidance: " + style_family_module)
    content_mode_module = content_mode_modules.get(content_mode, "")
    if content_mode_module:
        instructions.append("Content mode guidance: " + content_mode_module)
    if controls.get("preset"):
        instructions.append(f"Base visual preset: {controls['preset']}")
        if controls.get("preset_label"):
            instructions.append(f"Base preset label: {controls['preset_label']}")
        if style_mode == "mixed-by-type":
            instructions.append("Style mode: mixed-by-type (cover/infographic/inline use different presets).")
            if item.get("visual_preset"):
                instructions.append(f"This image preset: {item.get('visual_preset')}")
            if item.get("visual_preset_label"):
                instructions.append(f"This image preset label: {item.get('visual_preset_label')}")
            instructions.append("Keep palette, icon language, and motif consistent across the whole article.")
        else:
            instructions.append("Keep the same visual language across cover, infographic, and inline illustrations for this article.")
    if section:
        instructions.append(f"Section focus: {section}")
    if scene_hint:
        instructions.append("Section excerpt: " + scene_hint)
    if item.get("layout_variant_label"):
        instructions.append(f"Layout variant: {item['layout_variant_label']}")
    if item.get("layout_variant_instruction"):
        instructions.append(f"Composition rule: {item['layout_variant_instruction']}")
    instructions.append(f"Text budget: {text_policy['text_budget']}")
    instructions.append(f"Text policy: {text_policy['mode']}")
    instructions.append(f"Preferred label language: {text_policy['label_language']}")
    instructions.append("Allowed labels: " + (" / ".join(text_policy["label_strategy"]) if text_policy["label_strategy"] else "none"))
    instructions.append(cfg.image_type_prompt_modules.get(item["type"], cfg.image_type_prompt_modules["正文插图"]))
    instructions.extend(text_policy["prompt_lines"])
    instructions.append("Never render copied article paragraphs, generic section labels, or UI cards filled with body text.")
    instructions.extend(cfg.image_differentiation_modules)
    instructions.append("Avoid clutter, excessive small text, watermarks, and brand logos unless explicitly requested.")
    return "\n".join(line for line in instructions if line).strip()


def prompt_markdown(title: str, audience: str, controls: dict[str, Any], item: dict[str, Any], *, cfg: ImagePromptingConfig) -> str:
    prompt = item.get("prompt") or ""
    layout_spec = image_layout_spec(item)
    visual_elements = image_visual_elements(item, cfg=cfg)
    text_policy = resolve_image_text_policy(controls, item, cfg=cfg)
    label_strategy = text_policy["label_strategy"]
    text_budget = text_policy["text_budget"]
    aspect_policy = image_aspect_policy(item)
    style_mode = item.get("style_mode") or controls.get("style_mode") or "uniform"
    base_style_label = (item.get("base_preset_label") or controls.get("preset_label") or controls.get("style") or "").strip()
    visual_style_label = (item.get("visual_preset_label") or base_style_label).strip()
    article_strategy = item.get("article_visual_strategy") or {}
    style_lines: list[str] = []
    if style_mode == "mixed-by-type":
        style_lines.append(f"- 基调风格：{base_style_label or 'default'}")
        style_lines.append(f"- 当前图片风格：{visual_style_label or 'default'}")
    else:
        style_lines.append(f"- 统一风格：{base_style_label or 'default'}")
    lines = [
        "---",
        f"id: {item['id']}",
        f"title: {title}",
        f"type: {item['type']}",
        f"position: {image_position_label(item)}",
        f"target_section: {item.get('target_section', '')}",
        f"layout_variant: {item.get('layout_variant_key', '')}",
        f"layout_family: {controls.get('layout_family', '')}",
        f"style_mode: {style_mode}",
        f"decision_source: {item.get('decision_source', '')}",
        f"base_preset: {controls.get('preset', '')}",
        f"preset: {item.get('visual_preset') or controls.get('preset', '')}",
        f"density: {controls.get('density', 'balanced')}",
        "---",
        "",
        f"# 图片 Prompt：{item['id']}",
        "",
        f"- 用途：{image_purpose_label(item)}",
        f"- 目标读者：{audience}",
    ]
    lines.extend(style_lines)
    lines.extend([
        f"- 文章视觉方向：{article_strategy.get('visual_direction') or 'auto'}",
        f"- 风格家族：{article_strategy.get('style_family') or 'auto'}",
        f"- 内容模式：{article_strategy.get('content_mode') or 'auto'}",
        f"- 类型决策：{item.get('type_reason') or 'auto'}",
        f"- 风格决策：{item.get('style_reason') or 'auto'}",
        f"- 版式变体：{item.get('layout_variant_label', '默认构图')}",
        "",
        "## 视觉内容",
        "",
        image_visual_content(item, cfg=cfg),
        "",
        "## 视觉元素",
        "",
    ])
    lines.extend(f"- {element}" for element in visual_elements)
    lines.extend([
        "",
        "## 布局规格",
        "",
        f"- 变体：{layout_spec['variant_label']} (`{layout_spec['variant_key']}`)",
        f"- 构图规则：{layout_spec['instruction']}",
        f"- 目标：{layout_spec['composition_goal']}",
        "",
        "## 文字策略",
        "",
        f"- 文本预算：{text_budget}",
        f"- 文字模式：{text_policy['label']}",
        f"- 标签语言：{text_policy['label_language']}",
        f"- 允许标签：{' / '.join(label_strategy) if label_strategy else '尽量不使用嵌入文字'}",
        "",
        "## 比例策略",
        "",
        f"- {aspect_policy}",
        "",
        "## 锚定段落（插入点）摘录",
        "",
        image_anchor_excerpt(item, 120, cfg=cfg) or "无",
        "",
        "## 章节摘要",
        "",
        image_section_excerpt(item, 140, cfg=cfg) or "无",
        "",
        "## Prompt",
        "",
        prompt,
        "",
    ])
    return "\n".join(line for line in lines if line is not None)
