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


from core.factory_acceptance import build_factory_acceptance_report, build_factory_audit  # noqa: E402
from core.workflow import write_delivery_report  # noqa: E402


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_fake_png(path: Path, width: int = 800, height: int = 450) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    path.write_bytes(header + (b"0" * 5000))


def seed_passed_workspace(workspace: Path) -> dict:
    article = """---
title: AI设备进了贷款支持清单，旧产线的升级窗口打开了
summary: 设备更新政策正在把 AI 生产工具推到更多旧产线前面。
---

一个工厂老板最怕的不是看不懂 AI，而是知道该换设备，却算不清这笔账什么时候回本。

公开报道提到，设备更新和技术改造正在进入更细的贷款支持清单。比如一条老产线，如果只补软件，不补检测设备，最后还是卡在交付质量上。

这件事好比给旧车换导航：路线变聪明了，但刹车和轮胎不跟上，速度越快风险越大。

| 表面变化 | 真正影响 |
| --- | --- |
| 多了贷款工具 | 决策从买不买变成先改哪一环 |

不是所有工厂都该立刻上 AI，而是先看质量、交期和现金流哪一个最先成为边界。
"""
    (workspace / "article.md").write_text(article, encoding="utf-8")
    (workspace / "publication.md").write_text(article, encoding="utf-8")
    write_json(
        workspace / "references.json",
        {
            "items": [
                {
                    "title": "AI equipment upgrade source",
                    "url": "https://example.com/a",
                    "summary": article,
                }
            ]
        },
    )
    (workspace / "article.wechat.html").write_text(
        "<section><img src='a.png'/><h2>现场</h2><p>正文</p><h2>对比</h2><table><tr><td>表</td></tr></table><h2>结尾</h2><p>参考来源</p></section>",
        encoding="utf-8",
    )
    write_json(workspace / "title-decision-report.json", {"selected_title": "AI设备进了贷款支持清单，旧产线的升级窗口打开了", "candidates": [{"title": "AI设备进了贷款支持清单，旧产线的升级窗口打开了", "title_gate_passed": True}]})
    write_json(workspace / "score-report.json", {"passed": True, "total_score": 90, "threshold": 88, "quality_gates": {"template_penalty_passed": True, "batch_uniqueness_passed": True}})
    write_json(workspace / "acceptance-report.json", {"passed": True, "gates": {"batch_uniqueness_passed": True}})
    write_json(
        workspace / "reader_gate.json",
        {
            "passed": True,
            "opening_four_factors_passed": True,
            "share_lines": ["旧产线最怕的不是贵，而是先改错地方。", "贷款支持改变的是升级顺序。", "AI设备真正考验的是现金流。"],
            "share_line_score": 10,
            "comment_seed": "你觉得旧产线最该先补哪一环？",
            "takeaway_module_type": "对比表",
            "counterpoint_count": 1,
            "hard_evidence_types": ["source", "comparison", "role"],
        },
    )
    write_json(workspace / "visual_gate.json", {"passed": True, "planned_inline_count": 1, "failed_checks": []})
    write_json(
        workspace / "final_gate.json",
        {
            "passed": True,
            "checks": {
                "batch_uniqueness_passed": True,
                "opening_four_factors_passed": True,
                "takeaway_module_passed": True,
            },
        },
    )
    write_json(workspace / "layout-plan.json", {"hero_template": "scene"})
    (workspace / "layout-plan.md").write_text("# layout\n", encoding="utf-8")
    write_fake_png(workspace / "assets" / "images" / "cover.png")
    write_json(
        workspace / "image-plan.json",
        {
            "provider": "codex",
            "planned_inline_count": 1,
            "items": [
                {
                    "id": "cover-01",
                    "type": "封面图",
                    "asset_path": "assets/images/cover.png",
                    "insert_strategy": "section_middle",
                    "role": "explain",
                    "text_policy": "short-zh",
                    "required_text": ["升级窗口"],
                }
            ],
        },
    )
    write_json(workspace / "publish-result.json", {"draft_media_id": "media-id", "verify_status": "passed"})
    write_json(workspace / "latest-draft-report.json", {"verify_status": "passed", "verified_inline_count": 1})
    manifest = {
        "selected_title": "AI设备进了贷款支持清单，旧产线的升级窗口打开了",
        "topic": "AI设备贷款支持",
        "topic_score_100": 91,
        "topic_heat_reason": "政策窗口正在影响旧产线设备更新节奏。",
        "repeat_risk": "low",
        "audience": "关注产业升级的公众号读者",
        "article_path": "article.md",
        "publication_path": "publication.md",
        "wechat_html_path": "article.wechat.html",
        "source_urls": ["https://example.com/a", "https://example.com/b"],
    }
    write_json(workspace / "manifest.json", manifest)
    return manifest


class FactoryAcceptanceTests(unittest.TestCase):
    def test_factory_acceptance_marks_force_published_quality_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text("---\ntitle: 测试\nsummary: 摘要\n---\n\n正文。", encoding="utf-8")
            write_json(workspace / "score-report.json", {"passed": False, "total_score": 73, "threshold": 88})
            write_json(workspace / "reader_gate.json", {"passed": False, "opening_four_factors_passed": False, "failed_checks": ["首屏四问未齐"]})
            write_json(workspace / "visual_gate.json", {"passed": False, "failed_checks": ["图片文字策略不符合当前规则"]})
            write_json(workspace / "final_gate.json", {"passed": False, "checks": {"batch_uniqueness_passed": False}})
            manifest = {"selected_title": "测试", "article_path": "article.md", "force_publish_reason": "用户要求先发草稿箱"}
            delivery = {
                "published": True,
                "readback_passed": True,
                "force_publish": True,
                "quality_passed": False,
                "publish_chain": {"published": True, "readback_passed": True, "force_publish": True},
                "quality_chain": {"passed": False},
                "batch_chain": {"status": "failed"},
            }
            report = build_factory_acceptance_report(workspace, manifest, delivery)
            self.assertEqual(report["status"], "force_publish_only")
            self.assertEqual(report["grade_label"], "已发布但不合格")
            self.assertIn("title_report_missing", report["blocking_reasons"])
            self.assertIn("first_screen_failed", report["blocking_reasons"])
            self.assertLessEqual(len(report["top_rework_actions"]), 3)

    def test_write_delivery_report_creates_factory_artifacts_for_true_qualified_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = seed_passed_workspace(workspace)
            payload = write_delivery_report(workspace, manifest)
            self.assertEqual(payload["factory_status"], "passed")
            self.assertTrue(payload["factory_ready"])
            for name in [
                "factory-acceptance-report.json",
                "topic-heat-pack.json",
                "topic-package.json",
                "material-pack.json",
                "fact-source-map.json",
                "section-quality-map.json",
                "viral-moment-map.json",
                "layout-render-audit.json",
                "draft-readability-audit.json",
                "image-asset-audit.json",
                "title-performance-report.json",
            ]:
                self.assertTrue((workspace / name).exists(), name)

    def test_factory_audit_summarizes_true_qualified_and_published_unqualified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            passed = root / "passed"
            passed.mkdir()
            manifest = seed_passed_workspace(passed)
            write_delivery_report(passed, manifest)

            failed = root / "failed"
            failed.mkdir()
            (failed / "manifest.json").write_text(json.dumps({"selected_title": "失败样本", "force_publish_reason": "先发"}, ensure_ascii=False), encoding="utf-8")
            (failed / "article.md").write_text("---\ntitle: 失败样本\nsummary: 摘要\n---\n\n正文。", encoding="utf-8")
            write_json(failed / "final-delivery-report.json", {"published": True, "readback_passed": True, "force_publish": True, "quality_chain": {"passed": False}})

            audit = build_factory_audit(root)
            self.assertEqual(audit["metrics"]["total"], 2)
            self.assertEqual(audit["metrics"]["true_qualified_count"], 1)
            self.assertEqual(audit["metrics"]["published_unqualified_count"], 1)
            self.assertTrue(audit["top_blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
