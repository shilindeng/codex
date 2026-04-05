import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.title_decision import build_title_decision_report, title_integrity_report  # noqa: E402


class TitleDecisionTests(unittest.TestCase):
    def test_title_decision_prefers_fresh_and_author_fit_title(self):
        manifest = {
            "recent_article_titles": [
                "企业 AI Agent 落地这次真正的信号，不在表面热闹，而在更深一层",
                "为什么大多数人做不好企业AI转型？普通人一定要先想清这3件事",
            ],
            "recent_corpus_summary": {
                "overused_title_patterns": [
                    {"key": "signal-briefing", "label": "信号模板", "count": 8},
                    {"key": "why-think-clear", "label": "想清模板", "count": 10},
                ]
            },
            "author_memory": {
                "title_preferences": {"average_length": 18, "question_ratio": 0.0, "colon_ratio": 0.3},
                "editorial_preferences": {"preferred_style_keys": ["case-memo"]},
            },
            "editorial_blueprint": {
                "style_key": "case-memo",
                "allowed_title_patterns": ["case-memo", "generic"],
                "blocked_title_patterns": ["signal-briefing", "why-think-clear"],
            },
            "account_strategy": {
                "blocked_title_patterns": ["signal-briefing", "why-think-clear", "not-but"],
                "blocked_title_fragments": ["这次真正的信号", "真正值得聊的", "更深一层"],
            },
        }
        report = build_title_decision_report(
            topic="企业 AI Agent 落地",
            audience="创业者",
            angle="交付链路",
            candidates=[
                {"title": "企业 AI Agent 落地这次真正的信号，不在表面热闹，而在更深一层"},
                {"title": "为什么大多数人做不好企业AI转型？普通人一定要先想清这3件事"},
                {"title": "复盘企业 AI Agent 落地：团队一提速，为什么后面反而更难交付？"},
            ],
            manifest=manifest,
            research={"sources": [{"url": "https://example.com"}], "evidence_items": ["一处官方说明"]},
            editorial_blueprint=manifest["editorial_blueprint"],
            account_strategy=manifest["account_strategy"],
        )
        self.assertEqual(report["selected_title"], "复盘企业 AI Agent 落地：团队一提速，为什么后面反而更难交付？")
        self.assertTrue(report["candidates"][0]["title_gate_passed"])
        self.assertIn("decision_breakdown", report["candidates"][0])

    def test_title_integrity_rejects_broken_double_template(self):
        report = title_integrity_report(
            "银行业 AI 竞争突然提速，真正被重写的不是流程，而真正值得聊的，不是表面答案，而是判断顺序",
            topic="银行业 AI 竞争突然提速",
            account_strategy={"blocked_title_fragments": ["真正值得聊的", "不是表面答案"]},
        )
        self.assertFalse(report["passed"])
        self.assertTrue(any("拼接" in item or "高风险碎片" in item for item in report["issues"]))


if __name__ == "__main__":
    unittest.main()
