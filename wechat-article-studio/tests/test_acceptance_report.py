import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.acceptance import build_acceptance_report  # noqa: E402


class AcceptanceReportTests(unittest.TestCase):
    def test_acceptance_report_passes_for_balanced_article(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.wechat.html").write_text('<section><p>摘要</p><p>正文片段</p><section data-wx-role="reference-list"><section data-wx-role="reference-card"></section></section></section>', encoding="utf-8")
            (workspace / "image-plan.json").write_text(
                json.dumps(
                    {
                        "article_visual_strategy": {"visual_route": "cold-hard"},
                        "items": [
                            {"id": "cover-01", "type": "封面图", "text_policy": "none", "article_visual_strategy": {"visual_route": "cold-hard"}},
                            {"id": "inline-01", "type": "正文插图", "text_policy": "none", "article_visual_strategy": {"visual_route": "cold-hard"}},
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "references.json").write_text(
                json.dumps({"items": [{"index": 1, "url": "https://example.com", "title": "官方文档"}]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            manifest = {
                "selected_title": "企业 AI 转型真正要先讲清楚的，不是工具",
                "wechat_html_path": "article.wechat.html",
                "references_path": "references.json",
                "image_plan_path": "image-plan.json",
                "wechat_header_mode": "drop-title",
                "viral_blueprint": {"article_archetype": "commentary", "primary_interaction_goal": "comment/share", "secondary_interaction_goal": "like"},
                "editorial_blueprint": {"style_key": "signal-briefing"},
                "research_requirements": {"requires_evidence": True, "passed": True},
            }
            score_report = {
                "passed": True,
                "depth_signals": {
                    "scene_paragraph_count": 1,
                    "evidence_paragraph_count": 1,
                    "counterpoint_paragraph_count": 1,
                    "long_paragraph_count": 1,
                    "paragraph_count": 6,
                },
                "viral_analysis": {
                    "core_viewpoint": "真正的问题不是会不会用，而是结果、责任和流程顺序不能说反。",
                    "secondary_viewpoints": ["返工会先冒出来。", "责任归属不清会先拖垮流程。"],
                },
                "material_signals": {"has_table": True, "comparison_count": 1, "analogy_count": 1, "citation_count": 2, "coverage_count": 4},
                "quality_gates": {"credibility_passed": True},
            }
            review_report = {"editorial_review": {"ending_naturalness": "high"}}
            layout_plan = {"recommended_style": "magazine", "section_plans": [{"module_type": "summary-card"}, {"module_type": "case-card"}, {"module_type": "conclusion-card"}], "module_types": ["summary-card", "case-card", "conclusion-card"]}
            body = "\n\n".join(
                [
                    "那天会议室里，大家第一次认真讨论 AI 要替团队扛什么结果。",
                    "真正的问题不是会不会用，而是如果先把结果、责任和流程顺序说反了，后面返工和买单都会一起冒出来。",
                    "一份官方文档已经把边界写得很明白。",
                    "但如果忽略责任归属，再好的工具也会被用成热闹。",
                    "## 带走这张判断卡",
                    "把这张判断卡留着：下次只要项目越忙越乱，先检查是不是结果、责任和流程顺序说反了。收藏这条，复盘时直接对照。",
                ]
            )
            payload = build_acceptance_report(
                workspace,
                manifest,
                title="企业 AI 转型真正要先讲清楚的，不是工具",
                summary="那天会议室里大家第一次认真讨论 AI 要替团队扛什么结果，真正要先补的不是工具，而是责任归属和流程顺序。",
                body=body,
                score_report=score_report,
                review_report=review_report,
                layout_plan=layout_plan,
                recent_fingerprints=[],
            )
            self.assertTrue(payload["gates"]["score_passed"])
            self.assertTrue(payload["gates"]["opening_scene_passed"])
            self.assertTrue(payload["gates"]["evidence_passed"])
            self.assertTrue(payload["gates"]["layout_plan_passed"])
            self.assertTrue(payload["gates"]["reference_tail_passed"])
            self.assertTrue(payload["gates"]["title_consistency_passed"])
            self.assertTrue(payload["gates"]["evidence_minimum_passed"])
            self.assertTrue(payload["gates"]["first_screen_passed"])
            self.assertTrue(payload["gates"]["hook_layer_passed"])
            self.assertTrue(payload["gates"]["insight_layer_passed"])
            self.assertTrue(payload["gates"]["takeaway_layer_passed"])
            self.assertTrue(payload["gates"]["image_text_density_passed"])
            self.assertTrue(payload["gates"]["score_ready"])
            self.assertTrue(payload["gates"]["render_ready"])
            self.assertTrue(payload.get("body_signature"))
            self.assertIn("dimension_11d_summary", payload)
            self.assertEqual(payload.get("schema_version"), "2026-04-v3")

    def test_acceptance_report_fails_when_reference_cards_not_rendered(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.wechat.html").write_text("<section><p>正文片段</p></section>", encoding="utf-8")
            (workspace / "image-plan.json").write_text(
                json.dumps(
                    {
                        "article_visual_strategy": {"visual_route": "data-explainer"},
                        "items": [
                            {"id": "cover-01", "type": "封面图", "text_policy": "short-any", "article_visual_strategy": {"visual_route": "data-explainer"}},
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "references.json").write_text(
                json.dumps({"items": [{"index": 1, "url": "https://example.com", "title": "官方文档"}]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            manifest = {
                "selected_title": "测试标题",
                "wechat_html_path": "article.wechat.html",
                "references_path": "references.json",
                "image_plan_path": "image-plan.json",
                "wechat_header_mode": "drop-title",
                "research_requirements": {"requires_evidence": True, "passed": True},
            }
            payload = build_acceptance_report(
                workspace,
                manifest,
                title="测试标题",
                summary="摘要",
                body="那天会议室里，大家第一次认真讨论 AI 要替团队扛什么结果。\n\n一份官方文档已经把边界写得很明白。",
                score_report={"passed": True, "depth_signals": {"scene_paragraph_count": 1, "evidence_paragraph_count": 1, "counterpoint_paragraph_count": 1, "long_paragraph_count": 1, "paragraph_count": 3}, "quality_gates": {"credibility_passed": True}},
                review_report={"editorial_review": {"ending_naturalness": "high"}},
                layout_plan={"recommended_style": "business", "section_plans": [{"module_type": "summary-card"}] * 3},
                recent_fingerprints=[],
            )
            self.assertFalse(payload["gates"]["reference_tail_passed"])
            self.assertFalse(payload["gates"]["image_text_density_passed"])
            self.assertFalse(payload["gates"]["publish_ready"])


if __name__ == "__main__":
    unittest.main()
