from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import legacy_studio as legacy

from core.artifacts import extract_summary, join_frontmatter, strip_leading_h1, write_json, write_text
from providers.text.gemini_web import GeminiWebTextProvider
from providers.text.openai_compatible import OpenAICompatibleTextProvider

def auto_rewrite_article(*args, **kwargs):
    return legacy.auto_rewrite_article(*args, **kwargs)


def _active_text_provider_for_rewrite():
    provider_name = (os.getenv("ARTICLE_STUDIO_TEXT_PROVIDER") or "openai-compatible").strip().lower()
    if provider_name in {"gemini-web", "gemini_web"}:
        return GeminiWebTextProvider()
    if provider_name not in {"openai-compatible", "openai_compatible", ""}:
        raise SystemExit(f"暂不支持的文本 provider：{provider_name}")
    return OpenAICompatibleTextProvider()


def _low_dimensions(report: dict[str, Any]) -> list[str]:
    low_dims: list[str] = []
    for item in report.get("score_breakdown", []) or []:
        try:
            score = float(item.get("score") or 0)
            weight = float(item.get("weight") or 0) or 1.0
        except (TypeError, ValueError):
            continue
        if score / max(1.0, weight) < 0.75 and item.get("dimension"):
            low_dims.append(str(item.get("dimension")))
    return low_dims


def generate_revision_candidate(
    workspace: Path,
    title: str,
    meta: dict[str, str],
    body: str,
    report: dict,
    manifest: dict,
    output_name: str = "article-rewrite.md",
) -> dict:
    output_path = workspace / output_name

    provider = _active_text_provider_for_rewrite()
    if provider.configured():
        rewrite_goal = (
            "去 AI 味改写：\n"
            "- 删掉模板连接词（如：首先/其次/总之/综上所述/值得注意的是…），减少官话与空话。\n"
            "- 句式长短交替，段落更短，更像公众号真人编辑。\n"
            "- 有态度但不喊口号；不要编造事实和数据；保留原有信息与结构。\n"
            "- 保持 Markdown 结构（H2/H3、列表、引用、代码块），不要输出解释。\n"
        )
        context = {
            "title": title,
            "audience": manifest.get("audience") or "公众号读者",
            "direction": manifest.get("direction") or "",
            "summary": meta.get("summary") or manifest.get("summary") or extract_summary(body),
            "article_body": body,
            "rewrite_goal": rewrite_goal,
            "mandatory_revisions": report.get("mandatory_revisions") or [],
            "weaknesses": report.get("weaknesses") or [],
            "suggestions": report.get("suggestions") or {},
            "score_breakdown": report.get("score_breakdown") or [],
        }
        result = provider.revise_article(context)
        rewritten_body = str(result.payload or "").strip()
        rewritten_body = strip_leading_h1(rewritten_body, title).strip() + "\n"

        rewrite_meta = dict(meta)
        rewrite_meta["title"] = title
        rewrite_meta["summary"] = meta.get("summary") or manifest.get("summary") or extract_summary(rewritten_body)
        rewrite_meta["rewrite_from"] = meta.get("title") or title
        write_text(output_path, join_frontmatter(rewrite_meta, rewritten_body))

        threshold = int(report.get("threshold") or legacy.DEFAULT_THRESHOLD)
        preview_report = legacy.build_score_report(title, rewritten_body, manifest, threshold)
        rewrite = {
            "output_path": output_path.name,
            "triggered_dimensions": _low_dimensions(report),
            "applied_actions": ["模型改写：去 AI 味与节奏优化"],
            "preview_score": preview_report["total_score"],
            "preview_passed": preview_report["passed"],
            "preview_score_breakdown": preview_report["score_breakdown"],
            "preview_candidate_quotes": preview_report["candidate_quotes"],
            "provider": result.provider,
            "model": result.model,
        }
        write_json(output_path.with_suffix(".rewrite.json"), rewrite)
        return rewrite

    return legacy.auto_rewrite_article(title, meta, body, report, manifest, output_path)
