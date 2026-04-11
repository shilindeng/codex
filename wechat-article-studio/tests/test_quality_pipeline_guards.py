import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.ai_fingerprint import detect_ai_fingerprints  # noqa: E402
from core.content_fingerprint import build_article_fingerprint, summarize_batch_collisions  # noqa: E402
from core.quality_checks import metadata_integrity_report  # noqa: E402
from core.workflow import build_pipeline_readiness  # noqa: E402


class QualityPipelineGuardTests(unittest.TestCase):
    def test_metadata_integrity_report_rejects_broken_title_and_summary(self):
        payload = metadata_integrity_report("???? AI ??????", "????????????????")
        self.assertFalse(payload["passed"])
        self.assertTrue(payload["title_issues"])
        self.assertTrue(payload["summary_issues"])

    def test_batch_collisions_fail_for_same_day_near_duplicate_articles(self):
        current_body = "\n\n".join(
            [
                "4 月 10 日，教育系统连着放出两个信号。",
                "如果你把这两条消息叠在一起，就会发现 AI 进课堂已经不是会不会来的问题。",
                "这会逼着学校重新回答几个问题：老师怎么教，学生怎么学，系统怎么管。",
                "当 AI 成为课堂标配，学校先要补的不是设备，而是秩序。",
            ]
        )
        other_body = "\n\n".join(
            [
                "4 月 10 日，教育系统连着放出两个信号。",
                "如果你把这两条消息叠在一起，就会发现 AI 进课堂已经不是会不会来的问题。",
                "老师怎么教，学生怎么学，系统怎么管，都会被重新排一遍。",
                "当 AI 成为课堂标配，学校先要补的不是设备，而是秩序。",
            ]
        )
        current_fp = build_article_fingerprint(
            "教育部启动“人工智能+教育”行动计划：当 AI 成为课堂标配，学校先要补的不是设备",
            current_body,
            {"workspace": r"D:\tmp\20260411-a", "summary": "AI 进课堂不是有没有工具，而是秩序怎么重排。"},
        )
        other_fp = build_article_fingerprint(
            "北京 AI 覆盖率到了 87.7%：当 AI 成为课堂标配，学校先要补的不是设备",
            other_body,
            {"workspace": r"D:\tmp\20260411-b", "summary": "覆盖率上去之后，真正稀缺的是秩序和分工。"},
        )
        report = summarize_batch_collisions(
            current_fp,
            current_title=current_fp["title"],
            current_body=current_body,
            batch_items=[
                {
                    "workspace": r"D:\tmp\20260411-b",
                    "title": other_fp["title"],
                    "body": other_body,
                    "fingerprint": other_fp,
                }
            ],
        )
        self.assertFalse(report["passed"])
        self.assertTrue(report["batch_similar_items"])
        self.assertTrue(report["text_overlap_signals"])

    def test_build_pipeline_readiness_requires_acceptance_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text(
                "---\ntitle: 测试标题\nsummary: 那天会议室里大家第一次认真讨论 AI 要替团队扛什么结果，真正该先补的是责任和流程。\n---\n\n那天会议室里，大家第一次认真讨论 AI 要替团队扛什么结果。\n",
                encoding="utf-8",
            )
            (workspace / "score-report.json").write_text(
                json.dumps(
                    {
                        "title": "测试标题",
                        "passed": True,
                        "body_signature": "x",
                        "quality_gates": {
                            "metadata_integrity_passed": True,
                            "batch_uniqueness_passed": True,
                            "title_integrity_passed": True,
                            "credibility_passed": True,
                            "evidence_minimum_passed": True,
                            "summary_integrity_passed": True,
                            "prompt_leak_passed": True,
                            "similarity_passed": True,
                            "citation_policy_passed": True,
                            "editorial_review_passed": True,
                            "naturalness_floor_passed": True,
                            "reading_flow_passed": True,
                            "hook_quality_passed": True,
                            "ending_naturalness_passed": True,
                            "material_coverage_passed": True,
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            manifest = {
                "workspace": str(workspace),
                "selected_title": "测试标题",
                "article_path": "article.md",
                "score_passed": True,
                "score_status": "done",
                "stage": "score",
            }
            readiness = build_pipeline_readiness(workspace, manifest)
            self.assertFalse(readiness["render_ready"])
            self.assertTrue(any("acceptance-report.json" in item for item in readiness["render_blockers"]))

    def test_detect_ai_fingerprints_catches_structural_templates(self):
        body = "\n\n".join(
            [
                "很多人看到这条消息，第一反应是模型又变强了，但这次真正该看的不是这个。",
                "这更像一次分发权重排，这更像入口重排，这更像一次代价重估，也别急着把它理解成普通更新，当然这不代表风险会自己消失，反过来说代价只会更重。",
                "不是价格变了，而是入口变了。不是模型变了，而是分工变了。不是一个工具变了，而是组织开始重排。不是功能变多了，而是链路变长了。不是话术变强了，而是代价变重了。",
                "最后给你一个可执行清单。",
                "你只需要记住这一点就行。",
            ]
        )
        findings = {item.get("type") for item in detect_ai_fingerprints(body)}
        self.assertIn("judgment_first_opening", findings)
        self.assertIn("overused_not_but", findings)
        self.assertIn("overused_this_is_more_like", findings)
        self.assertIn("didactic_softener", findings)
        self.assertIn("two_sentence_protocol_close", findings)


if __name__ == "__main__":
    unittest.main()
