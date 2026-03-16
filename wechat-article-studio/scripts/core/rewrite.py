from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import legacy_studio as legacy

from core.artifacts import extract_summary, join_frontmatter, read_text, strip_leading_h1, write_json, write_text
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


def _ai_style_hits(text: str) -> int:
    value = text or ""
    return sum(value.count(phrase) for phrase in getattr(legacy, "AI_STYLE_PHRASES", []) or [])


def _sentence_stats(text: str) -> dict[str, Any]:
    lengths = [legacy.cjk_len(sentence) for sentence in legacy.sentence_split(text or "") if sentence.strip()]
    if not lengths:
        return {"count": 0, "avg": 0, "min": 0, "max": 0, "range": 0}
    return {
        "count": len(lengths),
        "avg": round(sum(lengths) / max(1, len(lengths)), 2),
        "min": min(lengths),
        "max": max(lengths),
        "range": max(lengths) - min(lengths),
    }


def _paragraph_count(text: str) -> int:
    blocks = [block for block in re.split(r"\n\s*\n", text or "") if block.strip()]
    return len(blocks)


def _write_rewrite_report(
    report_path: Path,
    *,
    mode: str,
    output_name: str,
    preview_score: int | None,
    preview_passed: bool | None,
    triggered_dimensions: list[str],
    applied_actions: list[str],
    diff_metrics: dict[str, Any],
) -> None:
    lines: list[str] = [
        "# 改写差异报告",
        "",
        f"- 模式：`{mode}`",
        f"- 输出：`{output_name}`",
    ]
    if preview_score is not None:
        lines.append(f"- 预评分：`{preview_score}` / 100｜`{'通过' if preview_passed else '未通过'}`")
    lines.extend(["", "## 指标对比", ""])
    hits = diff_metrics.get("ai_style_hits", {})
    lines.append(f"- 模板腔短语命中：`{hits.get('before', 0)}` -> `{hits.get('after', 0)}`（Δ {hits.get('delta', 0)}）")
    sent = diff_metrics.get("sentence_len", {})
    lines.append(
        f"- 句长均值：`{sent.get('before', {}).get('avg', 0)}` -> `{sent.get('after', {}).get('avg', 0)}`；"
        f"极差：`{sent.get('before', {}).get('range', 0)}` -> `{sent.get('after', {}).get('range', 0)}`"
    )
    paras = diff_metrics.get("paragraphs", {})
    lines.append(f"- 段落数：`{paras.get('before', 0)}` -> `{paras.get('after', 0)}`")
    if triggered_dimensions:
        lines.extend(["", "## 触发维度", ""] + [f"- {item}" for item in triggered_dimensions])
    if applied_actions:
        lines.extend(["", "## 已应用动作", ""] + [f"- {item}" for item in applied_actions])
    write_text(report_path, "\n".join(lines).rstrip() + "\n")


def generate_revision_candidate(
    workspace: Path,
    title: str,
    meta: dict[str, str],
    body: str,
    report: dict,
    manifest: dict,
    output_name: str = "article-rewrite.md",
    mode: str = "improve-score",
) -> dict:
    output_path = workspace / output_name
    report_path = output_path.with_suffix(".report.md")

    before_body = strip_leading_h1(body, title).strip() + "\n"
    before_hits = _ai_style_hits(before_body)
    before_sent = _sentence_stats(before_body)
    before_paras = _paragraph_count(before_body)

    provider = _active_text_provider_for_rewrite()
    mode = (mode or "improve-score").strip().lower().replace("_", "-")
    if mode not in {"improve-score", "de-ai"}:
        mode = "improve-score"

    triggered_dimensions = _low_dimensions(report)
    applied_actions: list[str] = []
    rewritten_body = ""
    provider_name = ""
    provider_model = ""
    legacy_rewrite: dict[str, Any] | None = None

    if provider.configured():
        if mode == "de-ai":
            rewrite_goal = (
                "去 AI 味改写：\n"
                "- 删掉模板连接词（如：首先/其次/总之/综上所述/值得注意的是…），减少官话与空话。\n"
                "- 删掉篇章自我说明和固定句式（如：先说结论/接下来我会/最后给你一个可执行清单/如果你只想记住一句话）。\n"
                "- 句式长短交替，段落更短，但不要碎成口号。\n"
                "- 有态度但不喊口号；不要编造事实和数据；保留原有信息与结构。\n"
                "- 保持 Markdown 结构（H2/H3、列表、引用、代码块），不要输出解释。\n"
            )
            applied_actions.append("模型改写：去 AI 味与节奏优化")
        else:
            rewrite_goal = (
                "爆款提分改写：\n"
                "- 优先修复最影响阅读完成度和传播力的 3 个问题，而不是机械套模板。\n"
                "- 开头可以用场景、反差、问题、细节或新闻切口，不要默认“先说结论”。\n"
                "- 结尾只有在教程/方法文里才适合给动作；分析稿优先用判断、余味、风险提醒或趋势观察收束。\n"
                "- 补情绪价值句和刺痛句，但不要让整篇变成统一口号。\n"
                "- 补论证多样性（对比/案例/数据/场景/步骤视题材而定），避免只讲观点不讲细节。\n"
                "- 继续去 AI 味（避免首先/其次/最后/综上所述、接下来我会、万能清单等模板腔）。\n"
                "- 不要编造事实、数据和来源；保持 Markdown 结构；不要输出解释。\n"
            )
            applied_actions.append("模型改写：按评分短板提分优化")

        context = {
            "mode": mode,
            "title": title,
            "audience": manifest.get("audience") or "公众号读者",
            "direction": manifest.get("direction") or "",
            "summary": meta.get("summary") or manifest.get("summary") or extract_summary(before_body),
            "article_body": before_body,
            "rewrite_goal": rewrite_goal,
            "mandatory_revisions": report.get("mandatory_revisions") or [],
            "weaknesses": report.get("weaknesses") or [],
            "suggestions": report.get("suggestions") or {},
            "score_breakdown": report.get("score_breakdown") or [],
            "viral_blueprint": report.get("viral_blueprint") or manifest.get("viral_blueprint") or {},
            "viral_analysis": report.get("viral_analysis") or {},
            "emotion_value_sentences": report.get("emotion_value_sentences") or [],
            "pain_point_sentences": report.get("pain_point_sentences") or [],
            "ai_smell_findings": report.get("ai_smell_findings") or [],
            "quality_gates": report.get("quality_gates") or {},
            "style_samples": manifest.get("style_sample_paths") or [],
            "style_signals": manifest.get("style_signals") or [],
        }
        result = provider.revise_article(context)
        provider_name = result.provider
        provider_model = result.model
        rewritten_body = strip_leading_h1(str(result.payload or ""), title).strip() + "\n"
    else:
        if mode == "de-ai":
            rewritten_body = legacy.cleanup_rewrite_markdown(before_body) or before_body
            applied_actions.append("规则清理：去模板连接词与口吻")
            rewrite_meta = dict(meta)
            rewrite_meta["title"] = title
            rewrite_meta["summary"] = meta.get("summary") or manifest.get("summary") or extract_summary(rewritten_body)
            rewrite_meta["rewrite_from"] = meta.get("title") or title
            write_text(output_path, join_frontmatter(rewrite_meta, rewritten_body))
        else:
            legacy_rewrite = legacy.auto_rewrite_article(title, meta, before_body, report, manifest, output_path)
            # Legacy already wrote files; we will augment the rewrite.json below for consistency.
            _, rewritten_body = legacy.split_frontmatter(read_text(output_path))
            rewritten_body = strip_leading_h1(rewritten_body, title).strip() + "\n"
            applied_actions.extend(list(legacy_rewrite.get("applied_actions") or []) or ["规则改写：按评分短板提分"])

    threshold = int(report.get("threshold") or legacy.DEFAULT_THRESHOLD)
    preview_report = legacy.build_score_report(title, rewritten_body, manifest, threshold)
    after_hits = _ai_style_hits(rewritten_body)
    after_sent = _sentence_stats(rewritten_body)
    after_paras = _paragraph_count(rewritten_body)
    diff_metrics = {
        "ai_style_hits": {"before": before_hits, "after": after_hits, "delta": after_hits - before_hits},
        "sentence_len": {"before": before_sent, "after": after_sent},
        "paragraphs": {"before": before_paras, "after": after_paras},
    }

    _write_rewrite_report(
        report_path,
        mode=mode,
        output_name=output_path.name,
        preview_score=preview_report.get("total_score"),
        preview_passed=preview_report.get("passed"),
        triggered_dimensions=triggered_dimensions,
        applied_actions=applied_actions,
        diff_metrics=diff_metrics,
    )

    rewrite_payload = {
        "output_path": output_path.name,
        "mode": mode,
        "report_path": report_path.name,
        "diff_metrics": diff_metrics,
        "triggered_dimensions": triggered_dimensions,
        "applied_actions": applied_actions,
        "preview_score": preview_report["total_score"],
        "preview_passed": preview_report["passed"],
        "preview_score_breakdown": preview_report["score_breakdown"],
        "preview_candidate_quotes": preview_report["candidate_quotes"],
    }
    if provider_name:
        rewrite_payload["provider"] = provider_name
        rewrite_payload["model"] = provider_model
    elif legacy_rewrite:
        # Preserve legacy evidence metadata on the rule-based improve-score path.
        rewrite_payload["evidence_report_path"] = legacy_rewrite.get("evidence_report_path")
        rewrite_payload["evidence_used_count"] = legacy_rewrite.get("evidence_used_count", 0)

    write_json(output_path.with_suffix(".rewrite.json"), rewrite_payload)
    return rewrite_payload
