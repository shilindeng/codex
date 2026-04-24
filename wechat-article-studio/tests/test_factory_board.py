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

            backlog = root / "20260423-evening-hot-batch"
            backlog.mkdir()
            (backlog / "manifest.json").write_text(json.dumps({}, ensure_ascii=False), encoding="utf-8")

            board = build_factory_board(root)
            self.assertEqual(board["metrics"]["total"], 3)
            self.assertEqual(board["metrics"]["status_counts"]["已交付"], 1)
            self.assertEqual(board["metrics"]["status_counts"]["生产中"], 1)
            self.assertEqual(board["metrics"]["status_counts"]["待清理"], 1)
            self.assertAlmostEqual(board["metrics"]["full_chain_pass_rate"], 1 / 3, places=4)
            delivered_item = next(item for item in board["items"] if item["workspace"] == "20260423-google-ai-code")
            self.assertEqual(delivered_item["status"], "已交付")


if __name__ == "__main__":
    unittest.main()
