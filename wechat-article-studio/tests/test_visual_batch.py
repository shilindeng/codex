import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.visual_batch import summarize_visual_batch_collisions  # noqa: E402


class VisualBatchTests(unittest.TestCase):
    def test_visual_batch_collisions_flag_same_day_near_duplicate_image_plans(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = root / "20260411-a"
            other = root / "20260411-b"
            current.mkdir()
            other.mkdir()
            current_plan = {
                "layout_family": "comparison",
                "image_controls": {"preset": "notion", "preset_cover": "notion", "preset_inline": "notion"},
                "article_visual_strategy": {"visual_route": "data-explainer", "style_family": "知识解释"},
                "items": [
                    {"id": "cover-01", "layout_variant_key": "split-diagram", "visual_preset": "notion"},
                    {"id": "inline-01", "layout_variant_key": "split-diagram", "visual_preset": "notion"},
                ],
            }
            other_plan = {
                "layout_family": "comparison",
                "image_controls": {"preset": "notion", "preset_cover": "notion", "preset_inline": "notion"},
                "article_visual_strategy": {"visual_route": "data-explainer", "style_family": "知识解释"},
                "items": [
                    {"id": "cover-01", "layout_variant_key": "split-diagram", "visual_preset": "notion"},
                    {"id": "inline-01", "layout_variant_key": "split-diagram", "visual_preset": "notion"},
                ],
            }
            (other / "image-plan.json").write_text(json.dumps(other_plan, ensure_ascii=False, indent=2), encoding="utf-8")
            report = summarize_visual_batch_collisions(current, current_plan)
            self.assertFalse(report["passed"])
            self.assertTrue(report["similar_items"])


if __name__ == "__main__":
    unittest.main()
