from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.quality_checks import workspace_batch_key


def _normalize_key(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _is_single_article_batch_workspace(path: Path, batch_key: str) -> bool:
    name = path.name
    if not name.startswith(f"{batch_key}-"):
        return False
    return "hot-topics" not in name.lower()


def image_plan_signature(plan: dict[str, Any]) -> dict[str, Any]:
    strategy = plan.get("article_visual_strategy") or {}
    items = list(plan.get("items") or [])
    cover = next((item for item in items if str(item.get("id") or "") == "cover-01"), {})
    first_inline = next((item for item in items if str(item.get("id") or "").startswith("inline-")), {})
    signature = {
        "visual_route": _normalize_key(strategy.get("visual_route")),
        "style_family": _normalize_key(strategy.get("style_family")),
        "layout_family": _normalize_key(plan.get("layout_family") or plan.get("image_controls", {}).get("layout_family") or strategy.get("layout_family")),
        "preset": _normalize_key(plan.get("image_controls", {}).get("preset") or strategy.get("preset")),
        "cover_preset": _normalize_key(cover.get("visual_preset") or plan.get("image_controls", {}).get("preset_cover") or strategy.get("preset_cover")),
        "inline_preset": _normalize_key(first_inline.get("visual_preset") or plan.get("image_controls", {}).get("preset_inline") or strategy.get("preset_inline")),
        "cover_layout": _normalize_key(cover.get("layout_variant_key")),
        "inline_layout": _normalize_key(first_inline.get("layout_variant_key")),
    }
    signature["tags"] = [value for value in signature.values() if isinstance(value, str) and value]
    return signature


def load_batch_image_plans(current_workspace: Path) -> list[dict[str, Any]]:
    batch_key = workspace_batch_key(current_workspace)
    if not batch_key:
        return []
    parent = current_workspace.parent
    if not parent.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in parent.iterdir():
        if not path.is_dir() or path.resolve() == current_workspace.resolve():
            continue
        if workspace_batch_key(path) != batch_key:
            continue
        if not _is_single_article_batch_workspace(path, batch_key):
            continue
        plan_path = path / "image-plan.json"
        if not plan_path.exists():
            continue
        try:
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        items.append({"workspace": str(path.resolve()), "plan": payload, "signature": image_plan_signature(payload)})
    return items


def summarize_visual_batch_collisions(current_workspace: Path, plan: dict[str, Any]) -> dict[str, Any]:
    current_signature = image_plan_signature(plan)
    current_tags = set(current_signature.get("tags") or [])
    collisions: list[dict[str, Any]] = []
    max_overlap = 0
    for item in load_batch_image_plans(current_workspace):
        other_signature = dict(item.get("signature") or {})
        other_tags = set(other_signature.get("tags") or [])
        overlap = len(current_tags & other_tags)
        same_route = bool(current_signature.get("visual_route")) and current_signature.get("visual_route") == other_signature.get("visual_route")
        same_layout = bool(current_signature.get("layout_family")) and current_signature.get("layout_family") == other_signature.get("layout_family")
        same_cover = bool(current_signature.get("cover_preset")) and current_signature.get("cover_preset") == other_signature.get("cover_preset")
        matched_rules: list[str] = []
        if same_route:
            matched_rules.append("same_visual_route")
        if same_layout:
            matched_rules.append("same_layout_family")
        if same_cover:
            matched_rules.append("same_cover_preset")
        if overlap >= 4:
            matched_rules.append("high_signature_overlap")
        max_overlap = max(max_overlap, overlap)
        if len(matched_rules) >= 3:
            collisions.append(
                {
                    "workspace": str(item.get("workspace") or ""),
                    "overlap": overlap,
                    "matched_rules": matched_rules,
                    "signature": other_signature,
                }
            )
    return {
        "passed": not collisions,
        "max_overlap": max_overlap,
        "signature": current_signature,
        "similar_items": collisions[:5],
    }
