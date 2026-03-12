import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


import legacy_studio as legacy  # noqa: E402
from core.rewrite import generate_revision_candidate  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
