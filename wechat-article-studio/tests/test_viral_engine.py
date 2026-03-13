import json
import sys
import tempfile
import unittest
import io
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.viral import build_score_report  # noqa: E402
from core.workflow import collect_publish_blockers, _run_revision_loop  # noqa: E402
import legacy_studio as legacy  # noqa: E402


class ViralEngineTests(unittest.TestCase):
    def test_score_report_has_quality_gates_and_can_pass(self):
        title = "为什么你越学越焦虑：真相是别再堆信息"
        body = "\n\n".join(
            [
                "先说结论：焦虑的不是你学得慢，而是你把力气花错了地方。",
                "你不是不够努力，只是方向错了。",
                "你会发现，越忙的人越焦虑。",
                "别急着自责，你缺的是判断。",
                "没关系，你现在开始也来得及。",
                "这很正常，你被信息洪流推着跑。",
                "不是你不行，而是方法不对。",
                "你并不需要把所有工具都学会。",
                "你可以先把最关键的动作做到位。",
                "至少今天，你先把一个动作做完。",
                "先别急着追热点，你先守住自己的节奏。",
                "很多人卡住在第一步：不知道怎么开始。",
                "被淘汰的恐惧，会让你越学越乱。",
                "如果你继续这样，代价是时间被浪费。",
                "最难受的是，你努力了却没结果。",
                "",
                "## 先把问题说透",
                "大多数人以为学得越多越安全，但真正让人掉队的是乱学。",
                "比如，一个团队把 2026年 的新工具都试了一遍，结果交付更慢。",
                "",
                "## 再给一个可执行的动作",
                "第一步：把你最近一周最耗时的动作写下来。",
                "第二步：删掉 80% 不产生结果的动作。",
                "第三步：把一个动作重复到位。",
                "官方文档 https://example.com/a 里写得很清楚，10% 的关键动作往往决定结果。",
                "报告 https://example.com/b 也提到同样的趋势，更多细节见 https://example.com/c 。",
                "",
                "## 最后给你一句话",
                "> 不是信息不够，而是判断不够。",
                "> 真正决定结果的，是你能否把关键动作重复到位。",
                "> 普通人拼信息，高手拼判断。",
                "作为编辑，我更想提醒你：别把努力浪费在看起来很忙的地方。",
                "我们都希望你能从今天开始，少一点焦虑，多一点掌控感。",
            ]
        ).strip()
        manifest = {"topic": "学习焦虑", "audience": "大众读者", "direction": "", "source_urls": ["https://example.com/a"]}

        report = build_score_report(title, body, manifest, threshold=88)
        self.assertIn("quality_gates", report)
        self.assertIn("passed", report)
        # This sample should be able to pass both total score and gates.
        self.assertTrue(bool(report.get("passed")))

    def test_publish_blockers_include_quality_gate_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {"text_model": "session", "selected_title": "t", "article_path": "article.md", "source_urls": []}
            (workspace / "score-report.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "quality_gates": {"de_ai_passed": False},
                        "score_breakdown": [{"dimension": "可信度与检索支撑", "weight": 10, "score": 10, "note": ""}],
                        "total_score": 99,
                        "threshold": 88,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            blockers = collect_publish_blockers(workspace, manifest)
            self.assertTrue(any("质量门槛未通过" in item for item in blockers))

    def test_revision_loop_writes_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {"selected_title": "测试", "audience": "大众读者", "direction": "", "article_path": "article.md", "source_urls": []},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("# 测试\n\n你不是不努力，只是方法不对。", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                score_report = _run_revision_loop(workspace, max_rounds=2, style_sample=[])
            self.assertIn("revision_rounds", score_report)
            self.assertIn("stop_reason", score_report)
            manifest = legacy.read_json(workspace / "manifest.json", default={}) or {}
            self.assertIsInstance(manifest.get("revision_rounds"), list)
            self.assertGreaterEqual(len(manifest.get("revision_rounds") or []), 1)


if __name__ == "__main__":
    unittest.main()
