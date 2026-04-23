from __future__ import annotations

from typing import Any


def collect_insertable_items(plan_items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]], list[dict[str, Any]]]:
    intro_items: list[dict[str, Any]] = []
    section_items: dict[int, list[dict[str, Any]]] = {}
    inserted: list[dict[str, Any]] = []
    lead_inline_promoted = False
    for item in plan_items:
        asset_path = item.get("asset_path")
        if not asset_path:
            continue
        if (item.get("source_meta") or {}).get("fallback_local_card"):
            continue
        if item.get("type") == "封面图" or item.get("insert_strategy") == "cover_only":
            continue
        inserted.append({"id": item["id"], "asset_path": asset_path, "type": item["type"]})
        if not lead_inline_promoted and str(item.get("id") or "").startswith("inline-") and item.get("insert_strategy") == "section_middle":
            promoted = dict(item)
            promoted["placement_block_index"] = max(0, len(intro_items))
            intro_items.append(promoted)
            lead_inline_promoted = True
            continue
        target_index = item.get("target_section_index", -1)
        if target_index == -1:
            intro_items.append(item)
        else:
            section_items.setdefault(target_index, []).append(item)
    return intro_items, section_items, inserted


def render_body_from_blocks(
    intro_blocks: list[str],
    sections: list[dict[str, Any]],
    intro_items: list[dict[str, Any]],
    section_items: dict[int, list[dict[str, Any]]],
) -> str:
    parts: list[str] = []
    intro_insert_map: dict[int, list[dict[str, Any]]] = {}
    for item in intro_items:
        key = item.get("placement_block_index", 0)
        intro_insert_map.setdefault(key, []).append(item)

    if intro_blocks:
        for index, block in enumerate(intro_blocks):
            parts.append(block)
            for item in intro_insert_map.get(index, []):
                parts.append(f"![{item['alt']}]({item['asset_path']})")
    elif intro_items:
        for item in intro_items:
            parts.append(f"![{item['alt']}]({item['asset_path']})")

    for section_index, section in enumerate(sections):
        heading_line = f"{'#' * section.get('level', 2)} {section.get('heading', '')}".strip()
        parts.append(heading_line)
        blocks = [block for block in section.get("blocks") or [] if block.strip()]
        insert_map: dict[int, list[dict[str, Any]]] = {}
        trailing_items: list[dict[str, Any]] = []
        for item in section_items.get(section_index, []):
            if not blocks:
                trailing_items.append(item)
                continue
            block_index = item.get("placement_block_index", 0)
            if block_index >= len(blocks):
                trailing_items.append(item)
            else:
                insert_map.setdefault(block_index, []).append(item)

        for block_index, block in enumerate(blocks):
            parts.append(block)
            for item in insert_map.get(block_index, []):
                parts.append(f"![{item['alt']}]({item['asset_path']})")
        for item in trailing_items:
            parts.append(f"![{item['alt']}]({item['asset_path']})")

    return "\n\n".join(part.strip() for part in parts if part and part.strip()) + "\n"


def assemble_body(intro_blocks: list[str], sections: list[dict[str, Any]], plan_items: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    intro_items, section_items, inserted = collect_insertable_items(plan_items)
    body = render_body_from_blocks(intro_blocks, sections, intro_items, section_items)
    return body, inserted
