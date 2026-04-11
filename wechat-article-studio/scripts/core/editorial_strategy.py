from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


RECENT_CORPUS_SCAN_LIMIT = 36


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", (value or "").strip().lower()).strip("-")


def _normalize_text(value: str) -> str:
    compact = re.sub(r"\s+", " ", str(value or ""))
    return compact.strip(" -•>\"'“”‘’\n\r\t")


def _clean_markdown_paragraph(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"<!--.*?-->", "", text)
    return _normalize_text(text)


def _split_frontmatter(text: str) -> tuple[str, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            return text[4:end], text[end + 5 :]
    return "", text


def _extract_title(raw: str, path: Path) -> str:
    meta, body = _split_frontmatter(raw)
    match = re.search(r"(?m)^title:\s*(.+?)\s*$", meta)
    if match:
        return _normalize_text(match.group(1).strip("\"'"))
    for line in body.splitlines():
        if line.startswith("# "):
            return _normalize_text(line[2:])
    return path.parent.name


def _paragraphs(body: str) -> list[str]:
    return [_clean_markdown_paragraph(part) for part in re.split(r"\n\s*\n", body or "") if _clean_markdown_paragraph(part)]


def _headings(body: str) -> list[str]:
    result: list[str] = []
    for line in (body or "").splitlines():
        match = re.match(r"^#{2,6}\s+(.+?)\s*$", line.strip())
        if match:
            text = _clean_markdown_paragraph(match.group(1))
            if text:
                result.append(text)
    return result


def title_template_key(title: str) -> str:
    text = _normalize_text(title)
    if not text:
        return "generic"
    if re.search(r"真正值得(?:写|看|聊|讨论|警惕|说明)的不是", text):
        return "worthwrite-not-but"
    if re.search(r"(真正关键的是|更该看清|真正会拉开差距的|真正会带来代价的|真正要重估的)", text):
        return "viewpoint-direct"
    if re.search(r"(最容易卡住的|最容易让人卡住的|背后缺的其实是|总在后面失控的)", text):
        return "pain-truth"
    if re.search(r"(最反常识的一点|最容易被忽略的其实是|大家最容易看偏的)", text):
        return "counterintuitive"
    if re.search(r"(最先受影响的是|先被改写的是|会先吃亏的是|真正会带来代价的是)", text):
        return "cost-consequence"
    if re.search(r"(先抓住这条规律|真正有效的方法|少走弯路|先把这一步做对)", text):
        return "method-rule"
    if re.search(r"为什么.*先想清.*[三3].*件事", text):
        return "why-think-clear"
    if "真正危险的不是" in text and "而是" in text:
        return "danger-not-but"
    if re.search(r"20\d{2}.+不是.+而是", text):
        return "year-not-but"
    if "不是" in text and "而是" in text:
        return "not-but"
    if re.search(r"看懂这\d+个信号", text) or "真正的信号" in text:
        return "signal-briefing"
    if "误区" in text or "别再" in text:
        return "myth-buster"
    if re.search(r"(写给|如果你也正在|给.+的信)", text):
        return "open-letter"
    if "复盘" in text or "拆解" in text:
        return "case-memo"
    if re.search(r"(先回答|先问清|追问)", text):
        return "qa-cross-exam"
    if text.startswith("为什么"):
        return "why-question"
    return "generic"


def opening_pattern_key(text: str) -> str:
    value = _normalize_text(text)
    if not value:
        return "none"
    if re.search(r"(会议室|办公室|工位|白板|那天|凌晨|晚上|中午|刚坐下|窗口里|头像)", value):
        return "scene-cut"
    if re.search(r"(代价|成本|返工|吃亏|买单|损失|后果|最贵的一笔)", value):
        return "cost-upfront"
    if value.startswith("你可能") or value.startswith("你大概"):
        return "reader-scene"
    if value.startswith("很多人") or "很多人一提到" in value or "很多人听到" in value:
        return "many-people-misread"
    if value.startswith("最近我越来越强烈地感觉到一件事"):
        return "recent-realization"
    if value.startswith("这两年") and "企业" in value:
        return "enterprise-trend"
    if value.startswith("先给结论"):
        return "direct-conclusion"
    if "这种场景" in value or "那个瞬间" in value:
        return "scene-cut"
    if re.search(r"(\d{1,2}\s*月\s*\d{1,2}\s*日|这次|刚刚|今天|本周|消息|报道|发布|披露|宣布)", value):
        return "news-hook"
    return "generic"


def ending_pattern_key(text: str) -> str:
    value = _normalize_text(text)
    if not value:
        return "none"
    if "参考资料" in value:
        return "references-block"
    if "留个问题" in value or value.endswith("？") or value.endswith("?"):
        return "question-close"
    if "评论区" in value:
        return "comment-invite"
    if re.search(r"(风险|代价|迟早|别把|最先塌掉|不能默认|后果)", value):
        return "risk-close"
    if re.search(r"(如果是你|你会怎么|你更认同|该不该|到底)", value):
        return "stance-question-close"
    if "真正该问的问题" in value or "最后的判断" in value:
        return "judgment-close"
    if "可执行清单" in value or "只记住这一个动作" in value:
        return "action-close"
    return "generic"


def heading_pattern_key(text: str) -> str:
    value = _normalize_text(text)
    if not value:
        return "none"
    if re.search(r"你(要|该)先想清.*[三3].*件事", value):
        return "think-clear-n"
    if value in {"更要紧的一句判断", "最后的判断", "结尾：一个问题"}:
        return "fixed-ending-heading"
    if re.match(r"^(变化|信号|机会点)\s*\d+", value):
        return "numbered-insight"
    if re.match(r"^第[一二三四五六七八九十\d]+类", value):
        return "enumerated-class"
    if value.startswith("为什么"):
        return "why-heading"
    if value.startswith("你"):
        return "reader-question-heading"
    return "generic"


TITLE_PATTERN_LABELS = {
    "worthwrite-not-but": "“真正值得写/看/聊的不是…”",
    "viewpoint-direct": "观点直述型",
    "pain-truth": "痛点真相型",
    "counterintuitive": "反常识拆解型",
    "cost-consequence": "代价后果型",
    "method-rule": "方法规律型",
    "why-think-clear": "“为什么 + 先想清几件事”",
    "danger-not-but": "“真正危险的不是…而是…”",
    "year-not-but": "“年份 + 不是…而是…”",
    "not-but": "“不是…而是…”",
    "signal-briefing": "“信号/看懂信号”",
    "myth-buster": "“误区/别再”",
    "open-letter": "“写给你/公开信”",
    "case-memo": "“复盘/拆解”",
    "qa-cross-exam": "“先问清几个问题”",
    "why-question": "“为什么”问题式",
}

OPENING_PATTERN_LABELS = {
    "reader-scene": "“你可能/你大概”代入式开头",
    "many-people-misread": "“很多人…”误判式开头",
    "recent-realization": "“最近我越来越感觉…”感悟式开头",
    "enterprise-trend": "“这两年企业…”趋势式开头",
    "direct-conclusion": "直接结论式开头",
    "scene-cut": "具体场景切口",
    "cost-upfront": "代价先行切口",
    "news-hook": "新闻切口",
}

ENDING_PATTERN_LABELS = {
    "question-close": "提问式结尾",
    "comment-invite": "评论区邀请式结尾",
    "judgment-close": "判断收束式结尾",
    "risk-close": "风险提醒式结尾",
    "stance-question-close": "站队式提问结尾",
    "action-close": "动作/清单式结尾",
}

HEADING_PATTERN_LABELS = {
    "think-clear-n": "“你要先想清几件事”小标题",
    "fixed-ending-heading": "固定结尾小标题",
    "numbered-insight": "“变化/信号/机会点 + 编号”小标题",
    "enumerated-class": "“第几类”枚举小标题",
    "why-heading": "“为什么”小标题",
    "reader-question-heading": "“你…”提问式小标题",
}

EDITORIAL_STYLE_LIBRARY: dict[str, dict[str, Any]] = {
    "signal-briefing": {
        "style_key": "signal-briefing",
        "style_label": "信号简报",
        "summary": "用新闻或新现象开门，迅速拉出更大的行业判断。",
        "suited_archetypes": ["commentary", "case-study"],
        "content_modes": ["tech-balanced", "tech-credible", "viral"],
        "topic_keywords": ["发布", "宣布", "上线", "融资", "大会", "模型", "OpenAI", "阿里", "Meta", "Google", "GTC", "新功能"],
        "title_strategy": "标题像风向判断，不用固定的“为什么大多数人”模版。",
        "opening_strategy": "从一条新闻、一个新动作或一个被忽略的细节切入，2 段内进入判断。",
        "body_strategy": "按“表面热闹 -> 真正信号 -> 后续影响”推进。",
        "heading_strategy": "小标题更像判断句或分水岭，不用“你该先想清的 3 件事”。",
        "evidence_strategy": "新闻事实 + 行业对比 + 一处更深层解释。",
        "ending_strategy": "收束到趋势判断、风险提醒或下一阶段会发生什么。",
        "paragraph_rhythm": "短段切入，中段允许稍长分析，结尾再收紧。",
        "language_texture": ["克制", "判断感", "少口号", "少说教"],
        "forbidden_moves": ["不要用“留个问题”结尾", "不要回到万能清单", "不要复用‘真正危险的不是’标题"],
        "preferred_devices": ["新闻切口", "对比", "分水岭判断"],
        "allowed_title_patterns": ["signal-briefing", "why-question", "not-but"],
    },
    "counterintuitive-column": {
        "style_key": "counterintuitive-column",
        "style_label": "反常识短论",
        "summary": "从常见误解切进去，靠反转和更深一层的判断撑起全文。",
        "suited_archetypes": ["commentary"],
        "content_modes": ["tech-balanced", "viral"],
        "topic_keywords": ["误区", "真相", "危险", "机会", "替代", "拐点", "风险", "判断"],
        "title_strategy": "标题要有反转，但不要变成固定的“不是…而是…”流水线。",
        "opening_strategy": "先摆出大家普遍的理解，再迅速翻转。",
        "body_strategy": "按“常见看法 -> 为什么错 -> 真正关键”推进。",
        "heading_strategy": "小标题像辩论中的论点推进，不要机械编号。",
        "evidence_strategy": "对比论证 + 一两个具体例子。",
        "ending_strategy": "用一句更硬的判断收尾，不强行留问答。",
        "paragraph_rhythm": "长短句交错，转折清晰。",
        "language_texture": ["锋利", "克制", "可争论", "少模板连接词"],
        "forbidden_moves": ["不要所有段落都先下定义", "不要用“先说结论”", "不要固定用‘普通人一定要先想清’"],
        "preferred_devices": ["反差", "拆错题", "立场判断"],
        "allowed_title_patterns": ["why-question", "myth-buster", "not-but"],
    },
    "case-memo": {
        "style_key": "case-memo",
        "style_label": "案例备忘录",
        "summary": "像给同行写一份复盘备忘录，细节先于道理。",
        "suited_archetypes": ["case-study", "commentary"],
        "content_modes": ["tech-balanced", "tech-credible", "viral"],
        "topic_keywords": ["案例", "复盘", "公司", "团队", "产品", "广告", "企业", "平台"],
        "title_strategy": "标题更像‘拆某件事’，而不是万能大词。",
        "opening_strategy": "从一个结果、场景或角色决策切入。",
        "body_strategy": "按“发生了什么 -> 哪一步最关键 -> 能迁移什么判断”推进。",
        "heading_strategy": "小标题像复盘节点，不像教科书目录。",
        "evidence_strategy": "场景细节 + 决策节点 + 结果反推。",
        "ending_strategy": "把个案抬升成通用判断，再收束到同行视角。",
        "paragraph_rhythm": "中段允许更具体，避免口号句堆满全篇。",
        "language_texture": ["细节", "复盘感", "像内部备忘录", "少空话"],
        "forbidden_moves": ["不要每一节都‘为什么’开头", "不要套三层方法论", "不要结尾直接抛万能问题"],
        "preferred_devices": ["结果倒叙", "复盘", "关键一步"],
        "allowed_title_patterns": ["case-memo", "signal-briefing"],
    },
    "field-observation": {
        "style_key": "field-observation",
        "style_label": "现场观察",
        "summary": "从具体瞬间和真实细节入手，再慢慢抬到判断层。",
        "suited_archetypes": ["narrative", "commentary"],
        "content_modes": ["viral", "tech-balanced"],
        "topic_keywords": ["现场", "办公室", "职场", "日常", "疲惫", "焦虑", "人", "浏览器", "会议"],
        "title_strategy": "标题带一点现场感或观察感，不用高压营销腔。",
        "opening_strategy": "第一段必须有一个画面或具体动作。",
        "body_strategy": "按“场景 -> 被忽略的原因 -> 读者会感到被说中”推进。",
        "heading_strategy": "小标题像观察所得，不像课程提纲。",
        "evidence_strategy": "场景 + 一点事实支撑 + 一句带余味的判断。",
        "ending_strategy": "回扣最初场景，留余味，不强行变成操作建议。",
        "paragraph_rhythm": "短段和稍长叙述穿插，给文章呼吸感。",
        "language_texture": ["具体", "有人味", "克制", "少概念堆积"],
        "forbidden_moves": ["不要统一写成行业分析报告", "不要密集抛 1/2/3", "不要结尾机械站队提问"],
        "preferred_devices": ["场景切口", "细节", "回扣"],
        "allowed_title_patterns": ["open-letter", "generic"],
    },
    "myth-buster": {
        "style_key": "myth-buster",
        "style_label": "误区拆解",
        "summary": "适合把一个被讲歪的问题拆回正轨，结构清楚但不能像流水线。",
        "suited_archetypes": ["tutorial", "commentary"],
        "content_modes": ["tech-balanced", "tech-credible"],
        "topic_keywords": ["误区", "理解", "不会", "做不好", "真相", "别再"],
        "title_strategy": "标题突出误读点，但不要再用‘为什么大多数人做不好’那套。",
        "opening_strategy": "从错误理解或错误动作开门。",
        "body_strategy": "按“误解 -> 正解 -> 为什么总会踩坑”推进。",
        "heading_strategy": "可以用‘误区/真相/别混淆’这样的结构，但不能每篇都复制。",
        "evidence_strategy": "反例 + 正例 + 一个简单框架。",
        "ending_strategy": "收束到读者最该改掉的一个认知偏差。",
        "paragraph_rhythm": "更直接，但要防止讲义味。",
        "language_texture": ["直给", "清楚", "少官话", "别喊口号"],
        "forbidden_moves": ["不要‘先想清 3 件事’", "不要写成题库答案", "不要只剩结论没有例子"],
        "preferred_devices": ["误区对照", "反例", "澄清"],
        "allowed_title_patterns": ["myth-buster", "why-question"],
    },
    "practical-playbook": {
        "style_key": "practical-playbook",
        "style_label": "实操打法",
        "summary": "面向教程与方法文，重点是顺序和动作，不是堆更多清单。",
        "suited_archetypes": ["tutorial"],
        "content_modes": ["tech-balanced", "tech-credible"],
        "topic_keywords": ["教程", "指南", "步骤", "搭建", "流程", "上手", "方法", "实操"],
        "title_strategy": "标题突出顺序、关键一步或真实卡点。",
        "opening_strategy": "从读者最常卡住的动作切入，而不是先上方法总览。",
        "body_strategy": "按“先拆卡点 -> 再给顺序 -> 最后讲边界”推进。",
        "heading_strategy": "小标题要像动作和判断，不像流水线任务编号。",
        "evidence_strategy": "场景 + 步骤 + 关键提醒。",
        "ending_strategy": "只留一个最先可以做的动作，不给大而全清单。",
        "paragraph_rhythm": "更短更清楚，但不能写成说明书。",
        "language_texture": ["实操", "清楚", "有判断", "少教程腔"],
        "forbidden_moves": ["不要所有小标题都‘第一步/第二步’", "不要结尾塞满 checklist", "不要每段都‘建议你’"],
        "preferred_devices": ["卡点", "顺序", "边界"],
        "allowed_title_patterns": ["qa-cross-exam", "generic"],
    },
    "open-letter": {
        "style_key": "open-letter",
        "style_label": "公开信",
        "summary": "像写给某类人看的公开信，强调身份、处境和价值判断。",
        "suited_archetypes": ["narrative", "commentary"],
        "content_modes": ["viral"],
        "topic_keywords": ["写给", "如果你也", "打工人", "创作者", "普通人", "创业者", "职场人"],
        "title_strategy": "标题像在对某一类人说话，而不是对所有人吼口号。",
        "opening_strategy": "直接跟目标读者对话，但要有具体处境。",
        "body_strategy": "按“我为什么想对你说这个 -> 你最容易误判什么 -> 我真正想提醒你的判断”推进。",
        "heading_strategy": "小标题更像提醒和告白，而不是结论列表。",
        "evidence_strategy": "处境描写 + 现实细节 + 一句更高层判断。",
        "ending_strategy": "像留下一句要紧的话，不强行互动。",
        "paragraph_rhythm": "短段为主，允许一两段稍长沉下来。",
        "language_texture": ["对话感", "真诚", "克制", "不鸡汤"],
        "forbidden_moves": ["不要写成鸡汤", "不要突然转成教程清单", "不要最后硬拉评论区"],
        "preferred_devices": ["直呼读者", "处境", "提醒"],
        "allowed_title_patterns": ["open-letter", "generic"],
    },
    "qa-cross-exam": {
        "style_key": "qa-cross-exam",
        "style_label": "追问答辩",
        "summary": "用连续追问把问题拆深，适合复杂议题和需要读者思考的内容。",
        "suited_archetypes": ["commentary", "tutorial"],
        "content_modes": ["tech-balanced", "tech-credible", "viral"],
        "topic_keywords": ["问题", "到底", "能不能", "该不该", "之前", "先回答"],
        "title_strategy": "标题像一组绕不过去的问题，而不是统一答案。",
        "opening_strategy": "第一段就抛出一个真正绕不开的追问。",
        "body_strategy": "按 3 到 4 个追问推进，每个追问都要更深一层。",
        "heading_strategy": "小标题可以是问题句，但每个问题都要不同，不要同一腔调复制。",
        "evidence_strategy": "每个问题配一个例子或反例。",
        "ending_strategy": "最后回答最关键的那个问题，或把问题留给读者自己对号入座。",
        "paragraph_rhythm": "问句和陈述句交错，避免连续盘问带来的疲劳。",
        "language_texture": ["追问感", "思辨", "像在拆问题", "不装腔"],
        "forbidden_moves": ["不要所有问题都以‘为什么’起手", "不要问完不答", "不要再回到万能清单"],
        "preferred_devices": ["追问", "反例", "对号入座"],
        "allowed_title_patterns": ["qa-cross-exam", "why-question"],
    },
}


def _recent_style_counts(summary: dict[str, Any]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for item in summary.get("recent_editorial_styles") or []:
        key = _normalize_key(str(item))
        if key:
            counter[key] += 1
    counts = summary.get("editorial_style_counts") or {}
    if isinstance(counts, dict):
        for key, value in counts.items():
            try:
                counter[_normalize_key(str(key))] += int(value)
            except (TypeError, ValueError):
                continue
    return counter


_OVERUSED_PATTERN_FIELDS = {
    "title": "overused_title_patterns",
    "opening": "overused_opening_patterns",
    "ending": "overused_ending_patterns",
    "heading": "overused_heading_patterns",
}

_STYLE_PATTERN_PRESSURE: dict[str, dict[str, set[str]]] = {
    "signal-briefing": {
        "title": {"signal-briefing"},
        "opening": {"news-hook"},
    },
    "counterintuitive-column": {
        "title": {"not-but", "myth-buster", "why-question"},
        "opening": {"many-people-misread", "recent-realization"},
        "heading": {"why-heading"},
    },
    "case-memo": {
        "title": {"case-memo"},
        "heading": {"enumerated-class", "numbered-insight"},
    },
    "field-observation": {
        "opening": {"reader-scene", "recent-realization"},
        "heading": {"reader-question-heading"},
    },
    "myth-buster": {
        "title": {"myth-buster", "why-think-clear", "not-but"},
        "opening": {"many-people-misread", "reader-scene"},
        "heading": {"why-heading"},
    },
    "practical-playbook": {
        "heading": {"numbered-insight", "enumerated-class"},
        "ending": {"action-close"},
    },
    "open-letter": {
        "title": {"open-letter"},
        "opening": {"reader-scene"},
        "ending": {"question-close", "comment-invite"},
    },
    "qa-cross-exam": {
        "title": {"qa-cross-exam", "why-question"},
        "heading": {"why-heading", "reader-question-heading"},
        "ending": {"question-close"},
    },
}


def _overused_pattern_counts(summary: dict[str, Any], group: str) -> Counter[str]:
    field = _OVERUSED_PATTERN_FIELDS.get(group)
    if not field:
        return Counter()
    counter: Counter[str] = Counter()
    for item in summary.get(field) or []:
        if not isinstance(item, dict):
            continue
        key = _normalize_key(str(item.get("key") or ""))
        if not key:
            continue
        try:
            count = int(item.get("count") or 0)
        except (TypeError, ValueError):
            count = 0
        counter[key] += max(count, 1)
    return counter


def summarize_recent_corpus(article_paths: list[Path], limit: int = RECENT_CORPUS_SCAN_LIMIT) -> dict[str, Any]:
    title_patterns: Counter[str] = Counter()
    opening_patterns: Counter[str] = Counter()
    ending_patterns: Counter[str] = Counter()
    heading_patterns: Counter[str] = Counter()
    style_counts: Counter[str] = Counter()
    archetype_counts: Counter[str] = Counter()
    titles: list[str] = []
    article_count = 0

    for article_path in article_paths[:limit]:
        try:
            raw = article_path.read_text(encoding="utf-8")
        except OSError:
            continue
        meta, body = _split_frontmatter(raw)
        manifest_path = article_path.parent / "manifest.json"
        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = {}
        title = _extract_title(raw, article_path)
        titles.append(title)
        title_patterns[title_template_key(title)] += 1
        paragraphs = _paragraphs(body)
        article_count += 1
        if paragraphs:
            opening_patterns[opening_pattern_key(paragraphs[0])] += 1
            if len(paragraphs) > 1:
                opening_patterns[opening_pattern_key(paragraphs[1])] += 1
            ending_patterns[ending_pattern_key(paragraphs[-1])] += 1
        for heading in _headings(body)[:5]:
            heading_patterns[heading_pattern_key(heading)] += 1
        style = _normalize_key(str((manifest.get("editorial_blueprint") or {}).get("style_key") or ""))
        if style:
            style_counts[style] += 1
        archetype = _normalize_key(str((manifest.get("viral_blueprint") or {}).get("article_archetype") or manifest.get("article_archetype") or ""))
        if archetype:
            archetype_counts[archetype] += 1

    def top(counter: Counter[str], labels: dict[str, str], minimum: int = 2, size: int = 5) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for key, count in counter.most_common(size):
            if not key or key in {"none", "generic"} or count < minimum:
                continue
            items.append({"key": key, "label": labels.get(key, key), "count": count})
        return items

    return {
        "article_count": article_count,
        "recent_titles": titles[:12],
        "title_pattern_counts": dict(title_patterns),
        "opening_pattern_counts": dict(opening_patterns),
        "ending_pattern_counts": dict(ending_patterns),
        "heading_pattern_counts": dict(heading_patterns),
        "editorial_style_counts": dict(style_counts),
        "archetype_counts": dict(archetype_counts),
        "overused_title_patterns": top(title_patterns, TITLE_PATTERN_LABELS),
        "overused_opening_patterns": top(opening_patterns, OPENING_PATTERN_LABELS),
        "overused_ending_patterns": top(ending_patterns, ENDING_PATTERN_LABELS),
        "overused_heading_patterns": top(heading_patterns, HEADING_PATTERN_LABELS),
        "recent_editorial_styles": list(style_counts.keys())[:8],
    }


def _pick_from_candidates(candidates: list[dict[str, Any]], summary: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    style_counts = _recent_style_counts(summary)
    overused_title_counts = _overused_pattern_counts(summary, "title")
    overused_opening_counts = _overused_pattern_counts(summary, "opening")
    overused_ending_counts = _overused_pattern_counts(summary, "ending")
    overused_heading_counts = _overused_pattern_counts(summary, "heading")
    corpus = " ".join(
        [
            str(context.get("topic") or ""),
            str(context.get("selected_title") or ""),
            str(context.get("title") or ""),
            str(context.get("direction") or ""),
            json.dumps(context.get("research") or {}, ensure_ascii=False),
        ]
    )
    content_mode = _normalize_key(str(context.get("content_mode") or ""))
    strategy = context.get("account_strategy") or {}
    target_reader = _normalize_key(str(strategy.get("target_reader") or ""))
    primary_goal = _normalize_key(str(strategy.get("primary_goal") or ""))
    preferred_styles = {_normalize_key(str(item)) for item in (strategy.get("preferred_editorial_styles") or []) if _normalize_key(str(item))}
    best: dict[str, Any] | None = None
    best_score = -10**9

    for profile in candidates:
        style_key = _normalize_key(str(profile.get("style_key") or ""))
        score = 0
        if content_mode and content_mode in profile.get("content_modes", []):
            score += 2
        for keyword in profile.get("topic_keywords", []):
            if keyword and keyword in corpus:
                score += 2
        score -= style_counts.get(style_key, 0) * 4
        if preferred_styles and style_key in preferred_styles:
            score += 3
        if target_reader == "general-tech" and primary_goal == "open-and-read":
            if style_key in {"field-observation", "case-memo"}:
                score += 4
            if style_key in {"signal-briefing", "qa-cross-exam"}:
                score -= 2

        allowed_patterns = {_normalize_key(str(item)) for item in (profile.get("allowed_title_patterns") or []) if _normalize_key(str(item))}
        overlap_pressure = len({item for item in allowed_patterns if overused_title_counts.get(item, 0) > 0})
        if overlap_pressure:
            score -= overlap_pressure * 2
        elif overused_title_counts:
            score += 1

        style_pressure = _STYLE_PATTERN_PRESSURE.get(style_key, {})
        title_penalty = sum(min(overused_title_counts.get(_normalize_key(item), 0), 4) for item in style_pressure.get("title", set()))
        opening_penalty = sum(min(overused_opening_counts.get(_normalize_key(item), 0), 4) for item in style_pressure.get("opening", set()))
        ending_penalty = sum(min(overused_ending_counts.get(_normalize_key(item), 0), 4) for item in style_pressure.get("ending", set()))
        heading_penalty = sum(min(overused_heading_counts.get(_normalize_key(item), 0), 4) for item in style_pressure.get("heading", set()))
        score -= (title_penalty * 1.4) + (opening_penalty * 1.1) + (ending_penalty * 1.1) + (heading_penalty * 1.1)

        seed = hashlib.md5(f"{context.get('topic','')}|{context.get('selected_title','')}|{style_key}".encode("utf-8")).hexdigest()
        score += int(seed[:4], 16) / 65535
        if score > best_score:
            best = profile
            best_score = score
    return dict(best or candidates[0])


def default_editorial_blueprint(context: dict[str, Any]) -> dict[str, Any]:
    archetype = _normalize_key(str(context.get("article_archetype") or ""))
    summary = context.get("recent_corpus_summary") or {}
    candidates = [
        profile
        for profile in EDITORIAL_STYLE_LIBRARY.values()
        if not archetype or archetype in profile.get("suited_archetypes", [])
    ]
    if not candidates:
        candidates = list(EDITORIAL_STYLE_LIBRARY.values())
    chosen = _pick_from_candidates(candidates, summary if isinstance(summary, dict) else {}, context)
    alternatives = [
        profile["style_key"]
        for profile in candidates
        if profile["style_key"] != chosen["style_key"]
    ][:3]
    chosen["alternate_style_keys"] = alternatives
    chosen["blocked_title_patterns"] = [item.get("key") for item in (summary.get("overused_title_patterns") or [])][:3] if isinstance(summary, dict) else []
    chosen["blocked_opening_patterns"] = [item.get("key") for item in (summary.get("overused_opening_patterns") or [])][:3] if isinstance(summary, dict) else []
    chosen["blocked_ending_patterns"] = [item.get("key") for item in (summary.get("overused_ending_patterns") or [])][:3] if isinstance(summary, dict) else []
    chosen["blocked_heading_patterns"] = [item.get("key") for item in (summary.get("overused_heading_patterns") or [])][:3] if isinstance(summary, dict) else []
    account_strategy = context.get("account_strategy") or {}
    if account_strategy:
        preferred_opening = [str(item).strip() for item in (account_strategy.get("preferred_opening_modes") or []) if str(item).strip()]
        preferred_ending = [str(item).strip() for item in (account_strategy.get("preferred_ending_modes") or []) if str(item).strip()]
        if preferred_opening:
            chosen["preferred_opening_modes"] = preferred_opening[:4]
            chosen["opening_strategy"] = f"{preferred_opening[0]}优先，不要先上抽象判断。"
        if preferred_ending:
            chosen["preferred_ending_modes"] = preferred_ending[:4]
            chosen["ending_strategy"] = f"{preferred_ending[0]}优先，少做模板化清单收尾。"
    chosen["diversity_note"] = (
        f"最近语料里高频出现的标题/开头/结尾模式要主动避开，当前优先改用“{chosen['style_label']}”这一路数。"
    )
    return chosen


def normalize_editorial_blueprint(payload: Any, context: dict[str, Any]) -> dict[str, Any]:
    base = default_editorial_blueprint(context)
    if not isinstance(payload, dict):
        return base
    merged = dict(base)
    style_key = _normalize_key(str(payload.get("style_key") or payload.get("style") or merged.get("style_key") or ""))
    if style_key in EDITORIAL_STYLE_LIBRARY:
        merged = merged | dict(EDITORIAL_STYLE_LIBRARY[style_key])
        merged["style_key"] = style_key
    for key, value in payload.items():
        if isinstance(value, str):
            cleaned = _normalize_text(value)
            if cleaned:
                merged[key] = cleaned
        elif isinstance(value, list):
            items = [_normalize_text(item) for item in value if _normalize_text(item)]
            if items:
                merged[key] = items[:8]
        elif value not in (None, "", [], {}):
            merged[key] = value
    merged.setdefault("style_key", base["style_key"])
    if merged["style_key"] in EDITORIAL_STYLE_LIBRARY:
        merged.setdefault("style_label", EDITORIAL_STYLE_LIBRARY[merged["style_key"]]["style_label"])
    return merged


def _short_focus(topic: str, angle: str = "") -> str:
    source = _normalize_text(topic or angle or "这个问题")
    source = re.sub(r"(这次真正的信号|真正值得聊的|真正的分水岭在这里|别急着下结论|先别急着站队|很多人看热闹|最容易被忽略的那一步|更深一层)", "", source)
    source = re.sub(r"(真正该看的.*|真正值得看的.*|真正要看的.*|更该看清.*|别只盯着.*)$", "", source).strip("，,:：。！？? ")
    source = re.split(r"[，,:：。！？?]", source, maxsplit=1)[0].strip()
    compact = re.sub(r"\s+", "", source)
    amount_match = re.search(
        r"^(?P<subject>[\u4e00-\u9fffA-Za-z]{2,8})(?:20\d{2}年)?(?:金融科技|金融|科技)?投入(?:超|破|达|过|近)?(?P<num>\d+(?:\.\d+)?亿)",
        compact,
    )
    if amount_match:
        return f"{amount_match.group('subject')}一年砸下{amount_match.group('num')}"
    compact = re.sub(r"20\d{2}年", "", compact)
    compact = re.sub(r"(真正|其实|正在|一下子|突然)", "", compact)
    compact = compact.strip("，,:：。！？? ")
    if not compact:
        return "这个问题"
    if len(compact) <= 16:
        return compact
    return compact[:16]


TITLE_FAMILY_LABELS = {
    "viewpoint-direct": "观点直述型",
    "pain-truth": "痛点真相型",
    "counterintuitive": "反常识拆解型",
    "cost-consequence": "代价后果型",
    "method-rule": "方法规律型",
}
TITLE_EMOTION_MODE = "共鸣+反差"
TITLE_COUNT_DEFAULT = 10
TITLE_FAMILY_QUOTAS = {
    "default": [("viewpoint-direct", 4), ("pain-truth", 2), ("counterintuitive", 2), ("cost-consequence", 2)],
    "tutorial": [("viewpoint-direct", 3), ("pain-truth", 2), ("counterintuitive", 2), ("cost-consequence", 2), ("method-rule", 1)],
}
TITLE_ABSOLUTE_WORDS = ("唯一", "彻底", "一定", "所有", "必然", "永远", "稳赢", "100%")


def _infer_title_archetype(topic: str, angle: str = "", editorial_blueprint: dict[str, Any] | None = None) -> str:
    blueprint = editorial_blueprint or {}
    style_key = _normalize_key(str(blueprint.get("style_key") or ""))
    corpus = _normalize_text(f"{topic} {angle}")
    if any(word in corpus for word in ["教程", "指南", "步骤", "怎么做", "如何", "方法", "实操", "SOP", "模板"]):
        return "tutorial"
    if any(word in corpus for word in ["案例", "复盘", "拆解", "公司", "团队", "项目"]):
        return "case-study"
    if any(word in corpus for word in ["现场", "一线", "对话", "故事", "经历", "写给", "那天", "后来"]):
        return "narrative"
    if style_key in {"practical-playbook"}:
        return "tutorial"
    if style_key in {"case-memo"}:
        return "case-study"
    if style_key in {"field-observation", "open-letter"}:
        return "narrative"
    return "commentary"


def _pick_first_hit(source: str, mapping: list[tuple[tuple[str, ...], str]], fallback: str) -> str:
    lowered = _normalize_text(source)
    for keywords, phrase in mapping:
        if any(keyword in lowered for keyword in keywords):
            return phrase
    return fallback


def _title_surface_phrase(topic: str, angle: str, archetype: str) -> str:
    return _pick_first_hit(
        f"{topic} {angle}",
        [
            (("投入", "融资", "预算", "成本"), "花了多少钱"),
            (("工具", "模型", "参数", "能力"), "工具和参数"),
            (("场景", "应用", "功能"), "场景数量"),
            (("流量", "热度", "发布", "消息"), "表面热闹"),
            (("方法", "步骤", "流程"), "动作做得更多"),
        ],
        "表面结果" if archetype != "tutorial" else "动作做得更多",
    )


def _title_truth_phrase(topic: str, angle: str, archetype: str) -> str:
    return _pick_first_hit(
        f"{topic} {angle}",
        [
            (("交付", "交付链路", "上线", "落地链路"), "交付顺序"),
            (("落地", "执行"), "落地顺序"),
            (("边界", "治理", "责任", "问责"), "责任边界"),
            (("顺序", "流程", "步骤", "优先级"), "判断顺序"),
            (("方法", "规律", "打法", "模板"), "关键规律"),
            (("代价", "成本", "后果", "影响"), "代价后果"),
            (("平台", "底座", "底层"), "底层能力"),
            (("趋势", "拐点", "信号", "风向"), "真正信号"),
        ],
        {
            "tutorial": "关键顺序",
            "case-study": "关键一步",
            "narrative": "真实处境",
        }.get(archetype, "真正信号"),
    )


def _title_pain_phrase(topic: str, angle: str, audience: str, archetype: str) -> str:
    return _pick_first_hit(
        f"{topic} {angle} {audience}",
        [
            (("焦虑", "疲惫", "混乱", "卡住"), "明明很努力却越来越累"),
            (("打工人", "职场", "团队", "管理者"), "团队越忙越容易卡住"),
            (("落地", "交付", "执行"), "总觉得会做却总做不顺"),
            (("判断", "误判", "决策"), "多数人总在关键处看偏"),
        ],
        {
            "tutorial": "总觉得会做却总做不顺",
            "case-study": "项目一提速就容易失控",
            "narrative": "明明在努力却越来越累",
        }.get(archetype, "多数人总在关键处看偏"),
    )


def _title_consequence_phrase(topic: str, angle: str, archetype: str) -> str:
    return _pick_first_hit(
        f"{topic} {angle}",
        [
            (("边界", "责任", "治理"), "责任边界"),
            (("交付", "执行", "流程"), "交付节奏"),
            (("团队", "组织", "管理"), "组织流程"),
            (("客户", "业务", "用户"), "业务结果"),
            (("风控", "合规", "审计"), "风控链路"),
        ],
        {
            "tutorial": "返工成本",
            "case-study": "结果走向",
            "narrative": "情绪判断",
        }.get(archetype, "结果走向"),
    )


def _title_share_hook(topic: str, angle: str, archetype: str) -> str:
    return _pick_first_hit(
        f"{topic} {angle}",
        [
            (("误判", "看偏", "忽略"), "原来问题在这里"),
            (("代价", "成本", "后果"), "太真实了"),
            (("方法", "步骤", "规律"), "这一步太关键了"),
            (("趋势", "拐点", "信号"), "这才是值得转发的判断"),
        ],
        "太真实了" if archetype != "tutorial" else "这一步太关键了",
    )


def _cleanup_title_text(title: str) -> str:
    value = _normalize_text(title)
    replacements = [
        ("真正真正", "真正"),
        ("其实其实", "其实"),
        ("最容易让人卡住的", "最容易卡住的"),
        ("真正有效的方法和规律", "真正有效的规律"),
        ("真正的信号和判断", "真正的判断"),
        ("真正的信号和拐点", "真正的拐点"),
        ("判断顺序和关键一步", "关键顺序"),
        ("影响路径和后果", "代价和后果"),
        ("真正会拉开差距的，是", "拉开差距的，是"),
        ("真正关键的是", "关键是"),
    ]
    for old, new in replacements:
        value = value.replace(old, new)
    value = re.sub(r"[，,:：]\s*[，,:：]", "，", value)
    value = re.sub(r"\s+", "", value)
    if value.count("：") + value.count("|") + value.count("｜") > 1:
        value = value.replace("｜", "").replace("|", "")
    return value.strip("，,:：。！？? ")


def _trim_title_length(title: str) -> str:
    value = _cleanup_title_text(title)
    if len(value) <= 28:
        return value
    shorter = value.replace("真正", "").replace("其实", "").replace("最容易", "最易")
    if len(shorter) <= 28:
        return shorter
    shorter = shorter.replace("更该看清", "看清").replace("真正会", "")
    if len(shorter) <= 28:
        return shorter
    return ""


def _build_title_entry(
    *,
    title: str,
    family: str,
    audience: str,
    components: dict[str, str],
    round_index: int,
) -> dict[str, str]:
    return {
        "title": _trim_title_length(title),
        "strategy": f"{TITLE_FAMILY_LABELS.get(family, family)}标题候选",
        "audience_fit": audience or "大众读者",
        "risk_note": "按爆款标题家族生成，并主动规避旧模板。",
        "title_family": family,
        "title_formula_components": components,
        "title_emotion_mode": TITLE_EMOTION_MODE,
        "title_generation_round": round_index,
    }


def _family_templates(family: str, focus: str, truth: str, pain: str, surface: str, consequence: str) -> list[str]:
    mapping = {
        "viewpoint-direct": [
            f"{focus}，真正关键的是{truth}",
            f"{focus}进入下一阶段，更该看清{truth}",
            f"{focus}真正会拉开差距的，是{truth}",
            f"{focus}别只盯着{surface}，更该看清{truth}",
            f"{focus}真正要重估的，是{truth}",
        ],
        "pain-truth": [
            f"{focus}最容易让人卡住的，往往是{truth}",
            f"{pain}的人越来越多，背后缺的其实是{truth}",
            f"{focus}最容易做反的，其实是{truth}",
            f"{focus}看上去不难，真正难的是{truth}",
        ],
        "counterintuitive": [
            f"关于{focus}，最反常识的一点是{truth}",
            f"{focus}最容易被忽略的，其实是{truth}",
            f"{focus}大家最容易看偏的，就是{truth}",
            f"{focus}真正出人意料的，不是{surface}，而是{truth}",
        ],
        "cost-consequence": [
            f"{focus}，最先吃亏的是{consequence}",
            f"{focus}一旦继续放大，先受影响的是{consequence}",
            f"{focus}看上去只是{surface}，先被改写的其实是{consequence}",
            f"{focus}最该担心的，不是{surface}，而是{consequence}",
        ],
        "method-rule": [
            f"{focus}想少走弯路，先抓住这条规律",
            f"{focus}真正有效的方法，是先把这一步做对",
            f"{focus}别再乱补动作，先把关键顺序做对",
        ],
    }
    return mapping.get(family, [])


def generate_diverse_title_variants(
    topic: str,
    angle: str = "",
    audience: str = "",
    *,
    editorial_blueprint: dict[str, Any] | None = None,
    recent_titles: list[str] | None = None,
    recent_corpus_summary: dict[str, Any] | None = None,
    writing_persona: dict[str, Any] | None = None,
    account_strategy: dict[str, Any] | None = None,
    count: int = TITLE_COUNT_DEFAULT,
    boost_round: int = 0,
    weakness_hints: list[str] | None = None,
) -> list[dict[str, str]]:
    blueprint = editorial_blueprint or {}
    strategy = account_strategy or {}
    recent_titles = [str(item or "").strip() for item in (recent_titles or []) if str(item or "").strip()]
    recent_summary = recent_corpus_summary or {}
    blocked_patterns = {
        str(item.get("key") or "").strip()
        for item in (recent_summary.get("overused_title_patterns") or [])
        if str(item.get("key") or "").strip()
    }
    blocked_patterns.update({str(item).strip() for item in (strategy.get("blocked_title_patterns") or []) if str(item).strip()})
    blocked_patterns.update({"why-think-clear", "danger-not-but"})
    blocked_fragments = {str(item).strip() for item in (strategy.get("blocked_title_fragments") or []) if str(item).strip()}
    blocked_fragments.update({"为什么大多数人", "普通人一定要先想清", "先想清 3 件事", "先想清3件事"})

    archetype = _infer_title_archetype(topic, angle, blueprint)
    focus = _short_focus(topic, angle)
    truth = _title_truth_phrase(topic, angle, archetype)
    surface = _title_surface_phrase(topic, angle, archetype)
    pain = _title_pain_phrase(topic, angle, audience, archetype)
    consequence = _title_consequence_phrase(topic, angle, archetype)
    share_hook = _title_share_hook(topic, angle, archetype)
    round_index = max(0, int(boost_round or 0))
    quotas = TITLE_FAMILY_QUOTAS["tutorial" if archetype == "tutorial" else "default"]

    if round_index >= 1:
        truth = _trim_title_length(f"更深一层的{truth}").replace("更深一层的", "") or truth
        consequence = consequence.replace("结果和", "").replace("真正", "")

    seen: set[str] = set()
    output: list[dict[str, str]] = []
    weakness_hints = [str(item or "").strip() for item in (weakness_hints or []) if str(item or "").strip()]
    if "高预期" in weakness_hints and archetype != "tutorial":
        quotas = [("viewpoint-direct", 5), ("pain-truth", 2), ("counterintuitive", 2), ("cost-consequence", 1)]

    for family, quota in quotas:
        components = {
            "pain_point": pain,
            "truth_or_rule": truth,
            "counterintuitive_hook": surface,
            "share_hook": share_hook,
        }
        variants = _family_templates(family, focus, truth, pain, surface, consequence)
        if round_index >= 1:
            variants = variants + [
                f"{focus}这件事，最容易看偏的是{truth}",
                f"{focus}越往后走，越要看清{truth}",
            ]
        picked = 0
        for raw_title in variants:
            title = _trim_title_length(raw_title)
            compact = re.sub(r"\s+", "", title)
            if not title or compact in seen or title in recent_titles:
                continue
            if any(word in title for word in TITLE_ABSOLUTE_WORDS):
                continue
            pattern_key = title_template_key(title)
            if blocked_patterns and pattern_key in blocked_patterns:
                continue
            if any(fragment in title for fragment in blocked_fragments):
                continue
            if len(title) < 12 or len(title) > 28:
                continue
            if title.count("？") + title.count("?") > 1:
                continue
            if title.count("：") + title.count("｜") + title.count("|") > 1:
                continue
            seen.add(compact)
            output.append(
                _build_title_entry(
                    title=title,
                    family=family,
                    audience=audience,
                    components=components,
                    round_index=round_index,
                )
            )
            picked += 1
            if picked >= quota:
                break

    if len(output) < count:
        rescue_templates = [
            f"{focus}，真正关键的是{truth}",
            f"{focus}最容易被忽略的，其实是{truth}",
            f"{focus}，最先吃亏的是{consequence}",
            f"{focus}想少走弯路，先抓住{truth}",
        ]
        for raw_title in rescue_templates:
            title = _trim_title_length(raw_title)
            compact = re.sub(r"\s+", "", title)
            if not title or compact in seen or title in recent_titles:
                continue
            pattern_key = title_template_key(title)
            if blocked_patterns and pattern_key in blocked_patterns:
                continue
            if any(fragment in title for fragment in blocked_fragments):
                continue
            seen.add(compact)
            output.append(
                _build_title_entry(
                    title=title,
                    family="viewpoint-direct",
                    audience=audience,
                    components={
                        "pain_point": pain,
                        "truth_or_rule": truth,
                        "counterintuitive_hook": surface,
                        "share_hook": share_hook,
                    },
                    round_index=round_index,
                )
            )
            if len(output) >= count:
                break
    return output[:count]
