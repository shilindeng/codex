import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.workflow import build_generation_preflight_report, harden_generated_article_body  # noqa: E402


class GenerationGuardrailTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("ARTICLE_STUDIO_TEXT_MODEL", None)
        os.environ.pop("ARTICLE_STUDIO_TEXT_BASE_URL", None)
        os.environ.pop("ARTICLE_STUDIO_TEXT_PROVIDER", None)

    def test_generation_preflight_detects_repetition_and_missing_depth(self):
        manifest = {
            "audience": "大众读者",
            "direction": "",
            "source_urls": [],
            "author_memory": {
                "phrase_blacklist": ["说白了"],
                "sentence_starters_to_avoid": ["如果你"],
            },
        }
        body = "\n\n".join(
            [
                "如果你最近也在关注这件事，你会发现很多人都在重复一样的话。",
                "如果你继续往下写，很容易又掉回同一套句式。",
                "",
                "## 为什么这件事重要？",
                "说白了，这就是大家总会写得一样的原因。",
                "",
                "## 为什么后面还是会一样？",
                "说白了，问题还在重复开头和重复小标题。",
            ]
        )
        report = build_generation_preflight_report("测试标题", body, manifest, {})
        self.assertTrue(report.get("needs_hardening"))
        self.assertTrue(report.get("missing_elements"))
        severe_types = {item.get("type") for item in report.get("severe_findings") or []}
        self.assertIn("repeated_starter", severe_types)
        self.assertIn("author_phrase", severe_types)

    def test_generation_preflight_uses_content_enhancement_material_hints(self):
        manifest = {
            "audience": "大众读者",
            "direction": "",
            "source_urls": [],
            "content_enhancement": {
                "section_enhancements": [
                    {
                        "support_quotes": [{"text": "一次真实案例显示，团队卡住的不是模型，而是责任边界。"}],
                        "support_sources": [{"title": "官方案例", "url": "https://example.com/a"}],
                        "detail_anchors": ["补一个会议室里的瞬间。"],
                        "counterpoint_targets": ["补一句适用边界。"],
                    }
                ]
            },
        }
        body = "\n\n".join(
            [
                "首先，我们来看看这件事。",
                "",
                "其次，这确实值得讨论。",
                "",
                "最后，综上所述，事情大概就是这样。",
            ]
        )
        report = build_generation_preflight_report("测试标题", body, manifest, {})
        self.assertTrue(any("来源材料" in item for item in report.get("missing_elements") or []))
        self.assertTrue(any("优先把这一条来源材料写进正文" in item for item in report.get("rewrite_focus") or []))

    def test_harden_generated_article_body_runs_local_pre_fix(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {
                "audience": "大众读者",
                "direction": "",
                "source_urls": [],
                "author_memory": {"phrase_blacklist": ["说白了"], "sentence_starters_to_avoid": ["如果你"]},
            }
            body = "\n\n".join(
                [
                    "首先，我们来看看这件事。",
                    "其次，如果你继续这样写，重复感会越来越重。",
                    "最后，综上所述，文章会显得很像模板。",
                ]
            )
            hardened, report = harden_generated_article_body(
                workspace,
                manifest,
                "测试标题",
                "摘要",
                body,
                outline_meta={},
                allow_model_repair=False,
            )
            self.assertTrue(report.get("used_repaired_body"))
            self.assertNotEqual(hardened.strip(), body.strip())
            self.assertTrue((workspace / "generation-preflight.json").exists())
            self.assertTrue((workspace / "generation-preflight.md").exists())


if __name__ == "__main__":
    unittest.main()
