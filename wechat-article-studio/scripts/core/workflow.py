from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from core.artifacts import (
    ensure_text_report,
    extract_summary,
    join_frontmatter,
    now_iso,
    read_input_file,
    read_json,
    read_text,
    split_frontmatter,
    strip_leading_h1,
    write_json,
    write_text,
)
from core.images import cmd_assemble as legacy_assemble
from core.images import cmd_generate_images as legacy_generate_images
from core.images import cmd_plan_images as legacy_plan_images
from core.manifest import ensure_workspace, load_manifest, save_manifest, update_stage, workspace_path
from core.render import cmd_render as legacy_render
from core.rewrite import generate_revision_candidate
from providers.text.gemini_web import GeminiWebTextProvider
from providers.text.openai_compatible import OpenAICompatibleTextProvider, placeholder_article, placeholder_outline
from publishers.wechat import cmd_publish as wechat_publish
from publishers.wechat import cmd_verify_draft as wechat_verify_draft


def active_text_provider():
    provider_name = (legacy.os.getenv("ARTICLE_STUDIO_TEXT_PROVIDER") or "openai-compatible").strip().lower()
    if provider_name in {"gemini-web", "gemini_web"}:
        return GeminiWebTextProvider()
    if provider_name not in {"openai-compatible", "openai_compatible", ""}:
        raise SystemExit(f"暂不支持的文本 provider：{provider_name}")
    return OpenAICompatibleTextProvider()


def normalize_urls(values: list[str]) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for raw in values:
        value = (raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        urls.append(value)
    return urls


def load_research(workspace: Path) -> dict[str, Any]:
    return read_json(workspace / "research.json", default={}) or {}


def load_ideation(workspace: Path) -> dict[str, Any]:
    return read_json(workspace / "ideation.json", default={}) or {}


def normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        candidates = []
        for line in raw.splitlines():
            cleaned = line.strip()
            cleaned = cleaned.lstrip("-*").strip()
            cleaned = cleaned.removeprefix("•").strip()
            if cleaned:
                candidates.append(cleaned)
        if len(candidates) <= 1:
            parts = [part.strip() for part in raw.split("。") if part.strip()]
            if len(parts) > 1:
                candidates = [part if part.endswith("。") else f"{part}。" for part in parts]
        normalized = []
        for item in candidates:
            item = item.strip()
            item = item[2:].strip() if len(item) > 2 and item[0].isdigit() and item[1] in {".", "、"} else item
            if item:
                normalized.append(item)
        return normalized
    return []


def looks_like_issue(text: str) -> bool:
    markers = ["不足", "偏弱", "问题", "缺少", "需要", "建议补", "可再", "不够", "避免", "警惕", "修正"]
    value = (text or "").strip()
    return any(marker in value for marker in markers)


def split_review_points(value: Any) -> tuple[list[str], list[str]]:
    raw_items = normalize_string_list(value)
    strengths: list[str] = []
    issues: list[str] = []
    for item in raw_items:
        if looks_like_issue(item):
            issues.append(item)
        else:
            strengths.append(item)
    return strengths, issues


def apply_research_credibility_boost(report: dict[str, Any], research: dict[str, Any]) -> dict[str, Any]:
    sources = normalize_string_list(research.get("sources"))
    evidence_items = normalize_string_list(research.get("evidence_items"))
    if not report or (not sources and not evidence_items):
        return report
    boosted = json.loads(json.dumps(report, ensure_ascii=False))
    target = None
    for item in boosted.get("score_breakdown", []):
        if item.get("dimension") == "可信度与检索支撑":
            target = item
            break
    if target is None:
        return boosted
    bonus = min(8, max(target.get("score", 0), min(4, len(sources)) + min(4, len(evidence_items))))
    target["score"] = bonus
    boosted["total_score"] = sum(item.get("score", 0) for item in boosted.get("score_breakdown", []))
    boosted["passed"] = boosted["total_score"] >= boosted.get("threshold", legacy.DEFAULT_THRESHOLD)
    weaknesses = normalize_string_list(boosted.get("weaknesses"))
    if bonus >= 4:
        weaknesses = [item for item in weaknesses if not item.startswith("可信度与检索支撑")]
    boosted["weaknesses"] = weaknesses
    return boosted


def cmd_research(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    provider = active_text_provider()
    source_urls = normalize_urls(args.source_url or manifest.get("source_urls") or [])
    topic = args.topic or manifest.get("topic") or "未命名主题"
    audience = args.audience or manifest.get("audience") or "大众读者"
    angle = args.angle or manifest.get("direction") or ""
    result = provider.generate_research_pack(
        {
            "topic": topic,
            "angle": angle,
            "audience": audience,
            "source_urls": source_urls,
        }
    )
    payload = dict(result.payload)
    payload.setdefault("topic", topic)
    payload.setdefault("angle", angle)
    payload.setdefault("audience", audience)
    payload["provider"] = result.provider
    payload["model"] = result.model
    payload["generated_at"] = now_iso()
    write_json(workspace / "research.json", payload)
    manifest.update(
        {
            "topic": topic,
            "direction": angle,
            "audience": audience,
            "source_urls": source_urls,
            "research_path": "research.json",
            "text_provider": result.provider,
            "text_model": result.model,
        }
    )
    update_stage(manifest, "research", "research_status")
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_titles(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    provider = active_text_provider()
    research = load_research(workspace)
    topic = manifest.get("topic") or research.get("topic") or "未命名主题"
    audience = manifest.get("audience") or research.get("audience") or "大众读者"
    count = args.count or 3
    result = provider.generate_titles(
        {
            "topic": topic,
            "audience": audience,
            "angle": manifest.get("direction") or research.get("angle") or "",
            "count": count,
            "research": research,
        }
    )
    ideation = load_ideation(workspace)
    titles = result.payload[:count] if isinstance(result.payload, list) else result.payload.get("titles", [])
    ideation.update(
        {
            "topic": topic,
            "direction": manifest.get("direction") or research.get("angle") or "",
            "titles": titles,
            "selected_title": args.selected_title or ideation.get("selected_title") or (titles[0]["title"] if titles else ""),
            "updated_at": now_iso(),
            "provider": result.provider,
            "model": result.model,
        }
    )
    write_json(workspace / "ideation.json", ideation)
    manifest["selected_title"] = ideation.get("selected_title") or manifest.get("selected_title", "")
    manifest["ideation_path"] = "ideation.json"
    update_stage(manifest, "titles", "title_status")
    save_manifest(workspace, manifest)
    print(json.dumps(ideation, ensure_ascii=False, indent=2))
    return 0


def cmd_outline(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    provider = active_text_provider()
    research = load_research(workspace)
    ideation = load_ideation(workspace)
    selected_title = args.title or manifest.get("selected_title") or ideation.get("selected_title") or manifest.get("topic") or "未命名标题"
    result = provider.generate_outline(
        {
            "topic": manifest.get("topic") or research.get("topic") or "",
            "selected_title": selected_title,
            "audience": manifest.get("audience") or research.get("audience") or "大众读者",
            "direction": manifest.get("direction") or research.get("angle") or "",
            "research": research,
            "titles": ideation.get("titles") or [],
        }
    )
    outline = dict(result.payload)
    outline.setdefault("title", selected_title)
    ideation["selected_title"] = selected_title
    ideation["outline"] = outline.get("sections") or []
    ideation["outline_meta"] = outline
    ideation["updated_at"] = now_iso()
    write_json(workspace / "ideation.json", ideation)
    manifest["selected_title"] = selected_title
    manifest["outline"] = [item.get("heading", "") for item in outline.get("sections") or []]
    update_stage(manifest, "outline", "outline_status")
    save_manifest(workspace, manifest)
    print(json.dumps(outline, ensure_ascii=False, indent=2))
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    provider = active_text_provider()
    research = load_research(workspace)
    ideation = load_ideation(workspace)
    outline_meta = dict(ideation.get("outline_meta") or {})
    if args.outline_file:
        outline_lines = [line.strip("- ").strip() for line in read_input_file(args.outline_file).splitlines() if line.strip()]
        outline_meta["sections"] = [{"heading": line, "goal": "展开该章节", "evidence_need": "按需补证据"} for line in outline_lines]
    selected_title = args.title or manifest.get("selected_title") or ideation.get("selected_title") or manifest.get("topic") or "未命名标题"
    result = provider.generate_article(
        {
            "topic": manifest.get("topic") or research.get("topic") or selected_title,
            "title": selected_title,
            "selected_title": selected_title,
            "audience": manifest.get("audience") or research.get("audience") or "大众读者",
            "direction": manifest.get("direction") or research.get("angle") or "",
            "research": research,
            "outline": outline_meta or {"sections": ideation.get("outline") or []},
        }
    )
    body = str(result.payload).strip()
    body = strip_leading_h1(body, selected_title)
    summary = extract_summary(body)
    article_path = workspace / "article.md"
    write_text(article_path, join_frontmatter({"title": selected_title, "summary": summary}, body))
    manifest.update(
        {
            "selected_title": selected_title,
            "summary": summary,
            "article_path": "article.md",
            "outline": [item.get("heading", "") for item in (outline_meta.get("sections") or [])],
            "text_provider": result.provider,
            "text_model": result.model,
        }
    )
    update_stage(manifest, "draft", "draft_status")
    save_manifest(workspace, manifest)
    print(str(article_path))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    provider = active_text_provider()
    article_path = workspace / (manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到待评审文章：{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
    body = legacy.strip_image_directives(body)
    title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名标题"
    result = provider.review_article(
        {
            "title": title,
            "audience": manifest.get("audience") or "大众读者",
            "direction": manifest.get("direction") or "",
            "summary": meta.get("summary") or manifest.get("summary") or extract_summary(body),
            "article_body": body,
        }
    )
    payload = dict(result.payload)
    strengths, issues = split_review_points(payload.get("findings"))
    payload["findings"] = strengths + issues
    payload["strengths"] = strengths
    payload["issues"] = issues
    payload["platform_notes"] = normalize_string_list(payload.get("platform_notes"))
    payload["title"] = title
    payload["provider"] = result.provider
    payload["model"] = result.model
    payload["generated_at"] = now_iso()
    write_json(workspace / "review-report.json", payload)
    lines = [payload.get("summary", "")]
    lines.extend(f"亮点：{item}" for item in payload.get("strengths", []))
    lines.extend(f"问题：{item}" for item in payload.get("issues", []))
    lines.extend(f"平台建议：{item}" for item in payload.get("platform_notes", []))
    ensure_text_report(workspace / "review-report.md", "编辑评审报告", lines)
    manifest["review_report_path"] = "review-report.json"
    update_stage(manifest, "review", "review_status")
    save_manifest(workspace, manifest)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_review_from_score(title: str, report: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    total = int(report.get("total_score") or 0)
    threshold = int(report.get("threshold") or legacy.DEFAULT_THRESHOLD)
    delta = total - threshold
    if delta >= 0:
        summary = f"《{title}》当前版本已达到发布阈值（{total}/{threshold}），可以进入配图与排版阶段。"
    else:
        summary = f"《{title}》当前版本暂未达到发布阈值（{total}/{threshold}），建议先按问题清单补强后再出图排版。"
    strengths = normalize_string_list(report.get("strengths"))[:4]
    issues = normalize_string_list(report.get("weaknesses"))[:4]
    mandatory = normalize_string_list(report.get("mandatory_revisions"))
    for item in mandatory:
        if item not in issues:
            issues.append(item)
    platform_notes = [
        "微信公众号优先短段落、小标题和重点句，避免连续大段文字。",
        "事实型内容在发布前应自行核验关键表述，但最终正文不自动附加来源区。",
    ]
    if manifest.get("score_passed"):
        platform_notes.append("当前稿件已过线，进入出图前可再检查封面标题和摘要是否适合转发。")
    return {
        "summary": summary,
        "findings": strengths + issues,
        "strengths": strengths,
        "issues": issues,
        "platform_notes": platform_notes,
        "title": title,
        "provider": "host-agent",
        "model": "session",
        "generated_at": now_iso(),
        "hosted": True,
    }


def write_review_report(workspace: Path, manifest: dict[str, Any], payload: dict[str, Any]) -> None:
    write_json(workspace / "review-report.json", payload)
    lines = [payload.get("summary", "")]
    lines.extend(f"亮点：{item}" for item in payload.get("strengths", []))
    lines.extend(f"问题：{item}" for item in payload.get("issues", []))
    lines.extend(f"平台建议：{item}" for item in payload.get("platform_notes", []))
    ensure_text_report(workspace / "review-report.md", "编辑评审报告", lines)
    manifest["review_report_path"] = "review-report.json"
    update_stage(manifest, "review", "review_status")


def _mark_publish_intent(workspace: Path) -> None:
    manifest = load_manifest(workspace)
    if manifest.get("publish_intent"):
        return
    manifest["publish_intent"] = True
    save_manifest(workspace, manifest)


def _maybe_promote_rewrite(manifest: dict[str, Any], rewrite: dict[str, Any]) -> None:
    output_path = str(rewrite.get("output_path") or "").strip()
    if not output_path:
        return
    current_path = str(manifest.get("article_path") or "article.md")
    if current_path != output_path:
        manifest["draft_source_path"] = current_path
    manifest["article_path"] = output_path
    manifest["active_article_variant"] = "rewrite"


def cmd_revise(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    article_path = workspace / (manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到待改写文章：{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
    body = legacy.strip_image_directives(body)
    title = manifest.get("selected_title") or meta.get("title") or manifest.get("topic") or "未命名标题"
    report = read_json(workspace / "score-report.json", default={}) or {}
    if not report:
        threshold = manifest.get("score_threshold") or legacy.DEFAULT_THRESHOLD
        report = legacy.build_score_report(title, body, manifest, threshold)
    report = apply_research_credibility_boost(report, load_research(workspace))
    write_json(workspace / "score-report.json", report)
    legacy.write_text(workspace / "score-report.md", legacy.markdown_report(report))
    manifest["score_report_path"] = "score-report.json"
    manifest["score_total"] = report["total_score"]
    manifest["score_passed"] = report["passed"]
    rewrite = generate_revision_candidate(workspace, title, meta, body, report, manifest)
    manifest["rewrite_path"] = rewrite["output_path"]
    manifest["rewrite_preview_score"] = rewrite.get("preview_score")
    manifest["rewrite_preview_passed"] = rewrite.get("preview_passed")
    if getattr(args, "promote", False):
        _maybe_promote_rewrite(manifest, rewrite)
    update_stage(manifest, "revise", "draft_status")
    save_manifest(workspace, manifest)
    print(json.dumps(rewrite, ensure_ascii=False, indent=2))
    return 0


def cmd_ideate(args: argparse.Namespace) -> int:
    return legacy.cmd_ideate(args)


def cmd_draft(args: argparse.Namespace) -> int:
    return legacy.cmd_draft(args)


def cmd_publish(args: argparse.Namespace) -> int:
    return wechat_publish(args)


def cmd_verify_draft(args: argparse.Namespace) -> int:
    return wechat_verify_draft(args)


def cmd_doctor(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve() if args.workspace else Path.cwd().resolve()
    provider = active_text_provider()
    report = {
        "python": {"version": legacy.sys.version.split()[0], "ok": legacy.sys.version_info >= (3, 10)},
        "workspace": {
            "path": str(workspace),
            "exists": workspace.exists(),
            "writable": legacy.can_write_directory(workspace if workspace.exists() else workspace.parent),
        },
        "text_provider": {
            "default_mode": "hosted-agent",
            "hosted_agent_ready": True,
            "api_provider": provider.provider_name,
            "api_configured": provider.configured(),
            "model": getattr(provider, "model", ""),
            "required_env": [] if not provider.configured() else ["ARTICLE_STUDIO_TEXT_MODEL", "OPENAI_API_KEY"],
            "notes": [
                "在 Codex / ClaudeCode / OpenClaw 中默认不要求文本环境变量，由宿主 agent 负责文本生成。",
                "只有脱离宿主、单独运行 run 子命令时，才需要配置文本 API。",
            ],
        },
        "image_providers": {
            "gemini-api": legacy.doctor_provider_status("gemini-api"),
            "openai-image": legacy.doctor_provider_status("openai-image"),
            "gemini-web": legacy.doctor_provider_status("gemini-web"),
        },
        "wechat": {
            "has_app_id": bool(legacy.os.getenv("WECHAT_APP_ID")),
            "has_app_secret": bool(legacy.os.getenv("WECHAT_APP_SECRET")),
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def cmd_consent(args: argparse.Namespace) -> int:
    return legacy.cmd_consent(args)


def _run_score(workspace: str) -> dict[str, Any]:
    cmd_score(
        argparse.Namespace(
            workspace=workspace,
            input=None,
            threshold=None,
            fail_below=False,
            no_rewrite=False,
            rewrite_output=None,
        )
    )
    return read_json(Path(workspace) / "score-report.json", default={}) or {}


def _effective_image_provider(args: argparse.Namespace) -> str | None:
    explicit = getattr(args, "image_provider", None)
    if explicit:
        return explicit
    if getattr(args, "dry_run_images", False):
        return "openai-image"
    return None


def _sync_image_controls(workspace: Path, args: argparse.Namespace) -> None:
    manifest = load_manifest(workspace)
    manifest["image_controls"] = legacy.resolve_image_controls(manifest.get("image_controls"), args)
    save_manifest(workspace, manifest)


def _write_hosted_research(workspace: Path, manifest: dict[str, Any], topic: str, angle: str, audience: str, source_urls: list[str]) -> None:
    payload = {
        "topic": topic,
        "angle": angle,
        "audience": audience,
        "sources": source_urls,
        "evidence_items": [],
        "information_gaps": ["正文由宿主 agent 直接生成；如含事实断言，请在发布前补充来源与证据。"],
        "forbidden_claims": ["不要把未验证信息写成确定事实。"],
        "provider": "host-agent",
        "model": "session",
        "generated_at": now_iso(),
        "hosted": True,
    }
    write_json(workspace / "research.json", payload)
    manifest.update(
        {
            "topic": topic,
            "direction": angle,
            "audience": audience,
            "source_urls": source_urls,
            "research_path": "research.json",
            "text_provider": "host-agent",
            "text_model": "session",
        }
    )
    update_stage(manifest, "research", "research_status")


def _write_hosted_ideation(workspace: Path, manifest: dict[str, Any], title: str, outline_file: str | None) -> None:
    ideation = load_ideation(workspace)
    ideation["topic"] = manifest.get("topic") or title
    ideation["direction"] = manifest.get("direction") or ""
    ideation["selected_title"] = title
    ideation["updated_at"] = now_iso()
    ideation["provider"] = "host-agent"
    ideation["model"] = "session"
    if not ideation.get("titles"):
        ideation["titles"] = [
            {
                "title": title,
                "strategy": "宿主 agent 直出",
                "audience_fit": manifest.get("audience") or "大众读者",
                "risk_note": "",
            }
        ]
    outline_items: list[str] = []
    if outline_file:
        outline_items = [line.strip("- ").strip() for line in read_input_file(outline_file).splitlines() if line.strip()]
    elif ideation.get("outline"):
        outline_items = [str(item).strip() for item in ideation.get("outline") if str(item).strip()]
    if outline_items:
        ideation["outline"] = outline_items
        ideation["outline_meta"] = {
            "title": title,
            "angle": manifest.get("direction") or "",
            "sections": [{"heading": item, "goal": "宿主 agent 已生成正文", "evidence_need": "按需补充"} for item in outline_items],
        }
    write_json(workspace / "ideation.json", ideation)
    manifest["selected_title"] = title
    if outline_items:
        manifest["outline"] = outline_items
        update_stage(manifest, "outline", "outline_status")
    update_stage(manifest, "titles", "title_status")


def _bootstrap_hosted_article(workspace: Path, manifest: dict[str, Any], topic: str, title: str, angle: str, audience: str) -> str:
    provider = active_text_provider()
    source_urls = normalize_urls(manifest.get("source_urls") or [])
    research = load_research(workspace)
    if not research:
        result = provider.generate_research_pack(
            {
                "topic": topic,
                "angle": angle,
                "audience": audience,
                "source_urls": source_urls,
            }
        )
        payload = dict(result.payload)
        payload.setdefault("topic", topic)
        payload.setdefault("angle", angle)
        payload.setdefault("audience", audience)
        payload["provider"] = result.provider
        payload["model"] = result.model
        payload["generated_at"] = now_iso()
        write_json(workspace / "research.json", payload)
        manifest["research_path"] = "research.json"
        manifest["text_provider"] = result.provider
        manifest["text_model"] = result.model
        update_stage(manifest, "research", "research_status")
        research = payload

    ideation = load_ideation(workspace)
    if not ideation.get("titles"):
        title_result = provider.generate_titles(
            {
                "topic": topic,
                "audience": audience,
                "angle": angle,
                "count": 3,
                "research": research,
            }
        )
        titles = title_result.payload[:3] if isinstance(title_result.payload, list) else title_result.payload.get("titles", [])
        ideation.update(
            {
                "topic": topic,
                "direction": angle,
                "titles": titles,
                "selected_title": title or (titles[0]["title"] if titles else topic),
                "updated_at": now_iso(),
                "provider": title_result.provider,
                "model": title_result.model,
            }
        )
        write_json(workspace / "ideation.json", ideation)
        manifest["selected_title"] = ideation.get("selected_title") or title
        update_stage(manifest, "titles", "title_status")
    title = title or ideation.get("selected_title") or manifest.get("selected_title") or topic

    outline_meta = dict(ideation.get("outline_meta") or {})
    if not outline_meta.get("sections"):
        outline_result = provider.generate_outline(
            {
                "topic": topic,
                "selected_title": title,
                "audience": audience,
                "direction": angle,
                "research": research,
                "titles": ideation.get("titles") or [],
            }
        )
        outline_meta = dict(outline_result.payload)
        if not outline_meta.get("sections"):
            outline_meta = placeholder_outline(title)
        ideation["selected_title"] = title
        ideation["outline"] = outline_meta.get("sections") or []
        ideation["outline_meta"] = outline_meta
        ideation["updated_at"] = now_iso()
        ideation["provider"] = outline_result.provider
        ideation["model"] = outline_result.model
        write_json(workspace / "ideation.json", ideation)
        manifest["outline"] = [item.get("heading", "") for item in outline_meta.get("sections") or []]
        update_stage(manifest, "outline", "outline_status")

    article_result = provider.generate_article(
        {
            "topic": topic,
            "title": title,
            "selected_title": title,
            "audience": audience,
            "direction": angle,
            "research": research,
            "outline": outline_meta or {"sections": ideation.get("outline") or []},
        }
    )
    body = str(article_result.payload).strip()
    if not body:
        body = placeholder_article(title, outline_meta or placeholder_outline(title), audience)
    body = strip_leading_h1(body, title)
    summary = extract_summary(body)
    write_text(workspace / "article.md", join_frontmatter({"title": title, "summary": summary}, body))
    manifest.update(
        {
            "selected_title": title,
            "summary": summary,
            "article_path": "article.md",
            "text_provider": article_result.provider,
            "text_model": article_result.model,
        }
    )
    update_stage(manifest, "draft", "draft_status")
    return title


def _import_hosted_article(
    workspace: Path,
    manifest: dict[str, Any],
    article_file: str | None,
    title_hint: str | None,
    summary_hint: str | None,
    angle: str,
    audience: str,
) -> str:
    article_path = workspace / "article.md"
    if article_file:
        raw = read_input_file(article_file)
        meta, body = split_frontmatter(raw)
        title = title_hint or meta.get("title") or manifest.get("selected_title") or manifest.get("topic") or "未命名标题"
        body = strip_leading_h1(body, title)
        summary = summary_hint or meta.get("summary") or extract_summary(body)
        write_text(article_path, join_frontmatter({"title": title, "summary": summary}, body))
    elif not article_path.exists():
        title = title_hint or manifest.get("selected_title") or manifest.get("topic") or "未命名标题"
        return _bootstrap_hosted_article(workspace, manifest, manifest.get("topic") or title, title, angle, audience)
    meta, body = split_frontmatter(read_text(article_path))
    title = title_hint or meta.get("title") or manifest.get("selected_title") or manifest.get("topic") or "未命名标题"
    summary = summary_hint or meta.get("summary") or extract_summary(body)
    write_text(article_path, join_frontmatter({"title": title, "summary": summary}, strip_leading_h1(body, title)))
    manifest.update(
        {
            "selected_title": title,
            "summary": summary,
            "article_path": "article.md",
            "text_provider": "host-agent",
            "text_model": "session",
        }
    )
    update_stage(manifest, "draft", "draft_status")
    return title


def _finalize_after_score(workspace: Path, manifest: dict[str, Any], title: str, score_report: dict[str, Any]) -> dict[str, Any]:
    manifest["score_status"] = "done"
    manifest["score_report_path"] = "score-report.json"
    manifest["score_total"] = score_report.get("total_score")
    manifest["score_passed"] = score_report.get("passed")
    manifest["stage"] = "score"
    review_payload = build_review_from_score(title, score_report, manifest)
    write_review_report(workspace, manifest, review_payload)
    save_manifest(workspace, manifest)
    return review_payload


def cmd_score(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    article_path = workspace / (args.input or manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到待评分文章：{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
    body = legacy.strip_image_directives(body)
    title = legacy.infer_title(manifest, meta, body)
    threshold = args.threshold or manifest.get("score_threshold") or legacy.DEFAULT_THRESHOLD
    report = legacy.build_score_report(title, body, manifest, threshold)
    report = apply_research_credibility_boost(report, load_research(workspace))

    if not report["passed"] and not args.no_rewrite:
        if args.rewrite_output:
            rewrite_path = Path(args.rewrite_output)
            if not rewrite_path.is_absolute():
                rewrite_path = workspace / rewrite_path
        else:
            rewrite_path = workspace / "article-rewrite.md"
        rewrite = generate_revision_candidate(workspace, title, meta, body, report, manifest, rewrite_path.name)
        report["rewrite"] = rewrite
        manifest["rewrite_path"] = rewrite["output_path"]
        manifest["rewrite_preview_score"] = rewrite.get("preview_score")
        manifest["rewrite_preview_passed"] = rewrite.get("preview_passed")

    write_json(workspace / "score-report.json", report)
    legacy.write_text(workspace / "score-report.md", legacy.markdown_report(report))
    manifest["score_breakdown"] = report["score_breakdown"]
    manifest["score_total"] = report["total_score"]
    manifest["score_passed"] = report["passed"]
    manifest["score_report_path"] = "score-report.json"
    manifest["score_status"] = "done"
    save_manifest(workspace, manifest)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.fail_below and report["total_score"] < threshold:
        return 2
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    topic = args.topic or manifest.get("topic") or "未命名主题"
    if not (workspace / "research.json").exists():
        cmd_research(
            argparse.Namespace(
                workspace=str(workspace),
                topic=topic,
                angle=args.angle or manifest.get("direction") or "",
                audience=args.audience or manifest.get("audience") or "大众读者",
                source_url=args.source_url or manifest.get("source_urls") or [],
            )
        )
    if not (workspace / "ideation.json").exists() or not load_ideation(workspace).get("titles"):
        cmd_titles(argparse.Namespace(workspace=str(workspace), count=args.title_count, selected_title=None))
    ideation = load_ideation(workspace)
    if not ideation.get("outline"):
        cmd_outline(argparse.Namespace(workspace=str(workspace), title=args.title or ideation.get("selected_title")))
    if not (workspace / "article.md").exists():
        cmd_write(argparse.Namespace(workspace=str(workspace), title=args.title or ideation.get("selected_title"), outline_file=None))
    cmd_review(argparse.Namespace(workspace=str(workspace)))
    score_report = _run_score(str(workspace))
    manifest = load_manifest(workspace)
    manifest["score_status"] = "done"
    manifest["score_report_path"] = "score-report.json"
    manifest["score_total"] = score_report.get("total_score")
    manifest["score_passed"] = score_report.get("passed")
    manifest["stage"] = "score"
    save_manifest(workspace, manifest)
    if score_report and not score_report.get("passed", False):
        cmd_revise(argparse.Namespace(workspace=str(workspace), promote=True))
        score_report = _run_score(str(workspace))
        manifest = load_manifest(workspace)
        manifest["score_status"] = "done"
        manifest["score_report_path"] = "score-report.json"
        manifest["score_total"] = score_report.get("total_score")
        manifest["score_passed"] = score_report.get("passed")
        manifest["stage"] = "score"
        save_manifest(workspace, manifest)
    _sync_image_controls(workspace, args)
    image_provider = _effective_image_provider(args)
    legacy_plan_images(argparse.Namespace(workspace=str(workspace), provider=image_provider, inline_count=args.inline_count))
    manifest = load_manifest(workspace)
    manifest["image_status"] = "planned"
    save_manifest(workspace, manifest)
    legacy_generate_images(
        argparse.Namespace(
            workspace=str(workspace),
            provider=image_provider,
            dry_run=args.dry_run_images,
            gemini_model=args.gemini_model,
            openai_model=args.openai_model,
        )
    )
    legacy_assemble(argparse.Namespace(workspace=str(workspace)))
    legacy_render(argparse.Namespace(workspace=str(workspace), input=None, output="article.html", accent_color=args.accent_color))
    manifest = load_manifest(workspace)
    manifest["image_status"] = "done"
    manifest["render_status"] = "done"
    manifest["stage"] = "render"
    save_manifest(workspace, manifest)
    if args.to == "publish":
        _mark_publish_intent(workspace)
        cmd_publish(
            argparse.Namespace(
                workspace=str(workspace),
                input=None,
                digest=None,
                author=None,
                cover=None,
                dry_run=args.dry_run_publish,
                confirmed_publish=args.confirmed_publish,
            )
        )
        if not args.dry_run_publish:
            cmd_verify_draft(argparse.Namespace(workspace=str(workspace), media_id=None))
    return 0


def cmd_hosted_run(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    topic = args.topic or manifest.get("topic") or "未命名主题"
    angle = args.angle or manifest.get("direction") or ""
    audience = args.audience or manifest.get("audience") or "大众读者"
    source_urls = normalize_urls(args.source_url or manifest.get("source_urls") or [])
    _write_hosted_research(workspace, manifest, topic, angle, audience, source_urls)
    title = args.title or manifest.get("selected_title") or topic
    _write_hosted_ideation(workspace, manifest, title, args.outline_file)
    title = _import_hosted_article(workspace, manifest, args.article_file, title, args.summary, angle, audience)
    save_manifest(workspace, manifest)

    score_report = _run_score(str(workspace))
    manifest = load_manifest(workspace)
    if score_report and not score_report.get("passed", False):
        cmd_revise(argparse.Namespace(workspace=str(workspace), promote=True))
        score_report = _run_score(str(workspace))
        manifest = load_manifest(workspace)
    _finalize_after_score(workspace, manifest, title, score_report)

    _sync_image_controls(workspace, args)
    image_provider = _effective_image_provider(args)
    legacy_plan_images(argparse.Namespace(workspace=str(workspace), provider=image_provider, inline_count=args.inline_count))
    manifest = load_manifest(workspace)
    manifest["image_status"] = "planned"
    save_manifest(workspace, manifest)
    legacy_generate_images(
        argparse.Namespace(
            workspace=str(workspace),
            provider=image_provider,
            dry_run=args.dry_run_images,
            gemini_model=args.gemini_model,
            openai_model=args.openai_model,
        )
    )
    legacy_assemble(argparse.Namespace(workspace=str(workspace)))
    legacy_render(argparse.Namespace(workspace=str(workspace), input=None, output="article.html", accent_color=args.accent_color))
    manifest = load_manifest(workspace)
    manifest["image_status"] = "done"
    manifest["render_status"] = "done"
    manifest["stage"] = "render"
    save_manifest(workspace, manifest)
    if args.to == "publish":
        _mark_publish_intent(workspace)
        cmd_publish(
            argparse.Namespace(
                workspace=str(workspace),
                input=None,
                digest=None,
                author=None,
                cover=None,
                dry_run=args.dry_run_publish,
                confirmed_publish=args.confirmed_publish,
            )
        )
        if not args.dry_run_publish:
            cmd_verify_draft(argparse.Namespace(workspace=str(workspace), media_id=None))
    return 0


def cmd_all(args: argparse.Namespace) -> int:
    return cmd_run(
        argparse.Namespace(
            workspace=args.workspace,
            topic=None,
            angle=None,
            audience=None,
            source_url=[],
            title=None,
            title_count=3,
            image_provider=args.provider,
            image_preset=args.image_preset,
            image_density=args.image_density,
            image_layout_family=args.image_layout_family,
            image_theme=args.image_theme,
            image_style=args.image_style,
            image_type=args.image_type,
            image_mood=args.image_mood,
            custom_visual_brief=args.custom_visual_brief,
            inline_count=args.inline_count,
            dry_run_images=args.dry_run_images,
            dry_run_publish=args.dry_run_publish,
            confirmed_publish=args.confirmed_publish,
            gemini_model=args.gemini_model,
            openai_model=args.openai_model,
            accent_color=args.accent_color,
            to="publish" if args.publish else "render",
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="studio.py", description="微信公众号图文工作流 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    research = subparsers.add_parser("research", help="初始化 research.json，沉淀调研输入与来源清单")
    research.add_argument("--workspace", required=True)
    research.add_argument("--topic", required=True)
    research.add_argument("--angle")
    research.add_argument("--audience")
    research.add_argument("--source-url", action="append", default=[])
    research.set_defaults(func=cmd_research)

    titles = subparsers.add_parser("titles", help="生成 3 个左右标题候选并写入 ideation.json")
    titles.add_argument("--workspace", required=True)
    titles.add_argument("--count", type=int, default=3)
    titles.add_argument("--selected-title")
    titles.set_defaults(func=cmd_titles)

    outline = subparsers.add_parser("outline", help="基于 research 和标题生成大纲")
    outline.add_argument("--workspace", required=True)
    outline.add_argument("--title")
    outline.set_defaults(func=cmd_outline)

    write = subparsers.add_parser("write", help="基于 research + ideation 产出 article.md 初稿")
    write.add_argument("--workspace", required=True)
    write.add_argument("--title")
    write.add_argument("--outline-file")
    write.set_defaults(func=cmd_write)

    review = subparsers.add_parser("review", help="生成独立的编辑评审报告，不替代 score")
    review.add_argument("--workspace", required=True)
    review.set_defaults(func=cmd_review)

    revise = subparsers.add_parser("revise", help="基于 score/report 生成 article-rewrite.md 候选稿")
    revise.add_argument("--workspace", required=True)
    revise.add_argument("--promote", action="store_true", help="将改写稿切换为后续流程默认正文")
    revise.set_defaults(func=cmd_revise)

    run = subparsers.add_parser("run", help="从 research 串到 render；显式要求时才继续 publish")
    run.add_argument("--workspace", required=True)
    run.add_argument("--topic")
    run.add_argument("--angle")
    run.add_argument("--audience")
    run.add_argument("--source-url", action="append", default=[])
    run.add_argument("--title")
    run.add_argument("--title-count", type=int, default=3)
    run.add_argument("--to", choices=["render", "publish"], default="render")
    run.add_argument("--image-provider", choices=["gemini-web", "gemini-api", "openai-image"])
    run.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    run.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default="rich")
    run.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    run.add_argument("--image-theme")
    run.add_argument("--image-style")
    run.add_argument("--image-type")
    run.add_argument("--image-mood")
    run.add_argument("--custom-visual-brief")
    run.add_argument("--inline-count", type=int, default=0)
    run.add_argument("--dry-run-images", action="store_true")
    run.add_argument("--dry-run-publish", action="store_true")
    run.add_argument("--confirmed-publish", action="store_true")
    run.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    run.add_argument("--openai-model", default="gpt-image-1")
    run.add_argument("--accent-color", default="#0F766E")
    run.set_defaults(func=cmd_run)

    hosted_run = subparsers.add_parser("hosted-run", help="由宿主 agent 负责文本生成，再继续评分、配图、渲染与发布")
    hosted_run.add_argument("--workspace", required=True)
    hosted_run.add_argument("--topic", required=True)
    hosted_run.add_argument("--angle")
    hosted_run.add_argument("--audience")
    hosted_run.add_argument("--source-url", action="append", default=[])
    hosted_run.add_argument("--title")
    hosted_run.add_argument("--outline-file")
    hosted_run.add_argument("--article-file")
    hosted_run.add_argument("--summary")
    hosted_run.add_argument("--to", choices=["render", "publish"], default="render")
    hosted_run.add_argument("--image-provider", choices=["gemini-web", "gemini-api", "openai-image"])
    hosted_run.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    hosted_run.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default="rich")
    hosted_run.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    hosted_run.add_argument("--image-theme")
    hosted_run.add_argument("--image-style")
    hosted_run.add_argument("--image-type")
    hosted_run.add_argument("--image-mood")
    hosted_run.add_argument("--custom-visual-brief")
    hosted_run.add_argument("--inline-count", type=int, default=0)
    hosted_run.add_argument("--dry-run-images", action="store_true")
    hosted_run.add_argument("--dry-run-publish", action="store_true")
    hosted_run.add_argument("--confirmed-publish", action="store_true")
    hosted_run.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    hosted_run.add_argument("--openai-model", default="gpt-image-1")
    hosted_run.add_argument("--accent-color", default="#0F766E")
    hosted_run.set_defaults(func=cmd_hosted_run)

    ideate = subparsers.add_parser("ideate", help="兼容模式入口：保存选题元信息到工作目录")
    ideate.add_argument("--workspace")
    ideate.add_argument("--topic", required=True)
    ideate.add_argument("--direction", default="")
    ideate.add_argument("--audience", default="大众读者")
    ideate.add_argument("--goal", default="公众号爆款图文")
    ideate.add_argument("--score-threshold", type=int, default=legacy.DEFAULT_THRESHOLD)
    ideate.add_argument("--source-url", action="append", default=[])
    ideate.add_argument("--title", action="append", default=[])
    ideate.add_argument("--selected-title")
    ideate.add_argument("--outline-file")
    ideate.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    ideate.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default="rich")
    ideate.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    ideate.add_argument("--image-theme")
    ideate.add_argument("--image-style")
    ideate.add_argument("--image-type")
    ideate.add_argument("--image-mood")
    ideate.add_argument("--custom-visual-brief")
    ideate.add_argument("--publish-intent", action="store_true")
    ideate.set_defaults(func=cmd_ideate)

    draft = subparsers.add_parser("draft", help="兼容模式入口：把现成 Markdown 落盘为 article.md")
    draft.add_argument("--workspace", required=True)
    draft.add_argument("--input", required=True)
    draft.add_argument("--selected-title")
    draft.add_argument("--summary")
    draft.add_argument("--author")
    draft.set_defaults(func=cmd_draft)

    score = subparsers.add_parser("score", help="运行启发式 lint + score，并在低分时生成改写候选")
    score.add_argument("--workspace", required=True)
    score.add_argument("--input")
    score.add_argument("--threshold", type=int)
    score.add_argument("--fail-below", action="store_true")
    score.add_argument("--no-rewrite", action="store_true")
    score.add_argument("--rewrite-output")
    score.set_defaults(func=cmd_score)

    plan_images = subparsers.add_parser("plan-images", help="按章节权重生成 image-plan.json")
    plan_images.add_argument("--workspace", required=True)
    plan_images.add_argument("--provider", choices=["gemini-web", "gemini-api", "openai-image"])
    plan_images.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    plan_images.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default="rich")
    plan_images.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    plan_images.add_argument("--image-theme")
    plan_images.add_argument("--image-style")
    plan_images.add_argument("--image-type")
    plan_images.add_argument("--image-mood")
    plan_images.add_argument("--custom-visual-brief")
    plan_images.add_argument("--inline-count", type=int, default=0)
    plan_images.set_defaults(func=legacy_plan_images)

    generate_images = subparsers.add_parser("generate-images", help="执行 image-plan.json 中的图片生成")
    generate_images.add_argument("--workspace", required=True)
    generate_images.add_argument("--provider", choices=["gemini-web", "gemini-api", "openai-image"])
    generate_images.add_argument("--dry-run", action="store_true")
    generate_images.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    generate_images.add_argument("--openai-model", default="gpt-image-1")
    generate_images.set_defaults(func=legacy_generate_images)

    assemble = subparsers.add_parser("assemble", help="把图片插回 Markdown，生成 assembled.md")
    assemble.add_argument("--workspace", required=True)
    assemble.set_defaults(func=legacy_assemble)

    render = subparsers.add_parser("render", help="渲染 article.html 和 article.wechat.html")
    render.add_argument("--workspace", required=True)
    render.add_argument("--input")
    render.add_argument("--output", default="article.html")
    render.add_argument("--accent-color", default="#0F766E")
    render.set_defaults(func=legacy_render)

    publish = subparsers.add_parser("publish", help="发布到微信公众号草稿箱；正式发布需显式确认")
    publish.add_argument("--workspace", required=True)
    publish.add_argument("--input")
    publish.add_argument("--digest")
    publish.add_argument("--author")
    publish.add_argument("--cover")
    publish.add_argument("--dry-run", action="store_true")
    publish.add_argument("--confirmed-publish", action="store_true")
    publish.set_defaults(func=cmd_publish)

    verify_draft = subparsers.add_parser("verify-draft", help="回读草稿箱内容，校验图片与 thumb_media_id")
    verify_draft.add_argument("--workspace", required=True)
    verify_draft.add_argument("--media-id")
    verify_draft.set_defaults(func=cmd_verify_draft)

    doctor = subparsers.add_parser("doctor", help="检查 Python、文本 provider、图片 provider、微信凭证")
    doctor.add_argument("--workspace")
    doctor.set_defaults(func=cmd_doctor)

    consent = subparsers.add_parser("consent", help="管理 gemini-web 的显式同意状态")
    consent.add_argument("--accept", action="store_true")
    consent.add_argument("--revoke", action="store_true")
    consent.set_defaults(func=cmd_consent)

    all_cmd = subparsers.add_parser("all", help="兼容别名：等价于 run")
    all_cmd.add_argument("--workspace", required=True)
    all_cmd.add_argument("--provider", choices=["gemini-web", "gemini-api", "openai-image"])
    all_cmd.add_argument("--image-preset", choices=legacy.IMAGE_STYLE_PRESET_CHOICES)
    all_cmd.add_argument("--image-density", choices=legacy.IMAGE_DENSITY_CHOICES, default="rich")
    all_cmd.add_argument("--image-layout-family", choices=legacy.IMAGE_LAYOUT_FAMILY_CHOICES)
    all_cmd.add_argument("--image-theme")
    all_cmd.add_argument("--image-style")
    all_cmd.add_argument("--image-type")
    all_cmd.add_argument("--image-mood")
    all_cmd.add_argument("--custom-visual-brief")
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
