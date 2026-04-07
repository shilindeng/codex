import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


import legacy_studio as legacy  # noqa: E402
from core.rewrite import generate_revision_candidate  # noqa: E402
from core.workflow import cmd_doctor  # noqa: E402


class RewriteModeTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("ARTICLE_STUDIO_TEXT_MODEL", None)
        os.environ.pop("ARTICLE_STUDIO_TEXT_BASE_URL", None)
        os.environ.pop("ARTICLE_STUDIO_TEXT_PROVIDER", None)

    def test_de_ai_mode_generates_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            title = "测试标题"
            meta = {"title": title, "summary": "摘要"}
            body = "首先，我们来看看。其次，这很重要。最后，综上所述。"
            manifest = {"source_urls": [], "audience": "大众读者", "direction": ""}
            report = legacy.build_score_report(title, body, manifest, threshold=85)

            rewrite = generate_revision_candidate(
                workspace,
                title,
                meta,
                body,
                report,
                manifest,
                output_name="article-rewrite.md",
                mode="de-ai",
            )
            self.assertEqual(rewrite.get("mode"), "de-ai")
            self.assertTrue((workspace / "article-rewrite.md").exists())
            self.assertTrue((workspace / "article-rewrite.report.md").exists())
            self.assertTrue((workspace / "article-rewrite.rewrite.json").exists())

            payload = json.loads((workspace / "article-rewrite.rewrite.json").read_text(encoding="utf-8"))
            hits = payload.get("diff_metrics", {}).get("ai_style_hits", {})
            self.assertIsInstance(hits.get("before"), int)
            self.assertIsInstance(hits.get("after"), int)

    def test_improve_score_mode_generates_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            title = "测试标题"
            meta = {"title": title, "summary": "摘要"}
            sample_source = workspace / "source.html"
            sample_source.write_text(
                "<html><head><title>官方说明</title></head><body><p>根据 2026 年官方文档：这个功能已经发布。</p></body></html>",
                encoding="utf-8",
            )
            body = "首先，我们来看看。其次，这很重要。最后，综上所述。"
            manifest = {"source_urls": [sample_source.resolve().as_uri()], "audience": "大众读者", "direction": ""}
            report = legacy.build_score_report(title, body, manifest, threshold=85)

            rewrite = generate_revision_candidate(
                workspace,
                title,
                meta,
                body,
                report,
                manifest,
                output_name="article-rewrite.md",
                mode="improve-score",
            )
            self.assertEqual(rewrite.get("mode"), "improve-score")
            self.assertTrue((workspace / "article-rewrite.report.md").exists())
            self.assertEqual(rewrite.get("evidence_report_path"), "evidence-report.json")
            self.assertGreaterEqual(int(rewrite.get("evidence_used_count") or 0), 0)

    def test_improve_score_mode_for_analysis_does_not_force_execution_checklist(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            title = "为什么 AI 公司迟早都要面对变现问题？"
            meta = {"title": title, "summary": "摘要"}
            body = (
                "很多人以为 AI 产品竞争只是在比模型参数，但真正难的，是找到能长期成立的商业逻辑。"
                "\n\n"
                "## 为什么这件事现在更重要\n\n"
                "因为成本、调用频率、用户预期和信任问题正在同时抬头。"
                "\n\n"
                "## 真正的分水岭在哪里\n\n"
                "真正拉开差距的，往往不是多一个功能，而是你的产品最后靠什么活下去。"
            )
            manifest = {"source_urls": [], "audience": "大众读者", "direction": ""}
            report = legacy.build_score_report(title, body, manifest, threshold=85)

            generate_revision_candidate(
                workspace,
                title,
                meta,
                body,
                report,
                manifest,
                output_name="article-rewrite.md",
                mode="improve-score",
            )
            rewritten = (workspace / "article-rewrite.md").read_text(encoding="utf-8")
            self.assertNotIn("最后给你一个可执行清单", rewritten)
            self.assertNotIn("## 最后给你一个可执行清单", rewritten)

    def test_de_ai_mode_uses_humanizerai_bridge_when_configured(self):
        class FakeHumanizer:
            def configured(self):
                return True

            def detect(self, text):
                overall = 86 if "首先" in text else 42
                return {"score_overall": overall, "score": {"overall": overall}}

            def humanize(self, text, intensity):
                return {
                    "text": "昨晚我又把这篇稿子顺了一遍。\n\n这一版更像一个人在说话。\n",
                    "intensity": intensity,
                    "credits_remaining": 999,
                }

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            title = "测试标题"
            meta = {"title": title, "summary": "摘要"}
            body = "首先，我们来看看。其次，这很重要。最后，综上所述。"
            manifest = {"source_urls": [], "audience": "大众读者", "direction": ""}
            report = legacy.build_score_report(title, body, manifest, threshold=85)

            with patch("core.rewrite._humanizer_client_for_rewrite", return_value=FakeHumanizer()):
                rewrite = generate_revision_candidate(
                    workspace,
                    title,
                    meta,
                    body,
                    report,
                    manifest,
                    output_name="article-rewrite.md",
                    mode="de-ai",
                )

            payload = json.loads((workspace / "article-rewrite.rewrite.json").read_text(encoding="utf-8"))
            self.assertEqual(rewrite.get("mode"), "de-ai")
            self.assertEqual(payload.get("humanizerai", {}).get("applied_intensity"), "aggressive")
            self.assertEqual(payload.get("humanizerai", {}).get("before", {}).get("score_overall"), 86)
            self.assertEqual(payload.get("humanizerai", {}).get("after", {}).get("score_overall"), 42)
            self.assertIn("HumanizerAI", "\n".join(payload.get("applied_actions") or []))
            rewritten = (workspace / "article-rewrite.md").read_text(encoding="utf-8")
            self.assertIn("更像一个人在说话", rewritten)

    def test_doctor_reports_humanizerai_bridge_status(self):
        class FakeHumanizer:
            def doctor_status(self):
                return {"configured": True, "base_url": "https://humanizerai.com/api/v1"}

        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            with patch("core.workflow.HumanizerAIClient.from_env", return_value=FakeHumanizer()):
                with patch("sys.stdout.write") as fake_write:
                    cmd_doctor(type("Args", (), {"workspace": str(workspace)})())
            combined = "".join(call.args[0] for call in fake_write.call_args_list)
            self.assertIn('"de_ai_bridge"', combined)
            self.assertIn('"humanizerai"', combined)
            self.assertIn('"configured": true', combined.lower())


if __name__ == "__main__":
    unittest.main()
