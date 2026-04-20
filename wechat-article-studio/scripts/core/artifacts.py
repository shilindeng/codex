from __future__ import annotations

from pathlib import Path
from typing import Any

import legacy_studio as legacy

STANDARD_ARTIFACTS = [
    "manifest.json",
    "topic-discovery.json",
    "topic-discovery.md",
    "viral-discovery.json",
    "viral-discovery.md",
    "research.json",
    "source-corpus.json",
    "viral-dna.json",
    "viral-dna.md",
    "publication.md",
    "publication-report.json",
    "ideation.json",
    "article.md",
    "title-report.json",
    "title-decision-report.json",
    "title-report.md",
    "content-enhancement.json",
    "content-enhancement.md",
    "editorial-anchor-plan.json",
    "editorial-anchor-plan.md",
    "review-report.json",
    "review-report.md",
    "score-report.json",
    "score-report.md",
    "similarity-report.json",
    "similarity-report.md",
    "content-fingerprint.json",
    "layout-plan.json",
    "acceptance-report.json",
    "reader_gate.json",
    "visual_gate.json",
    "final_gate.json",
    "final-delivery-report.json",
    "final-delivery-report.md",
    "image-plan.json",
    "image-outline.json",
    "image-outline.md",
    "assembled.md",
    "article.html",
    "article.wechat.html",
    "versions/manifest.json",
    "publish-result.json",
    "latest-draft-report.json",
]

read_text = legacy.read_text
write_text = legacy.write_text
read_json = legacy.read_json
write_json = legacy.write_json
read_input_file = legacy.read_input_file
split_frontmatter = legacy.split_frontmatter
join_frontmatter = legacy.join_frontmatter
extract_summary = legacy.extract_summary
relative_posix = legacy.relative_posix
extract_headings = legacy.extract_headings
list_paragraphs = legacy.list_paragraphs
strip_leading_h1 = legacy.strip_leading_h1
infer_title = legacy.infer_title
now_iso = legacy.now_iso


def standard_artifact_paths(workspace: Path) -> dict[str, Path]:
    return {name: workspace / name for name in STANDARD_ARTIFACTS}


def ensure_text_report(path: Path, title: str, lines: list[str]) -> None:
    body = [f"# {title}", ""] + [f"- {line}" for line in lines if line]
    write_text(path, "\n".join(body).strip() + "\n")


def ensure_json(path: Path, default: Any) -> Any:
    if path.exists():
        return read_json(path, default=default)
    write_json(path, default)
    return default
