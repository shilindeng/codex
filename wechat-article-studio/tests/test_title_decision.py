import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.editorial_strategy import generate_diverse_title_variants  # noqa: E402
from core.title_decision import build_title_decision_report, title_integrity_report  # noqa: E402
from core.workflow import select_scored_title  # noqa: E402


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
        self.assertIn("title_open_rate_score", report["candidates"][0])
        self.assertIn("title_gate_reason", report["candidates"][0])
        self.assertIn("title_formula_components", report["candidates"][0])
        self.assertIn("selected_explainer", report)
        self.assertIn("selected_title_contract", report)
        self.assertEqual(report["selected_title_contract"]["target_reader"], "创业者")
        self.assertIn("answer_too_complete", report["selected_title_contract"])

    def test_title_integrity_rejects_broken_double_template(self):
        report = title_integrity_report(
            "银行业 AI 竞争突然提速，真正被重写的不是流程，而真正值得聊的，不是表面答案，而是判断顺序",
            topic="银行业 AI 竞争突然提速",
            account_strategy={"blocked_title_fragments": ["真正值得聊的", "不是表面答案"]},
        )
        self.assertFalse(report["passed"])
        self.assertTrue(any("拼接" in item or "高风险碎片" in item for item in report["issues"]))

    def test_title_integrity_rejects_truncated_ascii_token(self):
        report = title_integrity_report("OpenAI推出ChatGPTW，最先吃亏的是组织流程")
        self.assertFalse(report["passed"])
        self.assertTrue(any("截断英文词" in item for item in report["issues"]))

    def test_generate_diverse_title_variants_does_not_cut_english_product_name_midway(self):
        titles = [
            item["title"]
            for item in generate_diverse_title_variants(
                topic="OpenAI推出ChatGPT Workspace，组织里最先被改写的是验收流程",
                angle="验收流程",
                audience="产品团队",
                count=8,
            )
        ]
        self.assertTrue(titles)
        self.assertFalse(any("ChatGPTW" in title or "Workspac" in title for title in titles))
        self.assertFalse(
            any(
                re.search(r"[A-Za-z]{4,}(?=[，,:：。！？?]|$)", title) and ("ChatGPTW" in title or "Workspac" in title)
                for title in titles
            )
        )

    def test_select_scored_title_triggers_rewrite_round_when_top_three_are_weak(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {
                "recent_article_titles": [
                    "这次真正的信号，不在表面热闹，而在更深一层",
                    "为什么大多数人做不好 AI 转型？普通人一定要先想清这3件事",
                ],
                "recent_corpus_summary": {
                    "overused_title_patterns": [
                        {"key": "signal-briefing", "label": "信号模板", "count": 8},
                        {"key": "why-think-clear", "label": "想清模板", "count": 10},
                    ]
                },
                "editorial_blueprint": {"style_key": "signal-briefing", "style_label": "信号简报"},
                "account_strategy": {
                    "blocked_title_patterns": ["signal-briefing", "why-think-clear", "not-but"],
                    "blocked_title_fragments": ["这次真正的信号", "更深一层"],
                },
            }
            ideation = {
                "titles": [
                    {"title": "这次真正的信号，不在表面热闹，而在更深一层"},
                    {"title": "为什么大多数人做不好 AI 转型？普通人一定要先想清这3件事"},
                    {"title": "AI 转型为什么重要"},
                ]
            }
            ideation, _selected = select_scored_title(
                workspace,
                manifest,
                ideation,
                "AI 转型",
                "大众读者",
                "从判断顺序和影响路径角度拆",
            )
            self.assertTrue((workspace / "title-decision-report.json").exists())
            payload = json.loads((workspace / "title-decision-report.json").read_text(encoding="utf-8"))
            self.assertEqual(payload.get("title_rewrite_round"), 1)
            self.assertGreaterEqual(len(payload.get("candidates") or []), 5)
            self.assertTrue(str(ideation.get("selected_title") or "").strip())

    def test_title_decision_dedupes_near_duplicate_titles_and_keeps_groups(self):
        manifest = {
            "recent_article_titles": [],
            "recent_corpus_summary": {},
            "author_memory": {},
            "editorial_blueprint": {"style_key": "case-memo"},
            "account_strategy": {},
        }
        report = build_title_decision_report(
            topic="企业 AI Agent 落地",
            audience="创业者",
            angle="交付链路",
            candidates=[
                {"title": "企业 AI Agent 落地：团队一提速，为什么后面反而更难交付？"},
                {"title": "企业 AI Agent 落地：团队一提速，为什么后面反而更难交付"},
                {"title": "企业 AI Agent 落地，真正该先看的是交付链路"},
                {"title": "企业 AI Agent 落地，别被参数热闹带着走"},
            ],
            manifest=manifest,
            research={"sources": [{"url": "https://example.com"}], "evidence_items": ["一处官方说明"]},
            editorial_blueprint=manifest["editorial_blueprint"],
            account_strategy=manifest["account_strategy"],
        )
        titles = [item["title"] for item in report.get("candidates") or []]
        self.assertLess(len(titles), 4)
        self.assertIn("candidate_groups", report)
        self.assertTrue(any(report.get("candidate_groups", {}).get(key) for key in ["强打开型", "强判断型", "强传播型", "稳妥保底型"]))

    def test_select_scored_title_manual_title_does_not_fall_back_to_legacy_side_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {
                "recent_article_titles": [],
                "recent_corpus_summary": {},
                "editorial_blueprint": {"style_key": "case-memo"},
                "account_strategy": {},
            }
            ideation = {"titles": [{"title": "企业 AI Agent 落地，别被参数热闹带着走"}]}
            manual_title = "企业 AI Agent 落地：团队一提速，为什么后面反而更难交付？"
            ideation, _selected = select_scored_title(
                workspace,
                manifest,
                ideation,
                "企业 AI Agent 落地",
                "创业者",
                "交付链路",
                manual_title,
            )
            payload = json.loads((workspace / "title-decision-report.json").read_text(encoding="utf-8"))
            self.assertTrue(any(item.get("title") == manual_title for item in payload.get("candidates") or []))
            self.assertIsInstance(ideation.get("selected_title_score"), int)


if __name__ == "__main__":
    unittest.main()
