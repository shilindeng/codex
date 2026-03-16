import json
import sys
import tempfile
import unittest
import io
from contextlib import redirect_stdout
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.viral import build_score_report, default_viral_blueprint, infer_article_archetype, normalize_outline_payload  # noqa: E402
from core.workflow import collect_publish_blockers, _run_revision_loop  # noqa: E402
import legacy_studio as legacy  # noqa: E402
from providers.text.openai_compatible import placeholder_article, placeholder_outline  # noqa: E402


class ViralEngineTests(unittest.TestCase):
    def test_commentary_topics_do_not_default_to_action_template_outline(self):
        context = {
            "topic": "如果 Gemini 开始上广告，AI 免费时代可能真的要变了",
            "selected_title": "如果 Gemini 开始上广告，AI 免费时代可能真的要变了",
            "audience": "大众读者",
            "direction": "",
            "research": {},
        }
        outline = normalize_outline_payload({}, context)
        headings = [item["heading"] for item in outline.get("sections") or []]
        self.assertEqual(outline.get("article_archetype"), "commentary")
        self.assertNotIn("把判断变成动作", headings)
        self.assertNotIn("最后把动作落地", headings)
        self.assertNotEqual(outline.get("ending_mode"), "行动提示")

    def test_tutorial_topics_can_still_use_tutorial_archetype(self):
        archetype = infer_article_archetype(
            topic="RAG 实战指南",
            title="RAG 实战指南：从 0 到 1 搭好检索增强流程",
            angle="",
            research={},
        )
        self.assertEqual(archetype, "tutorial")

    def test_blueprint_contains_interaction_design_fields(self):
        blueprint = default_viral_blueprint(
            topic="为什么好内容不一定高互动",
            title="为什么好内容不一定高互动",
            angle="",
            audience="大众读者",
            research={},
            style_signals=[],
        )
        self.assertIn("like_triggers", blueprint)
        self.assertIn("comment_triggers", blueprint)
        self.assertIn("share_triggers", blueprint)
        self.assertIn("social_currency_points", blueprint)
        self.assertIn("interaction_formula", blueprint)
        self.assertTrue(blueprint.get("peak_moment_design"))

    def test_placeholder_article_avoids_fixed_conclusion_and_checklist(self):
        title = "AI 产品为什么越来越像内容战争"
        article = placeholder_article(title, placeholder_outline(title), "公众号读者")
        self.assertNotIn("先说结论", article)
        self.assertNotIn("最后给你一个可执行清单", article)

    def test_score_report_fails_when_body_contains_raw_urls(self):
        title = "测试标题"
        body = "这里有一个事实依据 https://example.com/a ，但正文不该直接堆原始链接。"
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {
                "topic": title,
                "audience": "大众读者",
                "workspace": str(workspace),
                "references_path": "references.json",
                "source_urls": ["https://example.com/a"],
            }
            report = build_score_report(title, body, manifest, threshold=70)
            self.assertFalse(report.get("quality_gates", {}).get("citation_policy_passed"))

    def test_score_report_has_quality_gates_and_can_pass(self):
        title = "为什么你越学越焦虑：真相是别再堆信息"
        body = "\n\n".join(
            [
                "你可能也有过这种时刻：工具越看越多，收藏夹越堆越满，但真正要开始动手时，人反而更迟疑了。",
                "问题不在信息太少，而在你总把注意力花在看起来重要、实际上不决定结果的地方。",
                "如果你已经在这种循环里打转很久，那种疲惫不是矫情，而是注意力被不断切碎之后的自然反应。",
                "更糟的是，你越努力补工具，越容易误以为自己离解决问题更近，结果只是把焦虑包装得更体面。",
                "一份 GitHub Next 的开发者研究提醒过我们，真正让人疲惫的往往不是代码量，而是来回切换上下文带来的注意力流失 [1]。",
                "Stack Overflow 的开发者调查也反复出现同一个信号：工具越来越多，判断成本没有同步下降 [2]。",
                "",
                "## 大家真正误判了什么",
                "很多人把“学更多”误当成安全感，但真正能降低焦虑的，从来不是信息密度，而是判断顺序。",
                "当一个团队把新工具试了十轮，交付速度却没上来，问题通常不在努力不够，而在关键动作没有被单独拎出来。",
                "最刺人的地方就在这里：你明明投入了更多时间，却越来越说不清自己到底为什么还在累。",
                "",
                "## 真正拉开差距的分水岭",
                "真正能带来掌控感的，不是知道更多名词，而是知道哪一类动作必须先做、哪一类动作可以暂时不做。",
                "这句话之所以值得记住，是因为它把焦虑从情绪问题重新翻译成了排序问题。",
                "> 不是信息不够，而是判断顺序出了错。",
                "> 当你把注意力收回来，焦虑才会开始松动。",
                "> 最有价值的进步，往往发生在你终于敢停掉那些看起来很努力的动作之后。",
                "",
                "## 最后的判断",
                "如果你也处在那种“越学越乱”的阶段，也许真正该问自己的不是“我还缺什么工具”，而是“我现在到底该先守住哪一个动作？”",
                "这不是鸡汤，而是一种能帮你把注意力重新拿回来的判断。",
                "如果是你，你会先砍掉哪一类无效动作？",
            ]
        ).strip()
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "references.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {"index": 1, "url": "https://example.com/a", "title": "GitHub Next 研究", "domain": "example.com", "note": "关于上下文切换的研究"},
                            {"index": 2, "url": "https://example.com/b", "title": "Stack Overflow 调查", "domain": "example.com", "note": "开发者使用 AI 的调查"},
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            manifest = {
                "topic": "学习焦虑",
                "audience": "大众读者",
                "direction": "",
                "source_urls": ["https://example.com/a", "https://example.com/b"],
                "workspace": str(workspace),
                "references_path": "references.json",
            }
            report = build_score_report(title, body, manifest, threshold=76)
        self.assertIn("quality_gates", report)
        self.assertIn("passed", report)
        self.assertTrue(any(item["dimension"] == "互动参与与社交货币" for item in report.get("score_breakdown", [])))
        # This sample should be able to pass both total score and gates.
        self.assertTrue(bool(report.get("passed")))

    def test_publish_blockers_include_quality_gate_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {"text_model": "session", "selected_title": "t", "article_path": "article.md", "source_urls": []}
            (workspace / "score-report.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "quality_gates": {"de_ai_passed": False},
                        "score_breakdown": [{"dimension": "可信度与检索支撑", "weight": 10, "score": 10, "note": ""}],
                        "total_score": 99,
                        "threshold": 88,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            blockers = collect_publish_blockers(workspace, manifest)
            self.assertTrue(any("质量门槛未通过" in item for item in blockers))

    def test_revision_loop_writes_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {"selected_title": "测试", "audience": "大众读者", "direction": "", "article_path": "article.md", "source_urls": []},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("# 测试\n\n你不是不努力，只是方法不对。", encoding="utf-8")
            buf = io.StringIO()
            with redirect_stdout(buf):
                score_report = _run_revision_loop(workspace, max_rounds=2, style_sample=[])
            self.assertIn("revision_rounds", score_report)
            self.assertIn("stop_reason", score_report)
            manifest = legacy.read_json(workspace / "manifest.json", default={}) or {}
            self.assertIsInstance(manifest.get("revision_rounds"), list)
            self.assertGreaterEqual(len(manifest.get("revision_rounds") or []), 1)


if __name__ == "__main__":
    unittest.main()
