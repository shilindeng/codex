import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.analysis_11d import build_analysis_11d, score_analysis_11d, summarize_analysis_11d  # noqa: E402
from core.workflow import cmd_report_11d, cmd_review_batch  # noqa: E402


class Analysis11DTests(unittest.TestCase):
    def test_build_analysis_11d_returns_all_dimensions(self):
        body = "\n\n".join(
            [
                "那天会议室里，团队第一次发现返工不是因为不会做，而是因为判断顺序一直放反了。",
                "真正要先讲清楚的，不是工具，而是结果、责任和流程顺序。",
                "如果是你，你会先补工具，还是先收责任边界？",
                "把这张判断卡留着：下次越忙越乱，先检查是不是顺序说反了。",
            ]
        )
        analysis_11d = build_analysis_11d(
            title="团队真正拉开差距的，不是工具，而是判断顺序",
            body=body,
            summary="这篇文章先讲代价，再讲判断。",
            analysis={
                "core_viewpoint": "真正要先讲清楚的，不是工具，而是结果、责任和流程顺序。",
                "secondary_viewpoints": ["返工会先冒出来。", "责任归属不清会拖慢流程。"],
                "persuasion_strategies": ["对比论证", "案例复盘", "权威背书"],
                "emotion_triggers": ["紧迫", "共鸣", "好奇"],
                "signature_lines": [{"text": "真正要先讲清楚的，不是工具，而是结果、责任和流程顺序。"}],
                "emotion_curve": [{"stage": "开头", "emotion": "紧张", "goal": "先停下来"}, {"stage": "中段", "emotion": "理解", "goal": "讲清差距"}, {"stage": "结尾", "emotion": "带走", "goal": "留下判断卡"}],
                "emotion_layers": ["表层信息", "价值判断", "身份认同"],
                "argument_diversity": ["案例", "对比", "数据"],
                "perspective_shifts": ["读者视角", "团队视角", "编辑判断视角"],
                "style_traits": ["具体场景起笔", "判断克制"],
                "comment_triggers": ["如果是你，你会先补工具，还是先收责任边界？"],
                "share_triggers": ["真正要先讲清楚的，不是工具，而是结果、责任和流程顺序。"],
                "save_triggers": ["把这张判断卡留着：下次越忙越乱，先检查是不是顺序说反了。"],
                "controversy_anchors": ["先补工具，还是先收责任边界？"],
            },
            depth={"scene_paragraph_count": 1, "evidence_paragraph_count": 1, "counterpoint_paragraph_count": 1},
            material_signals={"has_table": True, "analogy_count": 1, "comparison_count": 1},
            humanness_signals={"sentence_length_range": 22, "paragraph_length_range": 42},
        )
        self.assertEqual(analysis_11d["core_viewpoint"], "真正要先讲清楚的，不是工具，而是结果、责任和流程顺序。")
        self.assertEqual(len(analysis_11d["secondary_viewpoints"]), 2)
        self.assertIn("sentence_length_mix", analysis_11d["language_style"])
        self.assertIn("comment_triggers", analysis_11d["interaction_hooks"])
        scores = score_analysis_11d(analysis_11d)
        self.assertEqual(len(scores), 11)
        summary = summarize_analysis_11d(analysis_11d, scores)
        self.assertTrue(summary["strongest_dimensions"])

    def test_report_11d_command_writes_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps({"selected_title": "测试标题", "article_path": "article.md"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text(
                "---\ntitle: 测试标题\nsummary: 摘要\n---\n\n那天会议室里，团队终于把责任讲清楚了。\n\n真正的问题不是工具，而是顺序。",
                encoding="utf-8",
            )
            (workspace / "review-report.json").write_text(
                json.dumps(
                    {
                        "viral_analysis": {
                            "core_viewpoint": "真正的问题不是工具，而是顺序。",
                            "secondary_viewpoints": ["责任先于工具。", "返工来自顺序错误。"],
                            "persuasion_strategies": ["对比论证", "案例复盘"],
                            "emotion_triggers": ["紧迫", "共鸣"],
                            "signature_lines": [{"text": "真正的问题不是工具，而是顺序。"}],
                            "emotion_curve": [{"stage": "开头", "emotion": "紧张", "goal": "停下来"}, {"stage": "中段", "emotion": "理解", "goal": "讲清楚"}, {"stage": "结尾", "emotion": "带走", "goal": "留下判断"}],
                            "emotion_layers": ["表层信息", "价值判断", "身份认同"],
                            "argument_diversity": ["案例", "对比", "判断"],
                            "perspective_shifts": ["读者视角", "团队视角"],
                            "comment_triggers": ["如果是你，你会先做什么？"],
                        }
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            cmd_report_11d(argparse.Namespace(workspace=str(workspace)))
            payload = json.loads((workspace / "report-11d.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["title"], "测试标题")
            self.assertEqual(len(payload["dimension_11d_scores"]), 11)
            self.assertTrue((workspace / "report-11d.md").exists())

    def test_review_batch_ignores_hot_topics_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            jobs_root = Path(tmp)
            for name in [
                "20260418-01-a",
                "20260418-02-b",
                "20260418-03-c",
                "20260418-hot-topics-batch",
            ]:
                workspace = jobs_root / name
                workspace.mkdir(parents=True, exist_ok=True)
                (workspace / "article.md").write_text(
                    "---\ntitle: 测试标题\nsummary: 摘要\n---\n\n那天会议室里，大家第一次认真讨论这个问题。\n\n## 带走这张判断卡\n\n把这张判断卡留着。",
                    encoding="utf-8",
                )
            cmd_review_batch(argparse.Namespace(jobs_root=str(jobs_root), batch_key="20260418"))
            payload = json.loads((jobs_root / "batch-review.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["item_count"], 3)
            self.assertTrue(any("同批次开头路线重复" == item for item in payload["batch_risks"]))
            self.assertTrue((jobs_root / "batch-review.md").exists())


if __name__ == "__main__":
    unittest.main()
