import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.generation_strategy import build_batch_guidance_payload, build_generation_strategy  # noqa: E402
from core.viral import normalize_outline_payload  # noqa: E402
from core.workflow import select_scored_title  # noqa: E402


class GenerationStrategyTests(unittest.TestCase):
    def test_batch_guidance_forbids_repeated_opening_and_double_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_root = Path(tmp)
            for name in ["20260418-01-a", "20260418-02-b"]:
                workspace = jobs_root / name
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "article.md").write_text(
                    "---\ntitle: 测试标题\nsummary: 摘要\n---\n\n那天会议室里，大家第一次认真讨论这个问题。\n\n## 带走这张判断卡\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n\n| C | D |\n| --- | --- |\n| 3 | 4 |",
                    encoding="utf-8",
                )
            current = jobs_root / "20260418-03-c"
            current.mkdir(parents=True, exist_ok=True)
            payload = build_batch_guidance_payload(jobs_root, "20260418", current_workspace=current)
            self.assertIn("scene-cut", payload.get("forbidden_opening_routes") or [])
            self.assertIn("judgment_card", payload.get("forbidden_ending_shapes") or [])
            self.assertEqual(payload.get("max_table_count"), 1)

    def test_build_generation_strategy_prefers_allowed_shape(self):
        strategy = build_generation_strategy(
            title="团队真正拉开的差距，不是工具，而是判断顺序",
            manifest={"audience": "团队负责人", "account_strategy": {"preferred_opening_modes": ["场景切口"]}},
            body="## 带走这张判断卡\n\n把这张判断卡留着。",
            batch_guidance={"forbidden_opening_routes": ["scene-cut"], "forbidden_ending_shapes": ["judgment_card"], "max_table_count": 1, "recommended_image_density": "balanced"},
            analysis_11d={"core_viewpoint": "真正的问题不是工具，而是判断顺序。", "interaction_hooks": {"save_triggers": ["把这张判断卡留着。"]}},
        )
        self.assertEqual(strategy["opening_strategy"]["route"], "cost-upfront")
        self.assertEqual(strategy["ending_strategy"]["shape"], "risk_warning")
        self.assertEqual(strategy["max_table_count"], 1)
        self.assertEqual(strategy["recommended_image_density"], "balanced")

    def test_select_scored_title_respects_batch_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {
                "recent_article_titles": [],
                "recent_corpus_summary": {},
                "editorial_blueprint": {"style_key": "signal-briefing"},
                "account_strategy": {},
                "batch_guidance": {"forbidden_title_patterns": ["why-think-clear"]},
            }
            ideation = {
                "titles": [
                    {"title": "为什么团队总是越忙越乱，先想清 3 件事"},
                    {"title": "团队真正拉开的差距，不是工具，而是判断顺序"},
                ]
            }
            ideation, _selected = select_scored_title(
                workspace,
                manifest,
                ideation,
                "AI 团队协作",
                "大众读者",
                "判断顺序",
            )
            self.assertEqual(ideation.get("selected_title"), "团队真正拉开的差距，不是工具，而是判断顺序")
            payload = json.loads((workspace / "title-decision-report.json").read_text(encoding="utf-8"))
            blocked = next(item for item in payload.get("candidates") or [] if "先想清 3 件事" in item.get("title", ""))
            self.assertFalse(blocked.get("title_gate_passed"))

    def test_outline_normalize_uses_generation_strategy(self):
        payload = normalize_outline_payload(
            {"sections": ["第一部分", "第二部分"]},
            {
                "topic": "测试主题",
                "selected_title": "测试标题",
                "audience": "大众读者",
                "direction": "",
                "research": {},
                "style_signals": [],
                "recent_corpus_summary": {},
                "content_mode": "tech-balanced",
                "editorial_blueprint": {"blocked_opening_patterns": ["scene-cut"]},
                "author_memory": {},
                "writing_persona": {},
                "generation_strategy": {
                    "opening_strategy": {"route": "cost-upfront"},
                    "ending_strategy": {"shape": "risk_warning", "allowed_shapes": ["风险提醒"], "heading_hint": "最后记住这条风险线"},
                },
            },
        )
        self.assertEqual(payload.get("opening_mode"), "代价先行切口")
        self.assertEqual(payload.get("ending_mode"), "风险提醒")
        self.assertEqual((payload.get("takeaway_strategy") or {}).get("allowed_shapes"), ["风险提醒"])


if __name__ == "__main__":
    unittest.main()
