import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.delivery_report import build_delivery_report, markdown_delivery_report  # noqa: E402


class DeliveryReportTests(unittest.TestCase):
    def test_delivery_report_separates_draft_readback_from_quality_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text(
                "---\ntitle: Token工厂开始赚钱\nsummary: Token 成本进入企业账单，真正要看的是一次任务贵不贵。\n---\n\n正文。",
                encoding="utf-8",
            )
            (workspace / "publication.md").write_text("正文。", encoding="utf-8")
            (workspace / "article.wechat.html").write_text("<section><p>正文</p></section>", encoding="utf-8")
            (workspace / "score-report.json").write_text(
                json.dumps({"title": "Token工厂开始赚钱", "total_score": 82, "threshold": 88, "passed": False, "quality_gates": {"hook_layer_passed": False}}, ensure_ascii=False),
                encoding="utf-8",
            )
            (workspace / "acceptance-report.json").write_text(
                json.dumps({"title": "Token工厂开始赚钱", "passed": False, "failed_gates": ["first_screen_passed"]}, ensure_ascii=False),
                encoding="utf-8",
            )
            (workspace / "reader_gate.json").write_text(json.dumps({"passed": False, "failed_checks": ["首屏四问未齐"]}, ensure_ascii=False), encoding="utf-8")
            (workspace / "visual_gate.json").write_text(json.dumps({"passed": True, "planned_inline_count": 3}, ensure_ascii=False), encoding="utf-8")
            (workspace / "final_gate.json").write_text(
                json.dumps(
                    {"passed": False, "failed_checks": ["score_total_passed", "batch_uniqueness_passed"], "checks": {"batch_uniqueness_passed": False}},
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (workspace / "layout-plan.json").write_text(json.dumps({"recommended_style": "magazine"}, ensure_ascii=False), encoding="utf-8")
            (workspace / "layout-plan.md").write_text("# 版式规划\n", encoding="utf-8")
            (workspace / "image-plan.json").write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
            (workspace / "publish-result.json").write_text(
                json.dumps({"draft_media_id": "media-id", "verify_status": "passed", "expected_inline_count": 4, "verified_inline_count": 4}, ensure_ascii=False),
                encoding="utf-8",
            )
            (workspace / "latest-draft-report.json").write_text(
                json.dumps({"draft_media_id": "media-id", "verify_status": "passed", "expected_inline_count": 4, "verified_inline_count": 4, "verify_errors": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            manifest = {
                "selected_title": "Token工厂开始赚钱",
                "article_path": "article.md",
                "publication_path": "publication.md",
                "wechat_html_path": "article.wechat.html",
                "score_report_path": "score-report.json",
                "acceptance_report_path": "acceptance-report.json",
                "reader_gate_path": "reader_gate.json",
                "visual_gate_path": "visual_gate.json",
                "final_gate_path": "final_gate.json",
                "layout_plan_path": "layout-plan.json",
                "image_plan_path": "image-plan.json",
                "publish_result_path": "publish-result.json",
                "latest_draft_report_path": "latest-draft-report.json",
            }

            report = build_delivery_report(workspace, manifest)

            self.assertEqual(report["overall_status"], "failed")
            self.assertFalse(report["quality_passed"])
            self.assertTrue(report["published"])
            self.assertTrue(report["readback_passed"])
            self.assertEqual(report["sections"]["title"]["status"], "missing")
            self.assertEqual(report["publish_chain"]["status"], "passed")
            self.assertEqual(report["quality_chain"]["status"], "failed")
            self.assertEqual(report["batch_chain"]["status"], "failed")
            self.assertIn("title_gate_passed", report["quality_chain"]["failed_gates"])
            self.assertIn("hook_layer_passed", report["sections"]["quality"]["failed_gates"])
            self.assertTrue(any("合格成品" in item for item in report["warnings"]))
            self.assertTrue(any("标题" in item for item in report["warnings"]))
            rendered = markdown_delivery_report(report)
            self.assertIn("质量结果：未通过", rendered)
            self.assertIn("回读结果：通过", rendered)
            self.assertIn("发布链：通过", rendered)
            self.assertIn("质量链：未通过", rendered)
            self.assertIn("批次链：未通过", rendered)
            self.assertIn("成品状态：已发布，但质量未过", rendered)

    def test_delivery_report_requires_title_report_even_when_other_gates_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text("---\ntitle: 标题测试\nsummary: 摘要\n---\n\n正文。", encoding="utf-8")
            (workspace / "publication.md").write_text("正文。", encoding="utf-8")
            (workspace / "article.wechat.html").write_text("<section><p>正文</p></section>", encoding="utf-8")
            (workspace / "score-report.json").write_text(json.dumps({"passed": True, "quality_gates": {}}, ensure_ascii=False), encoding="utf-8")
            (workspace / "acceptance-report.json").write_text(json.dumps({"passed": True, "gates": {}}, ensure_ascii=False), encoding="utf-8")
            (workspace / "reader_gate.json").write_text(json.dumps({"passed": True}, ensure_ascii=False), encoding="utf-8")
            (workspace / "visual_gate.json").write_text(json.dumps({"passed": True}, ensure_ascii=False), encoding="utf-8")
            (workspace / "final_gate.json").write_text(json.dumps({"passed": True, "checks": {"batch_uniqueness_passed": True}}, ensure_ascii=False), encoding="utf-8")
            (workspace / "layout-plan.json").write_text(json.dumps({"recommended_style": "magazine"}, ensure_ascii=False), encoding="utf-8")
            (workspace / "layout-plan.md").write_text("# 版式规划\n", encoding="utf-8")
            (workspace / "image-plan.json").write_text(json.dumps({"items": []}, ensure_ascii=False), encoding="utf-8")
            manifest = {
                "selected_title": "标题测试",
                "article_path": "article.md",
                "publication_path": "publication.md",
                "wechat_html_path": "article.wechat.html",
                "score_report_path": "score-report.json",
                "acceptance_report_path": "acceptance-report.json",
                "reader_gate_path": "reader_gate.json",
                "visual_gate_path": "visual_gate.json",
                "final_gate_path": "final_gate.json",
                "layout_plan_path": "layout-plan.json",
                "image_plan_path": "image-plan.json",
            }
            report = build_delivery_report(workspace, manifest)
            self.assertFalse(report["quality_passed"])
            self.assertEqual(report["sections"]["title"]["status"], "missing")
            self.assertTrue(any(item == "title-decision-report.json/title-report.json" for item in report["quality_chain"]["missing_artifacts"]))


if __name__ == "__main__":
    unittest.main()
