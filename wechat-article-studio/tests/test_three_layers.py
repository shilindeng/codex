import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.three_layers import (  # noqa: E402
    build_three_layer_diagnostics,
    default_layer_strategies,
    hook_layer_report,
    insight_layer_report,
    takeaway_layer_report,
)
from core.viral import build_score_report, normalize_outline_payload  # noqa: E402


class ThreeLayerTests(unittest.TestCase):
    def test_default_layer_strategies_exist_for_commentary(self):
        payload = default_layer_strategies(archetype="commentary", title="测试标题", topic="测试主题", audience="大众读者")
        self.assertIn("hook_strategy", payload)
        self.assertIn("insight_strategy", payload)
        self.assertIn("takeaway_strategy", payload)
        self.assertTrue(payload["takeaway_strategy"]["forbidden_moves"])

    def test_hook_layer_report_requires_title_and_first_screen_alignment(self):
        passed = hook_layer_report(
            "公司最先踩空的，不是预算，而是流程顺序",
            "\n\n".join(
                [
                    "周一早上九点，会议室里没人敢先开口。",
                    "真正的问题不是要不要上 AI，而是这件事会先让谁来买单。",
                    "后面继续展开。",
                ]
            ),
            topic="AI 转型",
            audience="大众读者",
        )
        failed = hook_layer_report(
            "AI 正在快速发展",
            "\n\n".join(["这是行业背景。", "这是泛泛说明。"]),
            topic="AI 转型",
            audience="大众读者",
        )
        self.assertTrue(passed["passed"])
        self.assertFalse(failed["passed"])

    def test_insight_layer_report_requires_two_core_hits_and_transferability(self):
        report = insight_layer_report(
            "正文。",
            analysis={"core_viewpoint": "真正的问题是判断顺序错了。", "secondary_viewpoints": ["旧流程会先拖垮结果。", "真正稀缺的是判断顺序。"]},
            depth={"counterpoint_paragraph_count": 1, "evidence_paragraph_count": 2, "long_paragraph_count": 1},
            material_signals={"has_table": True, "comparison_count": 1, "analogy_count": 1, "citation_count": 2, "coverage_count": 4},
        )
        self.assertTrue(report["passed"])

    def test_takeaway_layer_report_requires_reusable_tail_and_save_trigger(self):
        passed = takeaway_layer_report(
            "\n\n".join(
                [
                    "前文展开。",
                    "## 最后带走这张判断卡",
                    "把这张判断卡留着：下次只要团队越忙越乱，先检查是不是把“补工具”放在了“改动作”前面。",
                    "收藏这条，复盘时直接对照，也可以转给要一起改流程的人。",
                ]
            ),
            archetype="commentary",
            analysis={"ending_interaction_design": "结尾先收束成判断卡，再让读者想保存。"},
            material_signals={"has_table": True},
        )
        failed = takeaway_layer_report(
            "\n\n".join(["前文展开。", "最后的判断。", "如果是你，你会怎么选？"]),
            archetype="commentary",
            analysis={},
            material_signals={},
        )
        self.assertTrue(passed["passed"])
        self.assertFalse(failed["passed"])

    def test_outline_normalization_exposes_three_layer_strategies(self):
        outline = normalize_outline_payload(
            {},
            {"topic": "测试主题", "selected_title": "测试标题", "audience": "大众读者", "direction": "", "research": {}},
        )
        self.assertIn("hook_strategy", outline)
        self.assertIn("insight_strategy", outline)
        self.assertIn("takeaway_strategy", outline)
        self.assertIn("takeaway_scaffold", outline)
        self.assertTrue(outline["takeaway_scaffold"].get("core_line"))

    def test_score_report_exposes_three_layer_scores_and_gates(self):
        title = "公司最先踩空的，不是预算，而是流程顺序"
        body = "\n\n".join(
            [
                "周一早上九点，会议室里没人敢先开口。",
                "真正的问题不是要不要上 AI，而是这件事会先让谁来买单。",
                "多数团队卡住，不是因为工具不够，而是因为流程顺序一直排反了。",
                "根据一份行业报告，返工最常见的根源就是先补工具、后改动作 [1]。",
                "",
                "| 表面动作 | 真正该做的事 |",
                "| --- | --- |",
                "| 继续补工具 | 先改关键动作 |",
                "",
                "这就像收拾行李：东西当然越多越安全，但真正让你赶得上车的，往往是先把最关键的那几件装进去。",
                "## 最后带走这张判断卡",
                "把这张判断卡留着：下次只要项目越忙越乱，先检查是不是把“补工具”放在了“改动作”前面。",
                "收藏这条，复盘时直接对照，也可以转给一起背结果的人。",
            ]
        ).strip()
        tmp = Path("D:/vibe-coding/local/.wechat-jobs")
        manifest = {"topic": title, "audience": "大众读者", "direction": "", "source_urls": ["https://example.com/a"]}
        report = build_score_report(title, body, manifest, threshold=70)
        self.assertIn("hook_layer_score", report)
        self.assertIn("insight_layer_score", report)
        self.assertIn("takeaway_layer_score", report)
        self.assertTrue(report.get("hook_layer_passed"))
        self.assertTrue(report.get("insight_layer_passed"))
        self.assertTrue(report.get("takeaway_layer_passed"))


@unittest.skipUnless(Path(r"D:\vibe-coding\local\.wechat-jobs").exists(), "local regression corpus not available")
class ThreeLayerRealCorpusTests(unittest.TestCase):
    ROOT = Path(r"D:\vibe-coding\local\.wechat-jobs")

    def test_real_jobs_match_expected_layer_pattern(self):
        import legacy_studio as legacy  # noqa: E402

        expectations = {
            "20260411-12-anthropic-mythos-risk": {"hook": True, "takeaway": False},
            "20260411-13-openai-ads-model": {"hook": True, "takeaway": False},
            "20260411-14-ai-companion-rules": {"hook": True, "takeaway": False},
            "20260411-15-ai-education-plan": {"hook": True, "takeaway": False},
            "20260411-16-beijing-ai-coverage": {"hook": False, "takeaway": False},
            "20260411-17-ai-pilot-trap": {"hook": True, "takeaway": False},
            "20260411-18-ai-clone-boundary": {"hook": True, "takeaway": False},
        }
        for name, expected in expectations.items():
            with self.subTest(name=name):
                ws = self.ROOT / name
                meta, body = legacy.split_frontmatter((ws / "article.md").read_text(encoding="utf-8"))
                title = str(meta.get("title") or "")
                manifest = legacy.load_manifest(ws)
                manifest["summary"] = str(meta.get("summary") or manifest.get("summary") or "")
                report = build_score_report(title, body, manifest, threshold=70)
                self.assertEqual(bool(report.get("hook_layer_passed")), expected["hook"])
                self.assertEqual(bool(report.get("takeaway_layer_passed")), expected["takeaway"])


if __name__ == "__main__":
    unittest.main()
