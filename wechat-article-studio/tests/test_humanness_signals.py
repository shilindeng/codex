import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.viral import _depth_signals, build_score_report  # noqa: E402


class HumannessSignalTests(unittest.TestCase):
    def test_depth_signals_do_not_treat_browser_word_as_scene_or_generic_not_but_as_counterpoint(self):
        body = "\n\n".join(
            [
                "Anthropic 官方本来就有公开的 claude-code 仓库。",
                "Anthropic 更厉害的地方，不是把模型做成聊天窗口，而是把终端、工具和工作流接成一条线。",
                "浏览器只是入口之一，但这段话本身并没有具体现场、时间和动作细节。",
            ]
        )
        signals = _depth_signals(body, {"topic": "Claude Code", "selected_title": "Claude Code"})
        self.assertEqual(signals.get("scene_paragraph_count"), 0)
        self.assertEqual(signals.get("counterpoint_paragraph_count"), 0)

    def test_score_report_exposes_humanness_signals(self):
        title = "企业 AI 转型真正要先讲清楚的，不是工具"
        body = "\n\n".join(
            [
                "那天会议室里，大家第一次认真讨论 AI 要替团队扛什么结果。",
                "真正的问题不是会不会用，而是先把什么结果讲清楚。",
                "一份官方文档已经把边界写得很明白 [1]。",
                "但如果忽略责任归属，再好的工具也会被用成热闹。",
                "最后真正该记住的，不是工具，而是判断顺序。",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "references.json").write_text(
                json.dumps({"items": [{"index": 1, "url": "https://example.com", "title": "官方文档"}]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            manifest = {
                "topic": title,
                "audience": "大众读者",
                "direction": "",
                "workspace": str(workspace),
                "references_path": "references.json",
                "source_urls": ["https://example.com"],
                "writing_persona": {"name": "industry-observer"},
            }
            report = build_score_report(title, body, manifest, threshold=70)
        self.assertIn("humanness_signals", report)
        self.assertIn("humanness_score", report)
        self.assertIn("humanness_findings", report)


if __name__ == "__main__":
    unittest.main()
