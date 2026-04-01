from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.artifacts import now_iso, read_json, read_text, write_json, write_text
from core.editorial_strategy import (
    HEADING_PATTERN_LABELS,
    OPENING_PATTERN_LABELS,
    ENDING_PATTERN_LABELS,
    TITLE_PATTERN_LABELS,
    heading_pattern_key,
    opening_pattern_key,
    ending_pattern_key,
    summarize_recent_corpus,
    title_template_key,
)


PLAYBOOK_FILENAMES = (
    "style-playbook.json",
    "style-playbook.md",
    "playbook.json",
    "playbook.md",
)
LESSON_FILENAMES = (
    "author-lessons.json",
    "edit-lessons.json",
    "style-lessons.json",
)
MAX_SAMPLE_ARTICLES = 24
MAX_TEXT_LENGTH = 12000
AI_STYLE_PHRASES = [
    "首先",
    "其次",
    "最后",
    "总之",
    "综上所述",
    "值得注意的是",
    "需要指出的是",
    "接下来",
    "如果你只想记住一句话",
    "最后给你一个可执行清单",
]
STARTER_STOPWORDS = {
    "这是",
    "这个",
    "那个",
    "因为",
    "所以",
    "如果",
    "但是",
    "而且",
    "然后",
    "很多人",
    "你可能",
    "如果你",
    "我们",
    "他们",
    "其实",
}


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" -•>\"'“”‘’\n\r\t")


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text or "rule"


def _parse_iso(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _days_since(value: str) -> int:
    parsed = _parse_iso(value)
    if parsed is None:
        return 9999
    now = datetime.now(timezone.utc)
    return max(0, int((now - parsed).days))


def _rule_confidence(occurrences: int, last_seen: str) -> float:
    days = _days_since(last_seen)
    recency_bonus = 0.18 if days <= 30 else 0.1 if days <= 90 else 0.02
    confidence = 0.22 + min(0.6, occurrences * 0.16) + recency_bonus
    return round(max(0.1, min(confidence, 1.0)), 2)


def _rule_strength(occurrences: int, confidence: float) -> str:
    return "hard" if occurrences >= 2 and confidence >= 0.62 else "soft"


def _dedupe_examples(values: list[str], limit: int = 3) -> list[str]:
    output: list[str] = []
    for raw in values:
        value = _normalize_text(str(raw or ""))
        if not value or value in output:
            continue
        output.append(value)
        if len(output) >= limit:
            break
    return output


def _make_rule(
    *,
    key: str,
    rule_type: str,
    rule: str,
    examples: list[str] | None = None,
    occurrences: int = 1,
    last_seen: str | None = None,
    strength: str | None = None,
) -> dict[str, Any]:
    seen_at = last_seen or now_iso()
    confidence = _rule_confidence(int(max(1, occurrences)), seen_at)
    return {
        "key": _slug(key),
        "type": _normalize_text(rule_type) or "expression",
        "rule": _normalize_text(rule),
        "confidence": confidence,
        "occurrences": int(max(1, occurrences)),
        "last_seen": seen_at,
        "strength": strength or _rule_strength(int(max(1, occurrences)), confidence),
        "examples": _dedupe_examples(examples or []),
    }


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
    return path.stem


def _extract_body(raw: str) -> str:
    _, body = _split_frontmatter(raw)
    return body


def _clean_markdown(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", value)
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", value)
    value = re.sub(r"`([^`]+)`", r"\1", value)
    value = re.sub(r"<!--.*?-->", "", value, flags=re.S)
    value = re.sub(r"https?://\S+", "", value)
    return _normalize_text(value)


def _paragraphs(body: str) -> list[str]:
    return [_clean_markdown(block) for block in re.split(r"\n\s*\n", body or "") if _clean_markdown(block)]


def _headings(body: str) -> list[str]:
    items: list[str] = []
    for line in (body or "").splitlines():
        match = re.match(r"^#{2,6}\s+(.+?)\s*$", line.strip())
        if match:
            heading = _clean_markdown(match.group(1))
            if heading:
                items.append(heading)
    return items


def _sentence_split(body: str) -> list[str]:
    value = re.sub(r"\s+", " ", body or "").strip()
    if not value:
        return []
    return [part.strip() for part in re.split(r"(?<=[。！？!?；;])\s*", value) if part.strip()]


def _sentence_starters(body: str) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for sentence in _sentence_split(_clean_markdown(body)):
        compact = sentence.strip("，。！？!?；;：:、 ")
        if len(compact) < 6:
            continue
        for width in (4, 5, 6):
            if len(compact) < width:
                continue
            starter = compact[:width]
            if starter in STARTER_STOPWORDS:
                continue
            counter[starter] += 1
            break
    output: list[dict[str, Any]] = []
    for phrase, count in counter.most_common(8):
        output.append({"phrase": phrase, "count": count})
    return output


def _looks_like_scene_opening(paragraph: str) -> bool:
    value = _normalize_text(paragraph)
    if not value:
        return False
    if any(word in value for word in ["那天", "当时", "第一次", "现场", "会议室", "办公室", "群里", "那句", "刚坐下"]):
        return True
    return bool(re.search(r"\d{4}年|\d{1,2}月\d{1,2}日|\d{1,2}点", value))


def _voice_signals(body: str) -> list[str]:
    text = _clean_markdown(body)
    scores: Counter[str] = Counter()
    if any(word in text for word in ["我", "我们", "我一直", "我更在意", "我觉得"]):
        scores["第一人称判断"] += 2
    if any(word in text for word in ["看到", "刷到", "那一刻", "场景", "会议", "办公室", "消息"]):
        scores["场景切口"] += 2
    if any(word in text for word in ["数据", "报告", "研究", "官方", "文档", "案例"]):
        scores["证据托底"] += 2
    if any(word in text for word in ["判断", "信号", "分水岭", "误判", "边界"]):
        scores["判断递进"] += 2
    if any(word in text for word in ["你", "你会", "你会发现", "如果你"]):
        scores["对话感"] += 1
    if any(word in text for word in ["讲真", "坦白说", "说白了", "说实话"]):
        scores["口语感"] += 1
    if any(word in text for word in ["但是。", "可问题是", "偏偏", "反而"]):
        scores["转折张力"] += 1
    if any(word in text for word in ["真正拉开差距", "分水岭", "关键不是", "真正的问题"]):
        scores["分水岭判断"] += 2
    if any(word in text for word in ["误判", "边界", "例外", "反方"]):
        scores["边界意识"] += 2
    return [name for name, _ in scores.most_common(6)]


def _style_from_patterns(summary: dict[str, Any]) -> list[str]:
    counts = Counter(summary.get("editorial_style_counts") or {})
    return [str(key) for key, count in counts.most_common(4) if count > 0]


def _extract_example_snippets(article_paths: list[Path]) -> list[dict[str, str]]:
    snippets: list[dict[str, str]] = []
    seen: set[str] = set()
    for path in article_paths[:8]:
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            continue
        paragraphs = _paragraphs(_extract_body(raw))
        if not paragraphs:
            continue
        candidates: list[tuple[str, str]] = []
        opening = paragraphs[0]
        if 18 <= len(opening) <= 140:
            candidates.append(("opening", opening))
        transition = next(
            (
                item
                for item in paragraphs[1:-1]
                if any(word in item for word in ["不过", "但", "反过来", "话说回来", "不对", "更麻烦的是", "可真正的问题"])
                and 18 <= len(item) <= 140
            ),
            "",
        )
        if transition:
            candidates.append(("transition", transition))
        closing = paragraphs[-1]
        if 18 <= len(closing) <= 140:
            candidates.append(("closing", closing))
        for slot, text in candidates:
            normalized = _normalize_text(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            snippets.append({"slot": slot, "text": normalized})
            if len(snippets) >= 6:
                return snippets
    return snippets


def _normalize_rule_item(item: Any, *, fallback_seen_at: str = "") -> dict[str, Any] | None:
    if isinstance(item, dict) and item.get("rule"):
        rule_type = _normalize_text(str(item.get("type") or "expression")) or "expression"
        rule = _normalize_text(str(item.get("rule") or ""))
        if not rule:
            return None
        key = _normalize_text(str(item.get("key") or "")) or _slug(rule)
        examples = item.get("examples")
        if isinstance(examples, list):
            example_values = [str(value) for value in examples]
        else:
            example_values = []
        occurrences = int(item.get("occurrences") or 1)
        last_seen = str(item.get("last_seen") or fallback_seen_at or now_iso())
        confidence = float(item.get("confidence") or _rule_confidence(occurrences, last_seen))
        strength = str(item.get("strength") or _rule_strength(occurrences, confidence))
        return {
            "key": _slug(key),
            "type": rule_type,
            "rule": rule,
            "confidence": round(max(0.1, min(confidence, 1.0)), 2),
            "occurrences": max(1, occurrences),
            "last_seen": last_seen,
            "strength": "hard" if strength == "hard" else "soft",
            "examples": _dedupe_examples(example_values),
        }
    if isinstance(item, dict):
        value = _normalize_text(str(item.get("pattern") or item.get("summary") or ""))
    else:
        value = _normalize_text(str(item or ""))
    if not value:
        return None
    return _make_rule(key=value, rule_type="expression", rule=value, examples=[], occurrences=1, last_seen=fallback_seen_at or now_iso(), strength="soft")


def _rule_texts(rules: list[dict[str, Any]], limit: int = 16) -> list[str]:
    texts: list[str] = []
    for rule in rules:
        value = _normalize_text(str(rule.get("rule") or ""))
        if value and value not in texts:
            texts.append(value)
        if len(texts) >= limit:
            break
    return texts


def build_playbook_payload(article_paths: list[Path], lesson_patterns: list[str] | None = None) -> dict[str, Any]:
    valid_paths = [path.resolve() for path in article_paths if path.exists() and path.is_file()][:MAX_SAMPLE_ARTICLES]
    articles: list[dict[str, Any]] = []
    combined_body = []
    title_lengths: list[int] = []
    title_marks: Counter[str] = Counter()
    question_titles = 0
    colon_titles = 0
    for path in valid_paths:
        raw = path.read_text(encoding="utf-8")
        title = _extract_title(raw, path)
        body = _extract_body(raw)
        paragraphs = _paragraphs(body)
        headings = _headings(body)
        articles.append(
            {
                "path": str(path),
                "title": title,
                "body": body[:MAX_TEXT_LENGTH],
                "paragraphs": paragraphs,
                "headings": headings,
            }
        )
        combined_body.append(body[:MAX_TEXT_LENGTH])
        compact_title = re.sub(r"\s+", "", title)
        if compact_title:
            title_lengths.append(len(compact_title))
        if "？" in title or "?" in title:
            question_titles += 1
        if "：" in title or ":" in title or "｜" in title or "|" in title:
            colon_titles += 1
        for mark in ["？", "?", "：", ":", "｜", "|", "，", ","]:
            if mark in title:
                title_marks[mark] += 1

    summary = summarize_recent_corpus(valid_paths, limit=len(valid_paths)) if valid_paths else {}
    starters = Counter()
    voice = Counter()
    evidence_preferences: Counter[str] = Counter()
    judgment_preferences: Counter[str] = Counter()
    avg_paragraph_lengths: list[int] = []
    for item in articles:
        for starter in _sentence_starters(item["body"]):
            starters[starter["phrase"]] += int(starter["count"] or 0)
        for signal in _voice_signals(item["body"]):
            voice[signal] += 1
        body_text = item["body"]
        if any(word in body_text for word in ["案例", "复盘", "实例", "项目"]):
            evidence_preferences["案例"] += 1
        if any(word in body_text for word in ["数据", "研究", "报告", "%", "指标", "官方", "文档"]):
            evidence_preferences["事实/数据"] += 1
        if any(word in body_text for word in ["场景", "那一刻", "办公室", "会议", "现场"]):
            evidence_preferences["场景细节"] += 1
        if any(word in body_text for word in ["判断", "分水岭", "误判", "边界"]):
            judgment_preferences["判断推进"] += 1
        if any(word in body_text for word in ["反方", "边界", "例外", "别急着"]):
            judgment_preferences["边界提醒"] += 1
        if any(word in body_text for word in ["趋势", "信号", "风向", "拐点"]):
            judgment_preferences["趋势判断"] += 1
        avg_paragraph_lengths.extend(len(re.sub(r"\s+", "", para)) for para in item["paragraphs"][:8])

    title_preferences = {
        "average_length": round(sum(title_lengths) / max(1, len(title_lengths)), 1) if title_lengths else 0,
        "question_ratio": round(question_titles / max(1, len(valid_paths)), 2) if valid_paths else 0,
        "colon_ratio": round(colon_titles / max(1, len(valid_paths)), 2) if valid_paths else 0,
        "preferred_patterns": summary.get("overused_title_patterns") or [],
        "common_punctuation": [{"mark": key, "count": count} for key, count in title_marks.most_common(5)],
    }
    starter_blacklist = [phrase for phrase, count in starters.most_common(8) if count >= 2]
    phrase_blacklist = starter_blacklist[:]
    for item in summary.get("recent_titles") or []:
        normalized = _normalize_text(item)
        if 8 <= len(normalized) <= 32 and normalized not in phrase_blacklist:
            phrase_blacklist.append(normalized)
        if len(phrase_blacklist) >= 10:
            break

    editorial_preferences = {
        "preferred_style_keys": _style_from_patterns(summary),
        "opening_preferences": summary.get("overused_opening_patterns") or [],
        "ending_preferences": summary.get("overused_ending_patterns") or [],
        "heading_preferences": summary.get("overused_heading_patterns") or [],
        "judgment_preferences": [name for name, _ in judgment_preferences.most_common(4)],
        "evidence_preferences": [name for name, _ in evidence_preferences.most_common(4)],
    }
    average_paragraph_length = round(sum(avg_paragraph_lengths) / max(1, len(avg_paragraph_lengths)), 1) if avg_paragraph_lengths else 0
    rhythm_preferences = {
        "average_paragraph_length": average_paragraph_length,
        "preferred_rhythm": "短段快切" if average_paragraph_length and average_paragraph_length <= 42 else "中段展开" if average_paragraph_length >= 68 else "张弛平衡",
    }
    playbook_summary = [
        f"标题平均长度约 {title_preferences['average_length']} 字，问句占比 {title_preferences['question_ratio']:.0%}，冒号/竖线占比 {title_preferences['colon_ratio']:.0%}。",
        f"优先保留这些表达纹理：{'、'.join([name for name, _ in voice.most_common(5)]) or '克制判断感'}。",
    ]
    if editorial_preferences["preferred_style_keys"]:
        playbook_summary.append(f"近期更像这些写法：{'、'.join(editorial_preferences['preferred_style_keys'])}。")
    if starter_blacklist:
        playbook_summary.append(f"这些句式起手已经很密：{'、'.join(starter_blacklist[:5])}。")
    if lesson_patterns:
        playbook_summary.append(f"人工改稿反复强调：{'；'.join(lesson_patterns[:4])}。")
    if editorial_preferences["judgment_preferences"]:
        playbook_summary.append(f"这个号更常用的判断方式：{'、'.join(editorial_preferences['judgment_preferences'])}。")
    if editorial_preferences["evidence_preferences"]:
        playbook_summary.append(f"更常用的证据材料：{'、'.join(editorial_preferences['evidence_preferences'])}。")
    playbook_summary.append(f"正文节奏更偏向：{rhythm_preferences['preferred_rhythm']}。")
    example_snippets = _extract_example_snippets(valid_paths)

    return {
        "generated_at": now_iso(),
        "source_count": len(valid_paths),
        "source_paths": [str(path) for path in valid_paths],
        "title_preferences": title_preferences,
        "voice_fingerprint": [name for name, _ in voice.most_common(6)],
        "sentence_starters_to_avoid": starter_blacklist,
        "phrase_blacklist": phrase_blacklist[:12],
        "average_paragraph_length": average_paragraph_length,
        "pattern_summary": summary,
        "editorial_preferences": editorial_preferences,
        "rhythm_preferences": rhythm_preferences,
        "lesson_patterns": lesson_patterns or [],
        "playbook_summary": playbook_summary,
        "example_snippets": example_snippets,
    }


def render_playbook_markdown(payload: dict[str, Any]) -> str:
    title_preferences = payload.get("title_preferences") or {}
    editorial_preferences = payload.get("editorial_preferences") or {}
    lines = [
        "# 风格作战卡",
        "",
        f"- 样本数：`{payload.get('source_count') or 0}`",
        f"- 生成时间：`{payload.get('generated_at') or ''}`",
        "",
        "## 标题偏好",
        "",
        f"- 平均长度：`{title_preferences.get('average_length') or 0}`",
        f"- 问句占比：`{title_preferences.get('question_ratio') or 0}`",
        f"- 冒号/竖线占比：`{title_preferences.get('colon_ratio') or 0}`",
    ]
    if title_preferences.get("preferred_patterns"):
        lines.append(f"- 高出现标题模式：{_format_pattern_items(title_preferences['preferred_patterns'], TITLE_PATTERN_LABELS)}")
    if payload.get("voice_fingerprint"):
        lines.extend(["", "## 文风指纹", ""] + [f"- {item}" for item in payload.get("voice_fingerprint") or []])
    if editorial_preferences.get("opening_preferences"):
        lines.extend(["", "## 开头与结尾", "", f"- 开头高频：{_format_pattern_items(editorial_preferences['opening_preferences'], OPENING_PATTERN_LABELS)}"])
    if editorial_preferences.get("ending_preferences"):
        lines.append(f"- 结尾高频：{_format_pattern_items(editorial_preferences['ending_preferences'], ENDING_PATTERN_LABELS)}")
    if editorial_preferences.get("heading_preferences"):
        lines.append(f"- 小标题高频：{_format_pattern_items(editorial_preferences['heading_preferences'], HEADING_PATTERN_LABELS)}")
    if payload.get("sentence_starters_to_avoid"):
        lines.extend(["", "## 主动避开", ""] + [f"- {item}" for item in payload.get("sentence_starters_to_avoid") or []])
    if payload.get("lesson_patterns"):
        lines.extend(["", "## 人工改稿学到的偏好", ""] + [f"- {item}" for item in payload.get("lesson_patterns") or []])
    if payload.get("example_snippets"):
        lines.extend(["", "## 范文片段", ""])
        for item in payload.get("example_snippets") or []:
            if isinstance(item, dict):
                slot = _normalize_text(str(item.get("slot") or "片段"))
                text = _normalize_text(str(item.get("text") or ""))
                if text:
                    lines.append(f"- {slot}：{text}")
    if payload.get("playbook_summary"):
        lines.extend(["", "## 一句话提醒", ""] + [f"- {item}" for item in payload.get("playbook_summary") or []])
    return "\n".join(lines).rstrip() + "\n"


def _format_pattern_items(items: list[dict[str, Any]], labels: dict[str, str]) -> str:
    parts: list[str] = []
    for item in items[:4]:
        key = str(item.get("key") or "")
        count = int(item.get("count") or 0)
        label = labels.get(key, str(item.get("label") or key))
        if not label:
            continue
        parts.append(f"{label}（{count}）")
    return "、".join(parts) or "暂无"


def _candidate_paths(workspace: Path, manifest: dict[str, Any], names: tuple[str, ...], field: str) -> list[Path]:
    paths: list[Path] = []
    explicit = manifest.get(field) or []
    if isinstance(explicit, str):
        explicit = [explicit]
    for raw in explicit:
        value = str(raw or "").strip()
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = (workspace / path).resolve()
        else:
            path = path.resolve()
        if path.exists():
            paths.append(path)
    for name in names:
        path = workspace / name
        if path.exists():
            paths.append(path.resolve())
    seen: set[str] = set()
    deduped: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _load_playbook_payload(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        payload = read_json(path, default={}) or {}
        if isinstance(payload, dict):
            return payload
        return {}
    text = read_text(path)
    bullets = []
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned.startswith("- "):
            bullets.append(cleaned[2:].strip())
    return {
        "playbook_summary": bullets[:12],
        "voice_fingerprint": bullets[:6],
        "phrase_blacklist": [],
        "sentence_starters_to_avoid": [],
        "example_snippets": [],
    }


def _load_lesson_patterns(path: Path) -> list[str]:
    payload = read_json(path, default={}) or {}
    rules = _load_lesson_rules_from_payload(payload)
    if rules:
        return _rule_texts(rules)
    patterns: list[str] = []
    if isinstance(payload, list):
        for item in payload:
            value = _normalize_text(str(item.get("pattern") if isinstance(item, dict) else item or ""))
            if value:
                patterns.append(value)
    return patterns[:16]


def _load_lesson_rules_from_payload(payload: Any) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        source_rules = payload.get("rules")
        if isinstance(source_rules, list):
            for item in source_rules:
                normalized = _normalize_rule_item(item, fallback_seen_at=str(payload.get("generated_at") or now_iso()))
                if normalized:
                    rules.append(normalized)
        items = payload.get("items") or []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("rules"), list):
                    for rule in item.get("rules") or []:
                        normalized = _normalize_rule_item(rule, fallback_seen_at=str(item.get("generated_at") or payload.get("generated_at") or now_iso()))
                        if normalized:
                            rules.append(normalized)
                else:
                    normalized = _normalize_rule_item(item, fallback_seen_at=str(payload.get("generated_at") or now_iso()))
                    if normalized:
                        rules.append(normalized)
        if not rules and isinstance(payload.get("patterns"), list):
            for item in payload.get("patterns") or []:
                normalized = _normalize_rule_item(item, fallback_seen_at=str(payload.get("generated_at") or now_iso()))
                if normalized:
                    rules.append(normalized)
    elif isinstance(payload, list):
        for item in payload:
            normalized = _normalize_rule_item(item, fallback_seen_at=now_iso())
            if normalized:
                rules.append(normalized)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in rules:
        key = str(item.get("key") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:24]


def build_author_memory_bundle(workspace: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    playbook_paths = _candidate_paths(workspace, manifest, PLAYBOOK_FILENAMES, "author_playbook_paths")
    lesson_paths = _candidate_paths(workspace, manifest, LESSON_FILENAMES, "author_lesson_paths")
    sample_paths = [Path(path) for path in (manifest.get("style_sample_paths") or []) if Path(path).exists()]
    loaded_playbook: dict[str, Any] = {}
    if playbook_paths:
        loaded_playbook = _load_playbook_payload(playbook_paths[0])
    lesson_patterns: list[str] = []
    lesson_rules: list[dict[str, Any]] = []
    for path in lesson_paths:
        payload = read_json(path, default={}) or {}
        for item in _load_lesson_patterns(path):
            if item not in lesson_patterns:
                lesson_patterns.append(item)
        for rule in _load_lesson_rules_from_payload(payload):
            if str(rule.get("key") or "") not in {str(item.get("key") or "") for item in lesson_rules}:
                lesson_rules.append(rule)
    derived_playbook = build_playbook_payload(sample_paths, lesson_patterns=lesson_patterns) if sample_paths else {}
    phrase_blacklist = []
    for item in (loaded_playbook.get("phrase_blacklist") or []) + (derived_playbook.get("phrase_blacklist") or []):
        value = _normalize_text(str(item or ""))
        if value and value not in phrase_blacklist:
            phrase_blacklist.append(value)
    sentence_starters = []
    for item in (loaded_playbook.get("sentence_starters_to_avoid") or []) + (derived_playbook.get("sentence_starters_to_avoid") or []):
        value = _normalize_text(str(item or ""))
        if value and value not in sentence_starters:
            sentence_starters.append(value)
    playbook_summary = []
    for item in (loaded_playbook.get("playbook_summary") or []) + (derived_playbook.get("playbook_summary") or []):
        value = _normalize_text(str(item or ""))
        if value and value not in playbook_summary:
            playbook_summary.append(value)
    voice_fingerprint = []
    for item in (loaded_playbook.get("voice_fingerprint") or []) + (derived_playbook.get("voice_fingerprint") or []):
        value = _normalize_text(str(item or ""))
        if value and value not in voice_fingerprint:
            voice_fingerprint.append(value)
    example_snippets = []
    for item in (loaded_playbook.get("example_snippets") or []) + (derived_playbook.get("example_snippets") or []):
        if isinstance(item, dict):
            text = _normalize_text(str(item.get("text") or ""))
            slot = _normalize_text(str(item.get("slot") or "example")) or "example"
            if text and all(text != str(existing.get("text") or "") for existing in example_snippets):
                example_snippets.append({"slot": slot, "text": text})
    rhythm_preferences = loaded_playbook.get("rhythm_preferences") or derived_playbook.get("rhythm_preferences") or {}
    hard_rules = [rule for rule in lesson_rules if rule.get("strength") == "hard"]
    soft_rules = [rule for rule in lesson_rules if rule.get("strength") != "hard"]
    return {
        "playbook_paths": [str(path) for path in playbook_paths],
        "lesson_paths": [str(path) for path in lesson_paths],
        "playbook_summary": playbook_summary[:12],
        "voice_fingerprint": voice_fingerprint[:8],
        "phrase_blacklist": phrase_blacklist[:16],
        "sentence_starters_to_avoid": sentence_starters[:12],
        "lesson_patterns": lesson_patterns[:16],
        "lesson_rules": lesson_rules[:16],
        "hard_rules": hard_rules[:8],
        "soft_rules": soft_rules[:8],
        "title_preferences": loaded_playbook.get("title_preferences") or derived_playbook.get("title_preferences") or {},
        "editorial_preferences": loaded_playbook.get("editorial_preferences") or derived_playbook.get("editorial_preferences") or {},
        "rhythm_preferences": rhythm_preferences,
        "example_snippets": example_snippets[:6],
        "sample_playbook": derived_playbook,
    }


def compute_edit_lesson_payload(draft_text: str, final_text: str) -> dict[str, Any]:
    draft_title = _extract_title(draft_text, Path("draft.md"))
    final_title = _extract_title(final_text, Path("final.md"))
    draft_body = _extract_body(draft_text)
    final_body = _extract_body(final_text)
    draft_paragraphs = _paragraphs(draft_body)
    final_paragraphs = _paragraphs(final_body)
    diff = list(difflib.unified_diff(draft_text.splitlines(), final_text.splitlines(), lineterm=""))
    additions = [line[1:].strip() for line in diff if line.startswith("+") and not line.startswith("+++")]
    deletions = [line[1:].strip() for line in diff if line.startswith("-") and not line.startswith("---")]
    patterns: list[str] = []
    if draft_title != final_title and final_title:
        if title_template_key(draft_title) != title_template_key(final_title):
            patterns.append(f"标题从“{draft_title}”改到“{final_title}”，说明更偏好换掉旧模板。")
        else:
            patterns.append(f"标题被人工改短或改紧为“{final_title}”。")
    draft_ai = sum(draft_body.count(phrase) for phrase in AI_STYLE_PHRASES)
    final_ai = sum(final_body.count(phrase) for phrase in AI_STYLE_PHRASES)
    if final_ai < draft_ai:
        patterns.append("人工会主动删掉模板连接词和篇章自述。")
    if len(final_paragraphs) > len(draft_paragraphs) + 1:
        patterns.append("人工倾向把大段拆短，增强节奏和停顿。")
    if len(final_paragraphs) + 1 < len(draft_paragraphs):
        patterns.append("人工会删掉重复段落，保留更干净的推进。")
    if len(re.findall(r"\d", final_body)) > len(re.findall(r"\d", draft_body)):
        patterns.append("人工会补数字、时间或更具体的事实。")
    if any(_looks_like_scene_opening(para) or opening_pattern_key(para) == "scene-cut" for para in final_paragraphs[:2]) and not any(
        _looks_like_scene_opening(para) or opening_pattern_key(para) == "scene-cut" for para in draft_paragraphs[:2]
    ):
        patterns.append("人工更偏好用具体场景开头。")
    if any(ending_pattern_key(para) == "judgment-close" for para in final_paragraphs[-2:]) and not any(
        ending_pattern_key(para) == "judgment-close" for para in draft_paragraphs[-2:]
    ):
        patterns.append("人工更偏好用判断收尾，而不是互动口号式结尾。")
    if any(heading_pattern_key(item) == "why-heading" for item in _headings(draft_body)) and not any(
        heading_pattern_key(item) == "why-heading" for item in _headings(final_body)
    ):
        patterns.append("人工会主动打散“为什么”式小标题。")
    deduped_patterns: list[str] = []
    for item in patterns:
        if item not in deduped_patterns:
            deduped_patterns.append(item)
    rules: list[dict[str, Any]] = []
    if draft_title != final_title and final_title:
        rules.append(
            _make_rule(
                key="refresh-title-pattern",
                rule_type="title",
                rule="标题优先换掉旧模板，必要时改短改紧。",
                examples=[draft_title, final_title],
            )
        )
    if final_ai < draft_ai:
        rules.append(
            _make_rule(
                key="remove-template-connectors",
                rule_type="expression",
                rule="删掉模板连接词和篇章自述，别把结构说给读者听。",
                examples=deletions[:2],
            )
        )
    if len(final_paragraphs) > len(draft_paragraphs) + 1:
        rules.append(
            _make_rule(
                key="split-heavy-paragraphs",
                rule_type="structure",
                rule="长段拆开，给段落留停顿，但不要碎成口号。",
                examples=final_paragraphs[:2],
            )
        )
    if len(final_paragraphs) + 1 < len(draft_paragraphs):
        rules.append(
            _make_rule(
                key="trim-repetition",
                rule_type="para_delete",
                rule="删掉重复段落，只保留更干净的推进。",
                examples=deletions[:2],
            )
        )
    if len(re.findall(r"\d", final_body)) > len(re.findall(r"\d", draft_body)):
        rules.append(
            _make_rule(
                key="add-specific-facts",
                rule_type="para_add",
                rule="关键判断补数字、时间或更具体的事实。",
                examples=additions[:2],
            )
        )
    if any(_looks_like_scene_opening(para) or opening_pattern_key(para) == "scene-cut" for para in final_paragraphs[:2]) and not any(
        _looks_like_scene_opening(para) or opening_pattern_key(para) == "scene-cut" for para in draft_paragraphs[:2]
    ):
        rules.append(
            _make_rule(
                key="open-with-scene",
                rule_type="structure",
                rule="开头优先从具体场景、动作或瞬间切入。",
                examples=final_paragraphs[:2],
            )
        )
    if any(ending_pattern_key(para) == "judgment-close" for para in final_paragraphs[-2:]) and not any(
        ending_pattern_key(para) == "judgment-close" for para in draft_paragraphs[-2:]
    ):
        rules.append(
            _make_rule(
                key="close-with-judgment",
                rule_type="tone",
                rule="结尾优先用判断收束，不要口号式互动。",
                examples=final_paragraphs[-2:],
            )
        )
    if any(heading_pattern_key(item) == "why-heading" for item in _headings(draft_body)) and not any(
        heading_pattern_key(item) == "why-heading" for item in _headings(final_body)
    ):
        rules.append(
            _make_rule(
                key="diversify-headings",
                rule_type="structure",
                rule="主动打散“为什么”式小标题，别让整篇像统一模板。",
                examples=_headings(final_body)[:2],
            )
        )
    return {
        "generated_at": now_iso(),
        "title_changed": draft_title != final_title,
        "draft_title": draft_title,
        "final_title": final_title,
        "ai_phrase_hits": {"draft": draft_ai, "final": final_ai},
        "paragraph_count": {"draft": len(draft_paragraphs), "final": len(final_paragraphs)},
        "line_changes": {"added": len(additions), "deleted": len(deletions)},
        "patterns": deduped_patterns,
        "rules": rules,
        "edits": {
            "additions_sample": additions[:10],
            "deletions_sample": deletions[:10],
        },
    }


def append_lesson_payload(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    existing = read_json(path, default={}) or {}
    items = list(existing.get("items") or []) if isinstance(existing, dict) else []
    items.append(payload)
    counter: Counter[str] = Counter()
    aggregated_rules: dict[str, dict[str, Any]] = {}
    for item in items:
        for pattern in item.get("patterns") or []:
            value = _normalize_text(str(pattern or ""))
            if value:
                counter[value] += 1
        for rule in _load_lesson_rules_from_payload(item):
            key = str(rule.get("key") or "")
            current = aggregated_rules.get(key)
            if current is None:
                aggregated_rules[key] = dict(rule)
                continue
            current["occurrences"] = int(current.get("occurrences") or 1) + int(rule.get("occurrences") or 1)
            last_seen = str(rule.get("last_seen") or current.get("last_seen") or now_iso())
            if _days_since(last_seen) <= _days_since(str(current.get("last_seen") or last_seen)):
                current["last_seen"] = last_seen
                current["rule"] = str(rule.get("rule") or current.get("rule") or "")
                current["type"] = str(rule.get("type") or current.get("type") or "expression")
            current["examples"] = _dedupe_examples(list(current.get("examples") or []) + list(rule.get("examples") or []))
            current["confidence"] = _rule_confidence(int(current.get("occurrences") or 1), str(current.get("last_seen") or now_iso()))
            current["strength"] = _rule_strength(int(current.get("occurrences") or 1), float(current.get("confidence") or 0))
    rules = sorted(
        (
            {
                **rule,
                "confidence": _rule_confidence(int(rule.get("occurrences") or 1), str(rule.get("last_seen") or now_iso())),
                "strength": _rule_strength(
                    int(rule.get("occurrences") or 1),
                    _rule_confidence(int(rule.get("occurrences") or 1), str(rule.get("last_seen") or now_iso())),
                ),
            }
            for rule in aggregated_rules.values()
        ),
        key=lambda item: (float(item.get("confidence") or 0), int(item.get("occurrences") or 0)),
        reverse=True,
    )
    summary = {
        "format_version": 2,
        "generated_at": now_iso(),
        "items": items[-20:],
        "patterns": [{"pattern": key, "count": count} for key, count in counter.most_common(16)],
        "rules": rules[:16],
    }
    write_json(path, summary)
    return summary


def write_playbook_artifacts(output_base: Path, payload: dict[str, Any]) -> None:
    write_json(output_base.with_suffix(".json"), payload)
    write_text(output_base.with_suffix(".md"), render_playbook_markdown(payload))
