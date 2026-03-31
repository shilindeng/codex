import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.title_decision import build_title_decision_report  # noqa: E402


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
        }
        report = build_title_decision_report(
            topic="企业 AI Agent 落地",
            audience="创业者",
            angle="交付链路",
            candidates=[
                {"title": "企业 AI Agent 落地这次真正的信号，不在表面热闹，而在更深一层"},
                {"title": "为什么大多数人做不好企业AI转型？普通人一定要先想清这3件事"},
                {"title": "复盘企业 AI Agent 落地：真正拉开差距的，不是资源，而是判断顺序"},
            ],
            manifest=manifest,
            research={"sources": [{"url": "https://example.com"}], "evidence_items": ["一处官方说明"]},
            editorial_blueprint=manifest["editorial_blueprint"],
        )
        self.assertEqual(report["selected_title"], "复盘企业 AI Agent 落地：真正拉开差距的，不是资源，而是判断顺序")
        self.assertTrue(report["candidates"][0]["title_gate_passed"])
        self.assertIn("decision_breakdown", report["candidates"][0])


if __name__ == "__main__":
    unittest.main()
