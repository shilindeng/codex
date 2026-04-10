import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.ai_fingerprint import detect_ai_fingerprints  # noqa: E402
from core.viral import build_score_report  # noqa: E402
from core.workflow import build_generation_preflight_report  # noqa: E402


class AIFingerprintIntegrationTests(unittest.TestCase):
    def test_detect_ai_fingerprints_catches_dead_opening_and_blessing_close(self):
        body = "\n\n".join(
            [
                "大家好，今天想跟你聊聊为什么普通人总是把重点放错。",
                "如果你最近很焦虑，也总觉得自己做了很多却没结果，接下来这篇文章会给你答案。",
                "真正的问题，是你把所有动作都做成了表演。",
                "最后，愿你别再怀疑自己，你值得更好的结果。",
            ]
        )
        findings = detect_ai_fingerprints(body)
        finding_types = {item.get("type") for item in findings}
        self.assertIn("dead_opening_self_intro", finding_types)
        self.assertIn("opening_triad", finding_types)
        self.assertIn("blessing_close", finding_types)

    def test_generation_preflight_raises_dbskill_style_rewrite_focus(self):
        manifest = {"audience": "大众读者", "direction": "", "source_urls": []}
        body = "\n\n".join(
            [
                "如果你最近也在焦虑没流量、没结果、做不好，这篇文章会告诉你一个真正的答案。",
                "你可能会觉得问题出在执行力，其实不是。",
                "归根结底，本质上是你一直在用错误的方法理解问题。",
            ]
        )
        report = build_generation_preflight_report("测试标题", body, manifest, {})
        severe_types = {item.get("type") for item in report.get("severe_findings") or []}
        self.assertIn("opening_triad", severe_types)
        self.assertIn("reader_strawman", severe_types)
        rewrite_focus = report.get("rewrite_focus") or []
        self.assertTrue(any("真实处境" in item or "卖焦虑" in item for item in rewrite_focus))

    def test_score_report_exposes_ai_fingerprint_summary_and_humanness_penalty(self):
        manifest = {"topic": "测试主题", "audience": "大众读者", "direction": "", "source_urls": []}
        body = "\n\n".join(
            [
                "你可能会觉得问题只是不会用工具，但这篇文章会直接告诉你答案。",
                "本质上，归根结底，真正重要的不是表面的动作，而是底层逻辑。",
                "有人跟我说过这件事，但故事本身并没有更多细节。",
                "最后，愿你别再怀疑自己，你值得被看见。",
            ]
        )
        report = build_score_report("测试标题", body, manifest, threshold=70)
        self.assertIn("ai_fingerprint_summary", report)
        self.assertGreaterEqual(int(report["ai_fingerprint_summary"].get("strong_count") or 0), 1)
        self.assertTrue(any(item.get("type") == "reader_strawman" for item in report.get("ai_smell_findings") or []))
        self.assertTrue(any("AI 指纹" in item for item in report.get("humanness_findings") or []))


if __name__ == "__main__":
    unittest.main()
