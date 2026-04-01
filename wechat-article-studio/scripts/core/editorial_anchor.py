from __future__ import annotations

from pathlib import Path
from typing import Any

from core.artifacts import now_iso, read_json, write_json, write_text


def build_editorial_anchor_plan(
    *,
    title: str,
    manifest: dict[str, Any],
    review_report: dict[str, Any] | None = None,
    score_report: dict[str, Any] | None = None,
    content_enhancement: dict[str, Any] | None = None,
) -> dict[str, Any]:
    review_report = review_report or {}
    score_report = score_report or {}
    content_enhancement = content_enhancement or {}
    humanness_findings = list(score_report.get("humanness_findings") or [])
    mandatory_revisions = list(score_report.get("mandatory_revisions") or [])
    section_enhancements = list(content_enhancement.get("section_enhancements") or [])
    anchors: list[dict[str, Any]] = []

    opening_reason = "开头再补一句具体瞬间，会更像真人写出来的现场。"
    if any("场景" in item for item in humanness_findings + mandatory_revisions):
        opening_reason = "首屏还缺现场感，补一句动作、时间或反应会明显更稳。"
    anchors.append(
        {
            "slot": "opening",
            "goal": "首屏补现场或动作瞬间",
            "reason": opening_reason,
            "suggestion": "在前两段里补一句能被看见的动作、时间点或对话，不要直接上抽象判断。",
        }
    )

    middle_targets = []
    if section_enhancements:
        middle_targets = list(section_enhancements[0].get("evidence_targets") or []) + list(section_enhancements[0].get("counterpoint_targets") or [])
    middle_reason = "中段再压一层事实或反方，专业度会更稳。"
    if any("证据" in item or "反方" in item or "边界" in item for item in mandatory_revisions):
        middle_reason = "现在最缺的是托底材料和边界提醒，中段该补这一下。"
    anchors.append(
        {
            "slot": "middle",
            "goal": "中段补证据或边界",
            "reason": middle_reason,
            "suggestion": (middle_targets[0] if middle_targets else "在主判断后补一个案例、数字、来源，或补一句“什么情况下这个判断不成立”。"),
        }
    )

    ending_reason = "结尾再收得准一点，文章会更有余味。"
    if any("结尾" in item or "判断" in item for item in mandatory_revisions):
        ending_reason = "结尾还不够稳，应该再压一句更能带走的判断。"
    anchors.append(
        {
            "slot": "ending",
            "goal": "结尾补一句可带走的判断",
            "reason": ending_reason,
            "suggestion": "最后别重复总结，补一句更短、更准、能被转述的话，或者补一句适用边界。",
        }
    )
    return {
        "title": title,
        "generated_at": now_iso(),
        "anchors": anchors[:3],
        "source_signals": {
            "humanness_findings": humanness_findings[:4],
            "mandatory_revisions": mandatory_revisions[:4],
            "review_summary": str(review_report.get("summary") or ""),
        },
    }


def markdown_editorial_anchor_plan(payload: dict[str, Any]) -> str:
    lines = [f"# 编辑锚点建议：{payload.get('title') or '未命名标题'}", ""]
    for item in payload.get("anchors") or []:
        lines.append(f"## {item.get('goal') or item.get('slot')}")
        lines.append("")
        lines.append(f"- 为什么补这里：{item.get('reason') or ''}")
        lines.append(f"- 建议怎么补：{item.get('suggestion') or ''}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_editorial_anchor_artifacts(workspace: Path, payload: dict[str, Any]) -> None:
    write_json(workspace / "editorial-anchor-plan.json", payload)
    write_text(workspace / "editorial-anchor-plan.md", markdown_editorial_anchor_plan(payload))


def load_editorial_anchor_plan(workspace: Path) -> dict[str, Any]:
    return read_json(workspace / "editorial-anchor-plan.json", default={}) or {}
