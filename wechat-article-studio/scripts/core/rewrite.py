from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import legacy_studio as legacy

from core.artifacts import extract_summary, join_frontmatter, read_text, strip_leading_h1, write_json, write_text
from core.humanizerai import HumanizerAIClient, HumanizerAIError, normalize_humanizerai_intensity
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


def _humanizer_client_for_rewrite() -> HumanizerAIClient:
    return HumanizerAIClient.from_env()


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
    humanizerai_before: dict[str, Any] | None = None
    humanizerai_after: dict[str, Any] | None = None
    humanizerai_error = ""
    humanizerai_applied = ""
    humanizerai_seed_body = before_body
    humanizer = _humanizer_client_for_rewrite()

    if mode == "de-ai" and humanizer.configured():
        try:
            humanizerai_before = humanizer.detect(before_body)
            requested_intensity = os.getenv("HUMANIZERAI_INTENSITY")
            chosen_intensity = normalize_humanizerai_intensity(
                requested_intensity,
                score_overall=int(humanizerai_before.get("score_overall") or 0),
            )
            humanized = humanizer.humanize(before_body, chosen_intensity)
            humanizerai_seed_body = strip_leading_h1(str(humanized.get("text") or ""), title).strip() + "\n"
            humanizerai_applied = chosen_intensity
            applied_actions.append(f"HumanizerAI：外部去味初改（{chosen_intensity}）")
        except HumanizerAIError as exc:
            humanizerai_error = str(exc)
            applied_actions.append("HumanizerAI：调用失败，已回退当前去味链路")

    if provider.configured():
        if mode == "de-ai":
            rewrite_goal = (
                "去 AI 味改写：\n"
                "- 删掉模板连接词（如：首先/其次/总之/综上所述/值得注意的是…），减少官话与空话。\n"
                "- 删掉篇章自我说明和固定句式（如：先说结论/接下来我会/最后给你一个可执行清单/如果你只想记住一句话）。\n"
                "- 不要反复写“不是X，而是Y”“问题不在X，而在Y”这种强行反转句；真要反转，只保留最值钱的一两处。\n"
                "- 少用“换句话说/更重要的是/真正的问题是”这类先铺垫再说重点的句子，能直说就直说。\n"
                "- 不要让“数据/趋势/市场/AI/系统”替人做动作，优先写清楚是谁在判断、谁在选择、谁在承担后果。\n"
                "- 句式长短交替，段落更短，但不要碎成口号。\n"
                "- 如果全篇像提纲，就补一两段真正展开的分析段；如果段落起手老是一样，就重写起手。\n"
                "- 保留一个具体场景、一个真实细节和一个边界提醒，不要只剩抽象判断。\n"
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
                "- 必须至少补一处现场/动作/瞬间，一处案例/数据/事实，一处反方/误判/边界。\n"
                "- 如果正文段落全都太短，必须合并出一两段真正展开的分析段。\n"
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
                "article_body": humanizerai_seed_body if mode == "de-ai" else before_body,
                "source_article_body": before_body,
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
            "recent_phrase_blacklist": manifest.get("recent_phrase_blacklist") or [],
            "recent_article_titles": manifest.get("recent_article_titles") or [],
            "recent_corpus_summary": manifest.get("recent_corpus_summary") or {},
            "corpus_root": manifest.get("corpus_root") or "",
            "editorial_blueprint": manifest.get("editorial_blueprint") or {},
                "author_memory": manifest.get("author_memory") or {},
                "writing_persona": manifest.get("writing_persona") or {},
                "content_enhancement": legacy.read_json(workspace / "content-enhancement.json", default={}) or {},
                "humanness_signals": report.get("humanness_signals") or {},
                "humanizerai_detection": humanizerai_before or {},
                "humanizerai_humanized_body": humanizerai_seed_body if humanizerai_applied else "",
            }
            result = provider.revise_article(context)
        provider_name = result.provider
        provider_model = result.model
        rewritten_body = strip_leading_h1(str(result.payload or ""), title).strip() + "\n"
    else:
        if mode == "de-ai":
            seed_for_cleanup = humanizerai_seed_body if humanizerai_applied else before_body
            rewritten_body = legacy.cleanup_rewrite_markdown(seed_for_cleanup) or seed_for_cleanup
            if not humanizerai_applied:
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
    if mode == "de-ai" and humanizer.configured():
        try:
            humanizerai_after = humanizer.detect(rewritten_body)
        except HumanizerAIError as exc:
            humanizerai_error = humanizerai_error or str(exc)
    diff_metrics = {
        "ai_style_hits": {"before": before_hits, "after": after_hits, "delta": after_hits - before_hits},
        "sentence_len": {"before": before_sent, "after": after_sent},
        "paragraphs": {"before": before_paras, "after": after_paras},
    }
    if humanizerai_before or humanizerai_after:
        diff_metrics["humanizerai_score"] = {
            "before": int((humanizerai_before or {}).get("score_overall") or 0),
            "after": int((humanizerai_after or {}).get("score_overall") or 0),
            "delta": int((humanizerai_after or {}).get("score_overall") or 0)
            - int((humanizerai_before or {}).get("score_overall") or 0),
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
    if humanizerai_before or humanizerai_after or humanizerai_error:
        rewrite_payload["humanizerai"] = {
            "enabled": humanizer.configured(),
            "applied_intensity": humanizerai_applied,
            "before": humanizerai_before or {},
            "after": humanizerai_after or {},
            "error": humanizerai_error,
        }

    write_json(output_path.with_suffix(".rewrite.json"), rewrite_payload)
    return rewrite_payload
