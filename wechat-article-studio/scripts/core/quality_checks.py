from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any


BROKEN_CHAR_PATTERN = re.compile(r"\uFFFD")
VISIBLE_TOKEN_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]+")
ACTION_WORDS = (
    "发布",
    "启动",
    "规范",
    "拉到",
    "推到",
    "进入",
    "冲到",
    "上线",
    "封杀",
    "接进",
    "接入",
    "改写",
    "重排",
    "盯上",
    "开打",
    "出手",
    "放出",
    "叫停",
    "收紧",
    "涨到",
    "跌到",
    "推上",
)
OUTCOME_WORDS = (
    "代价",
    "后果",
    "吃亏",
    "风险",
    "买单",
    "重排",
    "失控",
    "信任",
    "秩序",
    "边界",
    "成本",
    "门槛",
    "节奏",
    "入口",
    "分发",
    "岗位",
    "用人成本",
    "流程问题",
    "系统建设",
    "判断顺序",
)
ABSTRACT_TAIL_WORDS = (
    "边界",
    "秩序",
    "流程问题",
    "系统建设",
    "判断顺序",
    "真实处境",
)
COST_SIGNAL_PATTERNS = (
    r"成本",
    r"代价",
    r"吃亏",
    r"买单",
    r"返工",
    r"损耗",
    r"窗口",
    r"赔钱",
    r"浪费",
    r"付出",
)
DISCUSSION_SIGNAL_PATTERNS = (
    r"如果是你",
    r"你会怎么",
    r"你更认同",
    r"该不该",
    r"到底",
    r"站队",
    r"争议",
    r"你最想",
    r"你会先",
)
SUMMARY_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_visible_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def visible_length(value: str) -> int:
    return len(normalize_visible_text(value))


def broken_char_ratio(value: str) -> float:
    visible = normalize_visible_text(value)
    if not visible:
        return 0.0
    hits = visible.count("?") + len(BROKEN_CHAR_PATTERN.findall(visible))
    return hits / max(1, len(visible))


def has_broken_char_run(value: str, *, min_run: int = 4) -> bool:
    visible = normalize_visible_text(value)
    return "?" * int(min_run) in visible or bool(re.search(rf"\uFFFD{{{int(min_run)},}}", visible))


def metadata_field_issues(value: str, *, field: str) -> list[str]:
    visible = normalize_visible_text(value)
    issues: list[str] = []
    if not visible:
        issues.append(f"{field} 为空")
        return issues
    ratio = broken_char_ratio(visible)
    if ratio >= 0.2:
        issues.append(f"{field} 含异常字符比例过高")
    if has_broken_char_run(visible):
        issues.append(f"{field} 出现连续异常字符")
    if field == "summary" and len(visible) < 18:
        issues.append("summary 过短")
    return issues


def metadata_integrity_report(title: str, summary: str) -> dict[str, Any]:
    title_issues = metadata_field_issues(title, field="title")
    summary_issues = metadata_field_issues(summary, field="summary")
    reasons = [*title_issues, *summary_issues]
    return {
        "passed": not reasons,
        "status": "passed" if not reasons else "failed",
        "title_passed": not title_issues,
        "summary_passed": not summary_issues,
        "title_issues": title_issues,
        "summary_issues": summary_issues,
        "reasons": reasons,
        "title_length": visible_length(title),
        "summary_length": visible_length(summary),
        "title_broken_char_ratio": round(broken_char_ratio(title), 4),
        "summary_broken_char_ratio": round(broken_char_ratio(summary), 4),
    }


def workspace_batch_key(workspace: Path | str | None) -> str:
    if workspace is None:
        return ""
    name = Path(str(workspace)).name
    match = re.match(r"^(\d{8})", name)
    return str(match.group(1)) if match else ""


def title_token_set(value: str) -> set[str]:
    return {item.lower() for item in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}", normalize_visible_text(value))}


def title_token_similarity(left: str, right: str) -> float:
    left_tokens = title_token_set(left)
    right_tokens = title_token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return round(len(left_tokens & right_tokens) / len(union), 3)


def split_markdown_paragraphs(text: str) -> list[str]:
    return [_normalize_text(part) for part in re.split(r"\n\s*\n", str(text or "")) if _normalize_text(part)]


def lead_paragraph_count(body: str) -> int:
    before_heading: list[str] = []
    for line in str(body or "").splitlines():
        if re.match(r"^\s*##\s+", line):
            break
        before_heading.append(line)
    return len([item for item in re.split(r"\n\s*\n", "\n".join(before_heading)) if _normalize_text(item)])


def _excerpt_signature(paragraphs: list[str], *, count: int, tail: bool = False) -> str:
    if not paragraphs:
        return ""
    chosen = paragraphs[-count:] if tail else paragraphs[:count]
    payload = "\n".join(normalize_visible_text(item) for item in chosen if normalize_visible_text(item))
    if not payload:
        return ""
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def opening_excerpt_signature(body: str, *, count: int = 2) -> str:
    return _excerpt_signature(split_markdown_paragraphs(body), count=count, tail=False)


def ending_excerpt_signature(body: str, *, count: int = 2) -> str:
    return _excerpt_signature(split_markdown_paragraphs(body), count=count, tail=True)


def paragraph_overlap_signals(current_body: str, other_body: str) -> dict[str, Any]:
    current_paragraphs = split_markdown_paragraphs(current_body)
    other_paragraphs = split_markdown_paragraphs(other_body)
    current_norm = [normalize_visible_text(item) for item in current_paragraphs if visible_length(item) >= 12]
    other_norm = [normalize_visible_text(item) for item in other_paragraphs if visible_length(item) >= 12]
    shared = [item for item in current_norm if item in set(other_norm)]
    first_two_current = {normalize_visible_text(item) for item in current_paragraphs[:2] if visible_length(item) >= 12}
    first_two_other = {normalize_visible_text(item) for item in other_paragraphs[:2] if visible_length(item) >= 12}
    last_two_current = {normalize_visible_text(item) for item in current_paragraphs[-2:] if visible_length(item) >= 12}
    last_two_other = {normalize_visible_text(item) for item in other_paragraphs[-2:] if visible_length(item) >= 12}
    return {
        "shared_paragraph_count": len(shared),
        "shared_opening_paragraph_count": len(first_two_current & first_two_other),
        "shared_ending_paragraph_count": len(last_two_current & last_two_other),
        "shared_paragraph_examples": shared[:3],
    }


def title_hook_shape(title: str, *, topic: str = "", audience: str = "") -> dict[str, Any]:
    text = str(title or "")
    topic_tokens = title_token_set(f"{topic} {audience}")
    token_overlap = title_token_set(text) & topic_tokens
    has_object = bool(token_overlap) or bool(re.search(r"(OpenAI|Anthropic|Meta|微软|谷歌|腾讯|学校|银行|老师|商家|用户|团队|监管|教育部|五部门|企业)", text))
    has_action = any(word in text for word in ACTION_WORDS)
    has_outcome = any(word in text for word in OUTCOME_WORDS)
    return {
        "has_object": has_object,
        "has_action": has_action,
        "has_outcome": has_outcome,
        "shape_score": sum(1 for item in [has_object, has_action, has_outcome] if item),
    }


def cost_signal_count(text: str) -> int:
    return sum(len(re.findall(pattern, str(text or ""))) for pattern in COST_SIGNAL_PATTERNS)


def discussion_trigger_count(text: str) -> int:
    return sum(len(re.findall(pattern, str(text or ""))) for pattern in DISCUSSION_SIGNAL_PATTERNS)


def scene_signal_present(text: str) -> bool:
    value = str(text or "")
    return bool(
        re.search(r"(那天|刚刚|会议室|办公室|工位|白板|凌晨|晚上|中午|看到|听到|消息弹出来|群里|刚坐下|说：|他说|她说)", value)
    )


def cost_signal_present(text: str) -> bool:
    return cost_signal_count(text) >= 1


def discussion_trigger_present(text: str) -> bool:
    return discussion_trigger_count(text) >= 1


def abstract_tail_penalty(title: str) -> int:
    text = normalize_visible_text(title)
    if not text:
        return 0
    if not any(text.endswith(word) or word in text[-8:] for word in ABSTRACT_TAIL_WORDS):
        return 0
    if any(word in text for word in OUTCOME_WORDS):
        return 0
    return 1


def build_article_summary(title: str, body: str, *, min_len: int = 45, max_len: int = 90) -> str:
    paragraphs = split_markdown_paragraphs(body)
    if not paragraphs:
        return _normalize_text(title)[:max_len]
    lead = " ".join(paragraphs[:3])
    sentences = [_normalize_text(item) for item in SUMMARY_SENTENCE_SPLIT_RE.split(lead) if _normalize_text(item)]
    if not sentences:
        sentences = [_normalize_text(lead)]
    ranked = sorted(
        sentences,
        key=lambda item: (
            discussion_trigger_count(item) > 0,
            cost_signal_count(item) > 0,
            scene_signal_present(item),
            any(word in item for word in OUTCOME_WORDS),
            len(item),
        ),
        reverse=True,
    )
    pieces: list[str] = []
    total = 0
    for sentence in ranked:
        if sentence in pieces:
            continue
        pieces.append(sentence)
        total = len("".join(pieces))
        if total >= min_len:
            break
    summary = "".join(pieces).strip()
    if len(summary) > max_len:
        summary = summary[: max_len - 1].rstrip("，,；;。 ") + "。"
    if len(summary) < min_len and paragraphs:
        fallback = _normalize_text(" ".join(paragraphs[:2]))
        if len(fallback) > max_len:
            fallback = fallback[: max_len - 1].rstrip("，,；;。 ") + "。"
        summary = fallback
    return summary.strip()
