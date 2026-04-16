import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.layout_plan import build_layout_plan  # noqa: E402


class LayoutPlanV2Tests(unittest.TestCase):
    def test_commentary_plan_outputs_hero_and_closing_modules(self):
        plan = build_layout_plan(
            "测试标题",
            "摘要",
            {
                "sections": [
                    {"heading": "大家真正误判了什么", "goal": "先拆误区", "evidence_need": "案例和误判"},
                    {"heading": "真正拉开差距的分水岭", "goal": "展开证据和判断", "evidence_need": "数据和事实"},
                    {"heading": "最后的判断", "goal": "收束判断", "evidence_need": "边界"},
                ],
                "viral_blueprint": {"article_archetype": "commentary"},
            },
            {"viral_blueprint": {"article_archetype": "commentary"}},
        )
        self.assertEqual(plan.get("hero_module"), "hero-judgment")
        self.assertEqual(plan.get("closing_module"), "takeaway-card")
        self.assertEqual(plan.get("lead_visual_policy"), "allow-before-first-h2")
        self.assertEqual(plan.get("lead_visual_deadline_ratio"), 0.25)
        self.assertEqual(plan.get("pre_h2_max_paragraphs"), 4)
        self.assertEqual(plan.get("section_modules")[0].get("heading_role"), "section-break")
        self.assertEqual(plan.get("section_modules")[-1].get("module_type"), "takeaway-card")

    def test_tutorial_plan_uses_checkpoint_and_action_close(self):
        plan = build_layout_plan(
            "RAG 实战指南",
            "摘要",
            {
                "sections": [
                    {"heading": "先别急着上工具", "goal": "讲误区", "evidence_need": "案例"},
                    {"heading": "真正该先做哪一步", "goal": "讲步骤", "evidence_need": "步骤"},
                    {"heading": "最后把动作收住", "goal": "收尾", "evidence_need": "提醒"},
                ],
                "viral_blueprint": {"article_archetype": "tutorial"},
            },
            {"viral_blueprint": {"article_archetype": "tutorial"}},
        )
        self.assertEqual(plan.get("hero_module"), "hero-checkpoint")
        self.assertEqual(plan.get("closing_module"), "action-close")
        self.assertIn("step-stack", [item.get("module_type") for item in plan.get("section_modules") or []])


if __name__ == "__main__":
    unittest.main()
