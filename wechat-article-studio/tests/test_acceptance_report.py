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
            (workspace / "article.wechat.html").write_text("<section><p>摘要</p><h2>参考资料</h2></section>", encoding="utf-8")
            (workspace / "references.json").write_text(
                json.dumps({"items": [{"index": 1, "url": "https://example.com", "title": "官方文档"}]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            manifest = {
                "wechat_html_path": "article.wechat.html",
                "references_path": "references.json",
                "wechat_header_mode": "drop-title",
                "viral_blueprint": {"article_archetype": "commentary", "primary_interaction_goal": "comment/share", "secondary_interaction_goal": "like"},
                "editorial_blueprint": {"style_key": "signal-briefing"},
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
                "quality_gates": {"credibility_passed": True},
            }
            review_report = {"editorial_review": {"ending_naturalness": "high"}}
            layout_plan = {"recommended_style": "magazine", "section_plans": [{"module_type": "summary-card"}, {"module_type": "case-card"}, {"module_type": "conclusion-card"}], "module_types": ["summary-card", "case-card", "conclusion-card"]}
            body = "\n\n".join(
                [
                    "那天会议室里，大家第一次认真讨论 AI 要替团队扛什么结果。",
                    "真正的问题不是会不会用，而是先把什么结果讲清楚。",
                    "一份官方文档已经把边界写得很明白 [1]。",
                    "但如果忽略责任归属，再好的工具也会被用成热闹。",
                ]
            )
            payload = build_acceptance_report(
                workspace,
                manifest,
                title="企业 AI 转型真正要先讲清楚的，不是工具",
                summary="先把团队真正要扛的结果讲清楚，再谈工具和流程。",
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


if __name__ == "__main__":
    unittest.main()
