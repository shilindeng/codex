import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.workflow import cmd_select_topic  # noqa: E402


class SelectTopicTests(unittest.TestCase):
    def test_select_topic_writes_manifest_and_resets_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "topic-discovery.json").write_text(
                json.dumps(
                    {
                        "candidates": [
                            {
                                "recommended_topic": "测试主题",
                                "hot_title": "热点标题",
                                "recommended_title": "推荐标题",
                                "angles": ["角度 1", "角度 2"],
                                "source_url": "https://example.com",
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "topic": "旧主题",
                        "stage": "render",
                        "research_status": "done",
                        "title_status": "done",
                        "outline_status": "done",
                        "draft_status": "done",
                        "review_status": "done",
                        "score_status": "done",
                        "image_status": "done",
                        "render_status": "done",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_select_topic(
                    type(
                        "Args",
                        (),
                        {
                            "workspace": str(workspace),
                            "index": 1,
                            "angle_index": 1,
                            "angle": None,
                            "audience": None,
                        },
                    )()
                )

            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("topic"), "测试主题")
            self.assertEqual(manifest.get("direction"), "角度 1")
            self.assertEqual(manifest.get("selected_title"), "推荐标题")
            self.assertEqual(manifest.get("source_urls"), ["https://example.com"])
            self.assertEqual(manifest.get("stage"), "initialized")
            self.assertEqual(manifest.get("research_status"), "not_started")
            self.assertEqual(manifest.get("render_status"), "not_started")

            ideation = json.loads((workspace / "ideation.json").read_text(encoding="utf-8"))
            self.assertEqual(ideation.get("selected_title"), "推荐标题")
            self.assertEqual(ideation.get("topic"), "测试主题")


if __name__ == "__main__":
    unittest.main()
