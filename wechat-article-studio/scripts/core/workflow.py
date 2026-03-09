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
from providers.text.openai_compatible import OpenAICompatibleTextProvider
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


def build_research_reference_section(research: dict[str, Any]) -> str:
    sources = normalize_string_list(research.get("sources"))
    evidence_items = normalize_string_list(research.get("evidence_items"))
    if not sources and not evidence_items:
        return ""
    lines = ["## 参考与延伸", ""]
    for item in sources:
        lines.append(f"- 研究线索：{item}")
    for item in evidence_items[:3]:
        lines.append(f"- 关键信息：{item}")
    return "\n".join(lines).strip()


def ensure_reference_section(body: str, research: dict[str, Any]) -> str:
    if "## 参考" in body or "## 参考与延伸" in body or "## 来源" in body:
        return body
    block = build_research_reference_section(research)
    if not block:
        return body
    return body.rstrip() + "\n\n" + block + "\n"


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
    body = ensure_reference_section(body, research)
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


def cmd_revise(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    article_path = workspace / (manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到待改写文章：{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
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
            "selected_provider": provider.provider_name,
            "configured": provider.configured(),
            "model": getattr(provider, "model", ""),
            "required_env": ["ARTICLE_STUDIO_TEXT_MODEL", "OPENAI_API_KEY"],
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


def cmd_score(args: argparse.Namespace) -> int:
    workspace = ensure_workspace(workspace_path(args.workspace))
    manifest = load_manifest(workspace)
    article_path = workspace / (args.input or manifest.get("article_path") or "article.md")
    if not article_path.exists():
        raise SystemExit(f"找不到待评分文章：{article_path}")
    meta, body = split_frontmatter(read_text(article_path))
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
        cmd_revise(argparse.Namespace(workspace=str(workspace)))
    legacy_plan_images(argparse.Namespace(workspace=str(workspace), provider=args.image_provider, inline_count=args.inline_count))
    manifest = load_manifest(workspace)
    manifest["image_status"] = "planned"
    save_manifest(workspace, manifest)
    legacy_generate_images(
        argparse.Namespace(
            workspace=str(workspace),
            provider=args.image_provider,
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
    run.add_argument("--inline-count", type=int, default=0)
    run.add_argument("--dry-run-images", action="store_true")
    run.add_argument("--dry-run-publish", action="store_true")
    run.add_argument("--confirmed-publish", action="store_true")
    run.add_argument("--gemini-model", default="gemini-2.0-flash-preview-image-generation")
    run.add_argument("--openai-model", default="gpt-image-1")
    run.add_argument("--accent-color", default="#0F766E")
    run.set_defaults(func=cmd_run)

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
