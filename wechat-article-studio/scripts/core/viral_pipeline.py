from __future__ import annotations

import hashlib
import html
import json
import math
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from core.artifacts import extract_summary, join_frontmatter, now_iso, split_frontmatter, write_json, write_text
from core.content_fingerprint import build_article_fingerprint, compare_fingerprints
from core.editorial_strategy import TITLE_PATTERN_LABELS, normalize_editorial_blueprint, title_template_key
from core.persona import normalize_writing_persona
from core.viral import normalize_viral_blueprint, recompute_score_outcome

PLATFORM_CHOICES = ("wechat", "xiaohongshu", "weibo", "bilibili")
DISCOVERY_PRIMARY_COUNT = 3
DISCOVERY_SUPPORTING_COUNT = 2
CONTIGUOUS_REUSE_THRESHOLD = 24
FIVE_GRAM_OVERLAP_THRESHOLD = 0.18
TITLE_SIMILARITY_THRESHOLD = 0.55
ROUTE_SIMILARITY_THRESHOLD = 0.68
_HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _compact_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _tokenize(value: Any) -> list[str]:
    return re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", _normalize_text(value).lower())


def _dedupe_texts(values: list[str], limit: int | None = None) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = _normalize_text(raw)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
        if limit is not None and len(output) >= limit:
            break
    return output


def _stable_id(platform: str, url: str) -> str:
    return hashlib.sha1(f"{platform}:{url}".encode("utf-8")).hexdigest()[:16]


def _extract_json_blob(text: str) -> Any:
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    obj_start = raw.find("{")
    obj_end = raw.rfind("}")
    if 0 <= obj_start < obj_end:
        try:
            return json.loads(raw[obj_start : obj_end + 1])
        except json.JSONDecodeError:
            pass
    arr_start = raw.find("[")
    arr_end = raw.rfind("]")
    if 0 <= arr_start < arr_end:
        try:
            return json.loads(raw[arr_start : arr_end + 1])
        except json.JSONDecodeError:
            pass
    return {}


def _run_command(command: list[str], *, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def _http_get(url: str, *, timeout: int = 20) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _HTTP_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _extract_domain(url: str) -> str:
    return urllib.parse.urlparse(str(url or "")).netloc.replace("www.", "").lower()


def _parse_datetime(value: Any) -> datetime | None:
    text = _normalize_text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    for candidate in [text, text.replace("/", "-")]:
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def _days_since(value: Any) -> float | None:
    parsed = _parse_datetime(value)
    if parsed is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds() / 86400.0)


def _strip_tags(raw_html: str) -> str:
    return re.sub(r"(?is)<[^>]+>", "", raw_html or "")


def _html_to_markdown(raw_html: str) -> str:
    html_value = raw_html or ""
    html_value = re.sub(r"(?is)<script.*?>.*?</script>", "", html_value)
    html_value = re.sub(r"(?is)<style.*?>.*?</style>", "", html_value)
    html_value = re.sub(r"(?i)<br\s*/?>", "\n", html_value)
    html_value = re.sub(r"(?i)</(p|div|section|article|li|h1|h2|h3|h4|h5|h6)>", "\n\n", html_value)
    for level in range(6, 0, -1):
        html_value = re.sub(
            rf"(?is)<h{level}[^>]*>(.*?)</h{level}>",
            lambda match: f"\n\n{'#' * level} {_strip_tags(match.group(1))}\n\n",
            html_value,
        )
    html_value = re.sub(
        r'(?is)<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        lambda match: f"{_strip_tags(match.group(2))} ({html.unescape(match.group(1))})",
        html_value,
    )
    text = _strip_tags(html_value)
    text = re.sub(r"\n{3,}", "\n\n", html.unescape(text))
    return text.strip()


def _extract_meta(html_text: str, name: str) -> str:
    patterns = [
        rf'(?is)<meta[^>]+property="{re.escape(name)}"[^>]+content="([^"]+)"',
        rf'(?is)<meta[^>]+content="([^"]+)"[^>]+property="{re.escape(name)}"',
        rf'(?is)<meta[^>]+name="{re.escape(name)}"[^>]+content="([^"]+)"',
        rf'(?is)<meta[^>]+content="([^"]+)"[^>]+name="{re.escape(name)}"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html_text or "")
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def _extract_title_from_html(html_text: str) -> str:
    meta_title = _extract_meta(html_text, "og:title")
    if meta_title:
        return meta_title
    match = re.search(r"(?is)<title>(.*?)</title>", html_text or "")
    if match:
        return html.unescape(_strip_tags(match.group(1))).strip()
    return ""


def _fetch_with_jina(url: str) -> str:
    target = url if url.startswith(("http://", "https://")) else f"https://{url}"
    return _http_get(f"https://r.jina.ai/{target}", timeout=30)


def _read_wechat_article(url: str) -> dict[str, Any]:
    raw_html = _http_get(url, timeout=30)
    title = _extract_meta(raw_html, "og:title") or _extract_title_from_html(raw_html)
    author = _extract_meta(raw_html, "author")
    publish = ""
    publish_match = re.search(r"var\s+publish_time\s*=\s*\"([^\"]+)\"", raw_html)
    if publish_match:
        publish = publish_match.group(1).strip()
    content_match = re.search(r'(?is)<div[^>]+id="js_content"[^>]*>(.*?)</div>', raw_html)
    content_html = content_match.group(1) if content_match else raw_html
    markdown = _html_to_markdown(content_html)
    return {
        "title": title,
        "author": author,
        "published_at": publish,
        "fulltext_markdown": markdown,
        "fetch_method": "direct-html",
    }


def _read_generic_url(url: str) -> dict[str, Any]:
    domain = _extract_domain(url)
    if "mp.weixin.qq.com" in domain:
        try:
            return _read_wechat_article(url)
        except Exception:
            pass
    try:
        markdown = _fetch_with_jina(url)
        if markdown.strip():
            return {"fulltext_markdown": markdown, "fetch_method": "jina-reader"}
    except Exception:
        pass
    try:
        raw_html = _http_get(url, timeout=30)
    except Exception as exc:
        return {"fulltext_markdown": "", "fetch_method": "unreadable", "error": str(exc)}
    return {
        "title": _extract_title_from_html(raw_html),
        "author": _extract_meta(raw_html, "author"),
        "published_at": _extract_meta(raw_html, "article:published_time"),
        "fulltext_markdown": _html_to_markdown(raw_html),
        "fetch_method": "direct-html",
    }


def _normalize_engagement(payload: Any) -> dict[str, int]:
    data = payload if isinstance(payload, dict) else {}
    output: dict[str, int] = {}
    for key in ("likes", "liked_count", "like_count", "comments", "comment_count", "shares", "share_count", "views", "view_count", "play", "play_count", "danmaku"):
        value = data.get(key)
        try:
            number = int(float(value))
        except (TypeError, ValueError):
            continue
        mapped = {
            "liked_count": "likes",
            "like_count": "likes",
            "comment_count": "comments",
            "share_count": "shares",
            "view_count": "views",
            "play": "views",
            "play_count": "views",
            "danmaku": "comments",
        }.get(key, key)
        output[mapped] = max(output.get(mapped, 0), max(0, number))
    return output


def _engagement_score(payload: dict[str, int]) -> int:
    likes = int(payload.get("likes") or 0)
    comments = int(payload.get("comments") or 0)
    shares = int(payload.get("shares") or 0)
    views = int(payload.get("views") or 0)
    total = likes + comments * 3 + shares * 4 + int(views / 100)
    if total <= 0:
        return 20
    return min(100, int(round(math.log1p(total) * 18)))


def _freshness_score(published_at: str) -> int:
    days = _days_since(published_at)
    if days is None:
        return 45
    if days <= 2:
        return 100
    if days <= 7:
        return 85
    if days <= 30:
        return 65
    if days <= 90:
        return 45
    return 25


def _readability_score(item: dict[str, Any]) -> int:
    if str(item.get("fulltext_markdown") or "").strip():
        return 100
    url = str(item.get("url") or "")
    domain = _extract_domain(url)
    if any(key in domain for key in ("mp.weixin.qq.com", "bilibili.com", "xiaohongshu.com", "weibo.com")):
        return 70
    return 40


def _keyword_fit_score(item: dict[str, Any], query: str, account_strategy: dict[str, Any]) -> int:
    title = " ".join([str(item.get("title") or ""), str(item.get("excerpt") or ""), str(item.get("author") or "")])
    query_tokens = set(_tokenize(query))
    title_tokens = set(_tokenize(title))
    overlap = len(query_tokens & title_tokens)
    priority_words = [str(value) for value in (account_strategy.get("discovery_priority_keywords") or []) if str(value).strip()]
    deprioritize_words = [str(value) for value in (account_strategy.get("discovery_deprioritize_keywords") or []) if str(value).strip()]
    bonus = sum(1 for word in priority_words if word in title)
    penalty = sum(1 for word in deprioritize_words if word in title)
    base = 35 + overlap * 12 + bonus * 10 - penalty * 12
    return max(0, min(100, base))


def _diversity_score(item: dict[str, Any], peers: list[dict[str, Any]]) -> int:
    author = _normalize_text(item.get("author"))
    domain = _extract_domain(item.get("url"))
    duplicates = 0
    for other in peers:
        if other is item:
            continue
        if author and author == _normalize_text(other.get("author")):
            duplicates += 1
        elif domain and domain == _extract_domain(other.get("url")):
            duplicates += 1
    return max(20, 100 - duplicates * 25)


def score_discovery_candidates(candidates: list[dict[str, Any]], query: str, account_strategy: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in candidates:
        scored = dict(item)
        account_fit = _keyword_fit_score(scored, query, account_strategy)
        engagement = _engagement_score(_normalize_engagement(scored.get("engagement") or {}))
        freshness = _freshness_score(str(scored.get("published_at") or ""))
        readability = _readability_score(scored)
        diversity = _diversity_score(scored, candidates)
        total = round(account_fit * 0.35 + engagement * 0.25 + freshness * 0.15 + readability * 0.15 + diversity * 0.10, 2)
        scored["engagement"] = _normalize_engagement(scored.get("engagement") or {})
        scored["discovery_score"] = total
        scored["score_breakdown"] = {
            "account_match": account_fit,
            "engagement": engagement,
            "freshness": freshness,
            "readability": readability,
            "diversity": diversity,
        }
        output.append(scored)
    output.sort(key=lambda item: (item.get("discovery_score") or 0, _engagement_score(item.get("engagement") or {})), reverse=True)
    return output


def choose_discovery_selection(candidates: list[dict[str, Any]], *, primary_count: int = DISCOVERY_PRIMARY_COUNT, support_count: int = DISCOVERY_SUPPORTING_COUNT) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    used_platforms: set[str] = set()
    used_authors: set[str] = set()
    for item in candidates:
        platform = str(item.get("platform") or "")
        author = _normalize_text(item.get("author"))
        if len(selected) < primary_count:
            if platform and platform in used_platforms and author and author in used_authors:
                continue
            selected.append(dict(item, selection_tier="primary"))
            used_platforms.add(platform)
            if author:
                used_authors.add(author)
        elif len(selected) < primary_count + support_count:
            selected.append(dict(item, selection_tier="support"))
        if len(selected) >= primary_count + support_count:
            break
    return selected


@dataclass
class AdapterStatus:
    name: str
    available: bool
    mode: str
    detail: str


class ViralSourceAdapter:
    platform: str = ""

    def availability(self) -> AdapterStatus:
        return AdapterStatus(self.platform, True, "fallback", "ready")

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        raise NotImplementedError

    def read(self, item_or_url: dict[str, Any] | str) -> dict[str, Any]:
        raise NotImplementedError

    def comments(self, item_or_id: dict[str, Any] | str) -> list[dict[str, Any]]:
        return []


def _normalize_wechat_search_results(payload: Any, query: str) -> list[dict[str, Any]]:
    items = payload if isinstance(payload, list) else payload.get("results") if isinstance(payload, dict) else []
    output: list[dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or raw.get("link") or "").strip()
        if "mp.weixin.qq.com" not in url:
            continue
        title = _normalize_text(raw.get("title") or raw.get("name") or "")
        if not (url and title):
            continue
        output.append(
            {
                "source_id": _stable_id("wechat", url),
                "platform": "wechat",
                "url": url,
                "title": title,
                "author": _normalize_text(raw.get("author") or raw.get("siteName") or ""),
                "published_at": _normalize_text(raw.get("publishedDate") or raw.get("published_at") or ""),
                "engagement": {},
                "query": query,
                "excerpt": _normalize_text(raw.get("text") or raw.get("snippet") or ""),
                "media_type": "article",
                "fetch_method": "mcporter-exa",
                "fulltext_markdown": "",
                "comments": [],
                "transcript": "",
            }
        )
    return output


def _search_via_mcporter_exa(query: str, domain: str, limit: int) -> list[dict[str, Any]]:
    if not shutil.which("mcporter"):
        return []
    call = f'exa.web_search_exa(query: "{query}", numResults: {max(1, int(limit))}, includeDomains: ["{domain}"])'
    result = _run_command(["mcporter", "call", call], timeout=45)
    if result.returncode != 0:
        return []
    return _normalize_wechat_search_results(_extract_json_blob(result.stdout or result.stderr), query)


def _normalize_bing_result(url: str) -> str:
    if "bing.com/ck/a" in url and "u=" in url:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        for raw in qs.get("u", []):
            cleaned = urllib.parse.unquote(raw)
            if cleaned.startswith("http"):
                return cleaned
    return url


def _search_site_fallback(query: str, domain: str, platform: str, limit: int) -> list[dict[str, Any]]:
    encoded = urllib.parse.quote_plus(f"site:{domain} {query}")
    urls = [
        f"https://www.bing.com/search?q={encoded}&count={max(10, limit * 3)}",
        f"https://duckduckgo.com/html/?q={encoded}",
    ]
    output: list[dict[str, Any]] = []
    for search_url in urls:
        try:
            page = _http_get(search_url, timeout=20)
        except Exception:
            continue
        matches = re.findall(r'(?is)<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', page)
        for href, label in matches:
            normalized_url = _normalize_bing_result(html.unescape(href))
            if domain not in _extract_domain(normalized_url):
                continue
            title = _normalize_text(_strip_tags(label))
            if not (normalized_url and title):
                continue
            output.append(
                {
                    "source_id": _stable_id(platform, normalized_url),
                    "platform": platform,
                    "url": normalized_url,
                    "title": title,
                    "author": "",
                    "published_at": "",
                    "engagement": {},
                    "query": query,
                    "excerpt": "",
                    "media_type": "article" if platform != "bilibili" else "video",
                    "fetch_method": "site-search-fallback",
                    "fulltext_markdown": "",
                    "comments": [],
                    "transcript": "",
                }
            )
            if len(output) >= limit:
                return output
        if output:
            break
    return output[:limit]


def _normalize_xhs_items(payload: Any, query: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("data", {}).get("items") or payload.get("data", {}).get("notes") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    output: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        note = raw.get("note_card") or raw.get("note") or raw
        note_id = str(note.get("id") or note.get("note_id") or "").strip()
        xsec = str(note.get("xsec_token") or "").strip()
        url = str(note.get("url") or "").strip()
        if not url and note_id:
            token_part = f"?xsec_token={urllib.parse.quote(xsec)}" if xsec else ""
            url = f"https://www.xiaohongshu.com/explore/{note_id}{token_part}"
        title = _normalize_text(note.get("title") or note.get("desc") or note.get("content") or "")
        if not (url and title):
            continue
        user = note.get("user") or note.get("author") or {}
        engagement = _normalize_engagement(note.get("interact_info") or note.get("note_interact_info") or note)
        output.append(
            {
                "source_id": _stable_id("xiaohongshu", url),
                "platform": "xiaohongshu",
                "url": url,
                "title": title,
                "author": _normalize_text(user.get("nickname") or user.get("nick_name") or ""),
                "published_at": _normalize_text(note.get("time") or note.get("publish_time") or ""),
                "engagement": engagement,
                "query": query,
                "excerpt": _normalize_text(note.get("desc") or note.get("content") or ""),
                "media_type": "note",
                "fetch_method": "xhs-cli",
                "fulltext_markdown": "",
                "comments": [],
                "transcript": "",
                "note_id": note_id,
                "xsec_token": xsec,
            }
        )
    return output


def _run_xhs_search(query: str, limit: int) -> list[dict[str, Any]]:
    if not shutil.which("xhs"):
        return []
    commands = [
        ["xhs", "search", query, "--limit", str(limit), "--json"],
        ["xhs", "search", query, "-n", str(limit), "--json"],
        ["xhs", "search-notes", query, "--limit", str(limit), "--json"],
    ]
    for command in commands:
        try:
            result = _run_command(command, timeout=45)
        except Exception:
            continue
        if result.returncode != 0:
            continue
        normalized = _normalize_xhs_items(_extract_json_blob(result.stdout or result.stderr), query)
        if normalized:
            return normalized[:limit]
    return []


def _run_xhs_read(item: dict[str, Any]) -> dict[str, Any]:
    if not shutil.which("xhs"):
        return {}
    url = str(item.get("url") or "")
    commands = [
        ["xhs", "read", url, "--json"],
        ["xhs", "get", url, "--json"],
        ["xhs", "detail", url, "--json"],
    ]
    for command in commands:
        try:
            result = _run_command(command, timeout=45)
        except Exception:
            continue
        if result.returncode != 0:
            continue
        payload = _extract_json_blob(result.stdout or result.stderr)
        normalized = _normalize_xhs_items(payload, str(item.get("query") or ""))
        if normalized:
            detail = normalized[0]
            comments = payload.get("comments") if isinstance(payload, dict) else []
            if isinstance(comments, list):
                detail["comments"] = comments[:20]
            detail["fulltext_markdown"] = _normalize_text(payload.get("content") or payload.get("desc") or detail.get("excerpt") or "")
            detail["fetch_method"] = "xhs-cli"
            return detail
    return {}


def _search_weibo_mcp(query: str, limit: int) -> list[dict[str, Any]]:
    if not shutil.which("mcporter"):
        return []
    candidates = [
        f'weibo.search_weibo_content(query: "{query}", count: {limit})',
        f'weibo.search_weibo_content(keyword: "{query}", count: {limit})',
        f'weibo.search_content(query: "{query}", count: {limit})',
    ]
    for call in candidates:
        try:
            result = _run_command(["mcporter", "call", call], timeout=45)
        except Exception:
            continue
        if result.returncode != 0:
            continue
        payload = _extract_json_blob(result.stdout or result.stderr)
        items = payload if isinstance(payload, list) else payload.get("items") if isinstance(payload, dict) else []
        output: list[dict[str, Any]] = []
        for raw in items or []:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or raw.get("link") or "").strip()
            title = _normalize_text(raw.get("title") or raw.get("text") or raw.get("content") or "")
            if not (url and title):
                continue
            output.append(
                {
                    "source_id": _stable_id("weibo", url),
                    "platform": "weibo",
                    "url": url,
                    "title": title[:80],
                    "author": _normalize_text(raw.get("user_name") or raw.get("author") or raw.get("nickname") or ""),
                    "published_at": _normalize_text(raw.get("created_at") or raw.get("published_at") or ""),
                    "engagement": _normalize_engagement(raw),
                    "query": query,
                    "excerpt": _normalize_text(raw.get("text") or raw.get("content") or ""),
                    "media_type": "post",
                    "fetch_method": "weibo-mcp",
                    "fulltext_markdown": "",
                    "comments": [],
                    "transcript": "",
                }
            )
        if output:
            return output[:limit]
    return []


def _normalize_bilibili_items(payload: Any, query: str) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        items = payload.get("data", {}).get("result") or payload.get("items") or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    output: list[dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        bvid = str(raw.get("bvid") or raw.get("aid") or raw.get("id") or "").strip()
        url = str(raw.get("arcurl") or raw.get("url") or "").strip()
        if not url and bvid.startswith("BV"):
            url = f"https://www.bilibili.com/video/{bvid}"
        title = _normalize_text(_strip_tags(str(raw.get("title") or "")))
        if not (url and title):
            continue
        output.append(
            {
                "source_id": _stable_id("bilibili", url),
                "platform": "bilibili",
                "url": url,
                "title": title,
                "author": _normalize_text(raw.get("author") or raw.get("up_name") or raw.get("uname") or ""),
                "published_at": _normalize_text(raw.get("pubdate") or raw.get("created") or ""),
                "engagement": _normalize_engagement(raw),
                "query": query,
                "excerpt": _normalize_text(_strip_tags(str(raw.get("description") or raw.get("desc") or ""))),
                "media_type": "video",
                "fetch_method": "bilibili-api",
                "fulltext_markdown": "",
                "comments": [],
                "transcript": "",
            }
        )
    return output


def _search_bilibili(query: str, limit: int) -> list[dict[str, Any]]:
    if shutil.which("bili"):
        commands = [
            ["bili", "search", query, "--type", "video", "-n", str(limit), "--json"],
            ["bili", "search", query, "--type", "video", "-n", str(limit)],
        ]
        for command in commands:
            try:
                result = _run_command(command, timeout=45)
            except Exception:
                continue
            if result.returncode != 0:
                continue
            payload = _extract_json_blob(result.stdout or result.stderr)
            normalized = _normalize_bilibili_items(payload, query)
            if normalized:
                return normalized[:limit]
    encoded = urllib.parse.quote(query)
    api_url = (
        "https://api.bilibili.com/x/web-interface/search/type"
        f"?search_type=video&keyword={encoded}&page=1&page_size={max(1, int(limit))}"
    )
    try:
        payload = _extract_json_blob(_http_get(api_url, timeout=20))
    except Exception:
        return _search_site_fallback(query, "bilibili.com", "bilibili", limit)
    normalized = _normalize_bilibili_items(payload, query)
    return normalized[:limit] if normalized else _search_site_fallback(query, "bilibili.com", "bilibili", limit)


def _load_vtt_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = re.sub(r"WEBVTT.*?\n", "", raw)
    raw = re.sub(r"\d+\n", "", raw)
    raw = re.sub(r"\d{2}:\d{2}:\d{2}\.\d+\s+-->\s+\d{2}:\d{2}:\d{2}\.\d+\n", "", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = re.sub(r"\n{2,}", "\n", raw)
    return raw.strip()


def _read_bilibili(url: str) -> dict[str, Any]:
    if not shutil.which("yt-dlp"):
        return _read_generic_url(url)
    with tempfile.TemporaryDirectory() as tmp:
        base = str(Path(tmp) / "%(id)s")
        meta_result = _run_command(["yt-dlp", "--dump-single-json", url], timeout=90)
        payload = _extract_json_blob(meta_result.stdout or meta_result.stderr) if meta_result.returncode == 0 else {}
        transcript = ""
        sub_result = _run_command(
            [
                "yt-dlp",
                "--write-sub",
                "--write-auto-sub",
                "--sub-lang",
                "zh-Hans,zh,en",
                "--convert-subs",
                "vtt",
                "--skip-download",
                "-o",
                base,
                url,
            ],
            timeout=120,
        )
        if sub_result.returncode == 0:
            for path in Path(tmp).glob("*.vtt"):
                transcript = _load_vtt_text(path)
                if transcript:
                    break
        comments: list[dict[str, Any]] = []
        if isinstance(payload.get("comments"), list):
            comments = payload.get("comments")[:20]
        title = _normalize_text(payload.get("title") or "")
        description = _normalize_text(payload.get("description") or "")
        body = _dedupe_texts([description, transcript], limit=None)
        return {
            "title": title,
            "author": _normalize_text(payload.get("uploader") or ""),
            "published_at": _normalize_text(payload.get("upload_date") or payload.get("timestamp") or ""),
            "engagement": _normalize_engagement(payload),
            "fulltext_markdown": "\n\n".join(body).strip(),
            "transcript": transcript,
            "comments": comments,
            "fetch_method": "yt-dlp",
        }


class WeChatAdapter(ViralSourceAdapter):
    platform = "wechat"

    def availability(self) -> AdapterStatus:
        if shutil.which("mcporter"):
            return AdapterStatus(self.platform, True, "agent-reach", "mcporter + Exa")
        return AdapterStatus(self.platform, True, "fallback", "site search + direct read")

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        primary = _search_via_mcporter_exa(query, "mp.weixin.qq.com", limit)
        return primary or _search_site_fallback(query, "mp.weixin.qq.com", self.platform, limit)

    def read(self, item_or_url: dict[str, Any] | str) -> dict[str, Any]:
        item = item_or_url if isinstance(item_or_url, dict) else {"url": str(item_or_url or "")}
        url = str(item.get("url") or "").strip()
        if not url:
            return {}
        if shutil.which("mcporter"):
            call = f'exa.crawling_exa(urls: ["{url}"], maxCharacters: 12000)'
            result = _run_command(["mcporter", "call", call], timeout=60)
            if result.returncode == 0:
                payload = _extract_json_blob(result.stdout or result.stderr)
                if isinstance(payload, list) and payload:
                    payload = payload[0]
                if isinstance(payload, dict):
                    text = _normalize_text(payload.get("text") or payload.get("markdown") or payload.get("content") or "")
                    if text:
                        return {
                            "title": _normalize_text(payload.get("title") or item.get("title") or ""),
                            "author": _normalize_text(payload.get("author") or item.get("author") or ""),
                            "published_at": _normalize_text(payload.get("publishedDate") or item.get("published_at") or ""),
                            "fulltext_markdown": text,
                            "fetch_method": "mcporter-exa",
                        }
        return _read_generic_url(url)


class XiaoHongShuAdapter(ViralSourceAdapter):
    platform = "xiaohongshu"

    def availability(self) -> AdapterStatus:
        if shutil.which("xhs"):
            return AdapterStatus(self.platform, True, "agent-reach", "xhs-cli")
        return AdapterStatus(self.platform, True, "fallback", "site search + generic read")

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        primary = _run_xhs_search(query, limit)
        return primary or _search_site_fallback(query, "xiaohongshu.com", self.platform, limit)

    def read(self, item_or_url: dict[str, Any] | str) -> dict[str, Any]:
        item = item_or_url if isinstance(item_or_url, dict) else {"url": str(item_or_url or "")}
        primary = _run_xhs_read(item)
        if primary:
            return primary
        return _read_generic_url(str(item.get("url") or ""))


class WeiboAdapter(ViralSourceAdapter):
    platform = "weibo"

    def availability(self) -> AdapterStatus:
        if shutil.which("mcporter"):
            return AdapterStatus(self.platform, True, "agent-reach", "mcporter weibo mcp or fallback")
        return AdapterStatus(self.platform, True, "fallback", "site search + generic read")

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        primary = _search_weibo_mcp(query, limit)
        return primary or _search_site_fallback(query, "weibo.com", self.platform, limit)

    def read(self, item_or_url: dict[str, Any] | str) -> dict[str, Any]:
        item = item_or_url if isinstance(item_or_url, dict) else {"url": str(item_or_url or "")}
        return _read_generic_url(str(item.get("url") or ""))


class BilibiliAdapter(ViralSourceAdapter):
    platform = "bilibili"

    def availability(self) -> AdapterStatus:
        if shutil.which("yt-dlp"):
            return AdapterStatus(self.platform, True, "agent-reach", "bili api/cli + yt-dlp")
        return AdapterStatus(self.platform, True, "fallback", "site search + generic read")

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        return _search_bilibili(query, limit)

    def read(self, item_or_url: dict[str, Any] | str) -> dict[str, Any]:
        item = item_or_url if isinstance(item_or_url, dict) else {"url": str(item_or_url or "")}
        return _read_bilibili(str(item.get("url") or ""))


def adapter_for(platform: str) -> ViralSourceAdapter:
    mapping = {
        "wechat": WeChatAdapter,
        "xiaohongshu": XiaoHongShuAdapter,
        "weibo": WeiboAdapter,
        "bilibili": BilibiliAdapter,
    }
    normalized = str(platform or "").strip().lower()
    if normalized not in mapping:
        raise KeyError(f"unsupported platform: {platform}")
    return mapping[normalized]()


def discover_viral_candidates(
    query: str,
    *,
    platforms: list[str],
    limit_per_platform: int,
    account_strategy: dict[str, Any],
) -> dict[str, Any]:
    candidate_pool: list[dict[str, Any]] = []
    platform_status: dict[str, Any] = {}
    for platform in platforms:
        adapter = adapter_for(platform)
        status = adapter.availability()
        platform_status[platform] = {
            "available": status.available,
            "mode": status.mode,
            "detail": status.detail,
        }
        if not status.available:
            continue
        try:
            items = adapter.search(query, limit_per_platform)
        except Exception as exc:
            platform_status[platform]["error"] = str(exc)
            items = []
        candidate_pool.extend(items)
    deduped: dict[str, dict[str, Any]] = {}
    for item in candidate_pool:
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        key = f"{item.get('platform')}::{url}"
        if key not in deduped or (item.get("discovery_score") or 0) > (deduped[key].get("discovery_score") or 0):
            deduped[key] = item
    ranked = score_discovery_candidates(list(deduped.values()), query, account_strategy)
    selected = choose_discovery_selection(ranked)
    selected_ids = {item.get("source_id") for item in selected}
    enriched = [dict(item, recommended=bool(item.get("source_id") in selected_ids)) for item in ranked]
    return {
        "query": query,
        "platforms": platforms,
        "limit_per_platform": limit_per_platform,
        "platform_status": platform_status,
        "candidates": enriched,
        "recommended_selection": selected,
        "generated_at": now_iso(),
    }


def markdown_discovery_report(payload: dict[str, Any]) -> str:
    lines = [
        "# 爆款发现报告",
        "",
        f"- 查询词：{payload.get('query') or ''}",
        f"- 平台：{', '.join(payload.get('platforms') or [])}",
        "",
        "## 渠道状态",
        "",
    ]
    for platform, status in (payload.get("platform_status") or {}).items():
        mode = status.get("mode") or "unknown"
        detail = status.get("detail") or ""
        lines.append(f"- {platform}：{mode}；{detail}")
    lines.extend(["", "## 推荐样本", ""])
    for item in payload.get("recommended_selection") or []:
        lines.append(
            f"- [{item.get('platform')}] {item.get('title')} | 分数 {item.get('discovery_score')} | {item.get('url')}"
        )
    lines.extend(["", "## 候选池", ""])
    for item in (payload.get("candidates") or [])[:12]:
        tag = "推荐" if item.get("recommended") else "备选"
        lines.append(
            f"- {tag} | [{item.get('platform')}] {item.get('title')} | 分数 {item.get('discovery_score')} | 作者 {item.get('author') or '未知'}"
        )
    return "\n".join(lines).rstrip() + "\n"


def select_viral_candidates(discovery_payload: dict[str, Any], indexes: list[int]) -> list[dict[str, Any]]:
    candidates = list(discovery_payload.get("candidates") or [])
    if not candidates:
        raise SystemExit("viral-discovery.json 中没有 candidates，无法选择。")
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index in indexes:
        if index < 1 or index > len(candidates):
            raise SystemExit(f"--index 超出范围：{index}（可选 1~{len(candidates)}）")
        item = dict(candidates[index - 1] or {})
        source_id = str(item.get("source_id") or "")
        if source_id in seen:
            continue
        seen.add(source_id)
        output.append(item)
    if not output:
        raise SystemExit("未选中任何爆款样本。")
    if len(output) > DISCOVERY_PRIMARY_COUNT + DISCOVERY_SUPPORTING_COUNT:
        raise SystemExit("一期最多只支持选择 5 篇样本。")
    return choose_discovery_selection(output, primary_count=min(DISCOVERY_PRIMARY_COUNT, len(output)), support_count=max(0, len(output) - DISCOVERY_PRIMARY_COUNT))


def collect_source_corpus(selected_items: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    readable_count = 0
    for raw in selected_items:
        item = dict(raw)
        platform = str(item.get("platform") or "").strip().lower()
        adapter = adapter_for(platform)
        detail = {}
        try:
            detail = adapter.read(item)
        except Exception as exc:
            detail = {"fetch_method": "failed", "error": str(exc)}
        collected = item | {
            "fulltext_markdown": _normalize_text(detail.get("fulltext_markdown") or item.get("fulltext_markdown") or ""),
            "comments": detail.get("comments") if isinstance(detail.get("comments"), list) else item.get("comments") or [],
            "transcript": _normalize_text(detail.get("transcript") or item.get("transcript") or ""),
            "fetch_method": detail.get("fetch_method") or item.get("fetch_method") or "",
            "author": _normalize_text(detail.get("author") or item.get("author") or ""),
            "title": _normalize_text(detail.get("title") or item.get("title") or ""),
            "published_at": _normalize_text(detail.get("published_at") or item.get("published_at") or ""),
            "engagement": _normalize_engagement(detail.get("engagement") or item.get("engagement") or {}),
        }
        body = collected.get("fulltext_markdown") or collected.get("transcript") or ""
        collected["excerpt"] = _normalize_text(item.get("excerpt") or extract_summary(body))
        collected["word_count"] = len(_tokenize(body))
        collected["readability_score"] = _readability_score(collected)
        if body:
            readable_count += 1
            fingerprint = build_article_fingerprint(
                str(collected.get("title") or ""),
                str(body),
                {
                    "topic": str(collected.get("query") or collected.get("title") or ""),
                    "summary": str(collected.get("excerpt") or ""),
                    "viral_blueprint": {"article_archetype": "commentary"},
                },
            )
        else:
            fingerprint = {}
        collected["content_fingerprint"] = fingerprint
        items.append(collected)
    return {
        "items": items,
        "primary_items": [item for item in items if item.get("selection_tier") == "primary"],
        "supporting_items": [item for item in items if item.get("selection_tier") == "support"],
        "readable_count": readable_count,
        "generated_at": now_iso(),
    }


def _top_patterns(items: list[str], label_map: dict[str, str], *, limit: int = 3) -> list[dict[str, Any]]:
    counter = Counter(items)
    output: list[dict[str, Any]] = []
    for key, count in counter.most_common(limit):
        output.append({"key": key, "label": label_map.get(key, key), "count": count})
    return output


def _classify_opening(text: str) -> str:
    value = _normalize_text(text)
    if not value:
        return "generic"
    if value.startswith("## "):
        value = value[3:].strip()
    if any(marker in value[:24] for marker in ["那天", "会议室", "工位", "消息弹出来", "凌晨", "屏幕上"]):
        return "scene"
    if "为什么" in value[:20] or value.endswith("？"):
        return "question"
    if any(marker in value for marker in ["数据显示", "报告", "%", "同比", "环比"]):
        return "data"
    if any(marker in value for marker in ["这次", "刚刚", "今天", "最近", "本周"]):
        return "news"
    if any(marker in value for marker in ["真正", "关键", "问题不在", "不是"]):
        return "judgment"
    return "generic"


def _extract_argument_modes(text: str) -> list[str]:
    corpus = _normalize_text(text)
    modes: list[str] = []
    mapping = [
        ("case-study", ("案例", "复盘", "有人", "一家公司", "一个团队")),
        ("data-backed", ("数据", "%", "报告", "研究", "指标")),
        ("contrast", ("不是", "而是", "对比", "一边", "另一边")),
        ("step-by-step", ("第一", "第二", "步骤", "顺序", "先做")),
        ("boundary", ("但这不代表", "边界", "前提", "例外", "误区")),
    ]
    for key, words in mapping:
        if any(word in corpus for word in words):
            modes.append(key)
    return modes or ["judgment"]


def _extract_interaction_triggers(items: list[dict[str, Any]]) -> dict[str, list[str]]:
    comment_text = " ".join(_normalize_text(comment.get("content") if isinstance(comment, dict) else comment) for item in items for comment in (item.get("comments") or [])[:10])
    article_text = " ".join(_normalize_text(item.get("fulltext_markdown") or item.get("transcript") or "") for item in items)
    like: list[str] = []
    comment: list[str] = []
    share: list[str] = []
    if "太真实" in comment_text or "说到我了" in comment_text or "扎心" in comment_text:
        like.append("结尾要留一句能让人点头或截图的判断")
    if "你们" in article_text or "如果是你" in article_text or "你会怎么" in article_text:
        comment.append("结尾保留一个让读者站队或补充经验的问题")
    if "误判" in article_text or "分水岭" in article_text or "关键顺序" in article_text:
        share.append("保留一个能转给同事的判断或提醒")
    if not like:
        like.append("首屏后 2 段内必须出现一个能让人继续读下去的明确判断")
    if not comment:
        comment.append("结尾用读者处境收束，而不是空问号")
    if not share:
        share.append("中段安排一个值得复述的分水岭判断")
    return {"like": like[:3], "comment": comment[:3], "share": share[:3]}


def analyze_source_corpus(
    corpus_payload: dict[str, Any],
    *,
    topic: str,
    angle: str,
    audience: str,
    content_mode: str,
    account_strategy: dict[str, Any],
) -> dict[str, Any]:
    items = list(corpus_payload.get("items") or [])
    readable = [item for item in items if str(item.get("fulltext_markdown") or item.get("transcript") or "").strip()]
    title_patterns = _top_patterns(
        [title_template_key(str(item.get("title") or "")) for item in readable if str(item.get("title") or "").strip()],
        TITLE_PATTERN_LABELS,
    )
    opening_patterns = _top_patterns(
        [_classify_opening(str((item.get("fulltext_markdown") or item.get("transcript") or "").split("\n\n")[0])) for item in readable],
        {
            "scene": "场景切口",
            "question": "问题切口",
            "data": "数据切口",
            "news": "新闻切口",
            "judgment": "判断切口",
            "generic": "通用切口",
        },
    )
    paragraph_counts = [
        len([block for block in re.split(r"\n\s*\n", str(item.get("fulltext_markdown") or item.get("transcript") or "")) if _normalize_text(block)])
        for item in readable
    ]
    avg_paragraphs = round(sum(paragraph_counts) / max(1, len(paragraph_counts)), 1) if paragraph_counts else 0.0
    avg_headings = round(sum(len(legacy.extract_headings(str(item.get("fulltext_markdown") or ""))) for item in readable) / max(1, len(readable)), 1) if readable else 0.0
    argument_modes = _dedupe_texts([mode for item in readable for mode in _extract_argument_modes(str(item.get("fulltext_markdown") or item.get("transcript") or ""))], limit=5)
    interaction_triggers = _extract_interaction_triggers(readable)
    evidence_items = _dedupe_texts(
        [
            f"样本《{item.get('title')}》主要靠{', '.join(_extract_argument_modes(str(item.get('fulltext_markdown') or item.get('transcript') or ''))[:2])}推进，首屏摘要：{extract_summary(str(item.get('fulltext_markdown') or item.get('transcript') or ''))}"
            for item in readable[:5]
            if str(item.get("title") or "").strip()
        ],
        limit=5,
    )
    reusable_elements = _dedupe_texts(
        [
            f"标题优先学习 {title_patterns[0]['label']}" if title_patterns else "",
            f"开头优先学习 {opening_patterns[0]['label']}" if opening_patterns else "",
            f"正文论证顺序优先保留 {', '.join(argument_modes[:3])}" if argument_modes else "",
            "中段必须安排一个值得截图或转述的判断峰值",
            "结尾要么收束成判断，要么留下与读者处境直接相关的问题",
        ],
        limit=6,
    )
    forbidden_reuse = _dedupe_texts(
        [
            "禁止直接复用任何原文标题核心短语和金句",
            "禁止复用原文案例细节、人物名字、具体情境顺序",
            "禁止只做同义替换，必须补新的事实、例子或对比",
            "禁止整篇照着单一样本的段落顺序重写",
            "禁止保留任何连续 24 个汉字以上的复用片段",
        ],
        limit=6,
    )
    top_title = title_patterns[0]["label"] if title_patterns else "观点直给"
    top_opening = opening_patterns[0]["label"] if opening_patterns else "场景切口"
    query_text = topic or str((readable[0].get("query") if readable else "") or "")
    research_context = {
        "topic": topic or query_text,
        "selected_title": topic or query_text,
        "direction": angle,
        "audience": audience,
        "research": {},
        "style_signals": [top_title, top_opening, *argument_modes[:2]],
    }
    viral_blueprint = normalize_viral_blueprint(
        {
            "core_viewpoint": f"{topic or query_text} 真正值得学的，不是单篇爆款的句子，而是它怎么抓住读者、怎么推进判断、怎么把互动点放在最值钱的位置。",
            "secondary_viewpoints": reusable_elements[:3],
            "persuasion_strategies": argument_modes[:4],
            "emotion_triggers": [top_opening, "误判提醒", "结果预期"],
            "emotion_curve": [
                {"stage": "开头", "emotion": "被带入", "goal": "两段内让读者进入问题现场"},
                {"stage": "中段", "emotion": "被说服", "goal": "用案例、对比或数据把判断托住"},
                {"stage": "结尾", "emotion": "愿意转述", "goal": "留下可点赞、可评论、可转发的收束"},
            ],
            "style_traits": [top_opening, f"平均 {avg_paragraphs} 段左右", f"平均 {avg_headings} 个小标题"],
            "pain_points": [
                "读者不是缺信息，而是缺一个能马上带走的判断",
                "只模仿句子会让文章更像洗稿，而不是更像爆款",
            ],
            "like_triggers": interaction_triggers["like"],
            "comment_triggers": interaction_triggers["comment"],
            "share_triggers": interaction_triggers["share"],
            "social_currency_points": ["给读者一个能转给同事的判断", "提供一个比热闹更深一层的分水岭视角"],
            "interaction_prompts": interaction_triggers["comment"],
            "article_archetype": "commentary" if "step-by-step" not in argument_modes else "tutorial",
        },
        research_context,
    )
    editorial_blueprint = normalize_editorial_blueprint(
        {
            "style_key": "case-memo" if "case-study" in argument_modes else "signal-briefing",
            "summary": f"以 {top_opening} 开场，用 {', '.join(argument_modes[:3]) or '判断推进'} 推正文，结尾收束互动。",
            "opening_strategy": f"首屏优先用 {top_opening}，不要先把结论喊出来。",
            "body_strategy": "正文先建立场景，再推进判断，再补案例或对比，最后再给边界。",
            "heading_strategy": "小标题要像判断推进，不要像模板化编号题。",
            "evidence_strategy": "必须补新的事实、例子或对比，不能贴着原样本只换词。",
            "ending_strategy": "用判断或提问收束，但不能变成生硬的任务清单。",
            "paragraph_rhythm": f"平均 {avg_paragraphs} 段，保持长短句交替。",
            "language_texture": [top_opening, "少模板连接词", "像真人编辑一样推进"],
            "forbidden_moves": forbidden_reuse[:4],
        },
        research_context | {"article_archetype": viral_blueprint.get("article_archetype") or "commentary", "content_mode": content_mode, "account_strategy": account_strategy},
    )
    writing_persona = normalize_writing_persona(
        None,
        {
            "article_archetype": viral_blueprint.get("article_archetype") or "commentary",
            "content_mode": content_mode,
            "audience": audience,
            "account_strategy": account_strategy,
        },
    )
    dna = {
        "title_formulas": title_patterns,
        "opening_hook_types": opening_patterns,
        "paragraph_rhythm": {
            "average_paragraph_count": avg_paragraphs,
            "average_heading_count": avg_headings,
            "rhythm_note": "短段引入 + 中段展开 + 结尾收束" if avg_paragraphs >= 6 else "短平快推进，但中段要保留展开段",
        },
        "argument_sequence": argument_modes or ["judgment"],
        "emotion_curve": viral_blueprint.get("emotion_curve") or [],
        "interaction_triggers": interaction_triggers,
        "reusable_elements": reusable_elements,
        "forbidden_reuse": forbidden_reuse,
        "viral_blueprint": viral_blueprint,
        "editorial_blueprint": editorial_blueprint,
        "writing_persona": writing_persona,
        "source_count": len(items),
        "readable_count": len(readable),
        "generated_at": now_iso(),
    }
    research = {
        "topic": topic or query_text,
        "angle": angle,
        "audience": audience,
        "sources": [
            {
                "url": item.get("url"),
                "title": item.get("title"),
                "platform": item.get("platform"),
                "author": item.get("author"),
                "engagement": item.get("engagement"),
                "tier": item.get("selection_tier"),
            }
            for item in items
        ],
        "evidence_items": evidence_items,
        "information_gaps": [
            "正文必须补新的事实、例子或对比，不能只做同义替换。",
            "如果样本里的时间、数据、案例要引用到正文，发布前必须单独核验原始来源。",
        ],
        "forbidden_claims": forbidden_reuse[:4],
        "viral_sources": [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "platform": item.get("platform"),
                "selection_tier": item.get("selection_tier"),
            }
            for item in items
        ],
        "viral_dna_summary": {
            "title_formula": top_title,
            "opening_hook": top_opening,
            "argument_sequence": argument_modes[:4],
        },
        "rewrite_constraints": {
            "mode": "original-remix",
            "must_add": ["新的事实", "新的例子", "新的对比"],
            "banned_reuse": forbidden_reuse[:5],
        },
        "viral_blueprint": viral_blueprint,
        "editorial_blueprint": editorial_blueprint,
        "writing_persona": writing_persona,
        "provider": "viral-pipeline",
        "model": "heuristic",
        "generated_at": now_iso(),
    }
    return {"dna": dna, "research": research}


def markdown_viral_dna_report(payload: dict[str, Any]) -> str:
    lines = [
        "# 爆款基因拆解",
        "",
        f"- 样本数：{payload.get('source_count') or 0}",
        f"- 可读全文数：{payload.get('readable_count') or 0}",
        "",
        "## 标题公式",
        "",
    ]
    for item in payload.get("title_formulas") or []:
        lines.append(f"- {item.get('label')}（{item.get('count')}）")
    lines.extend(["", "## 开头钩子", ""])
    for item in payload.get("opening_hook_types") or []:
        lines.append(f"- {item.get('label')}（{item.get('count')}）")
    lines.extend(["", "## 论证顺序", ""])
    for item in payload.get("argument_sequence") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## 可借元素", ""])
    for item in payload.get("reusable_elements") or []:
        lines.append(f"- {item}")
    lines.extend(["", "## 禁止复用", ""])
    for item in payload.get("forbidden_reuse") or []:
        lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def _clean_similarity_text(value: str) -> str:
    text = _compact_text(value)
    return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", text)


def _longest_common_contiguous(left: str, right: str) -> int:
    if not left or not right:
        return 0
    longest = 0
    previous = [0] * (len(right) + 1)
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, start=1):
            if left_char == right_char:
                value = previous[index - 1] + 1
                current.append(value)
                if value > longest:
                    longest = value
            else:
                current.append(0)
        previous = current
    return longest


def _five_gram_overlap(left: str, right: str) -> float:
    def grams(text: str) -> set[str]:
        compact = _clean_similarity_text(text)
        if len(compact) < 5:
            return {compact} if compact else set()
        return {compact[index : index + 5] for index in range(0, len(compact) - 4)}

    left_grams = grams(left)
    right_grams = grams(right)
    if not left_grams or not right_grams:
        return 0.0
    return round(len(left_grams & right_grams) / max(1, len(left_grams)), 3)


def _title_similarity(left: str, right: str) -> float:
    left_tokens = "".join(_tokenize(left))
    right_tokens = "".join(_tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return round(SequenceMatcher(None, left_tokens, right_tokens).ratio(), 3)


def build_source_similarity_report(
    title: str,
    body: str,
    manifest: dict[str, Any],
    corpus_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    items = list((corpus_payload or {}).get("items") or [])
    readable = [item for item in items if str(item.get("fulltext_markdown") or item.get("transcript") or "").strip()]
    if not readable:
        return {
            "available": False,
            "passed": True,
            "generated_at": now_iso(),
            "thresholds": {
                "max_contiguous_chars": CONTIGUOUS_REUSE_THRESHOLD,
                "max_five_gram_overlap": FIVE_GRAM_OVERLAP_THRESHOLD,
                "max_title_similarity": TITLE_SIMILARITY_THRESHOLD,
                "max_route_similarity": ROUTE_SIMILARITY_THRESHOLD,
            },
            "items": [],
        }
    current_fp = build_article_fingerprint(title, body, manifest)
    results: list[dict[str, Any]] = []
    for item in readable:
        source_body = str(item.get("fulltext_markdown") or item.get("transcript") or "")
        source_title = str(item.get("title") or "")
        source_fp = item.get("content_fingerprint") or build_article_fingerprint(
            source_title,
            source_body,
            {"topic": item.get("query") or source_title, "summary": item.get("excerpt") or "", "viral_blueprint": {"article_archetype": "commentary"}},
        )
        contiguous = _longest_common_contiguous(_clean_similarity_text(body), _clean_similarity_text(source_body))
        five_gram = _five_gram_overlap(body, source_body)
        title_sim = _title_similarity(title, source_title)
        route_sim = compare_fingerprints(current_fp, source_fp)
        passed = (
            contiguous <= CONTIGUOUS_REUSE_THRESHOLD
            and five_gram <= FIVE_GRAM_OVERLAP_THRESHOLD
            and title_sim <= TITLE_SIMILARITY_THRESHOLD
            and route_sim <= ROUTE_SIMILARITY_THRESHOLD
        )
        failures: list[str] = []
        if contiguous > CONTIGUOUS_REUSE_THRESHOLD:
            failures.append(f"连续复用 {contiguous} 字")
        if five_gram > FIVE_GRAM_OVERLAP_THRESHOLD:
            failures.append(f"5-gram 重合率 {five_gram}")
        if title_sim > TITLE_SIMILARITY_THRESHOLD:
            failures.append(f"标题相似度 {title_sim}")
        if route_sim > ROUTE_SIMILARITY_THRESHOLD:
            failures.append(f"结构路线相似度 {route_sim}")
        results.append(
            {
                "title": source_title,
                "url": item.get("url"),
                "platform": item.get("platform"),
                "contiguous_chars": contiguous,
                "five_gram_overlap": five_gram,
                "title_similarity": title_sim,
                "route_similarity": route_sim,
                "passed": passed,
                "failures": failures,
            }
        )
    results.sort(
        key=lambda item: (
            item.get("passed"),
            -(item.get("contiguous_chars") or 0),
            -(item.get("five_gram_overlap") or 0),
            -(item.get("route_similarity") or 0),
        )
    )
    return {
        "available": True,
        "passed": all(item.get("passed") for item in results),
        "generated_at": now_iso(),
        "thresholds": {
            "max_contiguous_chars": CONTIGUOUS_REUSE_THRESHOLD,
            "max_five_gram_overlap": FIVE_GRAM_OVERLAP_THRESHOLD,
            "max_title_similarity": TITLE_SIMILARITY_THRESHOLD,
            "max_route_similarity": ROUTE_SIMILARITY_THRESHOLD,
        },
        "max_contiguous_chars": max(item.get("contiguous_chars") or 0 for item in results),
        "max_five_gram_overlap": max(item.get("five_gram_overlap") or 0 for item in results),
        "max_title_similarity": max(item.get("title_similarity") or 0 for item in results),
        "max_route_similarity": max(item.get("route_similarity") or 0 for item in results),
        "items": results,
        "failed_items": [item for item in results if not item.get("passed")],
    }


def markdown_similarity_report(payload: dict[str, Any]) -> str:
    lines = [
        "# 来源相似度报告",
        "",
        f"- 是否启用：{'是' if payload.get('available') else '否'}",
        f"- 是否通过：{'通过' if payload.get('passed') else '未通过'}",
        "",
        "## 阈值",
        "",
        f"- 连续复用：{payload.get('thresholds', {}).get('max_contiguous_chars')}",
        f"- 5-gram 重合率：{payload.get('thresholds', {}).get('max_five_gram_overlap')}",
        f"- 标题相似度：{payload.get('thresholds', {}).get('max_title_similarity')}",
        f"- 结构路线相似度：{payload.get('thresholds', {}).get('max_route_similarity')}",
        "",
        "## 对比结果",
        "",
    ]
    for item in payload.get("items") or []:
        failures = "；".join(item.get("failures") or []) or "通过"
        lines.append(
            f"- [{item.get('platform')}] {item.get('title')} | 连续复用 {item.get('contiguous_chars')} | 5-gram {item.get('five_gram_overlap')} | 标题 {item.get('title_similarity')} | 路线 {item.get('route_similarity')} | {failures}"
        )
    return "\n".join(lines).rstrip() + "\n"


def apply_source_similarity_gate(report: dict[str, Any], similarity_report: dict[str, Any]) -> dict[str, Any]:
    if not report:
        return report
    updated = json.loads(json.dumps(report, ensure_ascii=False))
    quality_gates = dict(updated.get("quality_gates") or {})
    quality_gates["source_similarity_passed"] = bool(similarity_report.get("passed", True))
    updated["quality_gates"] = quality_gates
    updated["source_similarity"] = similarity_report
    if not similarity_report.get("passed", True):
        mandatory = list(updated.get("mandatory_revisions") or [])
        mandatory.insert(0, "与爆款样本相似度过高，必须继续改写标题、关键段落和结构推进。")
        updated["mandatory_revisions"] = _dedupe_texts(mandatory, limit=10)
        weaknesses = list(updated.get("weaknesses") or [])
        weaknesses.append("来源样本相似度过高，需要拉开标题、段落和结构路线。")
        updated["weaknesses"] = _dedupe_texts(weaknesses, limit=8)
    return recompute_score_outcome(updated)


def write_platform_versions(
    workspace: Path,
    *,
    article_text: str,
    selected_title: str,
    summary: str,
    dna_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    versions_dir = workspace / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)
    meta, body = split_frontmatter(article_text)
    title = selected_title or meta.get("title") or legacy.infer_title(body) or "未命名标题"
    summary_text = summary or meta.get("summary") or extract_summary(body)
    dna = dna_payload or {}
    reusable = _dedupe_texts(list(dna.get("reusable_elements") or []), limit=2)
    intro_note = reusable[0] if reusable else summary_text
    wechat_body = body.strip()
    if intro_note and intro_note not in wechat_body[:160]:
        wechat_body = f"{intro_note}\n\n{wechat_body}".strip()
    wechat_text = join_frontmatter({"title": title, "summary": summary_text}, wechat_body if wechat_body.endswith("\n") else wechat_body + "\n")
    manifest = {"generated_at": now_iso(), "items": []}
    path = versions_dir / "wechat.md"
    write_text(path, wechat_text)
    manifest["items"].append({"platform": "wechat", "path": f"versions/{path.name}"})
    write_json(versions_dir / "manifest.json", manifest)
    return manifest


def write_research_from_viral_analysis(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(workspace / "viral-dna.json", payload["dna"])
    write_text(workspace / "viral-dna.md", markdown_viral_dna_report(payload["dna"]))
    write_json(workspace / "research.json", payload["research"])


def write_similarity_artifacts(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(workspace / "similarity-report.json", payload)
    write_text(workspace / "similarity-report.md", markdown_similarity_report(payload))


def write_discovery_artifacts(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(workspace / "viral-discovery.json", payload)
    write_text(workspace / "viral-discovery.md", markdown_discovery_report(payload))


def write_source_corpus_artifacts(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(workspace / "source-corpus.json", payload)


def build_versioned_article(title: str, summary: str, body: str) -> str:
    return join_frontmatter({"title": title, "summary": summary}, body)
