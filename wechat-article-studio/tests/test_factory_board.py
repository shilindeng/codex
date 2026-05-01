import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.factory_board import build_factory_board  # noqa: E402


class FactoryBoardTests(unittest.TestCase):
    def test_factory_board_groups_workspaces_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            delivered = root / "20260423-google-ai-code"
            delivered.mkdir()
            (delivered / "manifest.json").write_text(
                json.dumps(
                    {
                        "topic": "Google 75% 新代码",
                        "selected_title": "Google 75% 新代码背后缺的其实是验收",
                        "canonical_job_id": "google-ai-code",
                        "batch_id": "20260423",
                        "retry_round": 1,
                        "publish_chain_status": "passed",
                        "quality_chain_status": "passed",
                        "batch_chain_status": "passed",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (delivered / "final-delivery-report.json").write_text(
                json.dumps(
                    {
                        "overall_status": "passed",
                        "published": True,
                        "quality_passed": True,
                        "force_publish": False,
                        "publish_chain": {"status": "passed", "published": True},
                        "quality_chain": {"status": "passed", "passed": True},
                        "batch_chain": {"status": "passed", "passed": True},
                        "factory_acceptance": {"status": "passed", "grade_label": "真合格成品", "blocking_reasons": [], "top_rework_actions": []},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            in_progress = root / "20260423-afternoon-amap-ai-agent-v2"
            in_progress.mkdir()
            (in_progress / "manifest.json").write_text(
                json.dumps({"topic": "高德 AI Agent", "selected_title": "高德把导航推到主动服务", "retry_round": 2}, ensure_ascii=False),
                encoding="utf-8",
            )
            (in_progress / "article.md").write_text("---\ntitle: 高德把导航推到主动服务\nsummary: 摘要\n---\n\n正文。", encoding="utf-8")

            published_rework = root / "20260423-openai-workspace"
            published_rework.mkdir()
            (published_rework / "manifest.json").write_text(
                json.dumps({"topic": "OpenAI Workspace", "selected_title": "OpenAI 工作区开始改写团队协作", "retry_round": 1}, ensure_ascii=False),
                encoding="utf-8",
            )
            (published_rework / "final-delivery-report.json").write_text(
                json.dumps(
                    {
                        "overall_status": "failed",
                        "published": True,
                        "quality_passed": False,
                        "publish_chain": {"status": "passed", "published": True},
                        "quality_chain": {"status": "failed", "passed": False, "missing_artifacts": ["title-decision-report.json/title-report.json"]},
                        "batch_chain": {"status": "passed", "passed": True},
                        "sections": {"title": {"status": "missing"}},
                        "factory_acceptance": {
                            "status": "force_publish_only",
                            "grade_label": "已发布但不合格",
                            "blocking_reasons": ["title_report_missing", "quality_chain_failed"],
                            "top_rework_actions": ["补齐标题决策报告，保留候选、评分、重写理由和最终选择证据。"],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            backlog = root / "20260423-evening-hot-batch"
            backlog.mkdir()
            (backlog / "manifest.json").write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")

            board = build_factory_board(root)
            self.assertEqual(board["metrics"]["total"], 4)
            self.assertEqual(board["metrics"]["status_counts"]["真合格成品"], 1)
            self.assertEqual(board["metrics"]["status_counts"]["待返工"], 1)
            self.assertEqual(board["metrics"]["status_counts"]["待清理"], 1)
            self.assertEqual(board["metrics"]["status_counts"]["已发布但不合格"], 1)
            self.assertAlmostEqual(board["metrics"]["full_chain_pass_rate"], 1 / 4, places=4)
            self.assertEqual(board["metrics"]["title_report_missing_count"], 1)
            self.assertEqual(board["metrics"]["needs_rework_count"], 2)
            self.assertEqual(board["metrics"]["true_qualified_count"], 1)
            self.assertEqual(board["metrics"]["published_unqualified_count"], 1)
            delivered_item = next(item for item in board["items"] if item["workspace"] == "20260423-google-ai-code")
            self.assertEqual(delivered_item["status"], "真合格成品")
            rework_item = next(item for item in board["items"] if item["workspace"] == "20260423-openai-workspace")
            self.assertTrue(rework_item["published_but_unqualified"])
            self.assertTrue(rework_item["title_report_missing"])
            self.assertEqual(rework_item["completion_status"], "已发布但不合格")
            self.assertIn("title_report_missing", rework_item["blocking_reasons"])


if __name__ == "__main__":
    unittest.main()
