from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import legacy_studio as legacy
from core.artifacts import extract_summary, join_frontmatter, now_iso, read_json, read_text, split_frontmatter, strip_leading_h1, write_json, write_text
from core.publication_cleanup import expand_compact_markdown_lists, strip_ai_label_phrases
from core.quality_checks import build_article_summary, lead_paragraph_count, metadata_integrity_report

COMMENTARY_ARCHETYPES = {"commentary", "case-study", "comparison", "narrative"}
WECHAT_PUBLICATION_STYLE_CHOICES = ("clean", "cards", "magazine", "business", "warm", "poster", "tech", "blueprint")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*]\([^)]+\)")
_RAW_HTML_IMAGE_RE = re.compile(r"(?is)<img\b[^>]*>")
_REFERENCE_CALLOUT_RE = re.compile(r"(?ms)^\s*>\s*\[!(?:TIP|NOTE)]\s*(?:参考资料|参考来源|参考与延伸).*?(?=^\s*(?:#|$)|\Z)")
_INLINE_CITATION_RE = re.compile(r"(?<!\w)\[(\d{1,2})](?!\()")
_BOXED_CITATION_RE = re.compile(r"【\s*(\d{1,2})\s*】")
_CODE_FENCE_RE = re.compile(r"^```")
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
_LIST_LINE_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_HEADING_LINE_RE = re.compile(r"^\s*#{1,6}\s+")
_BLOCKQUOTE_LINE_RE = re.compile(r"^\s*>")
_COMPARE_PATTERNS = [
    re.compile(r"^(?:真正[^，。；]{0,8}的)?问题不在(?P<left>[^，。；]{2,28})[，,；; ]*(?:而|而是|而在)(?P<right>.+)$"),
    re.compile(r"^(?P<left>[^，。；]{2,28})不是(?P<surface>[^，。；]{2,22})[，,；; ]*而是(?P<right>.+)$"),
    re.compile(r"^(?:表面上看|表面看|看上去|乍一看)(?P<left>[^，。；]{2,26})[，,；; ]*(?:真正|实际|本质上|更该看的是|真正要看的是)(?P<right>.+)$"),
]
_METRIC_VALUE_RE = re.compile(r"(¥?\$?\d+(?:\.\d+)?%|¥?\$?\d+(?:\.\d+)?(?:万|亿|倍|条|个|家|天|小时|分钟|年|月))")
_GENERIC_PRODUCT_RE = re.compile(r"\b(?:[A-Z]{2,}[A-Za-z0-9._+-]*|[A-Za-z]+(?:[._/-][A-Za-z0-9]+)+|--[a-z0-9][a-z0-9-]*)\b")
_VERSION_PHRASE_RE = re.compile(r"\b[A-Z][A-Za-z0-9+.-]*\s+\d+(?:\.\d+){0,2}\b")
_PATH_TERM_RE = re.compile(r"(?:/v?\d+)?/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+")
_TECH_COMMAND_RE = re.compile(r"^\s*(?:\$ )?(?:python|pip|uv|npm|pnpm|yarn|node|git|curl|pwsh|powershell|export|set |Get-|New-|Copy-|Move-|Remove-)\b", re.I)
_JSISH_RE = re.compile(r"^\s*(?:const|let|var|await|return|if\b|for\b|while\b|import\b|from\b|class\b|function\b|def\b|print\()")


def normalize_urls(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _reference_domain(url: str) -> str:
    return urlparse(url).netloc.replace("www.", "") or url


def _reference_label(url: str) -> str:
    domain = _reference_domain(url)
    path = (urlparse(url).path or "").strip("/")
    if path:
        parts = [part for part in path.split("/") if part]
        return f"{domain} / {parts[-1][:36]}"
    return domain


def _extract_body_urls(body: str) -> list[str]:
    urls = re.findall(r"https?://[^\s)>\]]+", body or "")
    return normalize_urls(urls)


def normalize_publication_body(title: str, body: str) -> str:
    normalized = body or ""
    normalized = re.sub(r"(?m)^(\s*>\s*)?金句\s*\d+\s*[：:]\s*", lambda m: m.group(1) or "", normalized)
    normalized = _BOXED_CITATION_RE.sub(lambda m: f"[{m.group(1)}]", normalized)
    normalized = strip_ai_label_phrases(normalized)
    normalized = expand_compact_markdown_lists(normalized)
    normalized = _REFERENCE_CALLOUT_RE.sub("", normalized)
    normalized = re.sub(r"\s\|\s\|", " |\n| ", normalized)
    intro_blocks, sections = legacy.split_sections(normalized)
    filtered_sections = [section for section in sections if not legacy.is_reference_heading(section.get("heading", ""))]
    rebuilt = legacy.reconstruct_body(intro_blocks, filtered_sections).strip()
    return (rebuilt + "\n") if rebuilt else ""


def build_references_payload(workspace: Path, manifest: dict[str, Any], body: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    existing_payload = read_json(workspace / "references.json", default={}) or {}
    for entry in (existing_payload.get("items") or []):
        url = str(entry.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "url": url,
                "title": str(entry.get("title") or _reference_label(url)).strip(),
                "domain": str(entry.get("domain") or _reference_domain(url)).strip(),
                "note": str(entry.get("note") or "").strip(),
                "source_type": str(entry.get("source_type") or "existing").strip(),
            }
        )
    evidence_report = read_json(workspace / "evidence-report.json", default={}) or {}
    for entry in (evidence_report.get("items") or []):
        url = str(entry.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "url": url,
                "title": str(entry.get("page_title") or entry.get("title") or _reference_label(url)).strip(),
                "domain": _reference_domain(url),
                "note": extract_summary(str(entry.get("sentence") or entry.get("description") or ""), 72),
                "source_type": "evidence",
            }
        )
    research = read_json(workspace / "research.json", default={}) or {}
    for entry in (research.get("sources") or []):
        if isinstance(entry, dict):
            url = str(entry.get("url") or entry.get("link") or "").strip()
            title = str(entry.get("title") or entry.get("name") or "").strip()
        else:
            url = str(entry or "").strip()
            title = ""
        if not url or url in seen:
            continue
        seen.add(url)
        items.append({"url": url, "title": title or _reference_label(url), "domain": _reference_domain(url), "note": "", "source_type": "research"})
    for url in normalize_urls(list(manifest.get("source_urls") or []) + _extract_body_urls(body)):
        if not url or url in seen:
            continue
        seen.add(url)
        items.append({"url": url, "title": _reference_label(url), "domain": _reference_domain(url), "note": "", "source_type": "manifest"})
    payload = {"items": [{**item, "index": index} for index, item in enumerate(items, start=1)], "generated_at": now_iso()}
    write_json(workspace / "references.json", payload)
    manifest["references_path"] = "references.json"
    return payload


def apply_reference_policy(workspace: Path, manifest: dict[str, Any], title: str, body: str, *, keep_inline_citations: bool = True) -> tuple[str, dict[str, Any]]:
    payload = build_references_payload(workspace, manifest, body)
    items = payload.get("items") or []
    title_map = {item["url"]: item["title"] for item in items}

    def replace_markdown_link(match: re.Match[str]) -> str:
        label = match.group(1).strip()
        url = match.group(2).strip()
        return label or title_map.get(url, _reference_label(url))

    normalized_body = re.sub(r"\[([^\]]+)]\((https?://[^)]+)\)", replace_markdown_link, body)

    def replace_raw_url(match: re.Match[str]) -> str:
        url = match.group(0).strip()
        return title_map.get(url, _reference_label(url))

    normalized_body = re.sub(r"https?://[^\s)>\]]+", replace_raw_url, normalized_body)
    if not keep_inline_citations:
        normalized_body = _INLINE_CITATION_RE.sub("", normalized_body)
        normalized_body = _BOXED_CITATION_RE.sub("", normalized_body)
    normalized_body = re.sub(r"[ \t]{2,}", " ", normalized_body)
    findings = {
        "raw_urls_before": len(_extract_body_urls(body)),
        "raw_urls_after": len(_extract_body_urls(normalized_body)),
        "body_citation_count": len(re.findall(r"\[(\d+)]", normalized_body)),
        "reference_count": len(items),
        "citation_policy_passed": len(_extract_body_urls(normalized_body)) == 0,
    }
    return normalized_body, findings


def _split_markdown_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    in_code = False
    for line in (text or "").splitlines():
        stripped = line.strip()
        if _CODE_FENCE_RE.match(stripped):
            current.append(line)
            in_code = not in_code
            continue
        if in_code:
            current.append(line)
            continue
        if not stripped:
            if current:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return blocks


def _guess_article_archetype(manifest: dict[str, Any], title: str, body: str) -> str:
    existing = str((manifest.get("viral_blueprint") or {}).get("article_archetype") or manifest.get("article_archetype") or "").strip().lower()
    if existing:
        return existing
    corpus = "\n".join([title, str(manifest.get("summary") or ""), body])
    if re.search(r"教程|指南|步骤|如何|怎么做|SOP|模板|上手|实操", corpus):
        return "tutorial"
    if re.search(r"案例|复盘|拆解|项目|公司|团队", corpus):
        return "case-study"
    if re.search(r"现场|对话|故事|经历|我在|那天", corpus):
        return "narrative"
    return "commentary"


def _inline_image_limit(workspace: Path, manifest: dict[str, Any], body: str, archetype: str) -> int:
    image_plan_rel = str(manifest.get("image_plan_path") or "image-plan.json").strip()
    if image_plan_rel:
        image_plan = read_json(workspace / image_plan_rel, default={}) or {}
        if image_plan:
            return int(image_plan.get("planned_inline_count") or image_plan.get("requested_inline_count") or 0)
    controls = dict(manifest.get("image_controls") or {})
    density_mode = legacy.normalize_image_density_mode(
        controls.get("density_mode")
        or manifest.get("image_density_mode")
        or controls.get("density")
        or ""
    )
    explicit_count = int(controls.get("inline_count") or manifest.get("image_inline_target") or 0)
    if density_mode in {"auto", "none", "minimal", "balanced", "dense", "custom"}:
        return int(legacy.estimate_inline_image_count(body, explicit_count, density_mode))
    return 3 if archetype == "tutorial" else 2


def _looks_like_standalone_image_block(block: str) -> bool:
    body = block.strip()
    if not body:
        return False
    cleaned = _MARKDOWN_IMAGE_RE.sub("", body)
    cleaned = _RAW_HTML_IMAGE_RE.sub("", cleaned)
    return not cleaned.strip()


def _trim_existing_image_blocks(blocks: list[str], *, limit: int) -> tuple[list[str], int, int]:
    output: list[str] = []
    kept = 0
    removed = 0
    for block in blocks:
        if _looks_like_standalone_image_block(block):
            if kept < limit:
                output.append(block)
                kept += 1
            else:
                removed += 1
            continue
        output.append(block)
    return output, kept, removed


def _extract_compare_rows(block: str) -> list[list[str]] | None:
    plain = re.sub(r"\s+", " ", block.strip())
    for pattern in _COMPARE_PATTERNS:
        match = pattern.match(plain)
        if not match:
            continue
        groups = match.groupdict()
        if "surface" in groups:
            left = groups.get("surface", "").strip("，,；;。 ")
            right = groups.get("right", "").strip("，,；;。 ")
            if left and right:
                return [["表面上看", "真正要看"], [left, right]]
        left = groups.get("left", "").strip("，,；;。 ")
        right = groups.get("right", "").strip("，,；;。 ")
        if left and right:
            return [["容易误判", "真正问题"], [left, right]]
    return None


def _metric_label(value: str, prefix: str) -> str:
    text = prefix.strip("，,；;。:： ")
    if "准确率" in text:
        return "回答准确率" if "回答" in text else "准确率"
    if "提升" in text:
        return "提升幅度"
    if "增长" in text:
        return "增长幅度"
    if "下降" in text:
        return "下降幅度"
    if "成本" in text:
        return "成本变化"
    if "租赁费" in text:
        return "租赁费变化"
    text = re.sub(r".{0,6}(达到|提升|增长|下降|接近|约|近|超|超过|为)$", "", text)
    text = re.sub(r"^(其中|比如|例如|还有|以及|并且|并|接入后|接入后的|当前|整体|近半年|去年|今年|本周|比原生记忆|比原生|原生记忆|原生)", "", text)
    text = text.strip("，,；;。 ")
    if len(text) > 8:
        text = text[-8:]
    return text or "关键指标"


def _extract_stats(block: str) -> list[tuple[str, str]]:
    plain = re.sub(r"\s+", " ", block.strip())
    if len(plain) > 90:
        return []
    if re.search(r"[。！？!?]", plain) and len(plain) > 45:
        return []
    if any(word in plain for word in ["会议室", "老板", "员工", "客户", "团队", "公司", "这意味着", "问题在于"]):
        return []
    results: list[tuple[str, str]] = []
    for match in _METRIC_VALUE_RE.finditer(plain):
        value = match.group(1).strip()
        prefix = plain[max(0, match.start() - 18) : match.start()]
        label = _metric_label(value, prefix)
        if not label:
            continue
        entry = (label, value)
        if entry not in results:
            results.append(entry)
    return results[:4]


def _looks_like_unfenced_code(block: str) -> tuple[str, str] | None:
    lines = [line.rstrip() for line in block.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    code_like = 0
    for line in lines:
        stripped = line.strip()
        if _TECH_COMMAND_RE.match(stripped) or _JSISH_RE.match(stripped) or stripped.endswith(";") or " = " in stripped or "=>" in stripped or stripped.startswith("{") or stripped.startswith("}"):
            code_like += 1
    if code_like < max(2, len(lines) - 1):
        return None
    lang = "bash" if any(_TECH_COMMAND_RE.match(line.strip()) for line in lines) else "javascript" if any("=>" in line or line.strip().endswith(";") for line in lines) else ""
    return lang, "\n".join(lines)


def _rewrite_blocks(blocks: list[str]) -> tuple[list[str], dict[str, Any]]:
    output: list[str] = []
    compare_count = 0
    stats_count = 0
    code_count = 0
    for block in blocks:
        if not block.strip():
            continue
        first_line = block.splitlines()[0].strip()
        if _HEADING_LINE_RE.match(first_line) or _LIST_LINE_RE.match(first_line) or _TABLE_LINE_RE.match(first_line) or _BLOCKQUOTE_LINE_RE.match(first_line) or _CODE_FENCE_RE.match(first_line) or _looks_like_standalone_image_block(block):
            output.append(block)
            continue
        compare_rows = _extract_compare_rows(block)
        if compare_rows:
            header, row = compare_rows
            output.append("\n".join([f"| {header[0]} | {header[1]} |", "| --- | --- |", f"| {row[0]} | {row[1]} |"]))
            compare_count += 1
            continue
        stats = _extract_stats(block)
        if len(stats) >= 2:
            output.extend([f"- {label}：{value}" for label, value in stats])
            stats_count += 1
            continue
        code = _looks_like_unfenced_code(block)
        if code:
            lang, content = code
            output.append("\n".join([f"```{lang}".rstrip(), content, "```"]))
            code_count += 1
            continue
        output.append(block)
    return output, {"compare_block_count": compare_count, "stats_block_count": stats_count, "code_block_count": code_count}


def _collect_technical_terms(title: str, summary: str, body: str) -> list[str]:
    corpus = "\n".join([title or "", summary or "", body or ""])
    terms: list[str] = []
    for pattern in (_GENERIC_PRODUCT_RE, _VERSION_PHRASE_RE, _PATH_TERM_RE):
        for match in pattern.finditer(corpus):
            value = match.group(0).strip()
            if len(value) < 3 or len(value) > 48:
                continue
            if re.fullmatch(r"[A-Za-z]+", value) and value.lower() not in {"api", "sdk", "cli", "mcp"}:
                continue
            if value not in terms:
                terms.append(value)
    return terms[:28]


def _suggest_wechat_style(archetype: str, body: str, terms: list[str], manifest: dict[str, Any]) -> str:
    audience = str(manifest.get("audience") or "")
    if archetype == "tutorial" or "```" in body or any(term.startswith("--") or "/" in term for term in terms):
        return "tech"
    if archetype == "narrative":
        return "warm"
    if archetype in {"case-study", "comparison"} or any(word in audience for word in ["企业", "商业", "老板", "管理", "运营", "银行", "金融"]):
        return "business"
    return "clean"


def prepare_publication_artifacts(workspace: Path, manifest: dict[str, Any], *, input_rel: str | None = None) -> dict[str, Any]:
    source_rel = input_rel or str(manifest.get("article_path") or "article.md")
    source_path = workspace / source_rel
    if not source_path.exists():
        raise SystemExit(f"找不到待整理正文：{source_path}")
    raw = read_text(source_path)
    meta, body = split_frontmatter(raw)
    title = str(manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名文章").strip()
    summary = str(meta.get("summary") or manifest.get("summary") or build_article_summary(title, body)).strip()
    body = strip_leading_h1(body, title)
    body = normalize_publication_body(title, body)
    body, citation_findings = apply_reference_policy(workspace, manifest, title, body, keep_inline_citations=True)
    archetype = _guess_article_archetype(manifest, title, body)
    inline_limit = _inline_image_limit(workspace, manifest, body, archetype)
    blocks = _split_markdown_blocks(body)
    blocks, kept_images, removed_images = _trim_existing_image_blocks(blocks, limit=inline_limit)
    blocks, rewrite_findings = _rewrite_blocks(blocks)
    publication_body = "\n\n".join(block.strip() for block in blocks if block.strip())
    publication_body = publication_body.strip() + ("\n" if publication_body.strip() else "")
    if not metadata_integrity_report(title, summary).get("summary_passed"):
        summary = build_article_summary(title, publication_body)
    technical_terms = _collect_technical_terms(title, summary, publication_body)
    wechat_style = _suggest_wechat_style(archetype, publication_body, technical_terms, manifest)
    pre_h2_count = lead_paragraph_count(publication_body)
    h2_count = len(re.findall(r"(?m)^\s*##\s+", publication_body))
    h3_count = len(re.findall(r"(?m)^\s*###\s+", publication_body))
    payload = {
        "source_path": source_rel,
        "output_path": "publication.md",
        "title": title,
        "summary": summary,
        "article_archetype": archetype,
        "inline_image_limit": inline_limit,
        "kept_existing_image_blocks": kept_images,
        "removed_existing_image_blocks": removed_images,
        "technical_terms": technical_terms,
        "reference_count": citation_findings.get("reference_count", 0),
        "citation_count": citation_findings.get("body_citation_count", 0),
        "suggested_wechat_style": wechat_style,
        "lead_paragraph_count": pre_h2_count,
        "h2_count": h2_count,
        "h3_count": h3_count,
        "summary_length": len(re.sub(r"\s+", "", summary)),
        **rewrite_findings,
        "generated_at": now_iso(),
    }
    write_text(workspace / "publication.md", join_frontmatter({"title": title, "summary": summary}, publication_body))
    write_json(workspace / "publication-report.json", payload)
    manifest["publication_path"] = "publication.md"
    manifest["publication_report_path"] = "publication-report.json"
    manifest["publication_style"] = wechat_style
    manifest["publication_source_path"] = source_rel
    return payload
