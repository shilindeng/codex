import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.editorial_anchor import build_editorial_anchor_plan  # noqa: E402
from core.workflow import write_editorial_anchor_plan  # noqa: E402


class EditorialAnchorTests(unittest.TestCase):
    def test_build_editorial_anchor_plan_returns_three_slots(self):
        payload = build_editorial_anchor_plan(
            title="测试标题",
            manifest={},
            review_report={"summary": "需要补细节"},
            score_report={"mandatory_revisions": ["补一个具体场景", "补反方边界"], "humanness_findings": ["缺少场景锚。"]},
            content_enhancement={"section_enhancements": [{"evidence_targets": ["一条真实案例"], "counterpoint_targets": ["补一句边界提醒"]}]},
        )
        self.assertEqual(len(payload.get("anchors") or []), 3)
        self.assertEqual(payload["anchors"][0]["slot"], "opening")
        self.assertEqual(payload["anchors"][1]["slot"], "middle")
        self.assertEqual(payload["anchors"][2]["slot"], "ending")

    def test_write_editorial_anchor_plan_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "content-enhancement.json").write_text(
                json.dumps(
                    {"section_enhancements": [{"evidence_targets": ["一条真实案例"], "counterpoint_targets": ["补一句边界提醒"]}]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            manifest = {}
            payload = write_editorial_anchor_plan(
                workspace,
                manifest,
                title="测试标题",
                review_report={"summary": "需要补细节"},
                score_report={"mandatory_revisions": ["补一个具体场景"], "humanness_findings": ["缺少场景锚。"]},
            )
            self.assertTrue((workspace / "editorial-anchor-plan.json").exists())
            self.assertTrue((workspace / "editorial-anchor-plan.md").exists())
            self.assertEqual(manifest.get("editorial_anchor_plan_path"), "editorial-anchor-plan.json")
            self.assertEqual(payload["anchors"][0]["slot"], "opening")


if __name__ == "__main__":
    unittest.main()
