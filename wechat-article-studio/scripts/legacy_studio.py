#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import copy
import gzip
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zlib
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable

from core.editorial_strategy import EDITORIAL_STYLE_LIBRARY, generate_diverse_title_variants, title_template_key
from core.image_assembly import assemble_body
from core.image_planning import ImagePlanConfig, build_plan_payload as _build_plan_payload, enrich_plan_items as _enrich_plan_items, image_planning_diagnostics as _image_planning_diagnostics
from core.image_prompting import (
    ImagePromptingConfig,
    cleaned_image_signal_text as _cleaned_image_signal_text,
    compact_label_strategy as _compact_label_strategy,
    compose_prompt as _compose_image_prompt,
    image_anchor_excerpt as _image_anchor_excerpt,
    image_aspect_policy as _image_aspect_policy,
    image_label_strategy as _image_label_strategy,
    image_position_label as _image_position_label,
    image_purpose_label as _image_purpose_label,
    image_section_excerpt as _image_section_excerpt,
    image_section_focus as _image_section_focus,
    image_text_budget as _image_text_budget,
    image_text_policy_variant_instruction as _image_text_policy_variant_instruction,
    image_visual_content as _image_visual_content,
    image_visual_elements as _image_visual_elements,
    image_layout_spec as _image_layout_spec,
    image_aspect_policy as _image_aspect_policy,
    normalize_image_text_policy as _core_normalize_image_text_policy,
    normalize_label_language as _core_normalize_label_language,
    prompt_markdown as _prompt_markdown,
    resolve_image_text_policy as _resolve_image_text_policy,
    short_sentence_chunks as _short_sentence_chunks,
)


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ASSETS_DIR = SKILL_DIR / "assets"
DEFAULT_THRESHOLD = 88
DISCLAIMER_VERSION = "1.0"
MANIFEST_VERSION = 2
DEFAULT_COVER_POLICY = "thumb_only"
NETWORK_TIMEOUT = 30
NETWORK_RETRIES = 3
GEMINI_WEB_IMAGE_TIMEOUT = 120
_gemini_web_timeout_raw = (os.getenv("GEMINI_WEB_IMAGE_TIMEOUT") or os.getenv("GEMINI_WEB_IMAGE_TIMEOUT_SEC") or "").strip()
if _gemini_web_timeout_raw:
    try:
        GEMINI_WEB_IMAGE_TIMEOUT = max(10, int(_gemini_web_timeout_raw))
    except ValueError:
        pass
WECHAT_BATCHGET_COUNT = 20
TRANSPARENT_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9pY8m7QAAAAASUVORK5CYII="
)

WEIGHTS: list[tuple[str, int]] = [
    ("标题与开头爆点", 12),
    ("核心观点与副观点", 10),
    ("说服策略与论证多样性", 12),
    ("情绪触发与刺痛感", 12),
    ("金句与传播句密度", 10),
    ("情感曲线与节奏", 8),
    ("情感层次与共鸣", 8),
    ("视角转化与认知增量", 8),
    ("语言风格自然度", 10),
    ("可信度与检索支撑", 10),
]

TITLE_POWER_WORDS = [
    "为什么",
    "真相",
    "底层",
    "机会",
    "方法",
    "公式",
    "清单",
    "趋势",
    "核心",
    "普通人",
    "高手",
    "真正",
    "别再",
    "一定",
    "秘密",
    "增长",
]
HOOK_WORDS = [
    "为什么",
    "但",
    "却",
    "不是",
    "而是",
    "真相",
    "大多数人",
    "很少有人",
    "你以为",
    "真正",
    "反而",
    "结果",
    "先说结论",
    "如果",
    "直到",
]
GOLDEN_QUOTE_WORDS = [
    "不是",
    "而是",
    "真正",
    "本质",
    "底层",
    "高手",
    "普通人",
    "决定",
    "差距",
    "增长",
    "价值",
    "能力",
    "信任",
]
TITLE_BENEFIT_WORDS = [
    "方法", "清单", "公式", "避坑", "模板", "答案", "机会", "趋势", "增长", "提升", "翻倍", "入门", "进阶", "判断", "指南", "秘籍",
]
TITLE_CURIOSITY_WORDS = [
    "为什么", "真相", "误区", "别再", "你以为", "其实", "背后", "被低估", "正在", "突然", "没想到", "关键", "看懂",
]
TITLE_TIMELY_WORDS = [
    "今天", "今年", "最近", "这次", "刚刚", "最新", "24小时", "本周", "2026", "眼下", "正在",
]
TITLE_AUDIENCE_WORDS = [
    "普通人", "新手", "职场人", "创业者", "管理者", "家长", "中小企业", "开发者", "运营人", "创作者", "打工人",
]
TITLE_SCORE_THRESHOLD = 68
DISCOVERY_TOPIC_LIMIT = 8
DISCOVERY_FEED_LIMIT = 20
DISCOVERY_PROVIDER_CHOICES = ("auto", "google-news-rss", "custom-rss", "tavily")
START_TOPIC_TOKENS = {"", "开始", "start", "begin", "go", "启动", "开启公众号创作", "开启创作", "开始创作"}
GEMINI_WEB_NO_IMAGE_MARKER = "No image returned in response."
GEMINI_WEB_IMAGE_MODEL_CANDIDATES = [
    "gemini-3.1-flash-image-preview",
    "gemini-2.5-flash-image",
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-image",
]
AI_STYLE_PHRASES = [
    "首先",
    "其次",
    "综上所述",
    "总的来说",
    "总而言之",
    "简而言之",
    "值得注意的是",
    "需要指出的是",
    "不可否认",
    "显而易见",
    "不难发现",
    "由此可见",
    "此外",
    "与此同时",
    "换句话说",
    "从某种意义上说",
    "值得一提的是",
    "归根结底",
    "在当今社会",
    "接下来，我会",
    "接下来我们来看",
    "这篇文章会",
    "如果你只想记住一句话",
    "最后给你一个可执行清单",
]

IMAGE_STYLE_PRESETS: dict[str, dict[str, str]] = {
    "cute": {
        "label": "可爱手账",
        "theme": "轻松可爱视觉表达",
        "style": "圆润手绘卡片风",
        "mood": "亲和活泼",
        "custom_visual_brief": "use rounded shapes, soft pastel palette, sticker-like accents, and friendly composition",
    },
    "fresh": {
        "label": "清新杂志",
        "theme": "清新轻盈视觉表达",
        "style": "留白编辑风",
        "mood": "清爽克制",
        "custom_visual_brief": "use airy whitespace, clean composition, light green-blue palette, and breathable editorial rhythm",
    },
    "warm": {
        "label": "温暖生活",
        "theme": "温暖治愈视觉表达",
        "style": "柔和生活方式插画",
        "mood": "松弛温柔",
        "custom_visual_brief": "use warm beige-orange palette, soft lighting, tactile details, and cozy storytelling mood",
    },
    "bold": {
        "label": "高对比海报",
        "theme": "强冲击信息表达",
        "style": "高对比图形海报",
        "mood": "果断鲜明",
        "custom_visual_brief": "use bold typography cues, strong contrast, large graphic blocks, and punchy poster composition",
    },
    "minimal": {
        "label": "极简理性",
        "theme": "极简理性视觉表达",
        "style": "极简几何编辑风",
        "mood": "冷静专业",
        "custom_visual_brief": "use minimal palette, restrained geometry, precise alignment, and remove decorative noise",
    },
    "retro": {
        "label": "复古印刷",
        "theme": "复古内容表达",
        "style": "复古印刷拼贴风",
        "mood": "怀旧沉稳",
        "custom_visual_brief": "use muted vintage palette, subtle print texture, retro poster balance, and nostalgic graphic treatment",
    },
    "pop": {
        "label": "流行拼贴",
        "theme": "流行文化视觉表达",
        "style": "高饱和拼贴风",
        "mood": "张扬有趣",
        "custom_visual_brief": "use saturated colors, playful geometry, energetic cutout composition, and expressive pop accents",
    },
    "notion": {
        "label": "知识卡片",
        "theme": "知识卡片视觉表达",
        "style": "中性色笔记系统",
        "mood": "清晰克制",
        "custom_visual_brief": "use neutral black-gray-beige palette, clean card layout, knowledge-product feel, and crisp modular hierarchy",
    },
    "chalkboard": {
        "label": "黑板讲解",
        "theme": "讲解板书视觉表达",
        "style": "黑板粉笔手绘风",
        "mood": "教学感强",
        "custom_visual_brief": "use dark chalkboard background, chalk-like strokes, hand-drawn diagram cues, and classroom explanation vibe",
    },
    "editorial-grain": {
        "label": "杂志颗粒",
        "theme": "编辑大片视觉表达",
        "style": "杂志颗粒拼版风",
        "mood": "克制高级",
        "custom_visual_brief": "use editorial magazine composition, subtle grain texture, restrained palette, and premium print-like balance",
    },
    "organic-natural": {
        "label": "自然有机",
        "theme": "自然有机视觉表达",
        "style": "植物感柔和插画",
        "mood": "舒展松弛",
        "custom_visual_brief": "use organic shapes, earthy palette, natural textures, and soft handcrafted rhythm",
    },
    "scientific-blueprint": {
        "label": "科学蓝图",
        "theme": "科学解释视觉表达",
        "style": "蓝图线稿信息风",
        "mood": "理性精确",
        "custom_visual_brief": "use blueprint-like diagrams, technical linework, subtle grid cues, and scientific precision",
    },
    "professional-corporate": {
        "label": "专业商务",
        "theme": "专业商务视觉表达",
        "style": "企业报告图形风",
        "mood": "稳健可信",
        "custom_visual_brief": "use polished business graphics, clean corporate hierarchy, and confident restrained color usage",
    },
    "abstract-geometric": {
        "label": "抽象几何",
        "theme": "抽象几何视觉表达",
        "style": "几何构成海报风",
        "mood": "前卫理性",
        "custom_visual_brief": "use bold geometric forms, abstract spatial balance, limited palette, and minimal symbolic storytelling",
    },
    "luxury-minimal": {
        "label": "轻奢极简",
        "theme": "轻奢极简视觉表达",
        "style": "高端留白版式",
        "mood": "高级冷静",
        "custom_visual_brief": "use generous whitespace, elegant material cues, sophisticated contrast, and premium understated composition",
    },
    "illustrated-handdrawn": {
        "label": "手绘讲述",
        "theme": "手绘叙事视觉表达",
        "style": "手绘说明插画风",
        "mood": "有人味",
        "custom_visual_brief": "use hand-drawn lines, annotated illustration feel, approachable storytelling, and warm human touch",
    },
    "photoreal-sketch": {
        "label": "写实速写",
        "theme": "写实概念视觉表达",
        "style": "写实草图混合风",
        "mood": "真实克制",
        "custom_visual_brief": "blend realistic lighting with sketch overlays, tactile surfaces, and concept-driven realism without heavy text",
    },
}
IMAGE_STYLE_PRESET_CHOICES = tuple(IMAGE_STYLE_PRESETS.keys())
IMAGE_DIRECTIVE_RE = re.compile(r"<!--\s*image:(.*?)-->", flags=re.I | re.S)
IMAGE_TYPE_ALIASES = {
    "插图": "正文插图",
    "正文插图": "正文插图",
    "illustration": "正文插图",
    "flow": "流程图",
    "flowchart": "流程图",
    "流程图": "流程图",
    "compare": "对比图",
    "comparison": "对比图",
    "对比图": "对比图",
    "infographic": "信息图",
    "信息图": "信息图",
    "divider": "分隔图",
    "separator": "分隔图",
    "分隔图": "分隔图",
}
IMAGE_LAYOUT_VARIANTS: dict[str, list[dict[str, str]]] = {
    "封面图": [
        {"key": "hero-object", "label": "中心主视觉", "instruction": "Use one dominant hero object in the center with strong negative space and no embedded headline text."},
        {"key": "editorial-collage", "label": "编辑拼贴", "instruction": "Use an editorial collage composition with layered shapes and two or three visual clusters, without text blocks."},
        {"key": "symbolic-scene", "label": "象征场景", "instruction": "Use a symbolic scene with depth and atmosphere, showing the article idea through metaphor instead of labels."},
        {"key": "diagonal-poster", "label": "斜向张力", "instruction": "Use a diagonal poster composition with directional energy and one clear focal object, keeping text out of the image."},
        {"key": "framed-window", "label": "窗景框构", "instruction": "Use a framed-window composition that creates depth and hierarchy through nested planes instead of text."},
    ],
    "信息图": [
        {"key": "stacked-cards", "label": "纵向卡片", "instruction": "Use a stacked-card infographic layout with 3 to 5 modules and only short keywords if absolutely needed."},
        {"key": "radial-map", "label": "中心辐射", "instruction": "Use a radial map layout with one core node and surrounding branches, relying on icons and shapes more than text."},
        {"key": "timeline-column", "label": "时间轴列", "instruction": "Use a vertical timeline or ladder layout with clear sequence and very limited short labels."},
        {"key": "dashboard-panels", "label": "仪表板面板", "instruction": "Use dashboard-like information panels with clear metrics, compact modules, and restrained labels."},
        {"key": "matrix-grid", "label": "矩阵网格", "instruction": "Use a matrix or quadrant grid with strong grouping and spatial categorization instead of explanatory text."},
        {"key": "tree-hierarchy", "label": "层级树", "instruction": "Use a hierarchy tree that shows parent-child structure clearly with icons, branches, and very short labels."},
        {"key": "map-geography", "label": "地理映射", "instruction": "Use a map-driven layout with location markers or regions, minimizing text and emphasizing spatial relationships."},
    ],
    "正文插图": [
        {"key": "scene-metaphor", "label": "场景隐喻", "instruction": "Use a scene-based metaphor with clear foreground and background, and avoid embedded text entirely."},
        {"key": "object-closeup", "label": "物件特写", "instruction": "Use one or two symbolic objects in close-up, emphasizing texture and concept rather than labels."},
        {"key": "abstract-geometry", "label": "抽象图形", "instruction": "Use abstract geometric composition to express the idea without any readable text."},
        {"key": "editorial-panel", "label": "编辑画面", "instruction": "Use an editorial illustration panel with one strong concept frame and no embedded text."},
        {"key": "cutaway-layer", "label": "剖面分层", "instruction": "Use a cutaway or layered depth composition to reveal the concept without resorting to labels."},
    ],
    "流程图": [
        {"key": "path-nodes", "label": "路径节点", "instruction": "Use a node-and-path flow layout with arrows and milestones, limiting text to tiny step tags only if unavoidable."},
        {"key": "ladder-steps", "label": "阶梯步骤", "instruction": "Use a ladder or staircase process layout that shows progression visually, not through long labels."},
        {"key": "swimlane-flow", "label": "泳道流转", "instruction": "Use a swimlane or track-based flow layout with lanes, icons, and connectors instead of paragraphs."},
        {"key": "loop-cycle", "label": "闭环循环", "instruction": "Use a cyclical process layout when the workflow repeats or feeds back into itself, keeping labels extremely short."},
        {"key": "timeline-flow", "label": "时间推进", "instruction": "Use a linear timeline flow with milestone markers and sparse labels to show sequence."},
    ],
    "对比图": [
        {"key": "split-panel", "label": "左右分栏", "instruction": "Use a clean split-panel comparison with strong contrast between left and right sides, minimizing text."},
        {"key": "cards-versus", "label": "卡片对照", "instruction": "Use parallel comparison cards with mirrored structure and icon cues, not dense wording."},
        {"key": "spectrum-contrast", "label": "光谱对照", "instruction": "Use a spectrum or axis-based contrast layout that shows differences through position, color, and shape."},
        {"key": "matrix-versus", "label": "矩阵对照", "instruction": "Use a comparison matrix to contrast multiple dimensions visually with minimal wording."},
        {"key": "before-after", "label": "前后对照", "instruction": "Use a before-versus-after composition emphasizing transition and difference rather than descriptive text."},
    ],
    "分隔图": [
        {"key": "motif-band", "label": "主题带状", "instruction": "Use a wide motif band as a visual pause, with no embedded text and a strong thematic cue."},
        {"key": "symbol-break", "label": "象征断点", "instruction": "Use a symbolic break image that resets rhythm between sections while staying visually minimal."},
        {"key": "atmospheric-divider", "label": "氛围分隔", "instruction": "Use an atmospheric divider composition with strong mood and no readable text."},
    ],
}
IMAGE_DENSITY_CHOICES = ("auto", "none", "minimal", "balanced", "dense", "custom")
ALLOW_CLOSING_IMAGE_CHOICES = ("auto", "on", "off")
IMAGE_LAYOUT_FAMILY_VARIANTS: dict[str, list[str]] = {
    "editorial": ["hero-object", "editorial-collage", "editorial-panel", "framed-window"],
    "process": ["path-nodes", "ladder-steps", "swimlane-flow", "timeline-flow", "loop-cycle"],
    "comparison": ["split-panel", "cards-versus", "spectrum-contrast", "matrix-versus", "before-after"],
    "timeline": ["timeline-column", "timeline-flow"],
    "hierarchy": ["tree-hierarchy", "radial-map"],
    "dashboard": ["dashboard-panels", "matrix-grid", "stacked-cards"],
    "map": ["map-geography"],
    "radial": ["radial-map"],
    "list": ["stacked-cards", "matrix-grid"],
}
IMAGE_LAYOUT_FAMILY_CHOICES = tuple(IMAGE_LAYOUT_FAMILY_VARIANTS.keys())
IMAGE_STYLE_MODE_CHOICES = ("uniform", "mixed-by-type")
IMAGE_AUTO_STYLE_PROFILES: dict[str, dict[str, Any]] = {
    "editorial-analysis": {
        "label": "编辑评论",
        "preset": "editorial-grain",
        "theme": "观点趋势洞察",
        "style": "编辑评论插画",
        "mood": "克制敏锐",
        "style_mode": "uniform",
        "layout_family": "editorial",
        "cover_preset": "bold",
        "infographic_preset": "notion",
        "inline_preset": "editorial-grain",
        "base_module": "Favor magazine-grade composition, conceptual metaphors, restrained texture, and opinionated framing over explanatory diagrams.",
    },
    "knowledge-explainer": {
        "label": "知识解释",
        "preset": "fresh",
        "theme": "知识解释与方法拆解",
        "style": "清晰解释型插画",
        "mood": "清楚友好",
        "style_mode": "mixed-by-type",
        "layout_family": "editorial",
        "cover_preset": "fresh",
        "infographic_preset": "notion",
        "inline_preset": "illustrated-handdrawn",
        "base_module": "Favor clear teaching visuals, explainer metaphors, and approachable detail. Only use structure graphics when the section is genuinely structural.",
    },
    "storytelling-human": {
        "label": "叙事手绘",
        "preset": "illustrated-handdrawn",
        "theme": "人物叙事与情绪共鸣",
        "style": "手绘叙事插画",
        "mood": "温和有人味",
        "style_mode": "uniform",
        "layout_family": "editorial",
        "cover_preset": "warm",
        "infographic_preset": "fresh",
        "inline_preset": "illustrated-handdrawn",
        "base_module": "Favor human-centered storytelling, tactile details, scene fragments, and emotional resonance instead of chart-like structure.",
    },
    "business-decision": {
        "label": "商业决策",
        "preset": "professional-corporate",
        "theme": "商业判断与策略取舍",
        "style": "商务图解与编辑海报",
        "mood": "稳健果断",
        "style_mode": "mixed-by-type",
        "layout_family": "comparison",
        "cover_preset": "bold",
        "infographic_preset": "professional-corporate",
        "inline_preset": "luxury-minimal",
        "base_module": "Favor sharp strategic framing, premium business graphics, and clear decision signals. Avoid generic blueprint wireframes unless the article is about actual systems architecture.",
    },
    "organic-lifestyle": {
        "label": "自然生活",
        "preset": "organic-natural",
        "theme": "生活方式与温和洞察",
        "style": "自然叙事插画",
        "mood": "舒展温暖",
        "style_mode": "uniform",
        "layout_family": "editorial",
        "cover_preset": "organic-natural",
        "infographic_preset": "fresh",
        "inline_preset": "organic-natural",
        "base_module": "Favor soft narrative imagery, organic shapes, and calm rhythm. Use diagrams sparingly and only when the article explicitly teaches a process.",
    },
    "abstract-trend": {
        "label": "抽象趋势",
        "preset": "abstract-geometric",
        "theme": "趋势变化与抽象张力",
        "style": "抽象几何趋势插画",
        "mood": "前卫理性",
        "style_mode": "uniform",
        "layout_family": "editorial",
        "cover_preset": "abstract-geometric",
        "infographic_preset": "notion",
        "inline_preset": "abstract-geometric",
        "base_module": "Favor abstract trend storytelling, symbolic geometry, and strong directional composition over literal diagram blocks.",
    },
}
IMAGE_CONTENT_MODE_MODULES: dict[str, str] = {
    "conceptual": "Express concepts through metaphor, symbolic objects, tension, and visual hierarchy rather than explicit labels.",
    "narrative": "Lean into scenes, character traces, tactile details, and emotional cues that feel like a story slice instead of a slide.",
    "structural": "Use structure only where it clarifies relationships. Prefer elegant modules and readable grouping, not dense arrows by default.",
    "data": "Use selective quantitative cues, contrast, and information layers. Keep labels extremely sparse and avoid turning every image into a dashboard.",
}
IMAGE_TYPE_PROMPT_MODULES: dict[str, str] = {
    "封面图": "Create a high-recognition hero image for WeChat: one dominant focal idea, strong atmosphere, strong crop safety, and no headline baked into the image.",
    "信息图": "Compress the key structure into a scan-friendly visual summary. Favor modular grouping, icon logic, and one clear reading path before adding any short labels.",
    "流程图": "Show a real sequence or operational path with just enough direction cues to be understood. Use arrows, nodes, and spacing first; only add very short labels when the flow would otherwise become unclear.",
    "对比图": "Make the contrast obvious at first glance through composition, grouping, and opposing cues. Let objects, position, color, and metaphor do most of the work, and use only very short labels if they truly help the comparison.",
    "分隔图": "Reset the reading rhythm with a thematic visual pause that still belongs to the article's visual world.",
    "正文插图": "Support the nearby paragraph through metaphor, objects, scenes, or conceptual framing. Do not fall back to a generic diagram unless the text truly demands structure.",
}
IMAGE_STYLE_FAMILY_MODULES: dict[str, str] = {
    "editorial-analysis": "Use editorial collage language, premium print rhythm, restrained palette shifts, and a thought-piece tone.",
    "knowledge-explainer": "Use approachable explainer illustration language with clear layers, digestible modules, and teaching clarity.",
    "storytelling-human": "Use warm hand-drawn storytelling language, lived-in details, and expressive scene-building.",
    "business-decision": "Use confident business-graphic language, premium contrast, and strategic framing with polished restraint.",
    "organic-lifestyle": "Use organic shapes, tactile textures, and soft narrative pacing with natural visual cues.",
    "abstract-trend": "Use abstract geometry, bold spatial contrast, and symbolic trend motion with minimal literalism.",
}
IMAGE_DIFFERENTIATION_MODULES = [
    "Do not reuse the same visual grammar across every image in the article.",
    "Vary the composition, camera distance, focal object strategy, and negative space pattern from image to image.",
    "If one image is structural, let neighboring images lean metaphorical or scenic unless the text explicitly requires repeated structure diagrams.",
]
IMAGE_TEXT_POLICY_CHOICES = ("auto", "none", "short-zh", "short-zh-numeric", "short-any")
IMAGE_TEXT_POLICY_DEFAULTS: dict[str, str] = {
    "封面图": "none",
    "正文插图": "none",
    "分隔图": "none",
    "流程图": "short-zh-numeric",
    "信息图": "short-zh-numeric",
    "对比图": "short-zh",
}
IMAGE_TEXT_POLICY_LABELS: dict[str, str] = {
    "auto": "按图片类型自动决定",
    "none": "无可读文字",
    "short-zh": "极少中文短标签",
    "short-zh-numeric": "极少中文短标签或数字",
    "short-any": "极少短标签",
}
IMAGE_LABEL_LANGUAGE_CHOICES = ("zh-CN", "any")
IMAGE_LABEL_BAD_PREFIXES = ("如果", "看到", "不过", "这里", "真正", "因为", "不是", "而是", "所以", "这个", "那个")
ARTICLE_VISUAL_HINT_WORDS: dict[str, tuple[str, ...]] = {
    "narrative": ("故事", "人物", "经历", "日常", "生活", "感受", "情绪", "焦虑", "治愈", "成长", "关系", "亲密", "家庭"),
    "business": ("商业", "增长", "市场", "变现", "策略", "决策", "竞争", "订阅", "广告", "公司", "收入", "利润", "品牌"),
    "technical": ("模型", "系统", "推理", "工程", "芯片", "算力", "基础设施", "架构", "平台", "评测", "部署", "Agent"),
    "tutorial": ("教程", "指南", "步骤", "实操", "上手", "怎么做", "如何", "方法", "SOP", "清单", "流程", "落地"),
    "comparison": ("对比", "区别", "差异", "A/B", "vs", "VS", "不是", "而是", "优劣", "取舍", "选择"),
    "data": ("数据", "指标", "趋势", "比例", "图表", "统计", "%", "同比", "环比", "增长率"),
}
DEPTH_WORDS = [
    "案例",
    "数据",
    "原因",
    "本质",
    "逻辑",
    "机制",
    "趋势",
    "拆解",
    "方法",
    "路径",
    "实验",
    "对比",
    "模型",
    "框架",
]
EMOTION_WORDS = [
    "焦虑",
    "惊讶",
    "兴奋",
    "失望",
    "希望",
    "担心",
    "共鸣",
    "治愈",
    "温暖",
    "遗憾",
    "后悔",
    "勇气",
]
SHARE_WORDS = [
    "建议",
    "清单",
    "步骤",
    "马上",
    "可以直接",
    "收藏",
    "转发",
    "复用",
    "模板",
    "打法",
]
IMAGE_PROVIDER_FILES = [
    "main.ts",
    "gemini-webapi/client.ts",
    "gemini-webapi/constants.ts",
    "gemini-webapi/exceptions.ts",
    "gemini-webapi/index.ts",
    "gemini-webapi/components/gem-mixin.ts",
    "gemini-webapi/components/index.ts",
    "gemini-webapi/types/candidate.ts",
    "gemini-webapi/types/gem.ts",
    "gemini-webapi/types/grpc.ts",
    "gemini-webapi/types/image.ts",
    "gemini-webapi/types/index.ts",
    "gemini-webapi/types/modeloutput.ts",
    "gemini-webapi/utils/cookie-file.ts",
    "gemini-webapi/utils/decorators.ts",
    "gemini-webapi/utils/get-access-token.ts",
    "gemini-webapi/utils/http.ts",
    "gemini-webapi/utils/index.ts",
    "gemini-webapi/utils/load-browser-cookies.ts",
    "gemini-webapi/utils/logger.ts",
    "gemini-webapi/utils/parsing.ts",
    "gemini-webapi/utils/paths.ts",
    "gemini-webapi/utils/rotate-1psidts.ts",
    "gemini-webapi/utils/upload-file.ts",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path) -> str:
    # PowerShell/Windows may write UTF-8 with BOM, which can break downstream processing and console output.
    return path.read_text(encoding="utf-8").lstrip("\ufeff")


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_print(text: str) -> None:
    """Write text to stdout without crashing on Windows console encodings (e.g. GBK)."""
    value = (text or "")
    if not value.endswith("\n"):
        value += "\n"
    try:
        sys.stdout.write(value)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(value.encode("utf-8", errors="replace"))
        sys.stdout.flush()


def safe_print_json(data: Any) -> None:
    safe_print(json.dumps(data, ensure_ascii=False, indent=2))


def slugify(text: str) -> str:
    safe = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text.strip().lower())
    safe = safe.strip("-")
    if safe:
        return safe[:48]
    return f"job-{hashlib.md5(text.encode('utf-8')).hexdigest()[:8]}"


def workspace_path(raw: str | None) -> Path:
    if raw:
        return Path(raw).resolve()
    return Path.cwd() / f"wechat-job-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def ensure_workspace(path: Path) -> Path:
    ensure_dir(path)
    ensure_dir(path / "assets" / "images")
    return path


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    parts = text.split("\n---\n", 1)
    if len(parts) != 2:
        return {}, text
    raw = parts[0].splitlines()[1:]
    meta: dict[str, str] = {}
    for line in raw:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, parts[1]


def join_frontmatter(meta: dict[str, Any], body: str) -> str:
    lines = ["---"]
    for key, value in meta.items():
        if value is None or value == "":
            continue
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body.lstrip("\n"))
    return "\n".join(lines).rstrip() + "\n"


def ensure_manifest_schema(manifest: dict[str, Any], workspace: Path | None = None) -> dict[str, Any]:
    manifest.setdefault("manifest_version", MANIFEST_VERSION)
    if workspace is not None:
        manifest.setdefault("workspace", str(workspace))
    manifest.setdefault("created_at", manifest.get("created_at") or now_iso())
    manifest.setdefault("updated_at", now_iso())
    manifest.setdefault("asset_paths", {})
    manifest.setdefault("cover_policy", DEFAULT_COVER_POLICY)
    manifest.setdefault("publish_status", "not_started")
    manifest.setdefault("draft_media_id", "")
    manifest.setdefault("uploaded_html_path", "")
    manifest.setdefault("verify_status", "not_run")
    manifest.setdefault("verify_errors", [])
    manifest.setdefault("expected_inline_count", 0)
    manifest.setdefault("uploaded_inline_count", 0)
    manifest.setdefault("verified_inline_count", 0)
    return manifest


def load_manifest(workspace: Path) -> dict[str, Any]:
    manifest = read_json(workspace / "manifest.json", default={}) or {}
    return ensure_manifest_schema(manifest, workspace)


def save_manifest(workspace: Path, manifest: dict[str, Any]) -> None:
    ensure_manifest_schema(manifest, workspace)
    manifest["updated_at"] = now_iso()
    write_json(workspace / "manifest.json", manifest)


def read_input_file(path_value: str | None) -> str:
    if not path_value or path_value == "-":
        return sys.stdin.read()
    return read_text(Path(path_value).resolve())


def extract_title_from_body(body: str) -> str | None:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _normalize_title_match(text: str) -> str:
    value = re.sub(r"^#\s+", "", text or "").strip()
    value = value.strip("《》\"'“”‘’")
    value = re.sub(r"[：:()\[\]（）\-—_·`~!@#$%^&*+=|\\/<>,.?？，。！、\s]+", "", value)
    return value.lower()


def strip_leading_h1(body: str, title: str) -> str:
    lines = body.splitlines()
    if lines and _normalize_title_match(lines[0]) == _normalize_title_match(title):
        return "\n".join(lines[1:]).lstrip("\n")
    return body


def extract_summary(text: str, limit: int = 120) -> str:
    text = IMAGE_DIRECTIVE_RE.sub(" ", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    body = re.sub(r"\s+", " ", text).strip()
    return body[:limit].strip()


HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WechatArticleStudio/1.0",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
}
EVIDENCE_STOPWORDS = {
    "我们", "你们", "他们", "这个", "那个", "这些", "那些", "一种", "一个", "一些", "已经", "没有", "不是", "以及",
    "因为", "所以", "如果", "但是", "而且", "还有", "可以", "需要", "进行", "相关", "关于", "更多", "使用", "平台",
    "内容", "文章", "标题", "用户", "官方", "账号", "公众号",
    "official", "account", "article", "content", "title", "about", "with", "from", "that", "this", "have", "will",
}


EVIDENCE_NOISE_PHRASES = ["Latest News", "Donate", "Search", "Read more", "Skip to content", "Help section", "Copyright", "Privacy"]


def decode_response_body(raw: bytes, headers: Any, default_charset: str = "utf-8") -> str:
    charset = None
    if headers is not None:
        getter = getattr(headers, "get_content_charset", None)
        if callable(getter):
            charset = getter()
        if not charset:
            content_type = headers.get("Content-Type", "")
            match = re.search(r"charset=([\w-]+)", content_type, flags=re.I)
            if match:
                charset = match.group(1)
    return raw.decode(charset or default_charset, errors="replace")


def urlopen_with_retry(request: urllib.request.Request | str, timeout: int = NETWORK_TIMEOUT, retries: int = NETWORK_RETRIES) -> tuple[bytes, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                content_encoding = (response.headers.get("Content-Encoding") or "").lower()
                if content_encoding == "gzip" or raw[:2] == bytes.fromhex("1f8b"):
                    raw = gzip.decompress(raw)
                elif content_encoding == "deflate":
                    raw = zlib.decompress(raw)
                return raw, response.headers
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            if exc.code >= 500 and attempt < retries:
                time.sleep(0.5 * attempt)
                continue
            message = decode_response_body(raw, exc.headers)
            raise SystemExit(f"请求失败：HTTP {exc.code} {message}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.5 * attempt)
                continue
            reason = getattr(exc, "reason", exc)
            raise SystemExit(f"请求失败：{reason}") from exc
    if last_error is not None:
        raise SystemExit(f"请求失败：{last_error}") from last_error
    raise SystemExit("请求失败：未知网络错误")


def fetch_text_from_url(url: str, timeout: int = 15) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in {"http", "https"}:
        request = urllib.request.Request(url, headers=HTTP_HEADERS)
        raw, headers = urlopen_with_retry(request, timeout=timeout)
        content_type = headers.get("Content-Type", "")
        return decode_response_body(raw, headers), content_type
    if parsed.scheme == "file":
        path = Path(urllib.request.url2pathname(parsed.path))
        return path.read_text(encoding="utf-8"), "text/plain"
    raise ValueError(f"unsupported source url: {url}")


def parse_rss_datetime(raw: str) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def google_news_feed_url(query: str = "", window_hours: int = 24) -> str:
    if query:
        q = f"{query} when:{window_hours}h"
        encoded = urllib.parse.quote(q)
        return f"https://news.google.com/rss/search?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    return "https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans"


def fetch_google_news_items(query: str, window_hours: int, limit: int) -> list[dict[str, Any]]:
    url = google_news_feed_url(query, window_hours)
    request = urllib.request.Request(url, headers=HTTP_HEADERS)
    raw, headers = urlopen_with_retry(request, timeout=NETWORK_TIMEOUT, retries=NETWORK_RETRIES)
    xml_text = decode_response_body(raw, headers)
    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    if channel is None:
        return []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    items: list[dict[str, Any]] = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_raw = (item.findtext("pubDate") or "").strip()
        source = ""
        source_elem = item.find("{http://search.yahoo.com/mrss/}source")
        if source_elem is not None and (source_elem.text or "").strip():
            source = source_elem.text.strip()
        published_at = parse_rss_datetime(pub_raw)
        if published_at and published_at < cutoff:
            continue
        if not title or not link:
            continue
        items.append(
            {
                "title": title,
                "link": link,
                "source": source or "Google 新闻",
                "published_at": published_at.isoformat() if published_at else "",
                "query": query or "top",
            }
        )
        if len(items) >= limit:
            break
    return items


TAVILY_SEARCH_ENDPOINT = "https://api.tavily.com/search"
DISCOVERY_FOCUS_CHOICES = ("ai-tech", "all")
DISCOVERY_QUERIES_ALL = ["", "热点", "科技", "AI", "财经", "就业", "教育"]
DISCOVERY_QUERIES_AI_TECH = ["AI", "人工智能", "大模型", "OpenAI", "Agent", "RAG", "芯片 算力", "互联网 平台"]
DISCOVERY_RSS_URLS_DEFAULT = [
    "https://hnrss.org/frontpage",
    "https://feed.infoq.com/",
    "https://export.arxiv.org/rss/cs.AI",
    "https://export.arxiv.org/rss/cs.LG",
    "https://export.arxiv.org/rss/cs.CL",
]


def discovery_rss_urls(extra: list[str] | None = None) -> list[str]:
    urls: list[str] = []
    # CLI-provided URLs should take priority.
    for raw in extra or []:
        value = (raw or "").strip()
        if value:
            urls.append(value)
    env_raw = (os.getenv("DISCOVERY_RSS_URLS") or "").strip()
    if env_raw:
        for part in env_raw.split(","):
            value = part.strip()
            if value:
                urls.append(value)
    urls.extend(DISCOVERY_RSS_URLS_DEFAULT)
    seen: set[str] = set()
    deduped: list[str] = []
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        deduped.append(url)
    return deduped


def rss_feed_label(feed_url: str) -> str:
    parsed = urllib.parse.urlparse(feed_url)
    domain = parsed.netloc.replace("www.", "").strip().lower()
    path = (parsed.path or "").strip()
    if domain == "hnrss.org":
        return "hn"
    if domain == "feed.infoq.com":
        return "infoq"
    if domain.endswith("arxiv.org") and path.startswith("/rss/"):
        return "arxiv " + path.removeprefix("/rss/").strip("/")
    if domain:
        return domain
    return feed_url.strip() or "rss"


def parse_atom_datetime(raw: str) -> datetime | None:
    value = (raw or "").strip()
    if not value:
        return None
    # Example: 2026-03-11T12:34:56Z
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_custom_rss_items(feed_url: str, window_hours: int, limit: int) -> list[dict[str, Any]]:
    label = rss_feed_label(feed_url)
    request = urllib.request.Request(feed_url, headers=HTTP_HEADERS)
    raw, headers = urlopen_with_retry(request, timeout=NETWORK_TIMEOUT, retries=NETWORK_RETRIES)
    xml_text = decode_response_body(raw, headers)
    root = ET.fromstring(xml_text)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    def text_of(elem: Any, tag: str) -> str:
        if elem is None:
            return ""
        for child in list(elem):
            if child is None:
                continue
            name = child.tag.split("}", 1)[-1].lower()
            if name == tag.lower():
                return (child.text or "").strip()
        return ""

    items: list[dict[str, Any]] = []
    root_name = root.tag.split("}", 1)[-1].lower()
    if root_name == "rss":
        channel = root.find("channel") or root.find("{*}channel")
        if channel is None:
            return []
        for item in channel.findall("item") or channel.findall("{*}item"):
            title = (item.findtext("title") or item.findtext("{*}title") or "").strip()
            link = (item.findtext("link") or item.findtext("{*}link") or "").strip()
            pub_raw = (item.findtext("pubDate") or item.findtext("{*}pubDate") or "").strip()
            published_at = parse_rss_datetime(pub_raw)
            if published_at and published_at < cutoff:
                continue
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "link": link,
                    "source": label,
                    "published_at": published_at.isoformat() if published_at else "",
                    "query": label,
                }
            )
            if len(items) >= limit:
                break
        return items

    if root_name == "feed":  # Atom
        for entry in root.findall("{*}entry"):
            title = (entry.findtext("{*}title") or "").strip()
            link = ""
            for link_elem in entry.findall("{*}link"):
                href = (link_elem.get("href") or "").strip()
                if href:
                    link = href
                    break
            published_raw = (entry.findtext("{*}updated") or entry.findtext("{*}published") or "").strip()
            published_at = parse_atom_datetime(published_raw)
            if published_at and published_at < cutoff:
                continue
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "link": link,
                    "source": label,
                    "published_at": published_at.isoformat() if published_at else "",
                    "query": label,
                }
            )
            if len(items) >= limit:
                break
        return items

    # Unknown format: try RSS-like fallback.
    for item in root.findall(".//item") + root.findall(".//{*}item"):
        title = (text_of(item, "title") or "").strip()
        link = (text_of(item, "link") or "").strip()
        if not title or not link:
            continue
        items.append({"title": title, "link": link, "source": label, "published_at": "", "query": label})
        if len(items) >= limit:
            break
    return items


def collect_custom_rss_items(rss_urls: list[str], window_hours: int, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    for feed_url in rss_urls:
        try:
            collected.extend(fetch_custom_rss_items(feed_url, window_hours, limit))
        except (SystemExit, Exception) as exc:
            errors.append(str(exc))
    return collected, errors


def tavily_api_key() -> str:
    return (os.getenv("TAVILY_API_KEY") or "").strip()


def normalize_discovery_provider(value: str | None) -> str:
    raw = (value or "auto").strip().lower()
    aliases = {
        "google": "google-news-rss",
        "google-news": "google-news-rss",
        "google_news_rss": "google-news-rss",
        "rss": "google-news-rss",
        "custom": "custom-rss",
        "custom_rss": "custom-rss",
        "custom-rss": "custom-rss",
        "rss-custom": "custom-rss",
        "tavily-api": "tavily",
    }
    normalized = aliases.get(raw, raw)
    return normalized if normalized in DISCOVERY_PROVIDER_CHOICES else "auto"


def normalize_discovery_focus(value: str | None) -> str:
    raw = (value or "ai-tech").strip().lower().replace("_", "-")
    aliases = {
        "ai": "ai-tech",
        "tech": "ai-tech",
        "ai/tech": "ai-tech",
        "ai-tech": "ai-tech",
        "all": "all",
        "full": "all",
    }
    normalized = aliases.get(raw, raw)
    return normalized if normalized in DISCOVERY_FOCUS_CHOICES else "ai-tech"


def tavily_query_text(query: str, window_hours: int) -> str:
    seed = (query or "").strip() or "今日热点"
    if seed in {"热点", "top"}:
        seed = "今日热点"
    return f"{seed} 新闻 热点 过去{window_hours}小时"


def fetch_tavily_news_items(query: str, window_hours: int, limit: int) -> list[dict[str, Any]]:
    api_key = tavily_api_key()
    if not api_key:
        raise SystemExit("未配置 TAVILY_API_KEY，无法使用 Tavily 热点发现。请先设置环境变量：TAVILY_API_KEY=tvly-***")
    payload = {
        "api_key": api_key,
        "query": tavily_query_text(query, window_hours),
        "search_depth": "advanced",
        "include_answer": False,
        "include_raw_content": False,
        "max_results": int(limit),
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        TAVILY_SEARCH_ENDPOINT,
        data=data,
        headers={**HTTP_HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    raw, headers = urlopen_with_retry(request, timeout=NETWORK_TIMEOUT, retries=NETWORK_RETRIES)
    text = decode_response_body(raw, headers)
    try:
        response = json.loads(text) if text else {}
    except json.JSONDecodeError as exc:
        raise SystemExit("Tavily 返回不是合法 JSON，无法解析热点发现结果。") from exc
    results = response.get("results") or []
    items: list[dict[str, Any]] = []
    for result in results:
        title = (result.get("title") or "").strip()
        link = (result.get("url") or result.get("link") or "").strip()
        if not title or not link:
            continue
        domain = urllib.parse.urlparse(link).netloc.strip()
        published_at = (result.get("published_date") or result.get("published_at") or result.get("date") or "").strip()
        items.append(
            {
                "title": title,
                "link": link,
                "source": domain or "Tavily",
                "published_at": published_at,
                "query": query or "top",
            }
        )
        if len(items) >= limit:
            break
    return items


def tavily_search_urls(query: str, max_results: int = 6) -> list[str]:
    api_key = tavily_api_key()
    if not api_key:
        return []
    payload = {
        "api_key": api_key,
        "query": (query or "").strip(),
        "search_depth": "advanced",
        "include_answer": False,
        "include_raw_content": False,
        "max_results": int(max_results),
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        TAVILY_SEARCH_ENDPOINT,
        data=data,
        headers={**HTTP_HEADERS, "Content-Type": "application/json"},
        method="POST",
    )
    raw, headers = urlopen_with_retry(request, timeout=NETWORK_TIMEOUT, retries=NETWORK_RETRIES)
    text = decode_response_body(raw, headers)
    try:
        response = json.loads(text) if text else {}
    except json.JSONDecodeError:
        return []
    results = response.get("results") or []
    urls: list[str] = []
    seen: set[str] = set()
    for result in results:
        url = (result.get("url") or result.get("link") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= int(max_results):
            break
    return urls


def classify_news_topic(title: str) -> dict[str, Any]:
    value = (title or "").strip()
    if re.search(
        r"AI|人工智能|大模型|模型|LLM|GPT|Claude|Gemini|DeepSeek|RAG|Agent|MCP|多模态|推理|训练|对齐|算力|芯片|GPU|CUDA|英伟达|NVIDIA|OpenAI|Anthropic|Google|Meta|xAI|机器人",
        value,
        flags=re.I,
    ):
        return {
            "topic_type": "科技/AI",
            "angles": ["这条新闻背后的行业信号是什么", "普通人/从业者会受到什么影响", "下一步产品与商业机会在哪里"],
            "viewpoints": ["不要只盯着发布本身，更要看背后能力边界有没有变化。", "热点的价值在于判断它会不会从新闻变成基础设施。"],
        }
    if re.search(
        r"开源|GitHub|API|SDK|云|Cloud|AWS|Azure|GCP|阿里云|腾讯云|华为云|字节|抖音|小红书|微博|微信|B站|淘宝|京东|拼多多|美团|滴滴|平台|互联网|App|iOS|Android|浏览器|Chrome|Edge|安全|漏洞|数据泄露|隐私|SaaS|数据库|Linux|Windows|macOS",
        value,
        flags=re.I,
    ):
        return {
            "topic_type": "科技/互联网",
            "angles": ["变化真正影响了谁、影响路径是什么", "这次更新/事件背后的平台规则或产品信号", "普通人/从业者该怎么调整自己的动作"],
            "viewpoints": ["平台和产品的变化，往往比新闻本身更值得解读。", "别只复述更新内容，关键是解释它改变了什么成本结构。"],
        }
    if re.search(r"股|融资|并购|财报|经济|关税|出口|消费|楼市|房价|就业|失业", value):
        return {
            "topic_type": "财经/职场",
            "angles": ["事件背后的底层变量是什么", "对普通人的资产/工作意味着什么", "哪些判断最容易被情绪带偏"],
            "viewpoints": ["财经热点更适合做‘判断框架’，而不是情绪复述。", "公众号文章要解释影响路径，而不是只重复涨跌结果。"],
        }
    if re.search(r"教育|学校|高考|考研|留学|老师|课程", value):
        return {
            "topic_type": "教育",
            "angles": ["政策/事件会改变哪些人的决策", "家长或学生真正该关注什么", "最容易踩的误区是什么"],
            "viewpoints": ["教育热点要少喊口号，多解释决策后果。", "真正有传播力的是‘怎么判断，怎么行动’。"],
        }
    if re.search(r"电影|综艺|明星|演唱会|游戏|社交平台|短视频|直播", value):
        return {
            "topic_type": "文娱/平台",
            "angles": ["为什么这件事能爆", "平台机制和用户情绪分别起了什么作用", "能沉淀出什么长期内容判断"],
            "viewpoints": ["流行事件适合写成‘爆红机制拆解’。", "不要只复盘热闹，要提炼可迁移的方法论。"],
        }
    return {
        "topic_type": "社会热点",
        "angles": ["这件事为什么现在值得关注", "真正影响普通人的点是什么", "如何避免只看表象不看结构"],
        "viewpoints": ["热点文章需要把新闻翻译成读者能执行的判断。", "好的选题不是复述事件，而是解释事件。"],
    }


def classify_discovery_content_kind(title: str) -> str:
    value = (title or "").strip()
    if re.search(r"教程|指南|入门|手把手|怎么|如何|实战|SOP|清单|模板|案例|Best Practice|最佳实践", value, flags=re.I):
        return "教程/工具"
    if re.search(r"发布|上线|更新|开源|推出|新增|版本|beta|preview|release|v\\d", value, flags=re.I):
        return "产品更新"
    if re.search(r"论文|arxiv|研究|paper|benchmark|评测", value, flags=re.I):
        return "研究/论文"
    if re.search(r"收购|融资|裁员|监管|诉讼|禁令|事故|故障|宕机|泄露|安全事件", value):
        return "事件解读"
    return "趋势观点"


def classify_discovery_source_tier(source_url: str) -> str:
    url = (source_url or "").strip()
    if not url:
        return "媒体"
    domain = urllib.parse.urlparse(url).netloc.replace("www.", "").strip().lower()
    if not domain:
        return "媒体"
    official = {
        "openai.com",
        "anthropic.com",
        "ai.google",
        "blog.google",
        "google.com",
        "deepmind.google",
        "microsoft.com",
        "azure.com",
        "meta.com",
        "nvidia.com",
        "apple.com",
        "aws.amazon.com",
        "huggingface.co",
        "pytorch.org",
        "tensorflow.org",
    }
    opensource = {"github.com", "gitlab.com", "bitbucket.org"}
    community = {"news.ycombinator.com", "hnrss.org"}
    if domain in opensource:
        return "开源"
    if domain in community:
        return "社区"
    if domain.endswith("arxiv.org"):
        return "媒体"
    if domain in official or domain.endswith((".openai.com", ".anthropic.com", ".microsoft.com", ".google.com")):
        return "官方"
    if domain.startswith("docs.") or ".docs." in domain:
        return "官方"
    return "媒体"


def evaluate_discovery_topic(title: str, audience: str = "大众读者") -> dict[str, Any]:
    variants = generate_hot_title_variants(title, angle="", audience=audience)
    ranked, selected = rank_title_candidates(variants, title, audience, angle="", selected_title="")
    best = selected or {}
    return {
        "recommended_title": best.get("title") or title,
        "recommended_title_score": int(best.get("title_score") or 0),
        "recommended_title_gate_passed": bool(best.get("title_gate_passed", False)),
        "recommended_title_score_breakdown": best.get("title_score_breakdown") or [],
        "recommended_title_threshold": int(best.get("title_score_threshold") or TITLE_SCORE_THRESHOLD),
    }


def build_topic_candidates_from_news(items: list[dict[str, Any]], limit: int, audience: str = "大众读者") -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    hit_queries: dict[str, set[str]] = {}
    for item in items:
        title = (item.get("title") or "").strip()
        normalized = re.sub(r"\s+", "", title)
        if not title or not normalized:
            continue
        query = (item.get("query") or "").strip() or "top"
        hit_queries.setdefault(normalized, set()).add(query)
    for item in items:
        title = (item.get("title") or "").strip()
        normalized = re.sub(r"\s+", "", title)
        if not title or normalized in seen:
            continue
        seen.add(normalized)
        classification = classify_news_topic(title)
        evaluation = evaluate_discovery_topic(title, audience=audience)
        hit_count = len(hit_queries.get(normalized) or set()) or 1
        content_kind = classify_discovery_content_kind(title)
        source_url = (item.get("link") or "").strip()
        source_tier = classify_discovery_source_tier(source_url)
        query_label = (item.get("query") or "").strip() or "top"
        why_now = f"该话题出现在最近 {query_label} 的新闻流中，具备时效与讨论度。"
        if hit_count >= 2:
            why_now = f"该话题在多个关键词新闻流中重复出现（{hit_count} 个流），具备更高讨论度与时效。"
        candidates.append(
            {
                "hot_title": title,
                "source": item.get("source", ""),
                "published_at": item.get("published_at", ""),
                "source_url": source_url,
                "query": item.get("query", ""),
                "hit_count": hit_count,
                "content_kind": content_kind,
                "source_tier": source_tier,
                "topic_type": classification["topic_type"],
                "recommended_topic": title,
                **evaluation,
                "angles": classification["angles"],
                "viewpoints": classification["viewpoints"],
                "why_now": why_now,
            }
        )
        if len(candidates) >= limit:
            break
    return candidates


def collect_google_news_items(queries: list[str], window_hours: int, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    for query in queries:
        try:
            collected.extend(fetch_google_news_items(query, window_hours, limit))
        except (SystemExit, Exception) as exc:
            errors.append(str(exc))
    return collected, errors


def collect_tavily_news_items(queries: list[str], window_hours: int, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    collected: list[dict[str, Any]] = []
    errors: list[str] = []
    for query in queries:
        try:
            collected.extend(fetch_tavily_news_items(query, window_hours, limit))
        except (SystemExit, Exception) as exc:
            errors.append(str(exc))
    return collected, errors


def discover_recent_topics(
    window_hours: int = 24,
    limit: int = DISCOVERY_TOPIC_LIMIT,
    provider: str | None = None,
    focus: str | None = None,
    rss_urls: list[str] | None = None,
) -> dict[str, Any]:
    chosen = normalize_discovery_provider(provider)
    chosen_focus = normalize_discovery_focus(focus)
    queries = list(DISCOVERY_QUERIES_AI_TECH if chosen_focus == "ai-tech" else DISCOVERY_QUERIES_ALL)
    feeds = discovery_rss_urls(rss_urls)
    candidate_seed_limit = max(int(limit) * 4, int(limit))

    def finalize(collected: list[dict[str, Any]], used_provider: str) -> dict[str, Any]:
        collected.sort(key=lambda item: item.get("published_at", ""), reverse=True)
        candidates = build_topic_candidates_from_news(collected, candidate_seed_limit, audience="大众读者")
        if chosen_focus == "ai-tech":
            candidates = [item for item in candidates if item.get("topic_type") in {"科技/AI", "科技/互联网"}]

        def tutorial_boost(item: dict[str, Any]) -> int:
            kind = str(item.get("content_kind") or "").strip()
            return 1 if kind in {"教程/工具", "产品更新"} else 0

        if chosen_focus == "ai-tech":
            candidates.sort(
                key=lambda item: (
                    bool(item.get("recommended_title_gate_passed", False)),
                    tutorial_boost(item),
                    int(item.get("hit_count") or 0),
                    int(item.get("recommended_title_score") or 0),
                    item.get("published_at", ""),
                ),
                reverse=True,
            )
        else:
            candidates.sort(
                key=lambda item: (
                    bool(item.get("recommended_title_gate_passed", False)),
                    int(item.get("hit_count") or 0),
                    int(item.get("recommended_title_score") or 0),
                    item.get("published_at", ""),
                ),
                reverse=True,
            )
        return {
            "provider": used_provider,
            "focus": chosen_focus,
            "window_hours": window_hours,
            "generated_at": now_iso(),
            "sources": collected[:candidate_seed_limit * 2],
            "candidates": candidates[: int(limit)],
        }

    if chosen == "google-news-rss":
        collected, errors = collect_google_news_items(queries, window_hours, DISCOVERY_FEED_LIMIT)
        if not collected:
            message = "Google News RSS 不可用或返回为空。"
            if errors:
                message += f" 诊断信息：{errors[0]}"
            raise SystemExit(message + "（可能是网络不可达或被封锁）")
        payload = finalize(collected, "google-news-rss")
        if not payload.get("candidates"):
            raise SystemExit("Google News RSS 返回为空，未能构建任何可写选题。")
        return payload

    if chosen == "custom-rss":
        collected, errors = collect_custom_rss_items(feeds, window_hours, DISCOVERY_FEED_LIMIT)
        if not collected:
            message = "Custom RSS 不可用或返回为空。"
            if errors:
                message += f" 诊断信息：{errors[0]}"
            raise SystemExit(message + "（可通过 --rss-url 或环境变量 DISCOVERY_RSS_URLS 配置源）")
        payload = finalize(collected, "custom-rss")
        if not payload.get("candidates"):
            raise SystemExit("Custom RSS 返回为空，未能构建任何可写选题。")
        return payload

    if chosen == "tavily":
        if not tavily_api_key():
            raise SystemExit("未配置 TAVILY_API_KEY，无法使用 Tavily 热点发现。请先设置环境变量：TAVILY_API_KEY=tvly-***")
        collected, _ = collect_tavily_news_items(queries, window_hours, DISCOVERY_FEED_LIMIT)
        if not collected:
            raise SystemExit("Tavily 热点发现返回为空，未能构建任何可写选题。")
        payload = finalize(collected, "tavily")
        if not payload.get("candidates"):
            raise SystemExit("Tavily 热点发现返回为空，未能构建任何可写选题。")
        return payload

    # auto
    rss_collected, rss_errors = collect_google_news_items(queries, window_hours, DISCOVERY_FEED_LIMIT)
    rss_payload = finalize(rss_collected, "google-news-rss") if rss_collected else {"candidates": []}
    if rss_payload.get("candidates"):
        return rss_payload
    custom_collected, custom_errors = collect_custom_rss_items(feeds, window_hours, DISCOVERY_FEED_LIMIT)
    custom_payload = finalize(custom_collected, "custom-rss") if custom_collected else {"candidates": []}
    if custom_payload.get("candidates"):
        return custom_payload
    if tavily_api_key():
        tav_collected, tav_errors = collect_tavily_news_items(queries, window_hours, DISCOVERY_FEED_LIMIT)
        tav_payload = finalize(tav_collected, "tavily") if tav_collected else {"candidates": []}
        if tav_payload.get("candidates"):
            return tav_payload
        diagnostic = ""
        if rss_errors:
            diagnostic = f" RSS 错误示例：{rss_errors[0]}"
        if custom_errors:
            diagnostic += f" Custom RSS 错误示例：{custom_errors[0]}"
        if tav_errors:
            diagnostic += f" Tavily 错误示例：{tav_errors[0]}"
        raise SystemExit("热点发现失败：RSS 无结果，Custom RSS 也无结果，Tavily 也无结果。" + diagnostic)
    diagnostic = f" RSS 错误示例：{rss_errors[0]}" if rss_errors else ""
    if custom_errors:
        diagnostic += f" Custom RSS 错误示例：{custom_errors[0]}"
    raise SystemExit("热点发现失败：RSS 无结果，Custom RSS 也无结果，且未配置 TAVILY_API_KEY。" + diagnostic)
    return {
        "window_hours": window_hours,
        "generated_at": now_iso(),
        "sources": collected[:limit * 2],
        "candidates": candidates,
    }


def extract_page_title(raw: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.I | re.S)
    if not match:
        return ""
    title = html.unescape(match.group(1))
    return re.sub(r"\s+", " ", title).strip()


def html_to_text(raw: str) -> str:
    main_match = re.search(r"(?is)<main[^>]*>(.*?)</main>", raw)
    article_match = re.search(r"(?is)<article[^>]*>(.*?)</article>", raw)
    content = main_match.group(1) if main_match else article_match.group(1) if article_match else raw
    content = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", content)
    content = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", content)
    content = re.sub(r"(?is)<!--.*?-->", " ", content)
    content = re.sub(r"(?i)<br\s*/?>", "\n", content)
    content = re.sub(r"(?i)</(p|div|li|section|article|h1|h2|h3|h4|h5|h6)>", "\n", content)
    content = re.sub(r"(?s)<[^>]+>", " ", content)
    content = html.unescape(content)
    content = re.sub(r"[ 	 ]+", " ", content)
    content = re.sub(r"\n{2,}", "\n", content)
    return content.strip()


def extract_keywords_for_evidence(title: str, body: str) -> list[str]:
    seed = " ".join([title, *[item["text"] for item in extract_headings(body)[:6]]])
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}|[一-鿿]{2,8}", seed)
    keywords: list[str] = []
    for token in tokens:
        lower = token.lower()
        if lower in EVIDENCE_STOPWORDS or token in EVIDENCE_STOPWORDS:
            continue
        if token not in keywords:
            keywords.append(token)
    return keywords[:12]


def split_evidence_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[。！？!?；;])", normalized)
    sentences = []
    for part in parts:
        sentence = part.strip()
        length = cjk_len(sentence)
        if not 18 <= length <= 140:
            continue
        if any(noise.lower() in sentence.lower() for noise in EVIDENCE_NOISE_PHRASES):
            continue
        if sentence.count("|") >= 1:
            continue
        sentences.append(sentence)
    return sentences



def score_evidence_sentence(sentence: str, keywords: list[str]) -> float:
    score = 0.0
    for keyword in keywords:
        if keyword.lower() in sentence.lower():
            score += 2.0 if len(keyword) >= 3 else 1.0
    if re.search(r"\d{4}年|\d+(?:\.\d+)?%|\d+(?:\.\d+)?(?:万|亿|倍|个|项|次)", sentence):
        score += 2.5
    if any(word in sentence for word in ["据", "显示", "研究", "报告", "according", "survey", "report", "study"]):
        score += 1.5
    if any(mark in sentence for mark in ["：", ":", "（", "("]):
        score += 0.5
    return score



def collect_online_evidence(title: str, body: str, source_urls: list[str], workspace: Path, max_items: int = 4) -> dict[str, Any]:
    evidence_items: list[dict[str, Any]] = []
    source_reports: list[dict[str, Any]] = []
    keywords = extract_keywords_for_evidence(title, body)
    for url in source_urls[:5]:
        report = {"url": url, "page_title": "", "ok": False, "selected_sentences": [], "error": None}
        try:
            raw, content_type = fetch_text_from_url(url)
            page_title = extract_page_title(raw)
            text = html_to_text(raw) if "html" in content_type.lower() or "<html" in raw.lower() else raw
            sentences = split_evidence_sentences(text)
            scored = []
            for sentence in sentences:
                score = score_evidence_sentence(sentence, keywords)
                if score >= 2:
                    scored.append({"sentence": sentence, "score": score})
            scored.sort(key=lambda item: item["score"], reverse=True)
            selected = scored[:2]
            report["ok"] = True
            report["page_title"] = page_title or url
            report["selected_sentences"] = [item["sentence"] for item in selected]
            for item in selected:
                evidence_items.append(
                    {
                        "url": url,
                        "page_title": report["page_title"],
                        "sentence": item["sentence"],
                        "score": item["score"],
                    }
                )
        except Exception as exc:
            report["error"] = str(exc)
        source_reports.append(report)
    evidence_items.sort(key=lambda item: item["score"], reverse=True)
    result = {
        "title": title,
        "keywords": keywords,
        "items": evidence_items[:max_items],
        "sources": source_reports,
        "generated_at": now_iso(),
    }
    write_json(workspace / "evidence-report.json", result)
    return result


def extract_headings(body: str) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    for index, line in enumerate(body.splitlines()):
        match = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if match:
            headings.append({"line": index, "level": len(match.group(1)), "text": match.group(2).strip()})
    return headings


def list_paragraphs(body: str) -> list[str]:
    body = IMAGE_DIRECTIVE_RE.sub("\n", body)
    blocks = [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]
    return [block for block in blocks if not block.startswith("#")]


def cjk_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def count_occurrences(text: str, words: Iterable[str]) -> int:
    return sum(text.count(word) for word in words)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def intro_text(body: str) -> str:
    paragraphs = []
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        if block.startswith("##"):
            break
        if block.startswith("#"):
            continue
        paragraphs.append(block)
        if len(paragraphs) >= 3:
            break
    return "\n\n".join(paragraphs)


def sentence_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])", text)
    return [part.strip() for part in parts if part.strip()]


def extract_candidate_quotes(body: str) -> list[str]:
    candidates: list[str] = []
    clean_body = re.sub(r"^#{1,6}\s+", "", body, flags=re.M)
    for sentence in sentence_split(clean_body):
        sentence = re.sub(r"\s+", " ", sentence).strip()
        length = cjk_len(sentence)
        if length < 12 or length > 42:
            continue
        if count_occurrences(sentence, GOLDEN_QUOTE_WORDS) == 0:
            continue
        if sentence not in candidates:
            candidates.append(sentence)
    return candidates[:6]


def title_score(title: str) -> tuple[int, str]:
    score = 2
    length = cjk_len(title)
    if 10 <= length <= 28:
        score += 2
    if any(word in title for word in TITLE_POWER_WORDS):
        score += 2
    if re.search(r"[0-9一二三四五六七八九十]", title):
        score += 1
    if any(mark in title for mark in ["？", "?", "：", ":"]):
        score += 1
    return min(score, 8), "标题越具体、越有利益点、越有反差，越接近高分。"


def title_dimension_score(title: str, audience: str = "", angle: str = "") -> dict[str, Any]:
    from core.title_decision import evaluate_title_open_rate

    value = (title or "").strip()
    report = evaluate_title_open_rate(
        value,
        topic=value,
        audience=audience,
        angle=angle,
        candidate={},
        research={},
        recent_titles=[],
        recent_patterns=[],
        account_strategy={},
    )
    return {
        "title": value,
        "total_score": report.get("title_open_rate_score", 0),
        "threshold": TITLE_SCORE_THRESHOLD,
        "passed": bool(report.get("title_gate_passed")),
        "score_breakdown": report.get("score_breakdown") or [],
    }


def rank_title_candidates(
    titles: list[dict[str, Any]],
    topic: str,
    audience: str,
    angle: str,
    selected_title: str = "",
    recent_titles: list[str] | None = None,
    recent_title_patterns: list[str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    from core.title_decision import build_title_decision_report

    recent_summary = {"overused_title_patterns": [{"key": key, "count": 8} for key in (recent_title_patterns or [])]}
    payload = build_title_decision_report(
        topic=topic,
        audience=audience,
        angle=angle,
        candidates=list(titles or []),
        manifest={"recent_article_titles": recent_titles or [], "recent_corpus_summary": recent_summary},
        research={},
        editorial_blueprint={},
        selected_title=selected_title,
        account_strategy={},
    )
    ranked = list(payload.get("candidates") or [])
    return ranked, ranked[0] if ranked else None


def generate_hot_title_variants(topic: str, angle: str = "", audience: str = "") -> list[dict[str, str]]:
    classification = classify_news_topic(topic)
    content_kind = classify_discovery_content_kind(topic)
    style_key = "signal-briefing"
    if content_kind == "教程/工具":
        style_key = "practical-playbook"
    elif content_kind == "研究/论文":
        style_key = "case-memo"
    elif classification.get("topic_type") == "文娱/平台":
        style_key = "field-observation"
    blueprint = {
        "style_key": style_key,
        "style_label": (EDITORIAL_STYLE_LIBRARY.get(style_key) or {}).get("style_label", style_key),
    }
    blocked_patterns = {
        "overused_title_patterns": [
            {"key": "why-think-clear", "count": 99},
            {"key": "danger-not-but", "count": 99},
            {"key": "not-but", "count": 99},
        ]
    }
    return generate_diverse_title_variants(
        topic,
        angle,
        audience,
        editorial_blueprint=blueprint,
        recent_titles=[],
        recent_corpus_summary=blocked_patterns,
        count=10,
        boost_round=1,
    )


def intro_score(title: str, intro: str) -> tuple[int, str]:
    score = 2
    length = cjk_len(intro)
    if 70 <= length <= 260:
        score += 3
    hook_hits = count_occurrences(intro, HOOK_WORDS)
    score += min(4, hook_hits)
    if any(word in intro for word in ["你", "我们", "很多人", "普通人", "读者"]):
        score += 1
    if title and any(word in intro for word in [title[:6], title[-6:]] if word.strip()):
        score += 1
    if any(word in intro for word in ["故事", "场景", "冲突", "问题", "结果", "消息", "细节", "那一刻", "刷到"]):
        score += 1
    if "?" in intro or "？" in intro:
        score += 1
    return min(score, 12), "前 2~4 段应快速建立代入感、反差、问题或结果期待，但不等于统一用一句话结论开场。"


def hook_score(title: str, intro: str, headings: list[dict[str, Any]]) -> tuple[int, str]:
    score = 2
    score += min(4, count_occurrences(title + intro, HOOK_WORDS))
    heading_text = " ".join(item["text"] for item in headings)
    score += min(2, count_occurrences(heading_text, HOOK_WORDS))
    if any(mark in intro for mark in ["?", "？"]):
        score += 1
    if any(phrase in intro for phrase in ["结果是", "但真正", "你可能", "那一刻", "刷到", "看到"]):
        score += 1
    return min(score, 10), "钩子需要贯穿标题、导语和小标题，但不该收敛成固定句式模板。"


def quote_score(body: str) -> tuple[int, str, list[str]]:
    quotes = extract_candidate_quotes(body)
    score = min(10, len(quotes) * 3 + (1 if count_occurrences(body, ["“", "”", "**"]) else 0))
    return score, "金句应具备可截图、可转述、可单独传播的密度。", quotes


def count_ai_style_hits(body: str) -> int:
    value = body or ""
    hits = 0
    for phrase in AI_STYLE_PHRASES:
        hits += value.count(phrase)
    hits += len(re.findall(r"(?:^|[。！？!?]\s*|\n\s*)(首先|其次|最后)(?:[，,:：\s])", value))
    return hits


def style_score(body: str) -> tuple[int, str]:
    score = 8
    penalty = min(5, count_ai_style_hits(body))
    score -= penalty
    sentence_lengths = [cjk_len(sentence) for sentence in sentence_split(body)]
    if sentence_lengths:
        variance = max(sentence_lengths) - min(sentence_lengths)
        if variance >= 12:
            score += 1
    if any(word in body for word in ["你", "我们", "他们"]):
        score += 1
    return int(clamp(score, 0, 10)), "避免模板化 AI 腔，保持统一、自然、有态度的表达。"


def structure_score(body: str, headings: list[dict[str, Any]]) -> tuple[int, str]:
    paragraphs = list_paragraphs(body)
    score = 3
    if 3 <= len(headings) <= 10:
        score += 4
    if len(paragraphs) >= 6:
        score += 2
    if re.search(r"(^|\n)-\s+", body, flags=re.M) or re.search(r"(^|\n)1\.\s+", body, flags=re.M):
        score += 1
    return min(score, 10), "结构高分稿通常具备稳定层次、节奏切换与明确的小结。"


def depth_score(body: str) -> tuple[int, str]:
    score = 4
    score += min(5, count_occurrences(body, DEPTH_WORDS))
    score += min(3, len(re.findall(r"\d+(?:\.\d+)?%?", body)))
    if any(word in body for word in ["案例", "比如", "例如", "实操"]):
        score += 2
    if any(word in body for word in ["为什么", "因为", "所以", "本质"]):
        score += 1
    return min(score, 15), "深度来自分析、对比、案例和方法，而不是空泛总结。"


def credibility_score(body: str, source_urls: list[str]) -> tuple[int, str]:
    score = min(4, len(source_urls) * 2)
    score += min(3, len(re.findall(r"https?://", body)))
    if re.search(r"\d{4}年|\d+%|\d+倍|第\d+", body):
        score += 1
    return min(score, 8), "事实型内容应给出来源、数据或可追溯信息。"


def readability_score(body: str, headings: list[dict[str, Any]]) -> tuple[int, str]:
    paragraphs = list_paragraphs(body)
    lengths = [cjk_len(paragraph) for paragraph in paragraphs] or [0]
    avg = sum(lengths) / max(1, len(lengths))
    score = 3
    if 35 <= avg <= 140:
        score += 2
    if headings:
        score += 1
    if re.search(r"(^|\n)>\s+", body, flags=re.M) or re.search(r"\*\*.+?\*\*", body):
        score += 1
    return min(score, 7), "移动端阅读更依赖短段落、分节、重点加粗和留白。"


def emotion_score(body: str) -> tuple[int, str]:
    extra_markers = ["刺痛", "后背一紧", "拧干", "拖垮", "被理解", "轻松感", "不是不会", "不是你不行"]
    score = min(5, 1 + count_occurrences(body, EMOTION_WORDS + extra_markers))
    return score, "情绪并非煽情，而是让读者感到‘这说的就是我’。"


def share_score(body: str, quotes: list[str]) -> tuple[int, str]:
    score = min(3, count_occurrences(body, SHARE_WORDS))
    if len(quotes) >= 2:
        score += 1
    if re.search(r"(^|\n)1\.\s+", body, flags=re.M) and re.search(r"教程|指南|步骤|如何|怎么|清单", body):
        score += 1
    return min(score, 5), "能被收藏或转发的内容，既可能因为观点有复述价值，也可能因为它真的有用；不等于一律上清单。"


def build_breakdown(title: str, body: str, headings: list[dict[str, Any]], source_urls: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    intro = intro_text(body)
    title_value, title_note = title_score(title)
    intro_value, intro_note = intro_score(title, intro)
    hook_value, hook_note = hook_score(title, intro, headings)
    quote_value, quote_note, quotes = quote_score(body)
    style_value, style_note = style_score(body)
    structure_value, structure_note = structure_score(body, headings)
    depth_value, depth_note = depth_score(body)
    credibility_value, credibility_note = credibility_score(body, source_urls)
    readability_value, readability_note = readability_score(body, headings)
    emotion_value, emotion_note = emotion_score(body)
    share_value, share_note = share_score(body, quotes)
    breakdown = [
        {"dimension": "标题传播力", "weight": 8, "score": title_value, "note": title_note},
        {"dimension": "开头吸引力", "weight": 12, "score": intro_value, "note": intro_note},
        {"dimension": "钩子设计", "weight": 10, "score": hook_value, "note": hook_note},
        {"dimension": "金句质量", "weight": 10, "score": quote_value, "note": quote_note},
        {"dimension": "文风适配度", "weight": 10, "score": style_value, "note": style_note},
        {"dimension": "结构清晰度", "weight": 10, "score": structure_value, "note": structure_note},
        {"dimension": "内容深度", "weight": 15, "score": depth_value, "note": depth_note},
        {"dimension": "可信度与检索支撑", "weight": 8, "score": credibility_value, "note": credibility_note},
        {"dimension": "可读性与节奏", "weight": 7, "score": readability_value, "note": readability_note},
        {"dimension": "情绪共鸣", "weight": 5, "score": emotion_value, "note": emotion_note},
        {"dimension": "收藏/转发潜力", "weight": 5, "score": share_value, "note": share_note},
    ]
    return breakdown, quotes

def strongest_and_weakest(breakdown: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    strengths = []
    weaknesses = []
    for item in breakdown:
        ratio = item["score"] / max(1, item["weight"])
        if ratio >= 0.8:
            strengths.append(f"{item['dimension']}表现较强：{item['note']}")
        elif ratio < 0.6:
            weaknesses.append(f"{item['dimension']}偏弱：{item['note']}")
    return strengths[:4], weaknesses[:4]


def rewrite_actions(breakdown: list[dict[str, Any]], title: str, body: str) -> tuple[list[str], dict[str, Any]]:
    needs = []
    by_name = {item["dimension"]: item for item in breakdown}
    if by_name["开头吸引力"]["score"] < 9:
        needs.append("重写前 300 字，优先加入反差、问题、结果前置或故事切口。")
    if by_name["钩子设计"]["score"] < 8:
        needs.append("在标题、导语和至少 2 个小标题里补强悬念、反常识或问题钩子。")
    if by_name["金句质量"]["score"] < 8:
        needs.append("补充 2~3 句可以单独截图传播的结论句、升维句或对比句。")
    if by_name["文风适配度"]["score"] < 8:
        needs.append("统一语气和视角，减少‘首先/其次/最后/综上所述’等模板化表达。")
    if by_name["可信度与检索支撑"]["score"] < 5:
        needs.append("补充来源、数据或案例出处，并在正文相关段落中自然融入可核验表述。")
    topic_hint = extract_summary(title + " " + body, 28)
    suggestions = {
        "opening_directions": [
            f"从一个与 {topic_hint} 直接相关的具体场景切入，而不是直接下总结。",
            "先立住反差或误判，再把判断慢一点抛出来。",
            "如果题材允许，可以从最近发生的一条消息、一个细节或一个真实处境开场。",
        ],
        "ending_directions": [
            "分析稿优先用判断或余味收束，不要默认上动作清单。",
            "教程稿才考虑动作化结尾，而且动作要少、真、能开始。",
            "结尾更适合回扣全文真正的分水岭，而不是重复目录。",
        ],
        "sample_gold_quotes": [
            f"{topic_hint} 真正难的，从来不是知道更多，而是你愿不愿意重新校准自己的判断。",
            "一篇有说服力的文章，真正值钱的不是信息量，而是它替读者省掉了多少误判。",
            "当别人只盯着表面的热闹时，真正拉开差距的那条线，往往已经悄悄开始移动了。",
        ],
        "style_adjustments": [
            "减少模板句，优先用场景、细节、对比和判断推进。",
            "不同小节换不同进入方式，别每节都用同一种句式起手。",
            "保留态度，但别把判断喊成口号。",
        ],
    }
    return needs[:5], suggestions


def markdown_report(report: dict[str, Any]) -> str:
    from core.viral import markdown_score_report

    return markdown_score_report(report)


def build_score_report(
    title: str,
    body: str,
    manifest: dict[str, Any],
    threshold: int,
    review: dict[str, Any] | None = None,
    revision_rounds: list[dict[str, Any]] | None = None,
    stop_reason: str = "",
) -> dict[str, Any]:
    from core.viral import build_score_report as build_viral_score_report

    return build_viral_score_report(
        title=title,
        body=body,
        manifest=manifest,
        threshold=threshold,
        review=review,
        revision_rounds=revision_rounds,
        stop_reason=stop_reason,
    )


def split_sections(body: str) -> tuple[list[str], list[dict[str, Any]]]:
    intro_lines: list[str] = []
    sections: list[dict[str, Any]] = []
    current_heading: dict[str, Any] | None = None
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_heading, current_lines, intro_lines
        content = "\n".join(current_lines).strip()
        if current_heading is None:
            intro_lines = content.splitlines() if content else []
        else:
            sections.append({**current_heading, "body": content})
        current_lines = []

    for line in body.splitlines():
        match = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if match:
            flush_current()
            current_heading = {"level": len(match.group(1)), "heading": match.group(2).strip()}
            continue
        current_lines.append(line)
    flush_current()
    intro_blocks = [block.strip() for block in re.split(r"\n\s*\n", "\n".join(intro_lines)) if block.strip()]
    normalized_sections = []
    for section in sections:
        blocks = [block.strip() for block in re.split(r"\n\s*\n", section["body"]) if block.strip()]
        normalized_sections.append({**section, "blocks": blocks})
    return intro_blocks, normalized_sections


def cleanup_rewrite_text(text: str) -> str:
    replacements = {
        r"^首先[，,：:]?": "先看最关键的一点，",
        r"^其次[，,：:]?": "再往下看，",
        r"^最后[，,：:]?": "最后要提醒的是，",
        r"^在本文中[，,：:]?": "",
        r"^本文将[，,：:]?": "这篇文章会",
        r"^这篇文章将[，,：:]?": "这篇文章会",
        r"^我们将[，,：:]?": "下面我会",
        r"^下面我们将[，,：:]?": "下面我会",
        r"^接下来[，,：:]?": "下面",
        r"综上所述": "说到底",
        r"总而言之": "说到底",
        r"总的来说": "说到底",
        r"归根结底": "说到底",
        r"简而言之": "更关键的是，",
        r"值得注意的是": "更关键的是",
        r"需要指出的是": "先把话说清楚，",
        r"不可否认": "先别急着反驳，",
        r"显而易见": "很直观，",
        r"不难发现": "你会发现",
        r"由此可见": "这也说明",
        r"换句话说": "说得更直白点",
        r"从某种意义上说": "更准确地说",
        r"值得一提的是": "顺带一提",
        r"与此同时": "同时",
        r"在当今社会": "放在今天的环境里",
    }
    cleaned = text.strip()
    for pattern, replacement in replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def cleanup_rewrite_markdown(body: str) -> str:
    blocks = [block.strip() for block in re.split(r"\n\s*\n", body or "") if block and block.strip()]
    cleaned_blocks: list[str] = []
    leak_markers = (
        "这类题目最怕的",
        "围绕“这个主题”",
        "围绕这个主题",
        "更值得展开的是",
        "先把主判断立住",
        "先给一个可代入的处境",
        "先把比较对象和判断方向亮出来",
        "正文由宿主 agent",
        "editorial_blueprint",
        "viral_blueprint",
    )
    for block in blocks:
        # Avoid breaking markdown structure.
        if re.match(r"^#{1,6}\s+", block):
            cleaned_blocks.append(block)
            continue
        if block.startswith(("```", ">")):
            cleaned_blocks.append(block)
            continue
        if re.match(r"^[-*]\s+", block) or re.match(r"^\d+\.\s+", block):
            cleaned_blocks.append(block)
            continue
        if any(marker in block for marker in leak_markers):
            continue
        cleaned_blocks.append(cleanup_rewrite_text(block))
    return ("\n\n".join(cleaned_blocks).strip() + "\n") if cleaned_blocks else ""


def make_section_opener(heading: str, first_block: str, title: str) -> str:
    focus = extract_summary(first_block or heading or title, 24)
    if "为什么" in heading:
        return f"{focus} 看起来像一个表面问题，但真正让人反复卡住的，往往是更底层的判断没有被说透。"
    if any(word in heading for word in ["三件事", "方法", "怎么", "如何"]):
        return f"真正有效的做法，不是把动作做多，而是先把最关键的顺序理清。围绕“{heading}”，这节更想讲清楚的是哪一步最不能做反。"
    return f"如果只从表面理解“{heading}”，很容易把力气花错地方。{focus}，才是这一部分真正想说明的问题。"


def build_rewritten_intro(title: str, intro_blocks: list[str], suggestions: dict[str, Any], manifest: dict[str, Any], sections: list[dict[str, Any]], low_dims: list[str]) -> list[str]:
    audience = manifest.get("audience") or "公众号读者"
    direction = manifest.get("direction") or "这个主题"
    first_heading = sections[0]["heading"] if sections else title
    opening_directions = list(suggestions.get("opening_directions") or [])
    lead = intro_blocks[0] if intro_blocks else ""
    hook = ""
    if lead:
        hook = cleanup_rewrite_text(lead)
    if not hook:
        hook = f"很多人谈 {direction} 时，往往只盯着最热闹的那层变化，但真正决定结果的，常常是那条更慢、也更难被看见的线。"
    paragraphs = [hook]
    if "情绪共鸣" in low_dims:
        paragraphs.append("如果你也在被新工具推着跑、却又隐约担心自己会被替代，这种焦虑并不丢人，它恰恰说明你开始认真看待自己的长期价值了。")
    if len(intro_blocks) > 1:
        tail = cleanup_rewrite_text(intro_blocks[1])
        if tail and tail not in paragraphs[-1]:
            paragraphs.append(tail)
    else:
        if opening_directions:
            paragraphs.append(f"真正值得往下读的，不是再重复一遍结论，而是把“{opening_directions[0]}”这层现实处境写实。")
        else:
            paragraphs.append(f"如果这件事和 {audience} 的日常判断有关，那最该拆开的，不是表面热闹，而是“{first_heading}”背后的现实后果。")
    return paragraphs[:4]


def build_closing_section(title: str, body: str, sections: list[dict[str, Any]]) -> tuple[str, list[str], bool]:
    tutorial_like = bool(re.search(r"教程|指南|步骤|怎么|如何|SOP|清单|模板|方法", f"{title}\n{body}"))
    if tutorial_like:
        bullets = []
        for section in sections[:3]:
            bullets.append(f"先回到“{section['heading']}”，只挑一个最容易开始的动作，今天先做一次，不要贪多。")
        if not bullets:
            bullets = [
                "先把这篇文章里最关键的一步写下来。",
                "只做一次最小动作，确认自己真的能开始。",
                "回头再补优化，而不是一开始就求完整。",
            ]
        return "如果你现在就要开始动手", bullets, True
    focus = extract_summary(title, 22)
    paragraphs = [
        f"{focus} 真正难的，从来不是知道更多，而是你愿不愿意把旧判断放下，重新看一遍那些被你忽略的细节。",
        "很多稿子喜欢在结尾甩出一张清单，好像这样就更有用。但真正会被读者带走的，往往是一句更稳的判断，或者一个以后看问题的角度。",
    ]
    return "最后想提醒的一点", paragraphs, False


def build_reference_section(manifest: dict[str, Any], evidence_report: dict[str, Any]) -> tuple[str, list[str]]:
    lines: list[str] = []
    seen: set[str] = set()
    for item in (evidence_report or {}).get("items") or []:
        url = (item.get("url") or "").strip()
        if not url or url in seen:
            continue
        title = (item.get("page_title") or urllib.parse.urlparse(url).netloc.replace("www.", "") or "参考来源").strip()
        lines.append(f"{title}：{url}")
        seen.add(url)
    for url in manifest.get("source_urls") or []:
        normalized = (url or "").strip()
        if not normalized or normalized in seen:
            continue
        domain = urllib.parse.urlparse(normalized).netloc.replace("www.", "") or normalized
        lines.append(f"{domain}：{normalized}")
        seen.add(normalized)
    if not lines:
        lines = [
            "补充 2~3 个可以公开验证的来源链接。",
            "优先使用官方发布、文档、研究或权威媒体来源。",
        ]
    return "参考来源", lines


REFERENCE_SECTION_TITLES = {
    "参考来源",
    "参考资料",
    "参考与延伸",
    "参考与延伸阅读",
    "资料来源",
    "延伸阅读",
}


def normalize_reference_heading(text: str) -> str:
    value = re.sub(r"[：:（）()\-—_\s]+", "", text or "")
    return value.strip()


def is_reference_heading(text: str) -> bool:
    normalized = normalize_reference_heading(text)
    return any(normalized == normalize_reference_heading(title) for title in REFERENCE_SECTION_TITLES)


def extract_urls_from_text(text: str) -> list[str]:
    return re.findall(r"https?://[^\s)`>]+", text)


def reconstruct_body(intro_blocks: list[str], sections: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    parts.extend(block for block in intro_blocks if block.strip())
    for section in sections:
        parts.append(f"{'#' * section.get('level', 2)} {section.get('heading', '')}".strip())
        parts.extend(block for block in section.get("blocks") or [] if block.strip())
    return "\n\n".join(part.strip() for part in parts if part and part.strip()) + "\n"


def normalize_image_type_label(raw: str) -> str:
    key = (raw or "").strip().lower()
    return IMAGE_TYPE_ALIASES.get(key, IMAGE_TYPE_ALIASES.get(raw or "", ""))


def parse_image_directives(text: str) -> tuple[dict[str, Any], str]:
    directives: dict[str, Any] = {}

    def replacer(match: re.Match[str]) -> str:
        content = match.group(1).strip()
        parts = [part.strip() for part in re.split(r"[\s,;]+", content) if part.strip()]
        for part in parts:
            lower = part.lower()
            if lower in {"force", "required"}:
                directives["force"] = True
                continue
            if lower in {"skip", "none"}:
                directives["skip"] = True
                continue
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "type":
                normalized = normalize_image_type_label(value)
                if normalized:
                    directives["type"] = normalized
            elif key == "count":
                try:
                    directives["count"] = max(0, min(4, int(value)))
                except ValueError:
                    pass
        return ""

    cleaned = IMAGE_DIRECTIVE_RE.sub(replacer, text)
    return directives, cleaned.strip()


def merge_image_directives(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    if extra.get("force"):
        merged["force"] = True
    if extra.get("skip"):
        merged["skip"] = True
    if extra.get("type"):
        merged["type"] = extra["type"]
    if "count" in extra:
        merged["count"] = extra["count"]
    return merged


def strip_image_directives(text: str) -> str:
    return IMAGE_DIRECTIVE_RE.sub("", text)


def strip_reference_section(body: str) -> tuple[str, list[str]]:
    intro_blocks, sections = split_sections(body)
    reference_blocks: list[str] = []
    kept_sections: list[dict[str, Any]] = []
    for index, section in enumerate(sections):
        if index == len(sections) - 1 and is_reference_heading(section.get("heading", "")):
            reference_blocks = [block for block in section.get("blocks") or [] if block.strip()]
            continue
        kept_sections.append(section)
    return reconstruct_body(intro_blocks, kept_sections), reference_blocks


def parse_reference_blocks(reference_blocks: list[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for block in reference_blocks:
        urls = extract_urls_from_text(block)
        if not urls:
            continue
        label = re.sub(r"https?://[^\s)`>]+", "", block)
        label = label.replace("`", "").strip(" -\uff1a:")
        for url in urls:
            parsed.append({"url": url, "title": label or urllib.parse.urlparse(url).netloc, "description": ""})
    return parsed


def build_reference_entries(body: str, manifest: dict[str, Any], evidence_report: dict[str, Any] | None = None) -> tuple[str, list[dict[str, Any]]]:
    clean_body, reference_blocks = strip_reference_section(body)
    parsed_entries = parse_reference_blocks(reference_blocks)
    evidence_items = (evidence_report or {}).get("items") or []
    evidence_sources = {item.get("url"): item for item in evidence_items if item.get("url")}
    seen: set[str] = set()
    entries: list[dict[str, Any]] = []

    def add_entry(url: str, title: str = "", description: str = "") -> None:
        normalized = url.strip()
        if not normalized or normalized in seen:
            return
        evidence_item = evidence_sources.get(normalized)
        page_title = ""
        for source in (evidence_report or {}).get("sources") or []:
            if source.get("url") == normalized and source.get("page_title"):
                page_title = source["page_title"]
                break
        title_value = title.strip() or page_title or urllib.parse.urlparse(normalized).netloc.replace("www.", "")
        description_value = description.strip() or (evidence_item.get("sentence") if evidence_item else "") or urllib.parse.urlparse(normalized).netloc.replace("www.", "")
        entries.append(
            {
                "url": normalized,
                "title": title_value,
                "description": description_value,
                "domain": urllib.parse.urlparse(normalized).netloc.replace("www.", ""),
            }
        )
        seen.add(normalized)

    for entry in parsed_entries:
        add_entry(entry["url"], entry.get("title", ""), entry.get("description", ""))
    for url in manifest.get("source_urls") or []:
        add_entry(url)
    for index, entry in enumerate(entries, start=1):
        entry["index"] = index
    return clean_body, entries


def reference_keywords(entry: dict[str, Any]) -> list[str]:
    source = " ".join([entry.get("title", ""), entry.get("domain", ""), entry.get("url", "")])
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9.-]{2,}|[\u4e00-\u9fff]{2,8}", source)
    keywords: list[str] = []
    skip = {"https", "http", "com", "org", "www", "index", "docs", "guide", "readme", "official"}
    for token in tokens:
        lower = token.lower()
        if lower in skip:
            continue
        if token not in keywords:
            keywords.append(token)
    fallback = entry.get("title", "")
    if fallback and fallback not in keywords:
        keywords.append(fallback)
    return keywords[:8]


def annotate_body_with_footnotes(body: str, reference_entries: list[dict[str, Any]]) -> str:
    if not reference_entries:
        return body
    intro_blocks, sections = split_sections(body)
    mutable_intro = intro_blocks[:]
    mutable_sections = [{**section, "blocks": (section.get("blocks") or [])[:]} for section in sections]

    def apply_marker(kind: str, section_heading: str | None, block_index: int, marker: int) -> None:
        marker_text = f" [{marker}]"
        if kind == "intro":
            if marker_text not in mutable_intro[block_index]:
                mutable_intro[block_index] = mutable_intro[block_index].rstrip() + marker_text
            return
        for section in mutable_sections:
            if section.get("heading") == section_heading:
                blocks = section.get("blocks") or []
                if marker_text not in blocks[block_index]:
                    blocks[block_index] = blocks[block_index].rstrip() + marker_text
                section["blocks"] = blocks
                return

    block_records: list[tuple[str, str | None, int, str]] = []
    for block_index, block in enumerate(mutable_intro):
        block_records.append(("intro", None, block_index, block))
    for section in mutable_sections:
        for block_index, block in enumerate(section.get("blocks") or []):
            block_records.append(("section", section.get("heading"), block_index, block))

    for entry in reference_entries:
        best_record = None
        best_score = 0
        keywords = reference_keywords(entry)
        for record in block_records:
            block = record[3]
            score = sum(1 for keyword in keywords if keyword and keyword.lower() in block.lower())
            if re.search(r"\d{4}\u5e74|\d+(?:\.\d+)?%|\u7b2c\d+|\u53d1\u5e03|\u4e0a\u7ebf|\u5b98\u65b9|API|README|\u63d2\u4ef6|\u6587\u6863|\u6a21\u578b|\u7248\u672c", block):
                score += 1
            if score > best_score:
                best_score = score
                best_record = record
        if best_record and best_score > 0:
            apply_marker(best_record[0], best_record[1], best_record[2], entry["index"])
    return reconstruct_body(mutable_intro, mutable_sections)


def build_reference_cards_preview(reference_entries: list[dict[str, Any]]) -> str:
    if not reference_entries:
        return ""
    items = []
    for entry in reference_entries:
        desc = html.escape(entry["title"] or entry["description"] or entry["domain"])
        url = html.escape(entry["url"], quote=True)
        items.append(
            f'<li><span class="reference-desc-inline">[{entry["index"]}] {desc}</span><br />'
            f'<a class="reference-link" href="{url}">{url}</a></li>'
        )
    return '<section class="reference-section"><h2>\u53c2\u8003\u6765\u6e90</h2><ol class="reference-list">' + ''.join(items) + '</ol></section>'


def auto_rewrite_article(title: str, meta: dict[str, str], body: str, report: dict[str, Any], manifest: dict[str, Any], output_path: Path) -> dict[str, Any]:
    low_dims = [item["dimension"] for item in report["score_breakdown"] if item["score"] / max(1, item["weight"]) < 0.75]
    intro_blocks, sections = split_sections(body)
    rewritten_parts: list[str] = []
    applied_actions: list[str] = []
    source_urls = manifest.get("source_urls") or []
    evidence_report = collect_online_evidence(title, body, source_urls, output_path.parent) if source_urls else {"items": [], "sources": []}
    evidence_pool = list((evidence_report or {}).get("items") or [])

    rewritten_intro = build_rewritten_intro(title, intro_blocks, report["suggestions"], manifest, sections, low_dims)
    rewritten_parts.append("\n\n".join(rewritten_intro))
    applied_actions.append("重写了开头钩子与导语结构")

    quote_pool = list(report["suggestions"].get("sample_gold_quotes") or [])
    for index, section in enumerate(sections):
        blocks = [cleanup_rewrite_text(block) for block in section.get("blocks") or [] if cleanup_rewrite_text(block)]
        section_parts = [f"{'#' * section['level']} {section['heading']}"]
        if blocks and any(dim in low_dims for dim in ["钩子设计", "内容深度", "文风适配度"]):
            section_parts.append(make_section_opener(section["heading"], blocks[0], title))
        if blocks:
            section_parts.extend(blocks)
        if evidence_pool and any(dim in low_dims for dim in ["内容深度", "可信度与检索支撑"]) and index < 2:
            evidence = evidence_pool.pop(0)
            section_parts.append(f"据《{evidence['page_title']}》：{evidence['sentence']} [来源]({evidence['url']})")
        if "金句质量" in low_dims and quote_pool and index < 2:
            section_parts.append(f"> {quote_pool.pop(0)}")
        if "内容深度" in low_dims and len(blocks) <= 2:
            section_parts.append("把这一节再往下拆，你会发现真正的分水岭不在于知道这件事重要，而在于有没有把它变成一个能重复执行、能被复盘、能持续积累的动作。")
        rewritten_parts.append("\n\n".join(section_parts).strip())

    if any(dim in low_dims for dim in ["收藏/转发潜力", "情绪共鸣"]):
        heading, closing_content, as_bullets = build_closing_section(title, body, sections)
        if as_bullets:
            rewritten_parts.append(f"## {heading}\n\n" + "\n".join(f"- {bullet}" for bullet in closing_content))
            applied_actions.append("按教程型收束补入了更克制的行动段落")
        else:
            rewritten_parts.append(f"## {heading}\n\n" + "\n\n".join(closing_content))
            applied_actions.append("把结尾改成更适合分析稿传播的判断收束")
    if "金句质量" in low_dims:
        applied_actions.append("补入了可截图传播的金句")
    if "文风适配度" in low_dims:
        applied_actions.append("清理了模板化连接词并统一语气")

    rewritten_body = "\n\n".join(part.strip() for part in rewritten_parts if part.strip()).strip() + "\n"
    rewritten_body = cleanup_rewrite_markdown(rewritten_body) or rewritten_body
    rewrite_meta = dict(meta)
    rewrite_meta["title"] = title
    rewrite_meta["summary"] = meta.get("summary") or manifest.get("summary") or extract_summary(rewritten_body)
    rewrite_meta["rewrite_from"] = meta.get("title") or title
    write_text(output_path, join_frontmatter(rewrite_meta, rewritten_body))

    preview_report = build_score_report(title, rewritten_body, manifest, report["threshold"])
    rewrite = {
        "output_path": output_path.name,
        "triggered_dimensions": low_dims,
        "applied_actions": applied_actions,
        "preview_score": preview_report["total_score"],
        "preview_passed": preview_report["passed"],
        "preview_score_breakdown": preview_report["score_breakdown"],
        "preview_candidate_quotes": preview_report["candidate_quotes"],
        "evidence_report_path": "evidence-report.json" if source_urls else None,
        "evidence_used_count": len((evidence_report or {}).get("items") or []),
    }
    write_json(output_path.with_suffix(".rewrite.json"), rewrite)
    return rewrite

def image_provider_from_env(explicit: str | None) -> str:
    if explicit:
        return explicit
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini-api"
    if os.getenv("OPENAI_API_KEY"):
        return "openai-image"
    raise SystemExit("未检测到稳定图片后端。默认仅自动选择 gemini-api 或 openai-image；如需 gemini-web，请显式传 --provider gemini-web。")


def fallback_image_provider(preferred: str) -> str | None:
    if preferred == "gemini-web":
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            return "gemini-api"
        if os.getenv("OPENAI_API_KEY"):
            return "openai-image"
    return None


def consent_dir() -> Path:
    if os.name == "nt":
        base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / "wechat-article-studio" / "gemini-web"


def consent_path() -> Path:
    return consent_dir() / "consent.json"


def local_chrome_user_data_root() -> Path | None:
    candidates = []
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "Google" / "Chrome" / "User Data")
        candidates.append(Path(local_app_data) / "Microsoft" / "Edge" / "User Data")
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate
    return None


def gemini_web_cookie_file() -> Path:
    base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    return base / "baoyu-skills" / "gemini-web" / "cookies.json"


def ensure_gemini_web_consent() -> dict[str, Any]:
    data = read_json(consent_path(), default={}) or {}
    if data.get("accepted") is True and data.get("disclaimerVersion") == DISCLAIMER_VERSION:
        return data
    raise SystemExit(
        "gemini-web 为非官方方式，必须先取得用户明确同意。请先运行：python scripts/studio.py consent --accept"
    )


def parse_cookie_string(raw: str) -> dict[str, str]:
    cookie_map: dict[str, str] = {}
    for item in raw.split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            cookie_map[key] = value
    return cookie_map


def write_cookie_payload(path: Path, cookie_map: dict[str, str]) -> None:
    payload = {
        "version": 1,
        "updatedAt": now_iso(),
        "cookieMap": cookie_map,
        "source": "wechat-article-studio",
    }
    write_json(path, payload)


def resolve_bun_command() -> list[str]:
    candidates = [["bun"], ["npx", "-y", "bun"]]
    for candidate in candidates:
        if shutil.which(candidate[0]) is None:
            continue
        try:
            subprocess.run(candidate + ["--version"], capture_output=True, text=True, check=True)
            return candidate
        except Exception:
            continue
    raise SystemExit("gemini-web 需要 bun 或 npx。请安装 bun，或确保 npx 可用。")


def vendor_root() -> Path:
    return SCRIPT_DIR / "_vendor" / "baoyu-danger-gemini-web"


def ensure_gemini_web_vendor() -> Path:
    root = vendor_root()
    main_ts = root / "main.ts"
    if main_ts.exists():
        return root
    base_url = "https://raw.githubusercontent.com/JimLiu/baoyu-skills/main/skills/baoyu-danger-gemini-web/scripts"
    for relative in IMAGE_PROVIDER_FILES:
        target = root / relative
        ensure_dir(target.parent)
        url = f"{base_url}/{relative}"
        target.write_bytes(download_binary(url))
    return root


def request_json(
    url: str,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    method: str | None = None,
    timeout: int = NETWORK_TIMEOUT,
    retries: int = NETWORK_RETRIES,
) -> dict[str, Any]:
    payload = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json; charset=utf-8", **(headers or {})}, method=method)
    try:
        raw, response_headers = urlopen_with_retry(req, timeout=timeout, retries=retries)
        return json.loads(decode_response_body(raw, response_headers))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"请求失败：响应不是合法 JSON：{url}") from exc


def download_binary(url: str, timeout: int = NETWORK_TIMEOUT, retries: int = NETWORK_RETRIES) -> bytes:
    request = urllib.request.Request(url, headers=HTTP_HEADERS)
    raw, _ = urlopen_with_retry(request, timeout=timeout, retries=retries)
    return raw


def save_binary(path: Path, payload: bytes) -> None:
    ensure_dir(path.parent)
    path.write_bytes(payload)


def image_size_hint(aspect: str) -> tuple[int, int, str]:
    mapping = {
        "16:9": (1536, 1024, "1536x1024"),
        "3:2": (1536, 1024, "1536x1024"),
        "4:3": (1024, 1024, "1024x1024"),
        "1:1": (1024, 1024, "1024x1024"),
        "3:4": (1024, 1536, "1024x1536"),
        "2:3": (1024, 1536, "1024x1536"),
    }
    return mapping.get(aspect, (1536, 1024, "1536x1024"))


GENERIC_SECTION_HEADING_RE = re.compile(r"^正文段落\s*\d+$")


def png_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def detect_dimensions(path: Path, fallback: tuple[int, int]) -> tuple[int, int]:
    result = png_dimensions(path)
    return result or fallback


def generate_openai_image(prompt: str, output_path: Path, model: str, aspect: str) -> dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("缺少 OPENAI_API_KEY。")
    width, height, size = image_size_hint(aspect)
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
    }
    response = request_json(
        "https://api.openai.com/v1/images/generations",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    data = (response.get("data") or [{}])[0]
    if data.get("b64_json"):
        save_binary(output_path, base64.b64decode(data["b64_json"]))
    elif data.get("url"):
        save_binary(output_path, download_binary(data["url"]))
    else:
        raise SystemExit(f"OpenAI 图片接口未返回图像数据：{json.dumps(response, ensure_ascii=False)}")
    actual_width, actual_height = detect_dimensions(output_path, (width, height))
    return {
        "provider": "openai-image",
        "prompt": prompt,
        "revised_prompt": data.get("revised_prompt") or prompt,
        "width": actual_width,
        "height": actual_height,
        "source_meta": {"model": model},
    }


def find_gemini_inline_data(candidate: Any) -> tuple[bytes, str] | None:
    for cand in candidate.get("candidates") or []:
        content = cand.get("content") or {}
        for part in content.get("parts") or []:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"]), inline.get("mimeType") or inline.get("mime_type") or "image/png"
    return None


def generate_gemini_api_image(prompt: str, output_path: Path, model: str, aspect: str) -> dict[str, Any]:
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("缺少 GEMINI_API_KEY 或 GOOGLE_API_KEY。")
    width, height, _ = image_size_hint(aspect)
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={urllib.parse.quote(api_key)}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    response = request_json(endpoint, data=payload, method="POST")
    inline = find_gemini_inline_data(response)
    if not inline:
        raise SystemExit(f"Gemini 官方图片接口未返回图片：{json.dumps(response, ensure_ascii=False)}")
    blob, _ = inline
    save_binary(output_path, blob)
    actual_width, actual_height = detect_dimensions(output_path, (width, height))
    revised_prompt = prompt
    for cand in response.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            text = part.get("text")
            if text:
                revised_prompt = text
                break
    return {
        "provider": "gemini-api",
        "prompt": prompt,
        "revised_prompt": revised_prompt,
        "width": actual_width,
        "height": actual_height,
        "source_meta": {"model": model},
    }


def normalize_gemini_web_model(requested: str | None) -> str:
    value = (requested or "").strip()
    if value and value.startswith("gemini-3."):
        return value
    return GEMINI_WEB_IMAGE_MODEL_CANDIDATES[0]


def _extract_prompt_field(prompt: str, label: str, next_labels: list[str]) -> str:
    markers = [re.escape(item) for item in next_labels]
    boundary = "|".join(markers) if markers else "$"
    match = re.search(rf"{re.escape(label)}\s*(.*?)(?=(?:{boundary})|$)", prompt, flags=re.S)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1) or "").strip()


def gemini_web_prompt_variants(prompt: str) -> list[tuple[str, str]]:
    raw = re.sub(r"\s+", " ", prompt or "").strip()
    if not raw:
        return [("original", prompt or "")]

    labels = [
        "Article title:",
        "Audience:",
        "Purpose:",
        "Theme:",
        "Style:",
        "Mood:",
        "Visual brief:",
        "Section focus:",
        "Section excerpt:",
        "Layout variant:",
        "Composition rule:",
        "Text budget:",
        "Text policy:",
        "Preferred label language:",
        "Allowed labels:",
    ]

    def field(name: str) -> str:
        index = labels.index(name)
        return _extract_prompt_field(raw, name, labels[index + 1 :])

    title = field("Article title:")
    purpose = field("Purpose:")
    theme = field("Theme:")
    style = field("Style:")
    mood = field("Mood:")
    visual_brief = field("Visual brief:")
    section_focus = field("Section focus:")
    section_excerpt = field("Section excerpt:")
    text_budget = field("Text budget:")
    text_policy = field("Text policy:")
    label_language = field("Preferred label language:")
    allowed_labels = field("Allowed labels:")

    subject = section_excerpt or section_focus or title
    subject = re.sub(r"\s+", " ", subject).strip()
    text_instruction = image_text_policy_variant_instruction(text_policy, label_language, allowed_labels)

    compact_prompt = (
        f"Create one polished editorial illustration for a Chinese WeChat article. "
        f"Purpose: {purpose or 'inline illustration'}. "
        f"Theme: {theme or 'editorial storytelling'}. Style: {style or 'editorial illustration'}. "
        f"Mood: {mood or 'calm and sharp'}. "
        f"Core focus: {section_focus or title or 'core idea'}. "
        f"Show this idea as one clear visual scene or structure: {subject}. "
        f"{text_instruction} "
        f"Avoid copied article paragraphs, screenshots, UI text, watermarks, and logos."
    ).strip()

    minimal_prompt = (
        f"Chinese editorial illustration for a WeChat article. "
        f"Show {section_focus or title or 'the core idea'} as a single strong scene or compact structure. "
        f"Use {style or 'hand-drawn editorial'} style, {mood or 'human and restrained'} mood. "
        f"Key idea: {subject}. "
        f"Text budget: {text_budget or 'minimal'}. "
        f"{text_instruction} "
        f"{visual_brief or ''}"
    ).strip()

    variants: list[tuple[str, str]] = [("original", prompt)]
    if compact_prompt and compact_prompt != prompt:
        variants.append(("compact-scene", compact_prompt))
    if minimal_prompt and minimal_prompt not in {prompt, compact_prompt}:
        variants.append(("minimal-scene", minimal_prompt))
    return variants


def generate_gemini_web_image(prompt: str, output_path: Path, model: str | None = None) -> dict[str, Any]:
    from core.gemini_web_session import run_gemini_web_command

    ensure_gemini_web_consent()
    bun = resolve_bun_command()
    root = ensure_gemini_web_vendor()
    completed: subprocess.CompletedProcess[str] | None = None
    session_info: dict[str, Any] = {}
    tried_models: list[str] = []
    last_error: str = ""
    used_prompt = prompt
    used_prompt_variant = "original"
    for candidate in [normalize_gemini_web_model(model)] + [name for name in GEMINI_WEB_IMAGE_MODEL_CANDIDATES if name != normalize_gemini_web_model(model)]:
        if candidate in tried_models:
            continue
        tried_models.append(candidate)
        for prompt_variant, prompt_value in gemini_web_prompt_variants(prompt):
            command = bun + [str(root / "main.ts"), "--prompt", prompt_value, "--image", str(output_path), "--json", "--model", candidate]
            try:
                completed, session_info = run_gemini_web_command(
                    command,
                    cwd=str(root),
                    label="gemini-web 图片生成",
                    timeout=GEMINI_WEB_IMAGE_TIMEOUT,
                )
                used_prompt = prompt_value
                used_prompt_variant = prompt_variant
                break
            except subprocess.TimeoutExpired:
                last_error = f"模型 {candidate} 调用超时"
                continue
            except SystemExit as exc:
                detail = str(exc)
                last_error = detail
                if GEMINI_WEB_NO_IMAGE_MARKER.lower() in detail.lower():
                    continue
                if "Unknown model name" in detail:
                    break
                raise
        if completed is not None:
            break
    if completed is None:
        raise SystemExit(
            "gemini-web 当前返回了文本响应，但没有返回图片。"
            " 已尝试图片模型："
            + ", ".join(tried_models)
            + "。这通常意味着 Gemini Web 图片能力或非官方接口已发生兼容变化。"
        )
    stdout = (completed.stdout or "").strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {"text": stdout}
    width, height = detect_dimensions(output_path, (1536, 1024))
    return {
        "provider": "gemini-web",
        "prompt": used_prompt,
        "revised_prompt": payload.get("text") or used_prompt,
        "width": width,
        "height": height,
        "source_meta": {
            "sessionId": payload.get("sessionId"),
            "model": payload.get("model"),
            "tried_models": tried_models,
            "prompt_variant": used_prompt_variant,
            "profile_dir": session_info.get("shared_profile_dir") or "",
            "session_source": session_info.get("active_source") or "",
        },
    }


def make_placeholder_png(path: Path) -> tuple[int, int]:
    save_binary(path, TRANSPARENT_PNG)
    return 1, 1


def make_fallback_card_png(path: Path, item: dict[str, Any]) -> tuple[int, int]:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return make_placeholder_png(path)

    width, height = (1600, 900) if str(item.get("type") or "") == "封面图" else (1400, 900)
    image = Image.new("RGB", (width, height), "#F4F0E8")
    draw = ImageDraw.Draw(image)
    try:
        font_title = ImageFont.truetype(r"C:\Windows\Fonts\msyhbd.ttc", 54)
        font_sub = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 24)
        font_tag = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 20)
    except Exception:
        font_title = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_tag = ImageFont.load_default()

    def wrap_text(text: str, font: Any, max_width: int) -> list[str]:
        lines: list[str] = []
        current = ""
        for char in text:
            trial = current + char
            if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = char
        if current:
            lines.append(current)
        return lines

    draw.rounded_rectangle((36, 36, width - 36, height - 36), radius=36, fill="#FFFDF8", outline="#D9D0C2", width=3)
    draw.line((86, 96, 310, 96), fill="#C96A3A", width=6)
    draw.ellipse((width - 280, 76, width - 120, 236), fill="#E5B287")
    draw.rectangle((90, height - 230, 290, height - 150), fill="#E5DED0")
    title = str(item.get("section_heading") or item.get("target_section") or item.get("alt") or "发布配图")
    excerpt = str(item.get("section_excerpt") or item.get("purpose") or "外部图片服务不可用，已自动生成本地卡片图。")
    label = str(item.get("type") or "正文插图")
    y = 120
    for line in wrap_text(title, font_title, width - 180)[:3]:
        draw.text((90, y), line, font=font_title, fill="#1D1A17")
        y += 74
    for line in wrap_text(excerpt, font_sub, width - 180)[:4]:
        draw.text((90, y + 8), line, font=font_sub, fill="#666259")
        y += 36
    tag_width = draw.textbbox((0, 0), label, font=font_tag)[2]
    draw.rounded_rectangle((90, height - 118, 90 + tag_width + 34, height - 72), radius=16, fill="#EFE7DA", outline="#D9D0C2")
    draw.text((107, height - 110), label, font=font_tag, fill="#1D1A17")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG")
    return width, height


def count_keyword_hits(text: str, keywords: Iterable[str]) -> int:
    haystack = text.lower()
    total = 0
    for keyword in keywords:
        token = str(keyword or "").strip().lower()
        if not token:
            continue
        total += haystack.count(token)
    return total


def infer_layout_family_from_strategy(content_mode: str, type_bias: dict[str, float]) -> str:
    dominant_type = max(type_bias.items(), key=lambda item: item[1])[0] if type_bias else "正文插图"
    if dominant_type == "流程图":
        return "process"
    if dominant_type == "对比图":
        return "comparison"
    if dominant_type == "信息图":
        return "dashboard" if content_mode == "data" else "hierarchy"
    return "editorial"


def normalize_type_bias(weights: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, value) for value in weights.values()) or 1.0
    return {key: round(max(0.0, value) / total, 3) for key, value in weights.items()}


def resolve_style_profile(profile_key: str) -> dict[str, Any]:
    return dict(IMAGE_AUTO_STYLE_PROFILES.get(profile_key) or IMAGE_AUTO_STYLE_PROFILES["editorial-analysis"])


def build_effective_image_controls(controls: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    profile = strategy.get("profile") or {}
    merged = dict(controls or {})
    merged["style_mode"] = controls.get("style_mode") or strategy.get("style_mode") or profile.get("style_mode") or "uniform"
    merged["density_mode"] = normalize_image_density_mode(controls.get("density_mode") or controls.get("density") or "auto")
    merged["density"] = merged["density_mode"]
    merged["inline_count"] = max(0, int(controls.get("inline_count") or 0))
    merged["allow_closing_image"] = str(controls.get("allow_closing_image") or "auto").strip().lower() or "auto"
    merged["layout_family"] = controls.get("layout_family") or strategy.get("layout_family") or profile.get("layout_family") or ""
    merged["preset"] = controls.get("preset") or strategy.get("preset") or profile.get("preset") or ""
    merged["preset_label"] = IMAGE_STYLE_PRESETS.get(merged.get("preset", ""), {}).get("label", controls.get("preset_label", ""))
    merged["theme"] = controls.get("theme") or strategy.get("theme") or profile.get("theme") or ""
    merged["style"] = controls.get("style") or strategy.get("style") or profile.get("style") or ""
    merged["mood"] = controls.get("mood") or strategy.get("mood") or profile.get("mood") or ""
    merged["custom_visual_brief"] = controls.get("custom_visual_brief") or strategy.get("custom_visual_brief") or ""
    merged["preset_cover"] = controls.get("preset_cover") or strategy.get("preset_cover") or profile.get("cover_preset") or merged.get("preset") or ""
    merged["preset_infographic"] = controls.get("preset_infographic") or strategy.get("preset_infographic") or profile.get("infographic_preset") or merged.get("preset") or ""
    merged["preset_inline"] = controls.get("preset_inline") or strategy.get("preset_inline") or profile.get("inline_preset") or merged.get("preset") or ""
    if merged.get("preset_cover"):
        merged["preset_cover_label"] = IMAGE_STYLE_PRESETS.get(merged["preset_cover"], {}).get("label", "")
    if merged.get("preset_infographic"):
        merged["preset_infographic_label"] = IMAGE_STYLE_PRESETS.get(merged["preset_infographic"], {}).get("label", "")
    if merged.get("preset_inline"):
        merged["preset_inline_label"] = IMAGE_STYLE_PRESETS.get(merged["preset_inline"], {}).get("label", "")
    return merged


def visual_profile_for_item(controls: dict[str, Any], item: dict[str, Any]) -> dict[str, str]:
    style_mode = controls.get("style_mode") or "uniform"
    base_preset = (controls.get("preset") or "").strip()
    base_preset_label = IMAGE_STYLE_PRESETS.get(base_preset, {}).get("label", (controls.get("preset_label") or "").strip())
    base_theme = controls.get("theme", "") or "文章主题导向"
    base_style = controls.get("style", "") or "内容驱动视觉表达"
    base_mood = controls.get("mood", "") or "克制清晰"
    base_brief = (controls.get("custom_visual_brief") or "").strip()
    profile_key = (controls.get("profile_key") or item.get("article_visual_strategy", {}).get("profile_key") or "").strip()
    style_reason = item.get("style_reason") or ""

    if style_mode != "mixed-by-type":
        return {
            "style_mode": "uniform",
            "base_preset": base_preset,
            "base_preset_label": base_preset_label,
            "visual_preset": base_preset,
            "visual_preset_label": base_preset_label,
            "visual_theme": base_theme,
            "visual_style": base_style,
            "visual_mood": base_mood,
            "visual_brief": base_brief or "highlight the core insight without clutter",
            "style_reason": style_reason or f"文章整体采用 {IMAGE_AUTO_STYLE_PROFILES.get(profile_key, {}).get('label', '统一风格')} 方向，当前图片沿用整篇主视觉。",
        }

    item_type = item.get("type", "正文插图")
    if item_type == "封面图":
        preset_key = (controls.get("preset_cover") or "").strip() or base_preset
    elif item_type == "信息图":
        preset_key = (controls.get("preset_infographic") or "").strip() or base_preset
    else:
        preset_key = (controls.get("preset_inline") or "").strip() or base_preset

    preset = IMAGE_STYLE_PRESETS.get(preset_key, {})
    preset_label = preset.get("label", "").strip()
    style = preset.get("style", "").strip() or base_style
    mood = preset.get("mood", "").strip() or base_mood
    item_brief = (preset.get("custom_visual_brief") or "").strip()

    merged_brief = base_brief
    if item_brief:
        if merged_brief and item_brief not in merged_brief:
            merged_brief = f"{merged_brief}; {item_brief}"
        elif not merged_brief:
            merged_brief = item_brief
    if merged_brief:
        merged_brief = f"{merged_brief}; keep palette and motif consistent with the base preset"
    else:
        merged_brief = "keep palette and motif consistent with the base preset"

    return {
        "style_mode": "mixed-by-type",
        "base_preset": base_preset,
        "base_preset_label": base_preset_label,
        "visual_preset": preset_key,
        "visual_preset_label": preset_label,
        "visual_theme": base_theme,
        "visual_style": style,
        "visual_mood": mood,
        "visual_brief": merged_brief,
        "style_reason": style_reason or f"{item_type} 继承文章主视觉，并按图片用途切换到 {preset_label or preset_key or '当前'} 风格表达。",
    }


def _image_prompting_config() -> ImagePromptingConfig:
    return ImagePromptingConfig(
        image_type_prompt_modules=IMAGE_TYPE_PROMPT_MODULES,
        image_differentiation_modules=IMAGE_DIFFERENTIATION_MODULES,
        image_text_policy_defaults=IMAGE_TEXT_POLICY_DEFAULTS,
        image_text_policy_labels=IMAGE_TEXT_POLICY_LABELS,
        image_label_bad_prefixes=IMAGE_LABEL_BAD_PREFIXES,
        extract_summary=extract_summary,
        cjk_len=cjk_len,
        sentence_split=sentence_split,
        is_generated_section_heading=is_generated_section_heading,
    )


def _image_planning_config() -> ImagePlanConfig:
    return ImagePlanConfig(
        compose_prompt=compose_prompt,
        resolve_image_text_policy=resolve_image_text_policy,
        visual_profile_for_item=visual_profile_for_item,
        candidate_keywords=_candidate_keywords,
        extract_summary=extract_summary,
        item_native_aspect_ratio=item_native_aspect_ratio,
        item_safe_crop_policy=item_safe_crop_policy,
        infer_article_category_label=infer_article_category_label,
        cjk_len=cjk_len,
        now_iso=now_iso,
    )


def compose_prompt(title: str, summary: str, controls: dict[str, Any], item: dict[str, Any], audience: str) -> str:
    return _compose_image_prompt(
        title,
        summary,
        controls,
        item,
        audience,
        cfg=_image_prompting_config(),
        style_family_modules=IMAGE_STYLE_FAMILY_MODULES,
        content_mode_modules=IMAGE_CONTENT_MODE_MODULES,
    )


def image_position_label(item: dict[str, Any]) -> str:
    return _image_position_label(item)


def is_generated_section_heading(value: str) -> bool:
    return bool(GENERIC_SECTION_HEADING_RE.match((value or "").strip()))


def cleaned_image_signal_text(text: str, limit: int = 120) -> str:
    return _cleaned_image_signal_text(text, limit, cfg=_image_prompting_config())


def image_section_focus(item: dict[str, Any], limit: int = 64) -> str:
    return _image_section_focus(item, limit, cfg=_image_prompting_config())


def image_anchor_excerpt(item: dict[str, Any], limit: int = 110) -> str:
    return _image_anchor_excerpt(item, limit, cfg=_image_prompting_config())


def image_section_excerpt(item: dict[str, Any], limit: int = 120) -> str:
    return _image_section_excerpt(item, limit, cfg=_image_prompting_config())


def image_purpose_label(item: dict[str, Any]) -> str:
    return _image_purpose_label(item)


def image_visual_content(item: dict[str, Any]) -> str:
    return _image_visual_content(item, cfg=_image_prompting_config())


def short_sentence_chunks(text: str, limit: int = 4, max_len: int = 18) -> list[str]:
    return _short_sentence_chunks(text, limit=limit, max_len=max_len, cfg=_image_prompting_config())


def image_text_budget(item: dict[str, Any]) -> str:
    return _image_text_budget(item)


def image_label_strategy(item: dict[str, Any]) -> list[str]:
    return _image_label_strategy(item, cfg=_image_prompting_config())


def _normalize_image_text_policy(value: str) -> str:
    return _core_normalize_image_text_policy(value)


def _normalize_label_language(value: str) -> str:
    return _core_normalize_label_language(value)


def compact_label_strategy(values: Any, *, limit: int = 4, max_len: int = 6) -> list[str]:
    return _compact_label_strategy(values, limit=limit, max_len=max_len)


def image_text_policy_variant_instruction(policy: str, label_language: str, allowed_labels: Any = None) -> str:
    return _image_text_policy_variant_instruction(policy, label_language, allowed_labels)


def resolve_image_text_policy(controls: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    return _resolve_image_text_policy(controls, item, cfg=_image_prompting_config())


def image_visual_elements(item: dict[str, Any]) -> list[str]:
    return _image_visual_elements(item, cfg=_image_prompting_config())


def image_layout_spec(item: dict[str, Any]) -> dict[str, str]:
    return _image_layout_spec(item)


def image_aspect_policy(item: dict[str, Any]) -> str:
    return _image_aspect_policy(item)


def prompt_markdown(title: str, audience: str, controls: dict[str, Any], item: dict[str, Any]) -> str:
    return _prompt_markdown(title, audience, controls, item, cfg=_image_prompting_config())


def write_image_outline_artifacts(workspace: Path, title: str, audience: str, controls: dict[str, Any], plan: dict[str, Any]) -> None:
    prompt_dir = ensure_dir(workspace / "prompts" / "images")
    article_strategy = plan.get("article_visual_strategy") or {}
    outline_items: list[dict[str, Any]] = []
    for item in plan.get("items") or []:
        prompt_path = prompt_dir / f"{item['id']}.md"
        write_text(prompt_path, prompt_markdown(title, audience, controls, item))
        layout_spec = image_layout_spec(item)
        text_policy = resolve_image_text_policy(controls, item)
        label_strategy = text_policy["label_strategy"]
        outline_items.append(
            {
                "id": item["id"],
                "type": item["type"],
                "position": image_position_label(item),
                "purpose": image_purpose_label(item),
                "target_section": item.get("target_section", ""),
                "layout_variant": item.get("layout_variant_label", ""),
                "style_mode": item.get("style_mode") or controls.get("style_mode") or "uniform",
                "base_preset": item.get("base_preset") or controls.get("preset") or "",
                "base_preset_label": item.get("base_preset_label") or controls.get("preset_label") or "",
                "preset": item.get("visual_preset") or controls.get("preset") or "",
                "preset_label": item.get("visual_preset_label") or "",
                "layout_spec": layout_spec,
                "visual_content": image_visual_content(item),
                "visual_elements": image_visual_elements(item),
                "label_strategy": label_strategy,
                "text_budget": text_policy["text_budget"],
                "text_policy": text_policy["mode"],
                "text_policy_label": text_policy["label"],
                "label_language": text_policy["label_language"],
                "aspect_policy": image_aspect_policy(item),
                "decision_source": item.get("decision_source", ""),
                "type_reason": item.get("type_reason", ""),
                "style_reason": item.get("style_reason", ""),
                "anchor_block_excerpt": item.get("anchor_block_excerpt") or "",
                "prompt_path": relative_posix(prompt_path, workspace),
            }
        )
    outline = {
        "title": title,
        "density": controls.get("density", "balanced"),
        "preset": controls.get("preset", ""),
        "preset_label": controls.get("preset_label", ""),
        "style_mode": controls.get("style_mode", "uniform"),
        "article_visual_strategy": article_strategy,
        "preset_cover": controls.get("preset_cover", ""),
        "preset_cover_label": controls.get("preset_cover_label", ""),
        "preset_infographic": controls.get("preset_infographic", ""),
        "preset_infographic_label": controls.get("preset_infographic_label", ""),
        "preset_inline": controls.get("preset_inline", ""),
        "preset_inline_label": controls.get("preset_inline_label", ""),
        "layout_family": controls.get("layout_family", ""),
        "planned_inline_count": plan.get("planned_inline_count", 0),
        "requested_inline_count": plan.get("requested_inline_count", plan.get("planned_inline_count", 0)),
        "planning_shortfall_reason": plan.get("planning_shortfall_reason", ""),
        "skipped_sections": plan.get("skipped_sections", []),
        "forced_sections": plan.get("forced_sections", []),
        "items": outline_items,
        "generated_at": now_iso(),
    }
    write_json(workspace / "image-outline.json", outline)
    lines = [f"# 插图大纲：{title}", ""]
    lines.append(f"- 密度：`{outline['density']}`")
    lines.append(f"- 视觉方向：`{article_strategy.get('visual_direction') or 'auto'}`")
    lines.append(f"- 风格家族：`{article_strategy.get('style_family') or 'auto'}`")
    lines.append(f"- 内容模式：`{article_strategy.get('content_mode') or 'auto'}`")
    if outline.get("style_mode") == "mixed-by-type":
        lines.append(
            f"- 风格模式：`{outline['style_mode']}`（封面 `{outline.get('preset_cover')}` / 信息图 `{outline.get('preset_infographic')}` / 正文 `{outline.get('preset_inline')}`）"
        )
        lines.append(f"- 基调预设：`{outline['preset'] or 'default'}`")
    else:
        lines.append(f"- 风格预设：`{outline['preset'] or 'default'}`")
    lines.append(f"- 布局家族：`{outline['layout_family'] or 'auto'}`")
    lines.append(f"- 正文插图：`{outline['planned_inline_count']}`（请求值 `{outline['requested_inline_count']}`）")
    if outline.get("planning_shortfall_reason"):
        lines.append(f"- 规划说明：{outline['planning_shortfall_reason']}")
    if outline.get("forced_sections"):
        lines.append(f"- 强制配图章节：{' / '.join(outline['forced_sections'])}")
    if outline.get("skipped_sections"):
        lines.append(f"- 跳过配图章节：{' / '.join(outline['skipped_sections'])}")
    lines.append("")
    for item in outline_items:
        lines.append(f"## {item['id']} · {item['type']}")
        lines.append("")
        lines.append(f"- 位置：`{item['position']}`")
        lines.append(f"- 用途：{item['purpose']}")
        lines.append(f"- 目标章节：{item['target_section'] or 'cover'}")
        lines.append(f"- 版式：{item['layout_variant']}")
        lines.append(f"- 布局规则：{item['layout_spec']['instruction']}")
        lines.append(f"- 决策来源：`{item['decision_source'] or 'auto'}`")
        lines.append(f"- 图型原因：{item['type_reason'] or 'auto'}")
        lines.append(f"- 风格原因：{item['style_reason'] or 'auto'}")
        lines.append(f"- 视觉内容：{item['visual_content']}")
        lines.append(f"- 视觉元素：{'；'.join(item['visual_elements'])}")
        lines.append(f"- 文字预算：{item['text_budget']}")
        lines.append(f"- 文字模式：{item.get('text_policy_label') or IMAGE_TEXT_POLICY_LABELS.get(item.get('text_policy') or 'auto', IMAGE_TEXT_POLICY_LABELS['auto'])}")
        lines.append(f"- 标签语言：{item.get('label_language') or 'zh-CN'}")
        lines.append(f"- 标签策略：{' / '.join(item['label_strategy']) if item['label_strategy'] else '尽量不用图中文字'}")
        lines.append(f"- 比例策略：{item['aspect_policy']}")
        lines.append(f"- Prompt 文件：`{item['prompt_path']}`")
        lines.append("")
    write_text(workspace / "image-outline.md", "\n".join(lines).rstrip() + "\n")


def write_topic_discovery_artifacts(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(workspace / "topic-discovery.json", payload)
    focus = str(payload.get("focus") or "all").strip().lower()
    scope_label = "AI/科技互联网（focus=ai-tech）" if focus == "ai-tech" else "全量热点（focus=all）"
    lines = [
        f"# 热点选题发现（最近 {payload.get('window_hours', 24)} 小时）",
        "",
        f"- 数据源：`{payload.get('provider', 'google-news-rss')}`",
        f"- 选题范围：{scope_label}",
        "",
    ]
    for index, item in enumerate(payload.get("candidates") or [], start=1):
        lines.append(f"## {index}. {item['recommended_topic']}")
        lines.append("")
        lines.append(f"- 热点标题：{item['hot_title']}")
        recommended_title = item.get("recommended_title") or item.get("recommended_topic") or item.get("hot_title")
        threshold = int(item.get('recommended_title_threshold') or TITLE_SCORE_THRESHOLD)
        score = int(item.get('recommended_title_score') or 0)
        gate = bool(item.get('recommended_title_gate_passed', False))
        lines.append(f"- 推荐标题：{recommended_title}｜评分 {score}/{threshold}｜{'通过' if gate else '未通过'}")
        lines.append(f"- 来源：{item['source']}")
        if item.get("published_at"):
            lines.append(f"- 时间：{item['published_at']}")
        hit_count = int(item.get("hit_count") or 1)
        lines.append(f"- 热度信号：在 {hit_count} 个关键词流中出现")
        if item.get("content_kind"):
            lines.append(f"- 内容类型：{item['content_kind']}")
        if item.get("source_tier"):
            lines.append(f"- 来源层级：{item['source_tier']}")
        lines.append(f"- 类型：{item['topic_type']}")
        lines.append(f"- 为什么值得写：{item['why_now']}")
        lines.append(f"- 建议角度：{' / '.join(item.get('angles') or [])}")
        lines.append(f"- 可写观点：{' / '.join(item.get('viewpoints') or [])}")
        lines.append(f"- 原始链接：{item['source_url']}")
        lines.append("")
    write_text(workspace / "topic-discovery.md", "\n".join(lines).rstrip() + "\n")


def cmd_discover_topics(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    try:
        from core.account_strategy import load_account_strategy
    except ImportError:
        load_account_strategy = None
    window_hours = int(args.window_hours or 24)
    limit = int(args.limit or DISCOVERY_TOPIC_LIMIT)
    provider = getattr(args, "provider", None)
    focus = normalize_discovery_focus(getattr(args, "focus", None))
    rss_urls = list(getattr(args, "rss_url", None) or [])
    payload = discover_recent_topics(window_hours=window_hours, limit=limit, provider=provider, focus=focus, rss_urls=rss_urls)
    write_topic_discovery_artifacts(workspace, payload)
    manifest["topic_discovery_path"] = "topic-discovery.json"
    manifest["topic_discovery_provider"] = payload.get("provider") or normalize_discovery_provider(provider)
    manifest["topic_discovery_focus"] = payload.get("focus") or focus
    strategy = load_account_strategy(workspace, manifest, create_if_missing=True) if load_account_strategy else (manifest.get("account_strategy") or {})
    controls = dict(manifest.get("image_controls") or {})
    # 无主题启动仅保留安全的密度默认，不再隐式锁定风格、主题或图型。
    controls.setdefault("density", str(strategy.get("image_density") or "balanced"))
    manifest["image_controls"] = controls
    save_manifest(workspace, manifest)
    safe_print_json(payload)
    return 0


def _has_explicit_image_controls(args: Any) -> bool:
    keys = [
        "image_preset",
        "image_style_mode",
        "image_preset_cover",
        "image_preset_infographic",
        "image_preset_inline",
        "image_layout_family",
        "image_theme",
        "image_style",
        "image_type",
        "image_mood",
        "custom_visual_brief",
        "image_density",
        "allow_closing_image",
    ]
    if any(str(getattr(args, key, "") or "").strip() for key in keys):
        return True
    try:
        return int(getattr(args, "inline_count", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


def infer_article_category_label(title: str, summary: str, body: str) -> str:
    corpus = f"{title}\n{summary}\n{body}"
    if re.search(r"教程|指南|手把手|实操|步骤|SOP|怎么做|如何|模板|清单", corpus):
        return "教程实操"
    if re.search(r"案例|复盘|拆解|项目|公司|产品", corpus):
        return "案例拆解"
    if re.search(r"故事|经历|生活|关系|成长|焦虑|情绪", corpus):
        return "叙事观察"
    return "分析评论"


def normalize_image_density_mode(value: str) -> str:
    normalized = str(value or "").strip().lower().replace("_", "-")
    if normalized in {"", "auto"}:
        return "auto"
    if normalized in {"rich", "per-section"}:
        return "dense"
    if normalized in {"none", "minimal", "balanced", "dense", "custom"}:
        return normalized
    return "auto"


def image_density_range(mode: str, explicit_count: int = 0) -> tuple[int, int]:
    normalized = normalize_image_density_mode(mode)
    if normalized == "custom":
        count = max(0, int(explicit_count or 0))
        return count, count
    if normalized == "none":
        return 0, 0
    if normalized == "minimal":
        return 0, 1
    if normalized == "balanced":
        return 1, 2
    if normalized == "dense":
        return 2, 4
    if explicit_count > 0:
        count = max(0, int(explicit_count))
        if count <= 1:
            return 0, 1
        if count == 2:
            return 1, 2
        return 2, 4
    return 0, 2


def resolve_inline_density_settings(
    body: str,
    explicit_count: int,
    density_mode: str = "auto",
    *,
    article_strategy: dict[str, Any] | None = None,
    sections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_mode = normalize_image_density_mode(density_mode)
    explicit = max(0, int(explicit_count or 0))
    inline_min, inline_max = image_density_range(normalized_mode, explicit)
    if normalized_mode == "custom":
        return {
            "mode": normalized_mode,
            "target_inline_count": explicit,
            "inline_range": (inline_min, inline_max),
            "allow_section_reuse": False,
        }
    if normalized_mode == "none":
        return {
            "mode": normalized_mode,
            "target_inline_count": 0,
            "inline_range": (0, 0),
            "allow_section_reuse": False,
        }
    if explicit > 0 and normalized_mode == "auto":
        return {
            "mode": normalized_mode,
            "target_inline_count": explicit,
            "inline_range": image_density_range(normalized_mode, explicit),
            "allow_section_reuse": False,
        }

    clean_body = strip_image_directives(body)
    char_count = cjk_len(re.sub(r"^#{1,6}\s+", "", clean_body, flags=re.M))
    normalized_sections = sections
    if normalized_sections is None:
        _, normalized_sections = normalize_sections_for_images(body)
    metrics = [
        extract_section_metrics(section, index)
        for index, section in enumerate(normalized_sections)
        if not is_reference_heading(section.get("heading", ""))
    ]
    eligible_sections = [metric for metric in metrics if not (metric.get("image_directives") or {}).get("skip")]
    structured_hits = sum(
        1
        for metric in eligible_sections
        if metric.get("info_hits", 0) >= 2 or metric.get("list_count", 0) >= 2 or metric.get("char_count", 0) >= 900
    )
    article_strategy = article_strategy or {}
    type_bias = article_strategy.get("type_bias") or {}
    structured_article = bool(
        structured_hits >= 2
        or type_bias.get("流程图", 0) >= 0.25
        or type_bias.get("对比图", 0) >= 0.22
        or type_bias.get("信息图", 0) >= 0.25
    )

    if normalized_mode == "minimal":
        target = 0 if char_count < 1100 and not structured_article else 1
    elif normalized_mode == "balanced":
        target = 1
        if structured_article or char_count >= 1800:
            target = 2
    elif normalized_mode == "dense":
        if char_count < 1500 and not structured_article:
            target = 2
        elif char_count < 3200:
            target = 3
        else:
            target = 4
    else:
        if char_count < 1000:
            target = 1 if structured_article else 0
        elif char_count < 2200:
            target = 2 if structured_article else 1
        elif char_count < 3800:
            target = 3 if structured_article else 2
        else:
            target = 4 if structured_article else 3

    target = max(inline_min, min(inline_max, target))
    available = len(eligible_sections)
    if available <= 0:
        target = 0
    elif normalized_mode in {"minimal", "balanced", "auto"}:
        target = min(target, available)
    return {
        "mode": normalized_mode,
        "target_inline_count": target,
        "inline_range": (inline_min, inline_max),
        "allow_section_reuse": normalized_mode == "dense",
    }


def should_include_closing_image(
    allow_mode: str,
    *,
    final_metric: dict[str, Any] | None,
    closing_decision: dict[str, str],
    article_strategy: dict[str, Any],
    inline_count: int,
) -> bool:
    normalized = str(allow_mode or "").strip().lower()
    if normalized == "on":
        return True
    if normalized == "off":
        return False
    if inline_count <= 0 and not final_metric:
        return False
    if closing_decision.get("type") in {"信息图", "对比图", "流程图"}:
        return True
    if final_metric and (final_metric.get("info_hits", 0) >= 1 or final_metric.get("list_count", 0) >= 1):
        return True
    type_bias = article_strategy.get("type_bias") or {}
    return bool(type_bias.get("信息图", 0) >= 0.3 or type_bias.get("对比图", 0) >= 0.25)


def infer_image_role(item: dict[str, Any], *, article_category: str = "", article_strategy: dict[str, Any] | None = None) -> tuple[str, str]:
    article_strategy = article_strategy or {}
    image_type = str(item.get("type") or "").strip()
    insert_strategy = str(item.get("insert_strategy") or "").strip()
    visual_route = str(article_strategy.get("visual_route") or "").strip()
    if image_type == "封面图" or insert_strategy == "cover_only":
        return "click", "封面图负责把读者先点进来。"
    if insert_strategy == "section_end":
        if image_type in {"信息图", "对比图", "流程图"} or visual_route == "conflict-alert":
            return "share", "结尾结构图负责可转述、可转发的收束。"
        return "remember", "结尾图负责把最后判断留在读者脑海里。"
    if image_type in {"信息图", "对比图", "流程图"}:
        return "explain", "结构图优先承担解释任务。"
    if image_type == "分隔图":
        return "remember", "分隔图负责节奏和记忆点。"
    if any(keyword in article_category for keyword in ["分析", "教程", "案例"]):
        return "explain", "正文图优先帮读者理解。"
    return "remember", "正文图优先承担记忆锚点。"


def _candidate_keywords(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_\-/\.]{2,}|[\u4e00-\u9fff]{2,8}", text or "")
    stop = {"这篇文章", "真正", "问题", "内容", "方法", "步骤", "清单", "最后", "为什么", "如果", "因为", "所以", "这个", "那个", "我们", "你们", "他们"}
    output: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        value = str(token).strip()
        if not value or value in stop or value in seen:
            continue
        seen.add(value)
        output.append(value)
        if len(output) >= 6:
            break
    return output


def item_native_aspect_ratio(item: dict[str, Any]) -> str:
    return "2:3" if item.get("aspect_ratio") == "3:4" else "3:2"


def item_safe_crop_policy(item: dict[str, Any]) -> str:
    if item.get("type") == "封面图":
        return "Keep the focal object within the central safe zone for WeChat thumbnail and header crops."
    if item.get("type") in {"信息图", "对比图", "流程图"}:
        return "Keep key structure away from the outer 8% edges so mobile crops do not break the reading path."
    return "Keep the main subject and symbolic cues centered enough to survive responsive cropping."


def resolve_image_controls(existing: dict[str, Any] | None, args: Any, *, title: str = "", summary: str = "", body: str = "") -> dict[str, Any]:
    current = dict(existing or {})
    raw_style_mode = getattr(args, "image_style_mode", None) or current.get("style_mode") or ""
    normalized_style_mode = str(raw_style_mode).strip().lower().replace("_", "-")
    if normalized_style_mode in {"mixed-by-type", "mixed"}:
        style_mode = "mixed-by-type"
    elif normalized_style_mode == "uniform":
        style_mode = "uniform"
    else:
        style_mode = ""
    explicit_preset = getattr(args, "image_preset", None)
    selected_preset = explicit_preset or current.get("preset") or ""
    preset = IMAGE_STYLE_PRESETS.get(selected_preset, {})
    density_mode = normalize_image_density_mode(
        getattr(args, "image_density", None)
        or current.get("density_mode")
        or current.get("density")
        or "auto"
    )
    layout_family = getattr(args, "image_layout_family", None) or current.get("layout_family") or ""
    text_policy = getattr(args, "image_text_policy", None) or current.get("text_policy") or ""
    label_language = getattr(args, "image_label_language", None) or current.get("label_language") or ""
    allow_closing_image = str(
        getattr(args, "allow_closing_image", None)
        or current.get("allow_closing_image")
        or "auto"
    ).strip().lower() or "auto"
    if allow_closing_image not in ALLOW_CLOSING_IMAGE_CHOICES:
        allow_closing_image = "auto"
    try:
        inline_count = max(0, int(getattr(args, "inline_count", None) or current.get("inline_count") or 0))
    except (TypeError, ValueError):
        inline_count = max(0, int(current.get("inline_count") or 0))

    preset_cover = getattr(args, "image_preset_cover", None) or current.get("preset_cover") or ""
    preset_infographic = getattr(args, "image_preset_infographic", None) or current.get("preset_infographic") or ""
    preset_inline = getattr(args, "image_preset_inline", None) or current.get("preset_inline") or ""

    if selected_preset and current.get("preset") != selected_preset:
        base = {
            "style_mode": style_mode,
            "preset": selected_preset,
            "preset_label": preset.get("label", ""),
            "theme": preset.get("theme", ""),
            "style": preset.get("style", ""),
            "type": current.get("type") or "",
            "mood": preset.get("mood", ""),
            "custom_visual_brief": preset.get("custom_visual_brief", ""),
            "density": density_mode,
            "density_mode": density_mode,
            "inline_count": inline_count,
            "allow_closing_image": allow_closing_image,
            "layout_family": layout_family,
            "text_policy": text_policy,
            "label_language": label_language,
            "preset_cover": preset_cover,
            "preset_infographic": preset_infographic,
            "preset_inline": preset_inline,
            "text_policy_overrides": dict(current.get("text_policy_overrides") or {}),
        }
    else:
        base = {
            "style_mode": style_mode,
            "preset": current.get("preset", selected_preset),
            "preset_label": current.get("preset_label", preset.get("label", "")),
            "theme": current.get("theme") or preset.get("theme") or "",
            "style": current.get("style") or preset.get("style") or "",
            "type": current.get("type") or "",
            "mood": current.get("mood") or preset.get("mood") or "",
            "custom_visual_brief": current.get("custom_visual_brief") or preset.get("custom_visual_brief") or "",
            "density": density_mode,
            "density_mode": density_mode,
            "inline_count": inline_count,
            "allow_closing_image": allow_closing_image,
            "layout_family": layout_family,
            "text_policy": text_policy,
            "label_language": label_language or current.get("label_language") or "",
            "preset_cover": preset_cover,
            "preset_infographic": preset_infographic,
            "preset_inline": preset_inline,
            "text_policy_overrides": dict(current.get("text_policy_overrides") or {}),
        }

    theme = getattr(args, "image_theme", None)
    style = getattr(args, "image_style", None)
    image_type = getattr(args, "image_type", None)
    mood = getattr(args, "image_mood", None)
    brief = getattr(args, "custom_visual_brief", None)

    if theme:
        base["theme"] = theme
    if style:
        base["style"] = style
    if image_type:
        base["type"] = image_type
    if mood:
        base["mood"] = mood
    if brief:
        base["custom_visual_brief"] = brief
    base["density"] = normalize_image_density_mode(base.get("density_mode") or base.get("density") or "auto")
    base["density_mode"] = base["density"]
    base["inline_count"] = inline_count
    base["allow_closing_image"] = allow_closing_image
    if base.get("preset"):
        base["preset_label"] = IMAGE_STYLE_PRESETS.get(base["preset"], {}).get("label", base.get("preset_label", ""))
    if base.get("preset_cover"):
        base["preset_cover_label"] = IMAGE_STYLE_PRESETS.get(base["preset_cover"], {}).get("label", "")
    if base.get("preset_infographic"):
        base["preset_infographic_label"] = IMAGE_STYLE_PRESETS.get(base["preset_infographic"], {}).get("label", "")
    if base.get("preset_inline"):
        base["preset_inline_label"] = IMAGE_STYLE_PRESETS.get(base["preset_inline"], {}).get("label", "")
    if _has_explicit_image_controls(args):
        base["decision_source"] = "explicit"
    elif title or summary or body:
        base["decision_source"] = "auto"
        base["article_category"] = infer_article_category_label(title, summary, body)
        base["auto_reason"] = f"未显式指定图片参数，按文章内容自动选择；当前判定为 {base['article_category']}。"
    else:
        base["decision_source"] = current.get("decision_source") or ""
    return base


def layout_variants_for_type(image_type: str) -> list[dict[str, str]]:
    return IMAGE_LAYOUT_VARIANTS.get(image_type, IMAGE_LAYOUT_VARIANTS.get("正文插图", []))


def pick_layout_variant(image_type: str, occurrence_index: int, layout_family: str = "") -> dict[str, str]:
    variants = layout_variants_for_type(image_type)
    if not variants:
        return {"key": "default", "label": "默认构图", "instruction": "Use a distinct composition and avoid embedded text."}
    if layout_family and layout_family in IMAGE_LAYOUT_FAMILY_VARIANTS:
        family_keys = set(IMAGE_LAYOUT_FAMILY_VARIANTS[layout_family])
        family_variants = [variant for variant in variants if variant["key"] in family_keys]
        if family_variants:
            return family_variants[occurrence_index % len(family_variants)]
    return variants[occurrence_index % len(variants)]


def extract_prompt_from_markdown(path: Path) -> str | None:
    if not path.exists():
        return None
    text = read_text(path)
    marker = "\n## Prompt\n"
    index = text.find(marker)
    if index == -1:
        marker = "## Prompt\n"
        index = text.find(marker)
        if index == -1:
            return None
    content = text[index + len(marker):].strip()
    return content or None


def infer_title(manifest: dict[str, Any], meta: dict[str, str], body: str) -> str:
    return (
        manifest.get("selected_title")
        or meta.get("title")
        or extract_title_from_body(body)
        or manifest.get("topic")
        or "未命名文章"
    )


def relative_posix(path: Path, base: Path) -> str:
    return path.resolve().relative_to(base.resolve()).as_posix()

def cmd_ideate(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    image_controls = resolve_image_controls(manifest.get("image_controls"), args)
    manifest.update(
        {
            "topic": args.topic or manifest.get("topic"),
            "direction": args.direction or manifest.get("direction") or "",
            "audience": args.audience or manifest.get("audience") or "大众读者",
            "goal": args.goal or manifest.get("goal") or "公众号爆款图文",
            "score_threshold": args.score_threshold or manifest.get("score_threshold") or DEFAULT_THRESHOLD,
            "source_urls": args.source_url or manifest.get("source_urls") or [],
            "image_controls": image_controls,
            "publish_intent": bool(args.publish_intent or manifest.get("publish_intent")),
        }
    )
    ideation = read_json(workspace / "ideation.json", default={}) or {}
    ideation.update(
        {
            "topic": manifest.get("topic"),
            "direction": manifest.get("direction"),
            "titles": args.title or ideation.get("titles") or [],
            "selected_title": args.selected_title or ideation.get("selected_title") or manifest.get("selected_title"),
            "outline": read_input_file(args.outline_file).strip().splitlines() if args.outline_file else ideation.get("outline") or [],
            "updated_at": now_iso(),
        }
    )
    if ideation.get("selected_title"):
        manifest["selected_title"] = ideation["selected_title"]
    if ideation.get("outline"):
        manifest["outline"] = ideation["outline"]
    write_json(workspace / "ideation.json", ideation)
    save_manifest(workspace, manifest)
    safe_print_json({"workspace": str(workspace), "manifest": str(workspace / "manifest.json")})
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    raw = read_input_file(args.input)
    meta, body = split_frontmatter(raw)
    title = args.selected_title or manifest.get("selected_title") or meta.get("title") or extract_title_from_body(body) or manifest.get("topic") or "未命名文章"
    body = strip_leading_h1(body, title)
    summary = args.summary or meta.get("summary") or manifest.get("summary") or extract_summary(body)
    author = args.author or meta.get("author") or manifest.get("author") or ""
    article_meta = {"title": title, "summary": summary}
    if author:
        article_meta["author"] = author
    final = join_frontmatter(article_meta, body)
    article_path = workspace / "article.md"
    write_text(article_path, final)
    manifest.update(
        {
            "selected_title": title,
            "summary": summary,
            "author": author,
            "article_path": relative_posix(article_path, workspace),
            "outline": [item["text"] for item in extract_headings(body)] or manifest.get("outline") or [],
        }
    )
    save_manifest(workspace, manifest)
    print(str(article_path))
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    article_path = workspace / (args.input or manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到待评分文章：{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
    title = infer_title(manifest, meta, body)
    threshold = args.threshold or manifest.get("score_threshold") or DEFAULT_THRESHOLD
    report = build_score_report(title, body, manifest, threshold)

    if not report["passed"] and not args.no_rewrite:
        if args.rewrite_output:
            rewrite_path = Path(args.rewrite_output)
            if not rewrite_path.is_absolute():
                rewrite_path = workspace / rewrite_path
        else:
            stem = article_path.stem
            suffix = article_path.suffix or ".md"
            if stem.endswith("-rewrite"):
                stem = f"{stem}-next"
            else:
                stem = f"{stem}-rewrite"
            rewrite_path = workspace / f"{stem}{suffix}"
        rewrite = auto_rewrite_article(title, meta, body, report, manifest, rewrite_path)
        report["rewrite"] = rewrite
        manifest["rewrite_path"] = relative_posix(rewrite_path, workspace)
        manifest["rewrite_preview_score"] = rewrite["preview_score"]
        manifest["rewrite_preview_passed"] = rewrite["preview_passed"]
        if rewrite.get("evidence_report_path"):
            manifest["evidence_report_path"] = rewrite["evidence_report_path"]
            manifest["evidence_used_count"] = rewrite.get("evidence_used_count", 0)

    write_json(workspace / "score-report.json", report)
    write_text(workspace / "score-report.md", markdown_report(report))
    manifest["score_breakdown"] = report["score_breakdown"]
    manifest["score_total"] = report["total_score"]
    manifest["score_passed"] = report["passed"]
    save_manifest(workspace, manifest)
    safe_print_json(report)
    if args.fail_below and report["total_score"] < threshold:
        return 2
    return 0
def normalize_sections_for_images(body: str) -> tuple[list[str], list[dict[str, Any]]]:
    intro_blocks, sections = split_sections(body)
    normalized_intro: list[str] = []
    intro_directives: dict[str, Any] = {}
    for block in intro_blocks:
        directives, cleaned = parse_image_directives(block)
        intro_directives = merge_image_directives(intro_directives, directives)
        if cleaned:
            normalized_intro.append(cleaned)
    normalized_sections: list[dict[str, Any]] = []
    for section in sections:
        directives: dict[str, Any] = {}
        cleaned_blocks: list[str] = []
        for block in section.get("blocks") or []:
            block_directives, cleaned = parse_image_directives(block)
            directives = merge_image_directives(directives, block_directives)
            if cleaned:
                cleaned_blocks.append(cleaned)
        normalized_sections.append({**section, "blocks": cleaned_blocks, "image_directives": directives})
    if sections:
        return normalized_intro, normalized_sections
    blocks = [block for block in list_paragraphs(body) if block.strip()]
    pseudo_sections: list[dict[str, Any]] = []
    for index in range(0, len(blocks), 2):
        chunk = blocks[index:index + 2]
        directives: dict[str, Any] = {}
        cleaned_chunk: list[str] = []
        for block in chunk:
            block_directives, cleaned = parse_image_directives(block)
            directives = merge_image_directives(directives, block_directives)
            if cleaned:
                cleaned_chunk.append(cleaned)
        pseudo_sections.append(
            {
                "level": 2,
                "heading": f"\u6b63\u6587\u6bb5\u843d {index // 2 + 1}",
                "body": "\n\n".join(cleaned_chunk),
                "blocks": cleaned_chunk,
                "generated_heading": True,
                "image_directives": directives,
            }
        )
    return normalized_intro, pseudo_sections


def extract_section_metrics(section: dict[str, Any], section_index: int) -> dict[str, Any]:
    blocks = [block for block in section.get("blocks") or [] if block.strip()]
    char_count = sum(cjk_len(block) for block in blocks)
    paragraph_count = len(blocks)
    list_count = sum(1 for block in blocks if re.search(r"(^|\n)([-*]|\d+\.)\s+", block, flags=re.M))
    quote_count = sum(1 for block in blocks if block.lstrip().startswith(">") or block.lstrip().startswith("|"))
    info_hits = sum(
        1
        for block in blocks
        if re.search(r"\d{4}\u5e74|\d+(?:\.\d+)?%|\u7b2c\d+|\u6b65\u9aa4|\u6e05\u5355|\u7ed3\u8bba|\u5bf9\u6bd4|\u539f\u56e0|\u903b\u8f91|\u8d8b\u52bf|\u5982\u4f55|\u4e3a\u4ec0\u4e48|\u98ce\u9669|\u5efa\u8bae", block)
    )
    heading = section.get("heading") or f"\u6b63\u6587\u6bb5\u843d {section_index + 1}"
    heading_bonus = 1.0 if re.search(r"\u7ed3\u8bba|\u4e3a\u4ec0\u4e48|\u65b9\u6cd5|\u5efa\u8bae|\u5224\u65ad|\u98ce\u9669|\u5173\u952e|\u5f71\u54cd|\u5bf9\u6bd4|\u7b56\u7565|\u673a\u4f1a", heading) else 0.0
    weight = round(char_count / 260 + paragraph_count * 0.9 + list_count * 1.6 + quote_count * 1.1 + info_hits * 1.2 + heading_bonus, 2)
    excerpt_source = "\n\n".join(blocks[:2]) if blocks else heading
    excerpt = extract_summary(excerpt_source, 220)
    directives = section.get("image_directives") or {}
    return {
        "section_index": section_index,
        "heading": heading,
        "level": section.get("level", 2),
        "blocks": blocks,
        "char_count": char_count,
        "paragraph_count": paragraph_count,
        "list_count": list_count,
        "quote_count": quote_count,
        "info_hits": info_hits,
        "section_weight": weight,
        "excerpt": excerpt,
        "image_directives": directives,
    }


def infer_article_visual_strategy(
    title: str,
    summary: str,
    body: str,
    audience: str,
    controls: dict[str, Any],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    combined = "\n".join(part for part in [title, summary, body] if part).strip()
    lowered = combined.lower()
    list_heavy_sections = 0
    data_heavy_sections = 0
    metrics = [extract_section_metrics(section, index) for index, section in enumerate(sections)]
    for metric in metrics:
        if metric.get("list_count", 0) >= 2:
            list_heavy_sections += 1
        if metric.get("info_hits", 0) >= 2:
            data_heavy_sections += 1

    scores = {
        "narrative": count_keyword_hits(lowered, ARTICLE_VISUAL_HINT_WORDS["narrative"]) + max(0, count_keyword_hits(combined, ("我", "我们", "你", "他们")) - 2),
        "business": count_keyword_hits(lowered, ARTICLE_VISUAL_HINT_WORDS["business"]),
        "technical": count_keyword_hits(lowered, ARTICLE_VISUAL_HINT_WORDS["technical"]),
        "tutorial": count_keyword_hits(lowered, ARTICLE_VISUAL_HINT_WORDS["tutorial"]) + list_heavy_sections * 2,
        "comparison": count_keyword_hits(lowered, ARTICLE_VISUAL_HINT_WORDS["comparison"]),
        "data": count_keyword_hits(lowered, ARTICLE_VISUAL_HINT_WORDS["data"]) + data_heavy_sections * 2,
    }

    narrative_score = scores["narrative"]
    business_score = scores["business"]
    technical_score = scores["technical"]
    tutorial_score = scores["tutorial"]
    comparison_score = scores["comparison"]
    data_score = scores["data"]
    explanatory_score = tutorial_score + data_score + list_heavy_sections

    if narrative_score >= max(explanatory_score, business_score, technical_score) + 1:
        profile_key = "storytelling-human"
    elif business_score >= max(technical_score, explanatory_score) + 1:
        profile_key = "business-decision"
    elif tutorial_score >= 4 or explanatory_score >= 7:
        profile_key = "knowledge-explainer"
    elif technical_score >= 5 and data_score <= 2:
        profile_key = "editorial-analysis"
    elif data_score >= 5 and comparison_score >= 2:
        profile_key = "business-decision"
    elif count_keyword_hits(lowered, ("生活", "日常", "方式", "疗愈", "自然", "习惯")) >= 3:
        profile_key = "organic-lifestyle"
    elif count_keyword_hits(lowered, ("趋势", "拐点", "周期", "转向", "变化")) >= 3:
        profile_key = "abstract-trend"
    else:
        profile_key = "editorial-analysis"

    profile = resolve_style_profile(profile_key)
    style_mode = controls.get("style_mode") or (
        "mixed-by-type"
        if profile.get("style_mode") == "mixed-by-type" and explanatory_score >= max(4, narrative_score + 1)
        else "uniform"
    )

    type_bias = normalize_type_bias(
        {
            "正文插图": 0.62 + narrative_score * 0.04 - tutorial_score * 0.03 - data_score * 0.02,
            "对比图": 0.12 + comparison_score * 0.06 + business_score * 0.01,
            "信息图": 0.14 + data_score * 0.05 + tutorial_score * 0.02,
            "流程图": 0.12 + tutorial_score * 0.05 - narrative_score * 0.03,
        }
    )
    layout_family = controls.get("layout_family") or infer_layout_family_from_strategy(
        "narrative" if narrative_score > explanatory_score and narrative_score >= 3 else "data" if data_score >= tutorial_score and data_score >= 4 else "structural" if explanatory_score >= 4 else "conceptual",
        type_bias,
    )
    visual_direction = extract_summary(
        controls.get("theme")
        or title
        or summary
        or profile.get("theme")
        or "文章视觉方向",
        28,
    )
    content_mode = "narrative"
    if data_score >= max(tutorial_score, narrative_score, 4):
        content_mode = "data"
    elif explanatory_score >= max(narrative_score + 1, 4):
        content_mode = "structural"
    elif narrative_score <= 2 and (technical_score >= 4 or business_score >= 4):
        content_mode = "conceptual"
    if narrative_score >= max(explanatory_score, business_score, technical_score) + 1:
        visual_route = "people-emotion"
        visual_route_label = "人物情绪型"
        visual_route_reason = "正文更依赖人物处境和情绪代入，视觉应先服务读者共感。"
    elif data_score >= max(narrative_score, 4) or explanatory_score >= 7:
        visual_route = "data-explainer"
        visual_route_label = "数据解释型"
        visual_route_reason = "正文更依赖结构、对比和信息压缩，视觉应先服务理解。"
    elif count_keyword_hits(lowered, ("风险", "代价", "警报", "踩空", "边界", "失控", "误判", "冲突")) >= 3:
        visual_route = "conflict-alert"
        visual_route_label = "冲突警报型"
        visual_route_reason = "正文的主要张力来自风险、边界或冲突，视觉应先放大警报感。"
    else:
        visual_route = "cold-hard"
        visual_route_label = "冷硬判断型"
        visual_route_reason = "正文更偏判断和观点，需要克制、冷静、可扫读的视觉路线。"

    explicit_overrides = [
        name
        for name in ["preset", "theme", "style", "mood", "style_mode", "layout_family", "preset_cover", "preset_infographic", "preset_inline"]
        if str(controls.get(name) or "").strip()
    ]
    reasons = [
        f"文章视觉方向判定为“{profile['label']}”，因为内容中 {('叙事/情绪表达' if narrative_score >= max(explanatory_score, 3) else '解释/结构化信息' if explanatory_score >= 4 else '观点/趋势分析')} 更强。",
        f"内容模式为 `{content_mode}`，正文默认偏向 `{max(type_bias, key=type_bias.get)}`。",
        f"整篇视觉路线采用“{visual_route_label}”，避免封面和正文换频道。",
    ]
    if explicit_overrides:
        reasons.append("检测到显式图片参数覆盖：" + "、".join(explicit_overrides) + "。")

    return {
        "profile_key": profile_key,
        "profile": profile,
        "visual_direction": visual_direction,
        "visual_route": visual_route,
        "visual_route_label": visual_route_label,
        "visual_route_reason": visual_route_reason,
        "style_family": profile["label"],
        "content_mode": content_mode,
        "style_mode": style_mode,
        "layout_family": layout_family,
        "preset": controls.get("preset") or profile.get("preset") or "",
        "preset_cover": controls.get("preset_cover") or profile.get("cover_preset") or "",
        "preset_infographic": controls.get("preset_infographic") or profile.get("infographic_preset") or "",
        "preset_inline": controls.get("preset_inline") or profile.get("inline_preset") or "",
        "theme": controls.get("theme") or profile.get("theme") or visual_direction,
        "style": controls.get("style") or profile.get("style") or "",
        "mood": controls.get("mood") or profile.get("mood") or "",
        "custom_visual_brief": controls.get("custom_visual_brief") or profile.get("base_module") or "",
        "type_bias": type_bias,
        "decision_reasoning": reasons,
        "explicit_overrides": explicit_overrides,
        "audience": audience,
        "diversity_tags": [visual_route, layout_family, max(type_bias, key=type_bias.get), profile_key],
    }


def infer_section_image_decision(section_metric: dict[str, Any], article_strategy: dict[str, Any] | None = None, is_final: bool = False) -> dict[str, str]:
    directives = section_metric.get("image_directives") or {}
    if directives.get("type"):
        return {"type": directives["type"], "reason": "用户通过文内 image directive 显式指定了图片类型。", "decision_source": "directive"}
    heading = section_metric.get("heading", "")
    blocks = "\n\n".join(section_metric.get("blocks") or [])
    combined = f"{heading}\n{blocks}"
    paragraph_count = section_metric.get("paragraph_count", 0)
    list_count = section_metric.get("list_count", 0)
    info_hits = section_metric.get("info_hits", 0)
    char_count = section_metric.get("char_count", 0)
    strategy = article_strategy or {}
    type_bias = strategy.get("type_bias") or {}

    process_markers = len(re.findall(r"(?:^|\n)\s*(?:\d+[\.、)]|第[一二三四五六七八九十\d]+步|步骤[一二三四五六七八九十\d]+)", combined, flags=re.M))
    contrast_markers = len(re.findall(r"(?:对比|区别|差异|vs|VS|不是.+而是|A/B|优劣|更适合|相反)", combined, flags=re.I))
    framework_markers = len(re.findall(r"(?:框架|模型|地图|全景|清单|结论|指标|趋势|数据|维度|模块|层)", combined))
    summary_markers = len(re.findall(r"(?:总结|最后的判断|结论|一句话|归纳|总的来看|归根结底)", combined))
    sequence_phrases = len(re.findall(r"(?:先.+再.+最后|首先.+其次|接着|然后|最后)", combined))
    two_sided_entities = bool(re.search(r"(免费模式|订阅模式).*(免费模式|订阅模式)|A.+B|一边.+另一边|左边.+右边", combined))

    if process_markers >= 2 and list_count >= 1 and paragraph_count >= 1:
        return {"type": "流程图", "reason": "章节同时包含明确的步骤编号和多段结构，属于真实流程型内容。", "decision_source": "auto-structure"}
    if re.search(r"流程|SOP|执行路径|操作路径|落地步骤|实施步骤|第[一二三四五六七八九十\d]+步", heading) and (list_count >= 1 or sequence_phrases >= 1):
        return {"type": "流程图", "reason": "标题明确是流程/步骤章节，且正文确有结构化步骤。", "decision_source": "auto-structure"}
    if (contrast_markers >= 2 and (list_count >= 1 or paragraph_count >= 2)) or (contrast_markers >= 1 and two_sided_entities):
        return {"type": "对比图", "reason": "章节存在明显双边对照关系，适合用对比图表达。", "decision_source": "auto-structure"}
    if framework_markers >= 2 and (info_hits >= 3 or list_count >= 3):
        return {"type": "信息图", "reason": "章节更像框架/清单/指标总结，适合压缩成信息图。", "decision_source": "auto-structure"}
    if is_final and summary_markers >= 1 and (list_count >= 2 or info_hits >= 2 or type_bias.get("信息图", 0) >= 0.28):
        return {"type": "信息图", "reason": "结尾章节具备明显总结与结构化特征，适合做收束信息图。", "decision_source": "auto-summary"}
    if paragraph_count >= 5 and char_count >= 1500 and type_bias.get("正文插图", 0) >= 0.5:
        return {"type": "分隔图", "reason": "章节较长，且文章整体更偏叙事/概念表达，补一张分隔图比结构图更自然。", "decision_source": "auto-rhythm"}
    return {"type": "正文插图", "reason": "章节更适合用概念性正文插图承接，而不是先验地转成结构图。", "decision_source": "auto-default"}


def infer_section_image_type(section_metric: dict[str, Any], article_strategy: dict[str, Any] | None = None, is_final: bool = False) -> str:
    return infer_section_image_decision(section_metric, article_strategy=article_strategy, is_final=is_final)["type"]


def infer_closing_image_decision(final_metric: dict[str, Any] | None, article_strategy: dict[str, Any]) -> dict[str, str]:
    if not final_metric:
        return {"type": "信息图", "reason": "缺少明确的收束章节，使用信息图作为默认全文总结图。", "decision_source": "auto-fallback"}
    final_decision = infer_section_image_decision(final_metric, article_strategy=article_strategy, is_final=True)
    if final_decision["type"] in {"信息图", "对比图", "流程图"}:
        return final_decision
    type_bias = article_strategy.get("type_bias") or {}
    if type_bias.get("信息图", 0) >= 0.3 and (final_metric.get("info_hits", 0) >= 1 or final_metric.get("list_count", 0) >= 1):
        return {"type": "信息图", "reason": "文章整体更偏结构化解释，结尾使用信息图收束更合适。", "decision_source": "auto-summary"}
    return {"type": "正文插图", "reason": "结尾更适合概念收束插图，不强制转成信息图。", "decision_source": "auto-summary"}


def estimate_inline_image_count(body: str, explicit_count: int, density: str = "balanced") -> int:
    _, sections = normalize_sections_for_images(body)
    article_strategy = infer_article_visual_strategy("", extract_summary(body), body, "大众读者", {"density": density}, sections)
    settings = resolve_inline_density_settings(
        body,
        explicit_count,
        density,
        article_strategy=article_strategy,
        sections=sections,
    )
    return int(settings.get("target_inline_count") or 0)


def choose_section_block_index(section_metric: dict[str, Any], variant: int) -> int:
    blocks = [block for block in (section_metric.get("blocks") or []) if str(block).strip()]
    paragraph_count = len(blocks) if blocks else int(section_metric.get("paragraph_count") or 0)
    if paragraph_count <= 1:
        return 0
    if not blocks:
        # fallback: keep previous placement heuristic when正文块不可用
        if variant <= 0:
            return 1 if paragraph_count >= 3 else 0
        if paragraph_count <= 3:
            return paragraph_count - 1
        return min(paragraph_count - 1, max(2, paragraph_count // 2))

    def block_score(index: int, block: str) -> float:
        length = cjk_len(block)
        score = 0.0
        if 80 <= length <= 380:
            score += 3.0
        elif 40 <= length < 80:
            score += 1.0
        elif length > 380:
            score += 1.0
        else:
            score -= 2.0

        if re.search(r"(^|\n)\s*(?:[-*]\s+|\d+[\.、]\s+)", block, flags=re.M):
            score += 2.0
        if re.search(r"\d{4}年|\d+(?:\.\d+)?%|\d+(?:\.\d+)?(?:万|亿|个|次|倍)", block):
            score += 2.0
        if re.search(r"步骤|清单|对比|区别|误区|结论|框架|模型|指标|数据|案例|例如|比如|要点|建议", block):
            score += 1.5
        if "：" in block or ":" in block:
            score += 0.5
        if length < 60 and re.search(r"^(所以|因此|然后|接下来|下面|再说|另外|总之)[，。:：]?$", re.sub(r"\s+", "", block)):
            score -= 3.0
        if block.strip().startswith(">"):
            score -= 1.0

        if variant <= 0:
            desired = 1 if paragraph_count >= 3 else 0
            if index == 0 and paragraph_count >= 3:
                score -= 1.0
        else:
            desired = min(paragraph_count - 1, max(2, paragraph_count // 2 + variant))
            if index < paragraph_count // 2:
                score -= 0.5
        score -= abs(index - desired) * 0.25
        return score

    desired = 1 if paragraph_count >= 3 else 0
    if variant > 0:
        desired = min(paragraph_count - 1, max(2, paragraph_count // 2 + variant))
    scored = [(block_score(i, blocks[i]), -abs(i - desired), i) for i in range(paragraph_count)]
    scored.sort(reverse=True)
    return int(scored[0][2])


def select_sections_for_images(
    body: str,
    inline_limit: int,
    article_strategy: dict[str, Any] | None = None,
    *,
    allow_section_reuse: bool = False,
) -> list[dict[str, Any]]:
    _, sections = normalize_sections_for_images(body)
    strategy = article_strategy or infer_article_visual_strategy("", extract_summary(body), body, "大众读者", {"density": "balanced"}, sections)
    metrics = []
    for index, section in enumerate(sections):
        if is_reference_heading(section.get("heading", "")):
            continue
        metric = extract_section_metrics(section, index)
        decision = infer_section_image_decision(metric, article_strategy=strategy, is_final=index == len(sections) - 1)
        metric["inferred_image_type"] = decision["type"]
        metric["inferred_image_type_reason"] = decision["reason"]
        metric["inferred_image_type_source"] = decision["decision_source"]
        metrics.append(metric)
    if not metrics or inline_limit <= 0:
        return []

    slots: list[dict[str, Any]] = []
    selected_unique: set[int] = set()
    force_slots: list[dict[str, Any]] = []

    eligible_metrics = [metric for metric in metrics if not (metric.get("image_directives") or {}).get("skip")]
    if not eligible_metrics:
        return []

    for metric in eligible_metrics:
        directives = metric.get("image_directives") or {}
        if not directives.get("force") and directives.get("count", 0) <= 0:
            continue
        desired = directives.get("count", 1 if directives.get("force") else 0)
        for variant in range(max(1, desired) if directives.get("force") else desired):
            force_slots.append({"section_index": metric["section_index"], "variant": variant, "forced": True})
        selected_unique.add(metric["section_index"])

    for slot in force_slots[:inline_limit]:
        slots.append(slot)

    directive_metrics = [
        metric
        for metric in eligible_metrics
        if str((metric.get("image_directives") or {}).get("type") or "").strip()
    ]
    for metric in directive_metrics:
        if len(slots) >= inline_limit:
            break
        if metric["section_index"] in {slot["section_index"] for slot in slots}:
            continue
        slots.append({"section_index": metric["section_index"], "variant": 0})
        selected_unique.add(metric["section_index"])

    if len(slots) < inline_limit and len(eligible_metrics) >= 3 and inline_limit >= 3:
        midpoint = max(1, len(eligible_metrics) // 2)
        first_half = eligible_metrics[:midpoint]
        second_half = eligible_metrics[midpoint:]
        if first_half:
            best_first = max(first_half, key=lambda item: item["section_weight"])
            if best_first["section_index"] not in {slot["section_index"] for slot in slots}:
                slots.append({"section_index": best_first["section_index"], "variant": 0})
            selected_unique.add(best_first["section_index"])
        if second_half:
            best_second = max(second_half, key=lambda item: item["section_weight"])
            if best_second["section_index"] not in selected_unique:
                slots.append({"section_index": best_second["section_index"], "variant": 0})
                selected_unique.add(best_second["section_index"])
    elif len(slots) < inline_limit:
        best_single = max(eligible_metrics, key=lambda item: item["section_weight"])
        slots.append({"section_index": best_single["section_index"], "variant": 0})
        selected_unique.add(best_single["section_index"])

    for metric in sorted(eligible_metrics, key=lambda item: (item["section_weight"], item["info_hits"]), reverse=True):
        if len(slots) >= inline_limit:
            break
        if metric["section_index"] in selected_unique:
            continue
        slots.append({"section_index": metric["section_index"], "variant": 0})
        selected_unique.add(metric["section_index"])

    if allow_section_reuse and len(slots) < inline_limit:
        for metric in sorted(eligible_metrics, key=lambda item: (item["section_weight"], item["char_count"], item["info_hits"]), reverse=True):
            if len(slots) >= inline_limit:
                break
            existing = sum(1 for slot in slots if slot["section_index"] == metric["section_index"])
            directives = metric.get("image_directives") or {}
            max_repeat = max(2, directives.get("count", 0)) if directives.get("force") else 2
            if metric["paragraph_count"] >= 4 and metric["char_count"] >= 700 and existing < max_repeat:
                slots.append({"section_index": metric["section_index"], "variant": existing})

    selected_metrics: list[dict[str, Any]] = []
    for slot in sorted(slots, key=lambda item: (item["section_index"], item["variant"])):
        metric = next(item for item in metrics if item["section_index"] == slot["section_index"])
        block_index = choose_section_block_index(metric, slot["variant"])
        placement_reason = "\u6309\u7ae0\u8282\u6743\u91cd\u548c\u4fe1\u606f\u5bc6\u5ea6\u4f18\u5148\u63d2\u56fe"
        if (metric.get("image_directives") or {}).get("force"):
            placement_reason = "\u6309\u6587\u5185\u6807\u8bb0\u5f3a\u5236\u914d\u56fe"
        if slot["variant"] > 0:
            placement_reason = "\u957f\u7ae0\u8282\u8865\u56fe\uff0c\u907f\u514d\u540e\u534a\u6bb5\u7eaf\u6587\u5b57\u5806\u79ef"
        image_type = metric.get("inferred_image_type") or "正文插图"
        if image_type == "正文插图" and slot["variant"] > 0 and metric["char_count"] >= 1200:
            image_type = "分隔图"
        selected_metrics.append(
            {
                **metric,
                "variant": slot["variant"],
                "placement_block_index": block_index,
                "placement_reason": placement_reason,
                "image_type": image_type,
                "image_type_reason": metric.get("inferred_image_type_reason") or "按章节内容自动判定。",
                "image_type_source": metric.get("inferred_image_type_source") or "auto-default",
            }
        )
    return selected_metrics


def image_planning_diagnostics(sections: list[dict[str, Any]], inline_sections: list[dict[str, Any]], requested_inline_count: int) -> dict[str, Any]:
    normalized_sections = []
    for section in sections:
        item = dict(section)
        item["is_reference_section"] = is_reference_heading(section.get("heading", ""))
        normalized_sections.append(item)
    return _image_planning_diagnostics(normalized_sections, inline_sections, requested_inline_count)

def cmd_plan_images(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    try:
        from core.account_strategy import infer_visual_preset, load_account_strategy
    except ImportError:
        infer_visual_preset = None
        load_account_strategy = None
    article_path = workspace / (manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"\u627e\u4e0d\u5230\u6587\u7ae0\u6587\u4ef6\uff1a{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
    title = infer_title(manifest, meta, body)
    summary = manifest.get("summary") or meta.get("summary") or extract_summary(body)
    account_strategy = load_account_strategy(workspace, manifest, create_if_missing=True) if load_account_strategy else (manifest.get("account_strategy") or {})
    controls = resolve_image_controls(manifest.get("image_controls"), args, title=title, summary=summary, body=body)
    strategy_text_policy = dict((account_strategy.get("image_text_policy") or {})) if isinstance(account_strategy, dict) else {}
    controls["text_policy_overrides"] = strategy_text_policy
    controls["label_language"] = str(controls.get("label_language") or strategy_text_policy.get("label_language") or "zh-CN")
    if infer_visual_preset and not _has_explicit_image_controls(args):
        controls["density_mode"] = normalize_image_density_mode(account_strategy.get("image_density") or controls.get("density_mode") or controls.get("density") or "auto")
        controls["density"] = controls["density_mode"]
    manifest["image_controls"] = controls
    audience = manifest.get("audience") or "\u5927\u4f17\u8bfb\u8005"
    intro_blocks, sections = normalize_sections_for_images(body)
    article_strategy = infer_article_visual_strategy(title, summary, body, audience, controls, sections)
    effective_controls = build_effective_image_controls(controls, article_strategy)
    effective_controls["profile_key"] = article_strategy.get("profile_key", "")
    if infer_visual_preset and not _has_explicit_image_controls(args):
        preset = infer_visual_preset(title, summary, body, account_strategy)
        blocked = {str(item).strip() for item in (account_strategy.get("blocked_image_presets") or []) if str(item).strip()}
        if preset and preset not in blocked:
            effective_controls["preset"] = preset
            effective_controls["preset_label"] = IMAGE_STYLE_PRESETS.get(preset, {}).get("label", effective_controls.get("preset_label", ""))
            effective_controls["preset_cover"] = preset
            effective_controls["preset_inline"] = preset if preset != "professional-corporate" else "notion"
            effective_controls["preset_infographic"] = "notion"
            effective_controls["preset_cover_label"] = IMAGE_STYLE_PRESETS.get(effective_controls["preset_cover"], {}).get("label", "")
            effective_controls["preset_inline_label"] = IMAGE_STYLE_PRESETS.get(effective_controls["preset_inline"], {}).get("label", "")
            effective_controls["preset_infographic_label"] = IMAGE_STYLE_PRESETS.get(effective_controls["preset_infographic"], {}).get("label", "")
    if not _has_explicit_image_controls(args):
        preferred_layout = str(account_strategy.get("image_layout_family") or "").strip()
        if preferred_layout and effective_controls.get("layout_family") not in {"process", "comparison"}:
            effective_controls["layout_family"] = preferred_layout
    provider = image_provider_from_env(args.provider)
    density_settings = resolve_inline_density_settings(
        body,
        int(getattr(args, "inline_count", 0) or effective_controls.get("inline_count") or 0),
        effective_controls.get("density_mode") or effective_controls.get("density") or "auto",
        article_strategy=article_strategy,
        sections=sections,
    )
    inline_limit = int(density_settings.get("target_inline_count") or 0)
    max_inline_images = int(account_strategy.get("max_inline_images") or 0) if isinstance(account_strategy, dict) else 0
    structured_bonus = 1 if any(keyword in f"{title}\n{summary}\n{body}" for keyword in ["对比", "流程", "复盘", "框架"]) else 0
    if max_inline_images and not _has_explicit_image_controls(args):
        inline_limit = min(inline_limit, max_inline_images + structured_bonus)
    inline_min, inline_max = density_settings.get("inline_range") or image_density_range(effective_controls.get("density_mode") or effective_controls.get("density") or "auto")
    inline_sections = select_sections_for_images(
        body,
        inline_limit,
        article_strategy=article_strategy,
        allow_section_reuse=bool(density_settings.get("allow_section_reuse")),
    )
    intro_char_count = sum(cjk_len(block) for block in intro_blocks)
    content_sections = [section for section in sections if not is_reference_heading(section.get("heading", ""))]
    final_section = content_sections[-1] if content_sections else None
    final_metric = extract_section_metrics(final_section, sections.index(final_section)) if final_section else None
    closing_decision = infer_closing_image_decision(final_metric, article_strategy)
    allow_closing_image = str(effective_controls.get("allow_closing_image") or "auto")
    if (effective_controls.get("density_mode") or effective_controls.get("density")) == "none":
        allow_closing_image = "off"
    closing_enabled = should_include_closing_image(
        allow_closing_image,
        final_metric=final_metric,
        closing_decision=closing_decision,
        article_strategy=article_strategy,
        inline_count=inline_limit,
    )
    diagnostics = image_planning_diagnostics(sections, inline_sections, inline_limit)

    items: list[dict[str, Any]] = [
        {
            "id": "cover-01",
            "type": "\u5c01\u9762\u56fe",
            "target_section": "cover",
            "target_section_index": -1,
            "insert_strategy": "cover_only",
            "placement_block_index": -1,
            "placement_reason": "\u4ec5\u4f5c\u4e3a\u516c\u4f17\u53f7\u5c01\u9762\u4e0e thumb_media_id\uff0c\u4e0d\u8fdb\u5165\u6b63\u6587",
            "section_weight": 0,
            "alt": f"{title} \u5c01\u9762\u56fe",
            "aspect_ratio": "16:9",
            "section_heading": title,
            "section_excerpt": extract_summary("\n\n".join(intro_blocks[:2]) if intro_blocks else summary, 220),
            "decision_source": "required-cover",
            "type_reason": "封面图是整篇文章的固定入口图，用于公众号封面与缩略图。",
            "style_reason": "封面图按整篇文章的自动视觉策略选择主视觉语言。",
            "text_policy": "none",
        },
    ]
    if closing_enabled:
        items.append(
            {
                "id": "closing-01",
                "type": closing_decision["type"],
                "target_section": final_metric["heading"] if final_metric else "\u6587\u672b\u603b\u7ed3",
                "target_section_index": final_metric["section_index"] if final_metric else -1,
                "insert_strategy": "section_end",
                "placement_block_index": final_metric["paragraph_count"] if final_metric else 0,
                "placement_reason": "\u5168\u6587\u6536\u675f\u578b\u914d\u56fe\uff0c\u653e\u5728\u6587\u672b\u5185\u5bb9\u6bb5\u843d\u4e4b\u540e\u7528\u4e8e\u6536\u675f\u5168\u6587",
                "section_weight": round((final_metric["section_weight"] if final_metric else 0) + intro_char_count / 500, 2),
                "alt": f"{title} {closing_decision['type']}",
                "aspect_ratio": "3:4" if closing_decision["type"] == "信息图" else "16:9",
                "section_heading": final_metric["heading"] if final_metric else "\u6587\u672b\u603b\u7ed3",
                "section_excerpt": final_metric.get("excerpt", "") if final_metric else extract_summary(summary, 220),
                "decision_source": closing_decision["decision_source"],
                "type_reason": closing_decision["reason"],
                "style_reason": "收束图沿用整篇自动视觉策略，并根据结尾章节是否结构化决定是否转为信息图。",
                "text_policy": "short-zh" if closing_decision["type"] in {"信息图", "对比图", "流程图"} else "none",
            }
        )
    type_occurrence: dict[str, int] = {}
    for item in items:
        occurrence_index = type_occurrence.get(item["type"], 0)
        variant = pick_layout_variant(item["type"], occurrence_index, effective_controls.get("layout_family", ""))
        item["layout_variant_key"] = variant["key"]
        item["layout_variant_label"] = variant["label"]
        item["layout_variant_instruction"] = variant["instruction"]
        type_occurrence[item["type"]] = occurrence_index + 1

    for index, section in enumerate(inline_sections, start=1):
        image_type = section.get("image_type") or "\u6b63\u6587\u63d2\u56fe"
        occurrence_index = type_occurrence.get(image_type, 0)
        variant = pick_layout_variant(image_type, occurrence_index, effective_controls.get("layout_family", ""))
        blocks = [block for block in (section.get("blocks") or []) if block.strip()]
        placement_index = int(section.get("placement_block_index", 0) or 0)
        anchor_index = 0
        if blocks:
            anchor_index = max(0, min(placement_index, len(blocks) - 1))
        anchor_excerpt = extract_summary(blocks[anchor_index], 220) if blocks else section.get("excerpt", "")
        items.append(
            {
                "id": f"inline-{index:02d}",
                "type": image_type,
                "target_section": section["heading"],
                "target_section_index": section["section_index"],
                "insert_strategy": "section_middle",
                "placement_block_index": section["placement_block_index"],
                "placement_reason": section["placement_reason"],
                "anchor_block_excerpt": anchor_excerpt,
                "section_weight": section["section_weight"],
                "alt": f"{section['heading']} {image_type}",
                "aspect_ratio": "16:9",
                "section_heading": section["heading"],
                "section_excerpt": section.get("excerpt", ""),
                "layout_variant_key": variant["key"],
                "layout_variant_label": variant["label"],
                "layout_variant_instruction": variant["instruction"],
                "decision_source": section.get("image_type_source") or "auto-default",
                "type_reason": section.get("image_type_reason") or "按章节内容自动判定。",
                "style_reason": "正文插图风格由整篇文章的自动视觉策略决定；若图片类型特殊，再按用途做轻微分化。",
                "text_policy": (
                    "none"
                    if image_type in {"正文插图", "分隔图"}
                    else "short-zh-numeric" if image_type in {"信息图", "流程图"} else "short-zh"
                ),
            }
        )
        type_occurrence[image_type] = occurrence_index + 1

    article_category = infer_article_category_label(title, summary, body)
    for item in items:
        role, role_reason = infer_image_role(item, article_category=article_category, article_strategy=article_strategy)
        item["role"] = role
        item["role_reason"] = role_reason

    items = _enrich_plan_items(
        items,
        title=title,
        summary=summary,
        body=body,
        provider=provider,
        article_strategy=article_strategy,
        effective_controls=effective_controls,
        audience=audience,
        cfg=_image_planning_config(),
    )

    decision_source = "explicit" if article_strategy.get("explicit_overrides") else "auto"
    auto_reason = "；".join(article_strategy.get("decision_reasoning") or []) or f"按文章内容自动判定为 {article_category}。"
    plan = _build_plan_payload(
        title=title,
        body=body,
        provider=provider,
        decision_source=decision_source,
        auto_reason=auto_reason,
        inline_sections=inline_sections,
        requested_inline_count=inline_limit,
        diagnostics=diagnostics,
        effective_controls=effective_controls,
        user_controls=controls,
        article_strategy=article_strategy,
        items=items,
        inline_range=(int(inline_min), int(inline_max)),
        allow_closing_image=allow_closing_image,
        closing_image_enabled=closing_enabled,
        cfg=_image_planning_config(),
    )
    article_category = plan["article_category"]
    write_json(workspace / "image-plan.json", plan)
    write_json(workspace / "image-strategy.json", plan["article_visual_strategy"])
    write_image_outline_artifacts(workspace, title, audience, effective_controls, plan)
    manifest["image_provider"] = provider
    manifest["image_plan_path"] = "image-plan.json"
    manifest["image_strategy_path"] = "image-strategy.json"
    manifest["image_outline_path"] = "image-outline.json"
    manifest["image_outline_markdown_path"] = "image-outline.md"
    manifest["image_prompt_dir"] = "prompts/images"
    manifest["image_decision_source"] = decision_source
    manifest["image_article_category"] = article_category
    manifest["image_density_mode"] = effective_controls.get("density_mode") or effective_controls.get("density") or "auto"
    manifest["image_inline_target"] = int(plan.get("requested_inline_count") or 0)
    manifest["allow_closing_image"] = allow_closing_image
    save_manifest(workspace, manifest)
    safe_print_json(plan)
    return 0

def cmd_generate_images(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    plan_path = workspace / "image-plan.json"
    plan = read_json(plan_path, default=None)
    if not plan:
        raise SystemExit("缺少 image-plan.json，请先运行 plan-images。")
    requested_provider = args.provider or plan.get("provider")
    provider = image_provider_from_env(requested_provider)
    images_dir = ensure_dir(workspace / "assets" / "images")
    generated = {}
    for item in plan.get("items") or []:
        filename = f"{item['id']}.png"
        output_path = images_dir / filename
        aspect = item.get("aspect_ratio") or "16:9"
        prompt_path = workspace / "prompts" / "images" / f"{item['id']}.md"
        prompt_override = extract_prompt_from_markdown(prompt_path)
        effective_prompt = prompt_override or item["prompt"]
        if prompt_override:
            item["prompt"] = prompt_override
        if args.dry_run:
            width, height = make_fallback_card_png(output_path, item)
            result = {
                "provider": provider,
                "prompt": effective_prompt,
                "revised_prompt": effective_prompt,
                "width": width,
                "height": height,
                "source_meta": {"dry_run": True, "prompt_source": "prompt-file" if prompt_override else "plan", "fallback_local_card": True},
            }
        elif provider == "gemini-web":
            try:
                result = generate_gemini_web_image(effective_prompt, output_path)
            except SystemExit as exc:
                fallback = fallback_image_provider(provider)
                message = str(exc)
                result = None
                if fallback:
                    try:
                        if fallback == "gemini-api":
                            result = generate_gemini_api_image(effective_prompt, output_path, args.gemini_model, aspect)
                        else:
                            result = generate_openai_image(effective_prompt, output_path, args.openai_model, aspect)
                        result["source_meta"] = {
                            **result.get("source_meta", {}),
                            "fallback_from": "gemini-web",
                            "fallback_reason": message,
                        }
                        provider = fallback
                    except SystemExit as fallback_exc:
                        message = f"{message}; fallback {fallback} failed: {fallback_exc}"
                        result = None
                if result is None:
                    width, height = make_fallback_card_png(output_path, item)
                    result = {
                        "provider": "local-card",
                        "prompt": effective_prompt,
                        "revised_prompt": effective_prompt,
                        "width": width,
                        "height": height,
                        "source_meta": {
                            "fallback_from": "gemini-web",
                            "fallback_reason": message,
                            "fallback_local_card": True,
                        },
                    }
        elif provider == "gemini-api":
            result = generate_gemini_api_image(effective_prompt, output_path, args.gemini_model, aspect)
        elif provider == "openai-image":
            result = generate_openai_image(effective_prompt, output_path, args.openai_model, aspect)
        else:
            raise SystemExit(f"不支持的图片后端：{provider}")
        item["provider"] = result.get("provider") or provider
        item["asset_path"] = relative_posix(output_path, workspace)
        item["revised_prompt"] = result["revised_prompt"]
        item["prompt_source"] = "prompt-file" if prompt_override else "plan"
        item["source_meta"] = result["source_meta"]
        item["width"] = result["width"]
        item["height"] = result["height"]
        generated[item["id"]] = item["asset_path"]
    write_json(plan_path, plan)
    manifest["image_provider"] = provider
    manifest.setdefault("asset_paths", {}).update(generated)
    save_manifest(workspace, manifest)
    safe_print_json(plan)
    return 0


def cmd_assemble(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    article_path = workspace / (manifest.get("article_path") or "article.md")
    plan = read_json(workspace / "image-plan.json", default=None)
    if not article_path.exists():
        raise SystemExit(f"找不到文章文件：{article_path}")
    if not plan:
        raise SystemExit("缺少 image-plan.json，请先运行 plan-images。")
    meta, body = split_frontmatter(read_text(article_path))
    intro_blocks, sections = normalize_sections_for_images(body)
    assembled_body, inserted = assemble_body(intro_blocks, sections, list(plan.get("items") or []))
    assembled_path = workspace / "assembled.md"
    write_text(assembled_path, join_frontmatter(meta, assembled_body.strip()))
    manifest["assembled_path"] = relative_posix(assembled_path, workspace)
    manifest["asset_paths"]["assembled_markdown"] = manifest["assembled_path"]
    cover = next((entry.get("asset_path") for entry in (plan.get("items") or []) if entry.get("type") == "封面图" and entry.get("asset_path")), None)
    if cover:
        manifest["asset_paths"]["cover"] = cover
    save_manifest(workspace, manifest)
    print(str(assembled_path))
    return 0

def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", lambda m: f"<code>{html.escape(m.group(1))}</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>', escaped)
    return escaped


def try_markdown_package(body: str) -> str | None:
    try:
        import markdown as markdown_module
    except Exception:
        return None
    return markdown_module.markdown(body, extensions=["extra", "sane_lists", "tables"])


def fallback_markdown_to_html(body: str) -> str:
    lines = body.splitlines()
    out: list[str] = []
    in_code = False
    code_lines: list[str] = []
    paragraph: list[str] = []
    list_mode: str | None = None
    list_buffer: list[str] = []
    quote_buffer: list[str] = []
    table_buffer: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append(f"<p>{inline_markdown(' '.join(paragraph).strip())}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal list_buffer, list_mode
        if list_buffer and list_mode:
            tag = "ul" if list_mode == "ul" else "ol"
            out.append(f"<{tag}>" + "".join(f"<li>{inline_markdown(item)}</li>" for item in list_buffer) + f"</{tag}>")
        list_buffer = []
        list_mode = None

    def flush_quote() -> None:
        nonlocal quote_buffer
        if quote_buffer:
            out.append(f"<blockquote>{''.join(f'<p>{inline_markdown(item)}</p>' for item in quote_buffer)}</blockquote>")
        quote_buffer = []

    def flush_table() -> None:
        nonlocal table_buffer
        if len(table_buffer) >= 2 and re.match(r"^\|?\s*[-: ]+\|", table_buffer[1]):
            headers = [cell.strip() for cell in table_buffer[0].strip("|").split("|")]
            body_rows = table_buffer[2:]
            html_rows = ["<table><thead><tr>" + "".join(f"<th>{inline_markdown(cell)}</th>" for cell in headers) + "</tr></thead><tbody>"]
            for row in body_rows:
                cells = [cell.strip() for cell in row.strip("|").split("|")]
                html_rows.append("<tr>" + "".join(f"<td>{inline_markdown(cell)}</td>" for cell in cells) + "</tr>")
            html_rows.append("</tbody></table>")
            out.append("".join(html_rows))
        else:
            for row in table_buffer:
                paragraph.append(row)
        table_buffer = []

    for line in lines + [""]:
        if line.startswith("```"):
            flush_paragraph()
            flush_list()
            flush_quote()
            flush_table()
            if in_code:
                code_html = html.escape("\n".join(code_lines))
                out.append(f"<pre><code>{code_html}</code></pre>")
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if line.strip().startswith("|"):
            flush_paragraph()
            flush_list()
            flush_quote()
            table_buffer.append(line)
            continue
        if table_buffer:
            flush_table()
        match_image = re.match(r"^!\[(.*?)\]\((.+?)\)\s*$", line.strip())
        if match_image:
            flush_paragraph()
            flush_list()
            flush_quote()
            out.append(f'<figure><img src="{html.escape(match_image.group(2), quote=True)}" alt="{html.escape(match_image.group(1), quote=True)}" /></figure>')
            continue
        match_heading = re.match(r"^(#{2,4})\s+(.+?)\s*$", line)
        if match_heading:
            flush_paragraph()
            flush_list()
            flush_quote()
            level = len(match_heading.group(1))
            out.append(f"<h{level}>{inline_markdown(match_heading.group(2))}</h{level}>")
            continue
        if re.match(r"^-{3,}\s*$", line.strip()):
            flush_paragraph()
            flush_list()
            flush_quote()
            out.append("<hr />")
            continue
        match_ul = re.match(r"^[-*]\s+(.+)$", line)
        if match_ul:
            flush_paragraph()
            flush_quote()
            if list_mode not in {None, "ul"}:
                flush_list()
            list_mode = "ul"
            list_buffer.append(match_ul.group(1).strip())
            continue
        match_ol = re.match(r"^\d+\.\s+(.+)$", line)
        if match_ol:
            flush_paragraph()
            flush_quote()
            if list_mode not in {None, "ol"}:
                flush_list()
            list_mode = "ol"
            list_buffer.append(match_ol.group(1).strip())
            continue
        match_quote = re.match(r"^>\s+(.+)$", line)
        if match_quote:
            flush_paragraph()
            flush_list()
            quote_buffer.append(match_quote.group(1).strip())
            continue
        if not line.strip():
            flush_paragraph()
            flush_list()
            flush_quote()
            continue
        paragraph.append(line.strip())
    return "\n".join(out)


def markdown_to_html(body: str) -> str:
    rendered = try_markdown_package(body)
    if rendered is not None:
        return rendered
    return fallback_markdown_to_html(body)


def build_reference_cards_wechat(reference_entries: list[dict[str, Any]], accent_color: str) -> str:
    if not reference_entries:
        return ""
    cards = []
    for entry in reference_entries:
        cards.append(
            '<section style="margin:12px 0;padding:14px 16px;border:1px solid #e5e7eb;border-radius:16px;background:#fafafa;">'
            f'<div style="display:flex;align-items:flex-start;gap:12px;">'
            f'<div style="min-width:32px;height:32px;border-radius:999px;background:{accent_color};color:#ffffff;font-size:13px;line-height:32px;text-align:center;font-weight:700;">[{entry["index"]}]</div>'
            '<div style="flex:1;min-width:0;">'
            f'<div style="font-size:16px;line-height:1.5;color:#111827;font-weight:700;">{html.escape(entry["title"])}</div>'
            f'<div style="margin-top:6px;font-size:14px;line-height:1.75;color:#4b5563;">{html.escape(entry["description"])}</div>'
            f'<a style="display:inline-block;margin-top:8px;font-size:13px;line-height:1.6;color:{accent_color};text-decoration:none;word-break:break-all;" href="{html.escape(entry["url"], quote=True)}">{html.escape(entry["domain"])}</a>'
            '</div></div></section>'
        )
    return ''.join(cards)


def build_wechat_fragment(content_html: str, title: str, summary: str, accent_color: str, reference_entries: list[dict[str, Any]] | None = None) -> str:
    styled = content_html
    styled = styled.replace('<blockquote class="insight-card">', f'<blockquote style="margin:18px 0;padding:16px 18px;border-radius:18px;background:#f8fafc;border:1px solid #e2e8f0;color:#0f172a;box-shadow:0 8px 24px rgba(15,23,42,0.04);">')
    styled = styled.replace('<blockquote>', f'<blockquote style="margin:18px 0;padding:16px 18px;border-radius:18px;background:#f8fafc;border:1px solid #e2e8f0;color:#0f172a;box-shadow:0 8px 24px rgba(15,23,42,0.04);">')
    replacements = {
        '<p>': '<p style="margin:14px 0;line-height:1.9;font-size:16px;color:#1f2937;letter-spacing:0.1px;">',
        '<h2>': f'<h2 style="margin:34px 0 14px;padding-left:10px;border-left:3px solid {accent_color};font-size:22px;line-height:1.45;color:#111827;font-weight:700;">',
        '<h3>': '<h3 style="margin:26px 0 10px;font-size:18px;line-height:1.5;color:#111827;font-weight:700;">',
        '<h4>': '<h4 style="margin:22px 0 8px;font-size:17px;line-height:1.5;color:#111827;font-weight:700;">',
        '<ul>': '<ul style="margin:16px 0;padding-left:22px;color:#1f2937;">',
        '<ol>': '<ol style="margin:16px 0;padding-left:22px;color:#1f2937;">',
        '<li>': '<li style="margin:8px 0;line-height:1.9;">',
        '<pre>': '<pre style="overflow-x:auto;margin:18px 0;padding:14px 16px;border-radius:14px;background:#111827;color:#f9fafb;">',
        '<code>': '<code style="padding:2px 6px;border-radius:6px;background:#f3f4f6;font-family:Cascadia Code,Consolas,monospace;font-size:0.92em;">',
        '<table>': '<table style="width:100%;border-collapse:collapse;font-size:14px;margin:16px 0;border-radius:12px;overflow:hidden;">',
        '<th>': '<th style="padding:10px 12px;border:1px solid #e5e7eb;background:#f8fafc;text-align:left;vertical-align:top;">',
        '<td>': '<td style="padding:10px 12px;border:1px solid #e5e7eb;text-align:left;vertical-align:top;">',
        '<hr />': '<hr style="border:none;border-top:1px solid #e5e7eb;margin:30px 0;" />',
        '<strong>': '<strong style="color:#111827;font-weight:700;">',
        '<em>': '<em style="font-style:italic;">',
    }
    for old, new in replacements.items():
        styled = styled.replace(old, new)
    styled = styled.replace('<figure>', '<p style="margin:22px 0 18px;text-align:center;">')
    styled = styled.replace('</figure>', '</p>')
    styled = re.sub(r'<a\s+href=', f'<a style="color:{accent_color};text-decoration:none;border-bottom:1px solid rgba(15,118,110,0.18);" href=', styled)
    styled = re.sub(r'<img\s+', '<img style="display:block;width:100%;height:auto;margin:0 auto;border-radius:16px;box-shadow:0 10px 30px rgba(15,23,42,0.06);" ', styled)
    styled = re.sub(r'<sup class="footnote-marker">\[(\d+)\]</sup>', r'<sup style="color:#0f766e;font-size:12px;font-weight:700;vertical-align:super;">[\1]</sup>', styled)
    styled = re.sub(r'<pre style="([^"]+)">\s*<code style="([^"]+)">', '<pre style="\\1"><code style="padding:0;background:transparent;color:inherit;font-family:Cascadia Code,Consolas,monospace;font-size:0.92em;">', styled)

    header = (
        '<section style="max-width:720px;margin:0 auto 12px;padding:0 0 4px 0;">'
        f'<h1 style="margin:0 0 14px;font-size:28px;line-height:1.35;color:#111827;letter-spacing:0.2px;font-weight:800;">{html.escape(title)}</h1>'
        f'<p style="margin:0 0 20px;padding:12px 14px;border-radius:14px;background:#f8fafc;color:#6b7280;font-size:14px;line-height:1.8;border:1px solid #eef2f7;">{html.escape(summary)}</p>'
        '</section>'
    )
    references_html = ''
    if reference_entries:
        references_html = (
            '<section style="max-width:720px;margin:34px auto 0;">'
            f'<h2 style="margin:0 0 14px;padding-left:10px;border-left:3px solid {accent_color};font-size:22px;line-height:1.45;color:#111827;font-weight:700;">\u53c2\u8003\u6765\u6e90</h2>'
            + build_reference_cards_wechat(reference_entries, accent_color)
            + '</section>'
        )
    return '<section style="max-width:720px;margin:0 auto;padding:8px 0 28px;font-family:PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif;color:#1f2937;">' + header + styled + references_html + '</section>'


def cmd_render(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    input_path = workspace / (args.input or manifest.get("assembled_path") or "assembled.md")
    if not input_path.exists():
        input_path = workspace / (manifest.get("article_path") or "article.md")
    if not input_path.exists():
        raise SystemExit(f"\u627e\u4e0d\u5230\u5f85\u6e32\u67d3\u6587\u4ef6\uff1a{input_path}")
    meta, body = split_frontmatter(read_text(input_path))
    body = strip_image_directives(body)
    title = infer_title(manifest, meta, body)
    summary = meta.get("summary") or manifest.get("summary") or extract_summary(body)
    body = strip_leading_h1(body, title)
    content_html = markdown_to_html(body)
    content_html = content_html.replace('<blockquote>', '<blockquote class="insight-card">')
    style = read_text(ASSETS_DIR / "wechat-style.css").replace("{{accent_color}}", args.accent_color)
    template = read_text(ASSETS_DIR / "wechat-template.html")
    theme_class = "wx-theme-clean"
    article_style = f"--accent:{args.accent_color};"
    rendered = (
        template.replace("{{title}}", html.escape(title))
        .replace("{{summary}}", html.escape(summary))
        .replace("{{style}}", style)
        .replace("{{theme_class}}", theme_class)
        .replace("{{article_style}}", article_style)
        .replace("{{content}}", textwrap.indent(content_html, "      ").strip())
    )
    output_path = workspace / args.output
    write_text(output_path, rendered)
    wechat_fragment = build_wechat_fragment(content_html, title, summary, args.accent_color, None)
    wechat_output = workspace / (Path(args.output).stem + ".wechat.html")
    write_text(wechat_output, wechat_fragment)
    manifest["html_path"] = relative_posix(output_path, workspace)
    manifest["wechat_html_path"] = relative_posix(wechat_output, workspace)
    save_manifest(workspace, manifest)
    print(str(output_path))
    return 0

def multipart_form(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f"----wechat-article-studio-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for key, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    for key, (filename, payload, mime_type) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode(),
                f"Content-Type: {mime_type}\r\n\r\n".encode(),
                payload,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def request_multipart(url: str, file_path: Path) -> dict[str, Any]:
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body, boundary = multipart_form({}, {"media": (file_path.name, file_path.read_bytes(), mime)})
    req = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    raw, response_headers = urlopen_with_retry(req)
    return json.loads(decode_response_body(raw, response_headers))


def wechat_access_token(app_id: str, app_secret: str) -> str:
    query = urllib.parse.urlencode({"grant_type": "client_credential", "appid": app_id, "secret": app_secret})
    response = request_json(f"https://api.weixin.qq.com/cgi-bin/token?{query}")
    if response.get("errcode"):
        raise SystemExit(f"微信 access_token 获取失败：{json.dumps(response, ensure_ascii=False)}")
    token = response.get("access_token")
    if not token:
        raise SystemExit(f"微信 access_token 响应异常：{json.dumps(response, ensure_ascii=False)}")
    return token


def upload_wechat_cover(access_token: str, cover_path: Path) -> str:
    response = request_multipart(f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={urllib.parse.quote(access_token)}&type=image", cover_path)
    if response.get("errcode"):
        raise SystemExit(f"微信封面上传失败：{json.dumps(response, ensure_ascii=False)}")
    media_id = response.get("media_id")
    if not media_id:
        raise SystemExit(f"微信封面响应异常：{json.dumps(response, ensure_ascii=False)}")
    return media_id


def upload_wechat_inline(access_token: str, image_path: Path) -> str:
    response = request_multipart(f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={urllib.parse.quote(access_token)}", image_path)
    if response.get("errcode"):
        raise SystemExit(f"微信正文图片上传失败：{json.dumps(response, ensure_ascii=False)}")
    url = response.get("url")
    if not url:
        raise SystemExit(f"微信正文图片响应异常：{json.dumps(response, ensure_ascii=False)}")
    return url


IMG_TAG_PATTERN = re.compile(r"<img\b[^>]*>", flags=re.I)
IMG_ATTR_PATTERN = re.compile(
    r"(?P<name>src|data-src)\s*=\s*(?:(?P<quote>[\"'])(?P<qvalue>.*?)(?P=quote)|(?P<uvalue>[^\s>]+))",
    flags=re.I,
)


def extract_image_attr_value(match: re.Match[str]) -> str:
    return html.unescape(match.group("qvalue") if match.group("qvalue") is not None else (match.group("uvalue") or ""))


def is_remote_image_reference(value: str) -> bool:
    lower = value.strip().lower()
    return lower.startswith("http://") or lower.startswith("https://") or lower.startswith("data:")


def is_wechat_image_url(value: str) -> bool:
    try:
        parsed = urllib.parse.urlparse(value)
    except ValueError:
        return False
    host = (parsed.netloc or "").lower()
    return host.endswith("qpic.cn") or host.endswith("mmbiz.qpic.cn")


def is_local_like_image_reference(value: str) -> bool:
    raw = value.strip()
    lower = raw.lower()
    if not raw or is_remote_image_reference(raw):
        return False
    if lower.startswith("file://"):
        return True
    if raw.startswith(("./", "../", "/", "\\")):
        return True
    if re.match(r"^[A-Za-z]:[\\/]", raw):
        return True
    return bool(re.search(r"\.(png|jpe?g|gif|webp|bmp|svg)(?:$|[?#])", lower))


def resolve_html_image_path(value: str, html_path: Path) -> Path | None:
    raw = value.strip()
    if not is_local_like_image_reference(raw):
        return None
    if raw.lower().startswith("file://"):
        parsed = urllib.parse.urlparse(raw)
        return Path(urllib.request.url2pathname(parsed.path)).resolve()
    if re.match(r"^[A-Za-z]:[\\/]", raw) or raw.startswith("\\"):
        return Path(raw).resolve()
    if raw.startswith("/"):
        return Path(raw).resolve()
    return (html_path.parent / raw).resolve()


def count_local_image_candidates(html_text: str, html_path: Path) -> int:
    count = 0
    for tag_match in IMG_TAG_PATTERN.finditer(html_text):
        tag = tag_match.group(0)
        attrs = [extract_image_attr_value(attr) for attr in IMG_ATTR_PATTERN.finditer(tag)]
        if any(resolve_html_image_path(value, html_path) is not None for value in attrs):
            count += 1
    return count


def count_wechat_remote_images(html_text: str) -> int:
    count = 0
    for tag_match in IMG_TAG_PATTERN.finditer(html_text):
        tag = tag_match.group(0)
        attrs = [extract_image_attr_value(attr) for attr in IMG_ATTR_PATTERN.finditer(tag)]
        if any(is_wechat_image_url(value) for value in attrs):
            count += 1
    return count


def find_residual_local_image_refs(html_text: str, html_path: Path | None = None) -> list[str]:
    residuals: list[str] = []
    for tag_match in IMG_TAG_PATTERN.finditer(html_text):
        tag = tag_match.group(0)
        for attr in IMG_ATTR_PATTERN.finditer(tag):
            value = extract_image_attr_value(attr)
            if is_local_like_image_reference(value):
                if html_path is None or resolve_html_image_path(value, html_path) is not None:
                    residuals.append(value)
    return list(dict.fromkeys(residuals))


def replace_local_images(
    html_text: str,
    html_path: Path,
    access_token: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], int, int]:
    uploads: list[dict[str, Any]] = []
    skipped_uploads: list[dict[str, Any]] = []
    upload_cache: dict[str, str] = {}
    expected_inline_count = 0
    replaced_inline_count = 0

    def replace_tag(match: re.Match[str]) -> str:
        nonlocal expected_inline_count, replaced_inline_count
        original_tag = match.group(0)
        attr_matches = list(IMG_ATTR_PATTERN.finditer(original_tag))
        local_entries: list[tuple[re.Match[str], str, Path | None]] = []
        for attr in attr_matches:
            raw_value = extract_image_attr_value(attr)
            resolved = resolve_html_image_path(raw_value, html_path)
            if resolved is not None:
                local_entries.append((attr, raw_value, resolved))
        if not local_entries:
            return original_tag
        expected_inline_count += 1
        valid_entry = next((entry for entry in local_entries if entry[2] and entry[2].exists()), None)
        if valid_entry is None:
            skipped_uploads.append(
                {
                    "local": local_entries[0][1],
                    "reason": "file_not_found",
                    "html_path": str(html_path),
                }
            )
            return original_tag
        image_path = valid_entry[2]
        cache_key = str(image_path)
        remote_url = upload_cache.get(cache_key)
        if remote_url is None:
            remote_url = upload_wechat_inline(access_token, image_path)
            upload_cache[cache_key] = remote_url
            uploads.append({"local": str(image_path), "remote": remote_url})
        updated_tag = original_tag
        for attr, raw_value, resolved in local_entries:
            if resolved is None:
                skipped_uploads.append({"local": raw_value, "reason": "unresolvable_path", "html_path": str(html_path)})
                continue
            if resolved != image_path:
                skipped_uploads.append({"local": raw_value, "reason": "multiple_local_refs_in_single_tag", "html_path": str(html_path)})
                continue
            quote = attr.group("quote") or '"'
            new_fragment = f'{attr.group("name")}={quote}{html.escape(remote_url, quote=True)}{quote}'
            updated_tag = updated_tag.replace(attr.group(0), new_fragment, 1)
        replaced_inline_count += 1
        return updated_tag

    updated = IMG_TAG_PATTERN.sub(replace_tag, html_text)
    return updated, uploads, skipped_uploads, expected_inline_count, replaced_inline_count


def resolve_wechat_credentials(required: bool) -> tuple[str | None, str | None, list[str]]:
    app_id = os.getenv("WECHAT_APP_ID")
    app_secret = os.getenv("WECHAT_APP_SECRET")

    # Optional fallback: allow loading credentials from a local config file so users
    # don't have to export env vars in every shell session. Env vars still take
    # precedence. The file lives under APPDATA by default to avoid accidental commits.
    if not app_id or not app_secret:
        cred_path = wechat_credential_path()
        if cred_path.exists():
            try:
                payload = read_json(cred_path, default={}) or {}
            except Exception:
                payload = {}
            if isinstance(payload, dict):
                if not app_id:
                    app_id = str(payload.get("WECHAT_APP_ID") or payload.get("app_id") or "").strip() or None
                if not app_secret:
                    app_secret = str(payload.get("WECHAT_APP_SECRET") or payload.get("app_secret") or "").strip() or None
    missing = []
    if not app_id:
        missing.append("WECHAT_APP_ID")
    if not app_secret:
        missing.append("WECHAT_APP_SECRET")
    if required and missing:
        raise SystemExit(
            "缺少微信发布配置："
            + ", ".join(missing)
            + "。请设置环境变量 WECHAT_APP_ID/WECHAT_APP_SECRET，"
            + f"或在 {wechat_credential_path()} 中填写同名字段。"
        )
    return app_id, app_secret, missing


def wechat_credential_path() -> Path:
    base = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    return base / "wechat-article-studio" / "wechat.json"


def wechat_draft_batchget(access_token: str, offset: int = 0, count: int = WECHAT_BATCHGET_COUNT, no_content: int = 0) -> dict[str, Any]:
    response = request_json(
        f"https://api.weixin.qq.com/cgi-bin/draft/batchget?access_token={urllib.parse.quote(access_token)}",
        data={"offset": offset, "count": count, "no_content": no_content},
        method="POST",
    )
    if response.get("errcode"):
        raise SystemExit(f"微信草稿回读失败：{json.dumps(response, ensure_ascii=False)}")
    return response


def select_draft_item(batchget_response: dict[str, Any], media_id: str | None) -> tuple[dict[str, Any] | None, str, list[str]]:
    items = batchget_response.get("item") or []
    if not items:
        return None, media_id or "", ["草稿箱回读为空。"]
    if media_id:
        for item in items:
            if item.get("media_id") == media_id:
                return item, media_id, []
        latest = items[0]
        return latest, latest.get("media_id") or media_id, [f"未在草稿回读中找到 media_id={media_id}，已回退到最新草稿进行验收。"]
    latest = items[0]
    return latest, latest.get("media_id") or "", []


def verify_draft_publication(
    workspace: Path,
    access_token: str,
    media_id: str | None = None,
    expected_inline_count: int | None = None,
) -> dict[str, Any]:
    batchget_response = wechat_draft_batchget(access_token)
    draft_batchget_path = workspace / "draft-batchget.json"
    latest_content_path = workspace / "latest-draft-content.html"
    latest_report_path = workspace / "latest-draft-report.json"
    write_json(draft_batchget_path, batchget_response)
    selected_item, selected_media_id, errors = select_draft_item(batchget_response, media_id)
    news_item = (((selected_item or {}).get("content") or {}).get("news_item") or [{}])[0]
    content_html = news_item.get("content") or ""
    write_text(latest_content_path, content_html)
    if not content_html:
        errors.append("草稿回读内容为空。")
    if expected_inline_count is None:
        publish_result = read_json(workspace / "publish-result.json", default={}) or {}
        manifest = load_manifest(workspace)
        expected_inline_count = int(
            publish_result.get("expected_inline_count")
            or manifest.get("expected_inline_count")
            or 0
        )
    residual_local_refs = find_residual_local_image_refs(content_html)
    verified_inline_count = count_wechat_remote_images(content_html)
    if expected_inline_count and verified_inline_count < expected_inline_count:
        errors.append(f"草稿回读只发现 {verified_inline_count} 张微信图片，少于预期的 {expected_inline_count} 张。")
    if residual_local_refs:
        preview = ", ".join(residual_local_refs[:3])
        errors.append(f"草稿回读仍包含本地图片路径：{preview}")
    if selected_item and not news_item.get("thumb_media_id"):
        errors.append("草稿回读缺少 thumb_media_id。")
    report = {
        "draft_media_id": selected_media_id,
        "expected_inline_count": expected_inline_count,
        "verified_inline_count": verified_inline_count,
        "verify_status": "passed" if not errors else "failed",
        "verify_errors": errors,
        "residual_local_refs": residual_local_refs,
        "thumb_media_id": news_item.get("thumb_media_id") or "",
        "draft_batchget_path": str(draft_batchget_path),
        "latest_draft_content_path": str(latest_content_path),
    }
    write_json(latest_report_path, report)
    return report


def derive_digest(meta: dict[str, str], manifest: dict[str, Any], body: str) -> str:
    return manifest.get("summary") or meta.get("summary") or extract_summary(body)


def cmd_publish(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    html_rel = args.input or manifest.get("wechat_html_path") or manifest.get("html_path") or "article.html"
    html_path = workspace / html_rel
    assembled_path = workspace / (manifest.get("assembled_path") or "assembled.md")
    article_source = assembled_path if assembled_path.exists() else workspace / "article.md"
    if not html_path.exists():
        if not article_source.exists():
            raise SystemExit(f"找不到待发布的 HTML 文件：{html_path}")
        meta, body = split_frontmatter(read_text(article_source))
        title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名文章"
        digest_preview = manifest.get("summary") or meta.get("summary") or extract_summary(body)
        # Keep legacy publish path consistent with core renderer output.
        from core.layout import DEFAULT_ACCENT_COLOR, THEMES, analyze_content_signals, choose_accent_color, choose_layout_style, markdown_to_html
        from core.wechat_fragment import render_wechat_fragment

        content_md = strip_leading_h1(body, title)
        signals = analyze_content_signals(content_md, "md")
        requested_style = str(manifest.get("layout_style") or "auto")
        layout_decision = choose_layout_style(requested_style, signals, manifest)
        chosen_style = layout_decision.style
        accent_arg = str(manifest.get("accent_color") or DEFAULT_ACCENT_COLOR)
        accent_decision = choose_accent_color(chosen_style, accent_arg, manifest)
        theme = THEMES.get(chosen_style, THEMES["clean"])
        content_html = markdown_to_html(content_md)
        fragment = render_wechat_fragment(
            content_html,
            title=title,
            summary=digest_preview,
            theme=theme,
            accent=accent_decision.accent,
            chosen_style=chosen_style,
        )
        html_path = workspace / "article.wechat.html"
        write_text(html_path, fragment)
        manifest["wechat_html_path"] = relative_posix(html_path, workspace)
        manifest["layout_style"] = chosen_style
        manifest["layout_style_reason"] = layout_decision.reason
        manifest["accent_color"] = accent_decision.accent
        manifest["accent_color_reason"] = accent_decision.reason
        save_manifest(workspace, manifest)
    meta, body = split_frontmatter(read_text(article_source))
    title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名文章"
    digest = args.digest or derive_digest(meta, manifest, body)
    author = args.author if args.author is not None else (meta.get("author") or manifest.get("author") or "")
    cover_rel = args.cover or manifest.get("asset_paths", {}).get("cover")
    cover_path = (workspace / cover_rel).resolve() if cover_rel else None
    if not cover_path or not cover_path.exists():
        raise SystemExit("找不到封面图。请先完成 assemble，或通过 --cover 显式传入封面图路径。")
    html_text = read_text(html_path)
    expected_inline_count = count_local_image_candidates(html_text, html_path)
    result: dict[str, Any] = {
        "title": title,
        "digest": digest,
        "author": author,
        "html_path": str(html_path),
        "cover_path": str(cover_path),
        "cover_policy": manifest.get("cover_policy") or DEFAULT_COVER_POLICY,
        "uploaded_html_path": "",
        "draft_media_id": "",
        "expected_inline_count": expected_inline_count,
        "uploaded_inline_count": 0,
        "verified_inline_count": 0,
        "verify_status": "not_run",
        "verify_errors": [],
        "skipped_uploads": [],
        "mode": "dry-run" if args.dry_run else "live",
        "generated_at": now_iso(),
    }
    if args.dry_run:
        app_id, app_secret, missing_env = resolve_wechat_credentials(required=False)
        result["missing_env"] = missing_env
        result["access_token_verified"] = False
        if app_id and app_secret:
            token = wechat_access_token(app_id, app_secret)
            result["access_token_verified"] = bool(token)
        manifest["publish_status"] = "dry_run_ready"
        manifest["expected_inline_count"] = expected_inline_count
        write_json(workspace / "publish-result.json", result)
        save_manifest(workspace, manifest)
        safe_print_json(result)
        return 0
    if not getattr(args, "confirmed_publish", False):
        raise SystemExit("正式发布前必须显式传入 --confirmed-publish。")
    if not manifest.get("publish_intent"):
        raise SystemExit("当前工作目录未记录 publish_intent=true。请先在用户明确确认后用 ideate --publish-intent 更新工作目录。")
    app_id, app_secret, _ = resolve_wechat_credentials(required=True)
    token = wechat_access_token(app_id, app_secret)
    thumb_media_id = upload_wechat_cover(token, cover_path)
    updated_html, uploads, skipped_uploads, expected_inline_count, replaced_inline_count = replace_local_images(html_text, html_path, token)
    uploaded_html_path = workspace / "article.wechat.uploaded.html"
    write_text(uploaded_html_path, updated_html)
    payload = {
        "articles": [
            {
                "title": title,
                "author": author,
                "digest": digest,
                "content": updated_html,
                "content_source_url": (manifest.get("source_urls") or [""])[0] if manifest.get("source_urls") else "",
                "thumb_media_id": thumb_media_id,
                "need_open_comment": 1,
                "only_fans_can_comment": 0,
            }
        ]
    }
    response = request_json(
        f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={urllib.parse.quote(token)}",
        data=payload,
        method="POST",
    )
    if response.get("errcode"):
        raise SystemExit(f"微信草稿发布失败：{json.dumps(response, ensure_ascii=False)}")
    draft_media_id = response.get("media_id") or ""
    verify_report = verify_draft_publication(workspace, token, media_id=draft_media_id, expected_inline_count=expected_inline_count)
    result.update(
        {
            "uploaded_html_path": str(uploaded_html_path),
            "thumb_media_id": thumb_media_id,
            "draft_media_id": draft_media_id,
            "inline_uploads": uploads,
            "expected_inline_count": expected_inline_count,
            "uploaded_inline_count": replaced_inline_count,
            "verified_inline_count": verify_report["verified_inline_count"],
            "verify_status": verify_report["verify_status"],
            "verify_errors": verify_report["verify_errors"],
            "skipped_uploads": skipped_uploads,
            "response": response,
            "draft_batchget_path": verify_report["draft_batchget_path"],
            "latest_draft_content_path": verify_report["latest_draft_content_path"],
        }
    )
    write_json(workspace / "publish-result.json", result)
    manifest["draft_media_id"] = draft_media_id
    manifest["uploaded_html_path"] = relative_posix(uploaded_html_path, workspace)
    manifest["expected_inline_count"] = expected_inline_count
    manifest["uploaded_inline_count"] = replaced_inline_count
    manifest["verified_inline_count"] = verify_report["verified_inline_count"]
    manifest["verify_status"] = verify_report["verify_status"]
    manifest["verify_errors"] = verify_report["verify_errors"]
    manifest["publish_status"] = "verified" if verify_report["verify_status"] == "passed" else "draft_verify_failed"
    save_manifest(workspace, manifest)
    safe_print_json(result)
    return 0 if verify_report["verify_status"] == "passed" else 2


def cmd_verify_draft(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    app_id, app_secret, _ = resolve_wechat_credentials(required=True)
    token = wechat_access_token(app_id, app_secret)
    report = verify_draft_publication(
        workspace,
        token,
        media_id=args.media_id or manifest.get("draft_media_id") or None,
        expected_inline_count=int(manifest.get("expected_inline_count") or 0),
    )
    manifest["draft_media_id"] = report.get("draft_media_id") or manifest.get("draft_media_id") or ""
    manifest["verified_inline_count"] = report["verified_inline_count"]
    manifest["verify_status"] = report["verify_status"]
    manifest["verify_errors"] = report["verify_errors"]
    manifest["publish_status"] = "verified" if report["verify_status"] == "passed" else manifest.get("publish_status") or "draft_verify_failed"
    save_manifest(workspace, manifest)
    safe_print_json(report)
    return 0 if report["verify_status"] == "passed" else 2


def can_write_directory(path: Path) -> bool:
    try:
        ensure_dir(path)
        handle = tempfile.NamedTemporaryFile(dir=path, prefix="doctor-", suffix=".tmp", delete=False)
        handle.close()
        Path(handle.name).unlink(missing_ok=True)
        return True
    except Exception:
        return False


def doctor_provider_status(provider: str) -> dict[str, Any]:
    if provider == "gemini-api":
        ok = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        return {
            "ok": ok,
            "missing": [] if ok else ["GEMINI_API_KEY/GOOGLE_API_KEY"],
            "notes": ["官方 Gemini 图片接口，推荐作为稳定路径。"],
        }
    if provider == "openai-image":
        ok = bool(os.getenv("OPENAI_API_KEY"))
        return {
            "ok": ok,
            "missing": [] if ok else ["OPENAI_API_KEY"],
            "notes": ["官方 OpenAI 图片接口，推荐作为稳定路径。"],
        }
    from core.gemini_web_session import has_session_material, session_diagnostics

    vendor_missing = [relative for relative in IMAGE_PROVIDER_FILES if not (vendor_root() / relative).exists()]
    diagnostics = session_diagnostics(os.environ.copy())
    cookie_ready = has_session_material(os.environ.copy())
    bun_ready = shutil.which("bun") is not None
    npx_ready = shutil.which("npx") is not None
    ok = cookie_ready and (bun_ready or npx_ready) and not vendor_missing
    missing: list[str] = []
    if not cookie_ready:
        missing.append("可复用的 gemini-web 登录态")
    if not (bun_ready or npx_ready):
        missing.append("bun 或 npx")
    if vendor_missing:
        missing.append("vendor 文件不完整")
    return {
        "ok": ok,
        "missing": missing,
        "notes": [
            "非官方 best-effort 路径，仅在显式指定 --provider gemini-web 时启用。",
            "当前若仅文本能返回、图片不返回，通常是 Gemini Web 上游图片能力或非官方接口发生兼容变化。",
        ],
        "bun_available": bun_ready,
        "npx_available": npx_ready,
        "vendor_missing_count": len(vendor_missing),
        "detected_cookie_file": diagnostics.get("shared_cookie_path") or "",
        "detected_profile_root": diagnostics.get("shared_profile_dir") or "",
        "session_diagnostics": diagnostics,
    }


def cmd_doctor(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve()
    workspace_target = workspace if workspace.exists() else workspace.parent
    auto_provider = None
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        auto_provider = "gemini-api"
    elif os.getenv("OPENAI_API_KEY"):
        auto_provider = "openai-image"
    provider = args.provider or auto_provider
    report = {
        "python": {
            "version": sys.version.split()[0],
            "ok": sys.version_info >= (3, 10),
        },
        "platform": {
            "os_name": os.name,
            "sys_platform": sys.platform,
        },
        "workspace": {
            "path": str(workspace),
            "exists": workspace.exists(),
            "writable": can_write_directory(workspace_target),
        },
        "wechat": {
            "has_app_id": bool(os.getenv("WECHAT_APP_ID")),
            "has_app_secret": bool(os.getenv("WECHAT_APP_SECRET")),
        },
        "auto_provider": auto_provider,
        "selected_provider": provider,
        "providers": {
            "gemini-api": doctor_provider_status("gemini-api"),
            "openai-image": doctor_provider_status("openai-image"),
            "gemini-web": doctor_provider_status("gemini-web"),
        },
    }
    safe_print_json(report)
    return 0

def cmd_consent(args: argparse.Namespace) -> int:
    path = consent_path()
    if args.accept:
        ensure_dir(path.parent)
        payload = {"version": 1, "accepted": True, "acceptedAt": now_iso(), "disclaimerVersion": DISCLAIMER_VERSION}
        write_json(path, payload)
        print(str(path))
        return 0
    if args.revoke:
        if path.exists():
            path.unlink()
        print(str(path))
        return 0
    payload = read_json(path, default={}) or {}
    safe_print_json(payload)
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    score_rc = cmd_score(
        argparse.Namespace(
            workspace=args.workspace,
            input=None,
            threshold=args.threshold,
            fail_below=True,
            no_rewrite=False,
            rewrite_output=None,
        )
    )
    if score_rc != 0:
        return score_rc
    plan_rc = cmd_plan_images(argparse.Namespace(workspace=args.workspace, provider=args.provider, inline_count=args.inline_count))
    if plan_rc != 0:
        return plan_rc
    image_rc = cmd_generate_images(
        argparse.Namespace(
            workspace=args.workspace,
            provider=args.provider,
            dry_run=args.dry_run_images,
            gemini_model=args.gemini_model,
            openai_model=args.openai_model,
        )
    )
    if image_rc != 0:
        return image_rc
    assemble_rc = cmd_assemble(argparse.Namespace(workspace=args.workspace))
    if assemble_rc != 0:
        return assemble_rc
    render_rc = cmd_render(argparse.Namespace(workspace=args.workspace, input=None, output="article.html", accent_color=args.accent_color))
    if render_rc != 0:
        return render_rc
    if args.publish:
        publish_rc = cmd_publish(
            argparse.Namespace(
                workspace=args.workspace,
                input=None,
                digest=None,
                author=None,
                cover=None,
                dry_run=args.dry_run_publish,
                confirmed_publish=args.confirmed_publish,
            )
        )
        if publish_rc != 0:
            return publish_rc
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studio.py", description="WeChat Article Studio")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ideate = subparsers.add_parser("ideate", help="初始化工作目录并保存选题信息")
    ideate.add_argument("--workspace")
    ideate.add_argument("--topic", required=True)
    ideate.add_argument("--direction", default="")
    ideate.add_argument("--audience", default="大众读者")
    ideate.add_argument("--goal", default="公众号爆款图文")
    ideate.add_argument("--score-threshold", type=int, default=DEFAULT_THRESHOLD)
    ideate.add_argument("--source-url", action="append", default=[])
    ideate.add_argument("--title", action="append", default=[])
    ideate.add_argument("--selected-title")
    ideate.add_argument("--outline-file")
    ideate.add_argument("--image-theme")
    ideate.add_argument("--image-style")
    ideate.add_argument("--image-type")
    ideate.add_argument("--image-mood")
    ideate.add_argument("--custom-visual-brief")
    ideate.add_argument("--publish-intent", action="store_true")
    ideate.set_defaults(func=cmd_ideate)

    draft = subparsers.add_parser("draft", help="保存正文稿件")
    draft.add_argument("--workspace", required=True)
    draft.add_argument("--input", required=True)
    draft.add_argument("--selected-title")
    draft.add_argument("--summary")
    draft.add_argument("--author")
    draft.set_defaults(func=cmd_draft)

    score = subparsers.add_parser("score", help="Generate score report and auto-create a rewrite draft when the score is low")
    score.add_argument("--workspace", required=True)
    score.add_argument("--input")
    score.add_argument("--threshold", type=int)
    score.add_argument("--fail-below", action="store_true")
    score.add_argument("--no-rewrite", action="store_true")
    score.add_argument("--rewrite-output")
    score.set_defaults(func=cmd_score)

    plan_images = subparsers.add_parser("plan-images", help="生成图片规划")
    plan_images.add_argument("--workspace", required=True)
    plan_images.add_argument("--provider", choices=["gemini-web", "gemini-api", "openai-image"])
    plan_images.add_argument("--image-density", choices=IMAGE_DENSITY_CHOICES, default=None)
    plan_images.add_argument("--allow-closing-image", choices=ALLOW_CLOSING_IMAGE_CHOICES, default=None)
    plan_images.add_argument("--inline-count", type=int, default=0)
    plan_images.set_defaults(func=cmd_plan_images)

    generate_images = subparsers.add_parser("generate-images", help="执行图片生成")
    generate_images.add_argument("--workspace", required=True)
    generate_images.add_argument("--provider", choices=["gemini-web", "gemini-api", "openai-image"])
    generate_images.add_argument("--dry-run", action="store_true")
    generate_images.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    generate_images.add_argument("--openai-model", default="gpt-image-1")
    generate_images.set_defaults(func=cmd_generate_images)

    assemble = subparsers.add_parser("assemble", help="把图片插回 Markdown")
    assemble.add_argument("--workspace", required=True)
    assemble.set_defaults(func=cmd_assemble)

    render = subparsers.add_parser("render", help="渲染公众号 HTML")
    render.add_argument("--workspace", required=True)
    render.add_argument("--input")
    render.add_argument("--output", default="article.html")
    render.add_argument("--accent-color", default="#0F766E")
    render.set_defaults(func=cmd_render)

    publish = subparsers.add_parser("publish", help="发布到公众号草稿箱")
    publish.add_argument("--workspace", required=True)
    publish.add_argument("--input")
    publish.add_argument("--digest")
    publish.add_argument("--author")
    publish.add_argument("--cover")
    publish.add_argument("--dry-run", action="store_true")
    publish.add_argument("--confirmed-publish", action="store_true")
    publish.set_defaults(func=cmd_publish)

    verify_draft = subparsers.add_parser("verify-draft", help="回读公众号草稿并做图片验收")
    verify_draft.add_argument("--workspace", required=True)
    verify_draft.add_argument("--media-id")
    verify_draft.set_defaults(func=cmd_verify_draft)

    doctor = subparsers.add_parser("doctor", help="检查本地环境和发布依赖")
    doctor.add_argument("--workspace")
    doctor.add_argument("--provider", choices=["gemini-web", "gemini-api", "openai-image"])
    doctor.set_defaults(func=cmd_doctor)

    consent = subparsers.add_parser("consent", help="管理 gemini-web 同意状态")
    consent.add_argument("--accept", action="store_true")
    consent.add_argument("--revoke", action="store_true")
    consent.set_defaults(func=cmd_consent)

    all_cmd = subparsers.add_parser("all", help="串联评分、配图、汇总、渲染、发布")
    all_cmd.add_argument("--workspace", required=True)
    all_cmd.add_argument("--provider", choices=["gemini-web", "gemini-api", "openai-image"])
    all_cmd.add_argument("--image-density", choices=IMAGE_DENSITY_CHOICES, default=None)
    all_cmd.add_argument("--allow-closing-image", choices=ALLOW_CLOSING_IMAGE_CHOICES, default=None)
    all_cmd.add_argument("--inline-count", type=int, default=0)
    all_cmd.add_argument("--threshold", type=int)
    all_cmd.add_argument("--dry-run-images", action="store_true")
    all_cmd.add_argument("--publish", action="store_true")
    all_cmd.add_argument("--dry-run-publish", action="store_true")
    all_cmd.add_argument("--confirmed-publish", action="store_true")
    all_cmd.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    all_cmd.add_argument("--openai-model", default="gpt-image-1")
    all_cmd.add_argument("--accent-color", default="#0F766E")
    all_cmd.set_defaults(func=cmd_all)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
