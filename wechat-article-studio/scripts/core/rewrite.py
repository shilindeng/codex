from __future__ import annotations

from pathlib import Path

import legacy_studio as legacy


def auto_rewrite_article(*args, **kwargs):
    return legacy.auto_rewrite_article(*args, **kwargs)


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
    return legacy.auto_rewrite_article(title, meta, body, report, manifest, output_path)
