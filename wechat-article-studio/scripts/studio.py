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
import zlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
ASSETS_DIR = SKILL_DIR / "assets"
DEFAULT_THRESHOLD = 85
DISCLAIMER_VERSION = "1.0"
MANIFEST_VERSION = 2
DEFAULT_COVER_POLICY = "thumb_only"
NETWORK_TIMEOUT = 30
NETWORK_RETRIES = 3
WECHAT_BATCHGET_COUNT = 20
TRANSPARENT_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9pY8m7QAAAAASUVORK5CYII="
)

WEIGHTS: list[tuple[str, int]] = [
    ("标题传播力", 8),
    ("开头吸引力", 12),
    ("钩子设计", 10),
    ("金句质量", 10),
    ("文风适配度", 10),
    ("结构清晰度", 10),
    ("内容深度", 15),
    ("可信度与检索支撑", 8),
    ("可读性与节奏", 7),
    ("情绪共鸣", 5),
    ("收藏/转发潜力", 5),
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
AI_STYLE_PHRASES = [
    "首先",
    "其次",
    "最后",
    "综上所述",
    "总的来说",
    "值得注意的是",
    "不难发现",
    "由此可见",
    "此外",
    "在当今社会",
]
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
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


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


def strip_leading_h1(body: str, title: str) -> str:
    lines = body.splitlines()
    if lines and lines[0].strip() == f"# {title}".strip():
        return "\n".join(lines[1:]).lstrip("\n")
    return body


def extract_summary(text: str, limit: int = 120) -> str:
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
    if any(word in intro for word in ["故事", "场景", "冲突", "问题", "结果"]):
        score += 1
    return min(score, 12), "前 2~4 段应快速建立好奇、痛点或结果期待。"


def hook_score(title: str, intro: str, headings: list[dict[str, Any]]) -> tuple[int, str]:
    score = 2
    score += min(4, count_occurrences(title + intro, HOOK_WORDS))
    heading_text = " ".join(item["text"] for item in headings)
    score += min(2, count_occurrences(heading_text, HOOK_WORDS))
    if any(mark in intro for mark in ["?", "？"]):
        score += 1
    if any(phrase in intro for phrase in ["先说结论", "先给答案", "结果是"]):
        score += 1
    return min(score, 10), "钩子需要贯穿标题、导语和小标题，而不是只出现在第一句。"


def quote_score(body: str) -> tuple[int, str, list[str]]:
    quotes = extract_candidate_quotes(body)
    score = min(10, len(quotes) * 3 + (1 if count_occurrences(body, ["“", "”", "**"]) else 0))
    return score, "金句应具备可截图、可转述、可单独传播的密度。", quotes


def style_score(body: str) -> tuple[int, str]:
    score = 8
    penalty = min(5, count_occurrences(body, AI_STYLE_PHRASES))
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
    score = min(5, 1 + count_occurrences(body, EMOTION_WORDS))
    return score, "情绪并非煽情，而是让读者感到‘这说的就是我’。"


def share_score(body: str, quotes: list[str]) -> tuple[int, str]:
    score = min(3, count_occurrences(body, SHARE_WORDS))
    if len(quotes) >= 2:
        score += 1
    if re.search(r"(^|\n)1\.\s+", body, flags=re.M):
        score += 1
    return min(score, 5), "能被收藏或转发的内容，通常既有观点价值也有立即可用性。"


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
        needs.append("补充来源、数据或案例出处，并在文末形成参考来源区。")
    topic_hint = extract_summary(title + " " + body, 28)
    suggestions = {
        "replacement_hook": f"大多数人以为 {topic_hint} 靠的是运气，但真正拉开差距的，往往是那些不容易被看见的底层动作。",
        "sample_gold_quotes": [
            f"{topic_hint} 不是信息不够，而是判断不够。",
            "真正决定结果的，从来不是知道多少，而是你能否把关键动作重复到位。",
            "当别人只盯着表面热闹时，高手已经开始搭建自己的长期优势。",
        ],
        "style_adjustments": [
            "减少模板句，优先使用结论句、判断句和对比句。",
            "让每个小节开头先给结论，再展开论证。",
            "保留强态度，但避免空喊口号。",
        ],
    }
    return needs[:5], suggestions


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# 文章评分报告：{report['title']}",
        "",
        f"- 总分：`{report['total_score']}` / 100",
        f"- 阈值：`{report['threshold']}`",
        f"- 结果：`{'通过' if report['passed'] else '未通过'}`",
        "",
        "## 分项得分",
        "",
    ]
    for item in report["score_breakdown"]:
        lines.append(f"- {item['dimension']}：`{item['score']}` / `{item['weight']}` - {item['note']}")
    lines.extend(["", "## 核心优点", ""])
    for item in report["strengths"] or ["暂无明显高分项。"]:
        lines.append(f"- {item}")
    lines.extend(["", "## 核心短板", ""])
    for item in report["weaknesses"] or ["暂无明显短板。"]:
        lines.append(f"- {item}")
    lines.extend(["", "## 必须修改项", ""])
    for item in report["mandatory_revisions"] or ["当前版本已达阈值，可进入下一步。"]:
        lines.append(f"- {item}")
    lines.extend(["", "## 建议补强", ""])
    lines.append(f"- 替换钩子：{report['suggestions']['replacement_hook']}")
    for quote in report["suggestions"]["sample_gold_quotes"]:
        lines.append(f"- 备选金句：{quote}")
    for item in report["suggestions"]["style_adjustments"]:
        lines.append(f"- 文风建议：{item}")
    if report["candidate_quotes"]:
        lines.extend(["", "## 文中已识别金句", ""])
        for quote in report["candidate_quotes"]:
            lines.append(f"> {quote}")
    if report.get("rewrite"):
        rewrite = report["rewrite"]
        lines.extend(["", "## 自动改写稿", ""])
        lines.append(f"- 改写稿：`{rewrite['output_path']}`")
        lines.append(f"- 触发维度：`{'、'.join(rewrite['triggered_dimensions'])}`")
        lines.append(f"- 预评分：`{rewrite['preview_score']}` / 100")
        lines.append(f"- 预评分是否过线：`{'是' if rewrite['preview_passed'] else '否'}`")
        for action in rewrite.get("applied_actions") or []:
            lines.append(f"- 已应用：{action}")
    return "\n".join(lines).rstrip() + "\n"


def build_score_report(title: str, body: str, manifest: dict[str, Any], threshold: int) -> dict[str, Any]:
    headings = extract_headings(body)
    source_urls = manifest.get("source_urls") or []
    breakdown, quotes = build_breakdown(title, body, headings, source_urls)
    total = sum(item["score"] for item in breakdown)
    strengths, weaknesses = strongest_and_weakest(breakdown)
    mandatory_revisions, suggestions = rewrite_actions(breakdown, title, body)
    return {
        "title": title,
        "threshold": threshold,
        "total_score": total,
        "passed": total >= threshold,
        "score_breakdown": breakdown,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "mandatory_revisions": mandatory_revisions,
        "suggestions": suggestions,
        "candidate_quotes": quotes,
        "generated_at": now_iso(),
    }


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
        r"综上所述": "说到底",
        r"总的来说": "说到底",
        r"值得注意的是": "更关键的是",
        r"不难发现": "你会发现",
        r"由此可见": "这也说明",
        r"在当今社会": "放在今天的环境里",
    }
    cleaned = text.strip()
    for pattern, replacement in replacements.items():
        cleaned = re.sub(pattern, replacement, cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def make_section_opener(heading: str, first_block: str, title: str) -> str:
    focus = extract_summary(first_block or heading or title, 24)
    if "为什么" in heading:
        return f"先说结论：{focus} 之所以让人反复卡住，不是因为你不够努力，而是因为你看见的只是表层现象。"
    if any(word in heading for word in ["三件事", "方法", "怎么", "如何"]):
        return f"真正有效的做法，不是把动作做多，而是把最关键的动作做到位。围绕“{heading}”，你至少要先抓住一条能立刻执行的主线。"
    return f"如果只从表面理解“{heading}”，很容易把力气花错地方。{focus}，才是这一部分真正想说明的问题。"


def build_rewritten_intro(title: str, intro_blocks: list[str], suggestions: dict[str, Any], manifest: dict[str, Any], sections: list[dict[str, Any]], low_dims: list[str]) -> list[str]:
    audience = manifest.get("audience") or "公众号读者"
    direction = manifest.get("direction") or "这个主题"
    first_heading = sections[0]["heading"] if sections else title
    paragraphs = [suggestions["replacement_hook"]]
    if "情绪共鸣" in low_dims:
        paragraphs.append("如果你也在被新工具推着跑、却又隐约担心自己会被替代，这种焦虑并不丢人，它恰恰说明你开始认真看待自己的长期价值了。")
    paragraphs.append(f"这篇文章不打算重复那些正确但空泛的大道理，而是围绕“{direction}”把问题拆开：为什么人会越学越焦虑，真正该补的能力是什么，以及从今天开始你能先做哪一步。")
    if intro_blocks:
        tail = cleanup_rewrite_text(intro_blocks[0])
        if tail and tail not in paragraphs[-1]:
            paragraphs.append(tail)
    paragraphs.append(f"接下来，我会从“{first_heading}”开始，把最容易被忽略、却最影响结果的那层逻辑讲透，尽量让 {audience} 读完就能立刻行动。")
    return paragraphs[:4]


def build_execution_section(sections: list[dict[str, Any]]) -> tuple[str, list[str]]:
    bullets = []
    for section in sections[:3]:
        bullets.append(f"先把“{section['heading']}”里最重要的一条动作写下来，并在 24 小时内执行一次。")
    if not bullets:
        bullets = [
            "先把这篇文章的核心判断用一句话复述出来。",
            "再选一个最容易开始的动作，今天就做。",
            "一周后复盘：什么动作真的带来了变化。",
        ]
    return "最后给你一个可执行清单", bullets


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
        heading, bullets = build_execution_section(sections)
        rewritten_parts.append(f"## {heading}\n\n" + "\n".join(f"- {bullet}" for bullet in bullets))
        applied_actions.append("补入了更适合收藏转发的行动清单")
    if "可信度与检索支撑" in low_dims:
        heading, items = build_reference_section(manifest, evidence_report)
        rewritten_parts.append(f"## {heading}\n\n" + "\n".join(f"- {item}" if not re.match(r"^\d+\.\s", item) else item for item in items))
        applied_actions.append("补入了参考与证据补强区")
        if evidence_report.get("items"):
            applied_actions.append("联网抓取并注入了外部证据")
    if "金句质量" in low_dims:
        applied_actions.append("补入了可截图传播的金句")
    if "文风适配度" in low_dims:
        applied_actions.append("清理了模板化连接词并统一语气")

    rewritten_body = "\n\n".join(part.strip() for part in rewritten_parts if part.strip()).strip() + "\n"
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


def generate_gemini_web_image(prompt: str, output_path: Path) -> dict[str, Any]:
    ensure_gemini_web_consent()
    bun = resolve_bun_command()
    root = ensure_gemini_web_vendor()
    cookie_temp: Path | None = None
    env = os.environ.copy()
    raw_cookie = env.get("GEMINI_WEB_COOKIE")
    if raw_cookie:
        cookie_map = parse_cookie_string(raw_cookie)
        if not cookie_map:
            raise SystemExit("GEMINI_WEB_COOKIE 解析失败，请提供标准 Cookie 字符串。")
        handle = tempfile.NamedTemporaryFile(prefix="gemini-web-cookie-", suffix=".json", delete=False)
        handle.close()
        cookie_temp = Path(handle.name)
        write_cookie_payload(cookie_temp, cookie_map)
        env["GEMINI_WEB_COOKIE_PATH"] = str(cookie_temp)
    command = bun + [str(root / "main.ts"), "--prompt", prompt, "--image", str(output_path), "--json"]
    if env.get("GEMINI_WEB_COOKIE_PATH"):
        command.extend(["--cookie-path", env["GEMINI_WEB_COOKIE_PATH"]])
    if env.get("GEMINI_WEB_CHROME_PROFILE_DIR"):
        command.extend(["--profile-dir", env["GEMINI_WEB_CHROME_PROFILE_DIR"]])
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stdout = (exc.stdout or "").strip()
        stderr = (exc.stderr or "").strip()
        combined = "\n".join(part for part in [stdout, stderr] if part).lower()
        auth_markers = [
            "autherror",
            "unauthorized",
            "login",
            "sign in",
            "signin",
            "__secure-1psid",
            "__secure-1psidts",
            "cookie",
            "refresh cookies",
            "failed to refresh cookies",
        ]
        if any(marker in combined for marker in auth_markers):
            raise SystemExit(
                "Gemini 登录态可能已失效，请重新登录 Gemini 后再试。"
                " 如果你使用的是 cookie 文件，请刷新 cookie；"
                " 如果你使用的是浏览器 Profile，请先在对应浏览器里确认 Gemini 已登录。"
            ) from exc
        detail = "\n".join(part for part in [stdout, stderr] if part)
        raise SystemExit(f"gemini-web 图片生成失败：{detail or str(exc)}") from exc
    finally:
        if cookie_temp and cookie_temp.exists():
            cookie_temp.unlink(missing_ok=True)
    stdout = (completed.stdout or "").strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        payload = {"text": stdout}
    width, height = detect_dimensions(output_path, (1536, 1024))
    return {
        "provider": "gemini-web",
        "prompt": prompt,
        "revised_prompt": payload.get("text") or prompt,
        "width": width,
        "height": height,
        "source_meta": {"sessionId": payload.get("sessionId"), "model": payload.get("model")},
    }


def make_placeholder_png(path: Path) -> tuple[int, int]:
    save_binary(path, TRANSPARENT_PNG)
    return 1, 1


def compose_prompt(title: str, summary: str, controls: dict[str, Any], item: dict[str, Any], audience: str) -> str:
    section = item.get("section_heading") or item.get("alt")
    instructions = [
        "Create a polished visual for a Chinese WeChat Official Account article.",
        f"Article title: {title}",
        f"Audience: {audience or 'general readers'}",
        f"Purpose: {item['type']}",
        f"Theme: {controls.get('theme', '科技')}",
        f"Style: {controls.get('style', '未来科技')}",
        f"Mood: {controls.get('mood', '专业理性')}",
        f"Visual brief: {controls.get('custom_visual_brief', 'highlight the core insight without clutter')}",
        f"Content summary: {summary}",
    ]
    if section:
        instructions.append(f"Section focus: {section}")
    if item["type"] == "封面图":
        instructions.append("Compose as a high-end WeChat cover, strong focal point, clean whitespace, no realistic faces unless requested.")
    elif item["type"] == "信息图":
        instructions.append("Design as an infographic with clear hierarchy, visual metaphors, and readable structure.")
    else:
        instructions.append("Design as an editorial inline illustration that supports the nearby paragraph.")
    instructions.append("Avoid clutter, excessive small text, watermarks, and brand logos unless explicitly requested.")
    return " ".join(instructions)


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
    image_controls = {
        "theme": args.image_theme or manifest.get("image_controls", {}).get("theme") or "科技",
        "style": args.image_style or manifest.get("image_controls", {}).get("style") or "未来科技",
        "type": args.image_type or manifest.get("image_controls", {}).get("type") or "封面图",
        "mood": args.image_mood or manifest.get("image_controls", {}).get("mood") or "专业理性",
        "custom_visual_brief": args.custom_visual_brief or manifest.get("image_controls", {}).get("custom_visual_brief") or "",
    }
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
    print(json.dumps({"workspace": str(workspace), "manifest": str(workspace / 'manifest.json')}, ensure_ascii=False, indent=2))
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
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_below and report["total_score"] < threshold:
        return 2
    return 0
def normalize_sections_for_images(body: str) -> tuple[list[str], list[dict[str, Any]]]:
    intro_blocks, sections = split_sections(body)
    if sections:
        return intro_blocks, sections
    blocks = [block for block in list_paragraphs(body) if block.strip()]
    pseudo_sections: list[dict[str, Any]] = []
    for index in range(0, len(blocks), 2):
        chunk = blocks[index:index + 2]
        pseudo_sections.append(
            {
                "level": 2,
                "heading": f"\u6b63\u6587\u6bb5\u843d {index // 2 + 1}",
                "body": "\n\n".join(chunk),
                "blocks": chunk,
                "generated_heading": True,
            }
        )
    return [], pseudo_sections


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
    }


def estimate_inline_image_count(body: str, explicit_count: int) -> int:
    if explicit_count and explicit_count > 0:
        return explicit_count
    char_count = cjk_len(re.sub(r"^#{1,6}\s+", "", body, flags=re.M))
    if char_count < 1200:
        return 2
    if char_count < 2500:
        return 3
    if char_count < 4000:
        return 4
    if char_count < 5500:
        return 5
    return 6


def choose_section_block_index(section_metric: dict[str, Any], variant: int) -> int:
    paragraph_count = section_metric.get("paragraph_count", 0)
    if paragraph_count <= 1:
        return 0
    if variant <= 0:
        return 1 if paragraph_count >= 3 else 0
    if paragraph_count <= 3:
        return paragraph_count - 1
    return min(paragraph_count - 1, max(2, paragraph_count // 2))


def select_sections_for_images(body: str, inline_limit: int) -> list[dict[str, Any]]:
    _, sections = normalize_sections_for_images(body)
    metrics = [
        extract_section_metrics(section, index)
        for index, section in enumerate(sections)
        if not is_reference_heading(section.get("heading", ""))
    ]
    if not metrics or inline_limit <= 0:
        return []

    slots: list[dict[str, Any]] = []
    selected_unique: set[int] = set()

    if len(metrics) >= 3 and inline_limit >= 3:
        midpoint = max(1, len(metrics) // 2)
        first_half = metrics[:midpoint]
        second_half = metrics[midpoint:]
        if first_half:
            best_first = max(first_half, key=lambda item: item["section_weight"])
            slots.append({"section_index": best_first["section_index"], "variant": 0})
            selected_unique.add(best_first["section_index"])
        if second_half:
            best_second = max(second_half, key=lambda item: item["section_weight"])
            if best_second["section_index"] not in selected_unique:
                slots.append({"section_index": best_second["section_index"], "variant": 0})
                selected_unique.add(best_second["section_index"])
    else:
        best_single = max(metrics, key=lambda item: item["section_weight"])
        slots.append({"section_index": best_single["section_index"], "variant": 0})
        selected_unique.add(best_single["section_index"])

    for metric in sorted(metrics, key=lambda item: item["section_weight"], reverse=True):
        if len(slots) >= inline_limit:
            break
        if metric["section_index"] in selected_unique:
            continue
        slots.append({"section_index": metric["section_index"], "variant": 0})
        selected_unique.add(metric["section_index"])

    if len(slots) < inline_limit:
        for metric in sorted(metrics, key=lambda item: (item["section_weight"], item["char_count"]), reverse=True):
            if len(slots) >= inline_limit:
                break
            existing = sum(1 for slot in slots if slot["section_index"] == metric["section_index"])
            if metric["paragraph_count"] >= 4 and metric["char_count"] >= 700 and existing < 2:
                slots.append({"section_index": metric["section_index"], "variant": existing})

    selected_metrics: list[dict[str, Any]] = []
    for slot in sorted(slots, key=lambda item: (item["section_index"], item["variant"])):
        metric = next(item for item in metrics if item["section_index"] == slot["section_index"])
        block_index = choose_section_block_index(metric, slot["variant"])
        placement_reason = "\u6309\u7ae0\u8282\u6743\u91cd\u548c\u4fe1\u606f\u5bc6\u5ea6\u4f18\u5148\u63d2\u56fe"
        if slot["variant"] > 0:
            placement_reason = "\u957f\u7ae0\u8282\u8865\u56fe\uff0c\u907f\u514d\u540e\u534a\u6bb5\u7eaf\u6587\u5b57\u5806\u79ef"
        selected_metrics.append(
            {
                **metric,
                "variant": slot["variant"],
                "placement_block_index": block_index,
                "placement_reason": placement_reason,
            }
        )
    return selected_metrics

def cmd_plan_images(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    article_path = workspace / (manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"\u627e\u4e0d\u5230\u6587\u7ae0\u6587\u4ef6\uff1a{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
    title = infer_title(manifest, meta, body)
    summary = manifest.get("summary") or meta.get("summary") or extract_summary(body)
    audience = manifest.get("audience") or "\u5927\u4f17\u8bfb\u8005"
    controls = manifest.get("image_controls") or {}
    intro_blocks, sections = normalize_sections_for_images(body)
    provider = image_provider_from_env(args.provider)
    inline_limit = estimate_inline_image_count(body, args.inline_count)
    inline_sections = select_sections_for_images(body, inline_limit)
    intro_char_count = sum(cjk_len(block) for block in intro_blocks)
    content_sections = [section for section in sections if not is_reference_heading(section.get("heading", ""))]
    final_section = content_sections[-1] if content_sections else None
    final_metric = extract_section_metrics(final_section, sections.index(final_section)) if final_section else None

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
        },
        {
            "id": "infographic-01",
            "type": "\u4fe1\u606f\u56fe",
            "target_section": final_metric["heading"] if final_metric else "\u6587\u672b\u603b\u7ed3",
            "target_section_index": final_metric["section_index"] if final_metric else -1,
            "insert_strategy": "section_end",
            "placement_block_index": final_metric["paragraph_count"] if final_metric else 0,
            "placement_reason": "\u5168\u6587\u603b\u7ed3\u578b\u4fe1\u606f\u56fe\uff0c\u653e\u5728\u6587\u672b\u5185\u5bb9\u6bb5\u843d\u4e4b\u540e\u66f4\u9002\u5408\u6536\u675f\u5168\u6587",
            "section_weight": round((final_metric["section_weight"] if final_metric else 0) + intro_char_count / 500, 2),
            "alt": f"{title} \u4fe1\u606f\u56fe",
            "aspect_ratio": "3:4",
        },
    ]

    for index, section in enumerate(inline_sections, start=1):
        image_type = "\u6b63\u6587\u63d2\u56fe"
        if section["char_count"] >= 1200 and section["variant"] > 0:
            image_type = "\u5206\u9694\u56fe"
        items.append(
            {
                "id": f"inline-{index:02d}",
                "type": image_type,
                "target_section": section["heading"],
                "target_section_index": section["section_index"],
                "insert_strategy": "section_middle",
                "placement_block_index": section["placement_block_index"],
                "placement_reason": section["placement_reason"],
                "section_weight": section["section_weight"],
                "alt": f"{section['heading']} {'\u5206\u9694\u56fe' if image_type == '\u5206\u9694\u56fe' else '\u63d2\u56fe'}",
                "aspect_ratio": "16:9",
            }
        )

    for item in items:
        item["provider"] = provider
        item["prompt"] = compose_prompt(title, summary, controls, item, audience)
        item["revised_prompt"] = item["prompt"]
        item["asset_path"] = None
        item["source_meta"] = {}

    plan = {
        "title": title,
        "provider": provider,
        "strategy": "mixed-section-density",
        "article_char_count": cjk_len(re.sub(r"^#{1,6}\s+", "", body, flags=re.M)),
        "planned_inline_count": inline_limit,
        "image_controls": controls,
        "items": items,
        "generated_at": now_iso(),
    }
    write_json(workspace / "image-plan.json", plan)
    manifest["image_provider"] = provider
    save_manifest(workspace, manifest)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0

def cmd_generate_images(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    plan_path = workspace / "image-plan.json"
    plan = read_json(plan_path, default=None)
    if not plan:
        raise SystemExit("缺少 image-plan.json，请先运行 plan-images。")
    provider = image_provider_from_env(args.provider or plan.get("provider"))
    images_dir = ensure_dir(workspace / "assets" / "images")
    generated = {}
    for item in plan.get("items") or []:
        filename = f"{item['id']}.png"
        output_path = images_dir / filename
        aspect = item.get("aspect_ratio") or "16:9"
        if args.dry_run:
            width, height = make_placeholder_png(output_path)
            result = {
                "provider": provider,
                "prompt": item["prompt"],
                "revised_prompt": item["prompt"],
                "width": width,
                "height": height,
                "source_meta": {"dry_run": True},
            }
        elif provider == "gemini-web":
            result = generate_gemini_web_image(item["prompt"], output_path)
        elif provider == "gemini-api":
            result = generate_gemini_api_image(item["prompt"], output_path, args.gemini_model, aspect)
        elif provider == "openai-image":
            result = generate_openai_image(item["prompt"], output_path, args.openai_model, aspect)
        else:
            raise SystemExit(f"不支持的图片后端：{provider}")
        item["provider"] = provider
        item["asset_path"] = relative_posix(output_path, workspace)
        item["revised_prompt"] = result["revised_prompt"]
        item["source_meta"] = result["source_meta"]
        item["width"] = result["width"]
        item["height"] = result["height"]
        generated[item["id"]] = item["asset_path"]
    write_json(plan_path, plan)
    manifest["image_provider"] = provider
    manifest.setdefault("asset_paths", {}).update(generated)
    save_manifest(workspace, manifest)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def insert_markdown_image(lines: list[str], index: int, alt: str, path_text: str) -> list[str]:
    snippet = ["", f"![{alt}]({path_text})", ""]
    return lines[:index] + snippet + lines[index:]


def find_heading_index(lines: list[str], heading: str) -> int | None:
    target = heading.strip()
    for index, line in enumerate(lines):
        if re.match(r"^#{2,4}\s+", line) and line.split(None, 1)[1].strip() == target:
            return index + 1
    return None


def render_body_from_blocks(intro_blocks: list[str], sections: list[dict[str, Any]], intro_items: list[dict[str, Any]], section_items: dict[int, list[dict[str, Any]]]) -> str:
    parts: list[str] = []
    intro_insert_map: dict[int, list[dict[str, Any]]] = {}
    for item in intro_items:
        key = item.get("placement_block_index", 0)
        intro_insert_map.setdefault(key, []).append(item)

    if intro_blocks:
        for index, block in enumerate(intro_blocks):
            parts.append(block)
            for item in intro_insert_map.get(index, []):
                parts.append(f"![{item['alt']}]({item['asset_path']})")
    elif intro_items:
        for item in intro_items:
            parts.append(f"![{item['alt']}]({item['asset_path']})")

    for section_index, section in enumerate(sections):
        heading_line = f"{'#' * section.get('level', 2)} {section.get('heading', '')}".strip()
        parts.append(heading_line)
        blocks = [block for block in section.get("blocks") or [] if block.strip()]
        insert_map: dict[int, list[dict[str, Any]]] = {}
        trailing_items: list[dict[str, Any]] = []
        for item in section_items.get(section_index, []):
            if not blocks:
                trailing_items.append(item)
                continue
            block_index = item.get("placement_block_index", 0)
            if block_index >= len(blocks):
                trailing_items.append(item)
            else:
                insert_map.setdefault(block_index, []).append(item)

        for block_index, block in enumerate(blocks):
            parts.append(block)
            for item in insert_map.get(block_index, []):
                parts.append(f"![{item['alt']}]({item['asset_path']})")
        for item in trailing_items:
            parts.append(f"![{item['alt']}]({item['asset_path']})")

    return "\n\n".join(part.strip() for part in parts if part and part.strip()) + "\n"


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

    intro_items: list[dict[str, Any]] = []
    section_items: dict[int, list[dict[str, Any]]] = {}
    inserted = []
    for item in plan.get("items") or []:
        asset_path = item.get("asset_path")
        if not asset_path:
            continue
        if item.get("type") == "封面图" or item.get("insert_strategy") == "cover_only":
            continue
        inserted.append({"id": item["id"], "asset_path": asset_path, "type": item["type"]})
        target_index = item.get("target_section_index", -1)
        if target_index == -1:
            intro_items.append(item)
        else:
            section_items.setdefault(target_index, []).append(item)

    assembled_body = render_body_from_blocks(intro_blocks, sections, intro_items, section_items)
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
    title = infer_title(manifest, meta, body)
    summary = meta.get("summary") or manifest.get("summary") or extract_summary(body)
    body = strip_leading_h1(body, title)
    evidence_report = read_json(workspace / "evidence-report.json", default={}) or {}
    clean_body, reference_entries = build_reference_entries(body, manifest, evidence_report)
    annotated_body = annotate_body_with_footnotes(clean_body, reference_entries)
    content_html = markdown_to_html(annotated_body)
    content_html = content_html.replace('<blockquote>', '<blockquote class="insight-card">')
    content_html = re.sub(r'(?<!\w)\[(\d+)\](?!\()', r'<sup class="footnote-marker">[\1]</sup>', content_html)
    preview_refs = build_reference_cards_preview(reference_entries)
    preview_content = content_html + preview_refs
    style = read_text(ASSETS_DIR / "wechat-style.css").replace("{{accent_color}}", args.accent_color)
    template = read_text(ASSETS_DIR / "wechat-template.html")
    rendered = (
        template.replace("{{title}}", html.escape(title))
        .replace("{{summary}}", html.escape(summary))
        .replace("{{style}}", style)
        .replace("{{content}}", textwrap.indent(preview_content, "      ").strip())
    )
    output_path = workspace / args.output
    write_text(output_path, rendered)
    wechat_fragment = build_wechat_fragment(content_html, title, summary, args.accent_color, reference_entries)
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
    missing = []
    if not app_id:
        missing.append("WECHAT_APP_ID")
    if not app_secret:
        missing.append("WECHAT_APP_SECRET")
    if required and missing:
        raise SystemExit(f"缺少微信发布环境变量：{', '.join(missing)}")
    return app_id, app_secret, missing


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
    return meta.get("summary") or manifest.get("summary") or extract_summary(body)


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
        digest_preview = meta.get("summary") or manifest.get("summary") or extract_summary(body)
        fragment = build_wechat_fragment(markdown_to_html(strip_leading_h1(body, title)), title, digest_preview, "#0F766E")
        html_path = workspace / "article.wechat.html"
        write_text(html_path, fragment)
        manifest["wechat_html_path"] = relative_posix(html_path, workspace)
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
        print(json.dumps(result, ensure_ascii=False, indent=2))
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
    print(json.dumps(result, ensure_ascii=False, indent=2))
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
    print(json.dumps(report, ensure_ascii=False, indent=2))
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
    vendor_missing = [relative for relative in IMAGE_PROVIDER_FILES if not (vendor_root() / relative).exists()]
    cookie_ready = bool(os.getenv("GEMINI_WEB_COOKIE") or os.getenv("GEMINI_WEB_COOKIE_PATH") or os.getenv("GEMINI_WEB_CHROME_PROFILE_DIR"))
    bun_ready = shutil.which("bun") is not None
    npx_ready = shutil.which("npx") is not None
    ok = cookie_ready and (bun_ready or npx_ready) and not vendor_missing
    missing: list[str] = []
    if not cookie_ready:
        missing.append("GEMINI_WEB_COOKIE/GEMINI_WEB_COOKIE_PATH/GEMINI_WEB_CHROME_PROFILE_DIR")
    if not (bun_ready or npx_ready):
        missing.append("bun 或 npx")
    if vendor_missing:
        missing.append("vendor 文件不完整")
    return {
        "ok": ok,
        "missing": missing,
        "notes": ["非官方 best-effort 路径，仅在显式指定 --provider gemini-web 时启用。"],
        "bun_available": bun_ready,
        "npx_available": npx_ready,
        "vendor_missing_count": len(vendor_missing),
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
    print(json.dumps(report, ensure_ascii=False, indent=2))
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
    print(json.dumps(payload, ensure_ascii=False, indent=2))
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
