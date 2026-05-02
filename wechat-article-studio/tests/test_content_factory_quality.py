import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.content_factory_quality import (  # noqa: E402
    build_draft_readability_audit,
    build_fact_source_map,
    build_image_asset_audit,
    build_section_quality_map,
    build_topic_heat_pack,
    build_topic_viral_bridge,
)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_article(workspace: Path, body: str) -> dict:
    (workspace / "article.md").write_text(f"---\ntitle: 测试标题\nsummary: 测试摘要\n---\n\n{body}", encoding="utf-8")
    manifest = {"selected_title": "测试标题", "topic": "测试选题", "article_path": "article.md"}
    write_json(workspace / "manifest.json", manifest)
    return manifest


def write_png(path: Path, width: int = 800, height: int = 450, filler: bytes = b"0") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    path.write_bytes(header + (filler * 5000))


class ContentFactoryQualityTests(unittest.TestCase):
    def test_fact_source_map_fails_when_critical_fact_has_no_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = write_article(workspace, "公开报道提到，2026 年这项政策会影响 3 类企业。真正的问题不是热闹，而是成本会先落到项目预算里。")
            report = build_fact_source_map(workspace, manifest)
            self.assertFalse(report["passed"])
            self.assertIn("has_sources_when_facts_present", report["failed_checks"])

    def test_section_quality_map_rejects_empty_core_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = write_article(workspace, "## 第一段\n这件事很重要，值得关注。\n\n## 第二段\n继续观察。")
            report = build_section_quality_map(workspace, manifest)
            self.assertFalse(report["passed"])
            self.assertGreaterEqual(report["failed_core_section_count"], 1)

    def test_draft_readability_audit_detects_collapsed_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = write_article(workspace, "正文")
            (workspace / "latest-draft-content.html").write_text("<section><img src='a.png'/><h2>标题</h2><ul><li>- 第一项 - 第二项 - 第三项</li></ul></section>", encoding="utf-8")
            report = build_draft_readability_audit(workspace, manifest)
            self.assertFalse(report["passed"])
            self.assertTrue(report["collapsed_list_detected"])

    def test_image_asset_audit_detects_placeholder_and_duplicate_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = write_article(workspace, "正文")
            write_png(workspace / "assets" / "same-a.png", width=1, height=1)
            write_png(workspace / "assets" / "same-b.png", width=1, height=1)
            image_plan = {
                "items": [
                    {"id": "a", "asset_path": "assets/same-a.png"},
                    {"id": "b", "asset_path": "assets/same-b.png"},
                ]
            }
            report = build_image_asset_audit(workspace, manifest, image_plan)
            self.assertFalse(report["passed"])
            self.assertIn("all_asset_files_exist_and_are_nontrivial", report["failed_checks"])
            self.assertIn("no_duplicate_image_hashes_in_article", report["failed_checks"])

    def test_topic_heat_pack_and_viral_bridge_check_hotspot_substance(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {
                "topic": "AI 设备补贴窗口",
                "selected_title": "AI 设备补贴窗口打开，旧产线先补哪一环",
                "topic_selected_index": 1,
                "audience": "产业升级读者",
                "repeat_risk": "low",
                "source_urls": ["https://example.com/a"],
            }
            discovery = {
                "provider": "test",
                "window_hours": 24,
                "sources": [{"link": "https://example.com/a"}, {"link": "https://news.example.com/b"}],
                "candidates": [
                    {
                        "recommended_topic": "AI 设备补贴窗口",
                        "recommended_title": "AI 设备补贴窗口打开，旧产线先补哪一环",
                        "hot_title": "AI 设备补贴窗口",
                        "summary": "公开报道引发企业预算争议。",
                        "heat_reason": "多地政策窗口集中发布",
                        "spread_reason": "企业会争论先买设备还是先补流程",
                        "title_direction_candidates": ["补贴来了，旧产线最该先补的不是设备", "AI 设备补贴打开后，老板会先问这笔账"],
                    },
                    {"recommended_topic": "旧产线升级", "hot_title": "旧产线升级清单", "summary": "同类企业讨论升级路径。"},
                ],
            }
            heat = build_topic_heat_pack(workspace, manifest, discovery=discovery, selected_candidate=discovery["candidates"][0])
            bridge = build_topic_viral_bridge(workspace, manifest, discovery=discovery, selected_candidate=discovery["candidates"][0])
            self.assertTrue(heat["passed"])
            self.assertTrue(bridge["passed"])
            self.assertGreaterEqual(len(bridge["similar_viral_samples"]), 2)


if __name__ == "__main__":
    unittest.main()
