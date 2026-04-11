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
from core.workflow import apply_research_credibility_boost, build_pipeline_readiness, collect_publish_blockers, collect_render_blockers, _run_revision_loop  # noqa: E402
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
                "周三晚上十一点，团队群里还在转新的工具榜单，但卡住交付的那一步，还是没人愿意先把它单独做完。",
                "这类焦虑最伤人的地方，不在于工具太少，而在于大家把判断顺序排反了：先补信息，后做动作，结果每个人都更累。",
                "当注意力被不断切碎，代价不会立刻写在报表上，但会先落在返工、拖延和越来越重的疲惫感上。",
                "一份 GitHub Next 的开发者研究提醒过我们，来回切换上下文带来的注意力流失，往往比代码量本身更容易把人拖垮 [1]。",
                "## 先看错在哪",
                "Stack Overflow 的开发者调查也反复出现同一个信号：工具越来越多，判断成本没有同步下降 [2]。",
                "",
                "| 动作 | 表面收益 | 长期代价 |",
                "| --- | --- | --- |",
                "| 一直补工具 | 看起来学得更快 | 判断越来越乱 |",
                "| 先收住一个关键动作 | 起步更慢 | 结果更稳 |",
                "很多人把“学更多”误当成安全感，但能降低焦虑的动作，其实是先把判断顺序收住。",
                "一个团队如果连着试了十轮新工具，交付速度却没上来，最常见的原因不是努力不够，而是关键动作一直没有被单独拎出来。",
                "最刺人的地方就在这里：你明明投入了更多时间，却越来越说不清自己到底为什么还在累。",
                "",
                "## 真正拉开差距的动作",
                "能带来掌控感的，是知道哪一类动作必须先做、哪一类动作可以暂时不做。",
                "这就像收拾行李：东西当然越多越安全，但真正让你赶得上车的，往往是先把最关键的那几件装进去。",
                "如果一个团队先守住一项关键动作，再决定还要不要继续补工具，后面的节奏通常会稳很多。",
                "",
                "## 也别把一切都怪工具",
                "工具本身并不是问题，很多时候它甚至真的帮你省掉了重复动作。",
                "相比之下，先收住一个动作的团队，后面更容易稳住节奏；一味补工具的团队，常常只是把混乱包装得更像努力。",
                "如果判断顺序一直是乱的，新工具只会把这种混乱包装得更像进步。",
                "",
                "## 留一个问题",
                "如果你也处在那种“越学越乱”的阶段，也许该问自己的，不是还缺什么工具，而是现在到底该先守住哪一个动作。",
                "这不是鸡汤，而是一种能帮你把注意力重新拿回来的判断。",
                "如果是你，你会先停掉哪一个看起来很努力、其实一直在拖住你的动作？",
                "先守住一个动作，再决定还要不要继续往上堆信息。",
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
            report = build_score_report(title, body, manifest, threshold=74)
        self.assertIn("quality_gates", report)
        self.assertIn("passed", report)
        self.assertTrue(any(item["dimension"] == "评论与传播触发" for item in report.get("score_breakdown", [])))
        self.assertIn("score_groups", report)
        self.assertIn("virality_score", report)
        self.assertIn("publishability_score", report)
        self.assertIn("persona_fit_score", report)
        self.assertTrue(report.get("quality_gates", {}).get("material_coverage_passed"))
        # This sample should be able to pass both total score and gates.
        self.assertTrue(bool(report.get("passed")))

    def test_score_report_flags_outline_like_ai_copy(self):
        title = "为什么很多团队做不好 AI 落地"
        body = "\n\n".join(
            [
                "很多人一上来就想做 AI 落地。",
                "很多人以为问题只是工具不够。",
                "很多人后来又去补更多工具。",
                "",
                "## 为什么第一步总会错",
                "如果你现在很焦虑，那就说明你还没有想清楚。",
                "",
                "## 为什么第二步还是会错",
                "如果你继续这样做，结果通常也不会太好。",
                "",
                "## 为什么最后还是没结果",
                "如果你还想继续推进，那就先别急着下结论。",
            ]
        ).strip()
        report = build_score_report(title, body, {"topic": title, "audience": "大众读者", "direction": "", "source_urls": []}, threshold=70)
        self.assertFalse(report.get("quality_gates", {}).get("depth_passed"))
        self.assertFalse(report.get("quality_gates", {}).get("structure_passed"))
        patterns = {item.get("type") for item in report.get("ai_smell_findings") or []}
        self.assertIn("outline_like", patterns)
        self.assertIn("repeated_starter", patterns)
        self.assertTrue(
            any(
                ("补现场、案例和反方边界" in item) or ("先把中段写顺" in item) or ("真正立起来" in item)
                for item in report.get("mandatory_revisions", [])
            )
        )

    def test_score_report_respects_author_memory_blacklist(self):
        title = "一个看上去没问题但其实很模板的稿子"
        body = "\n\n".join(
            [
                "如果你最近也在关注这件事，你会发现很多人都在重复同一种判断。",
                "如果你最近继续往下看，你还会看到同一种展开方式。",
                "",
                "## 为什么这件事重要？",
                "说白了，这件事的本质并不复杂。",
                "",
                "## 为什么很多人会误判？",
                "说白了，问题不在信息，而在判断顺序。",
                "",
                "## 为什么最后还是会写成一样？",
                "如果你最近刚好也在写类似文章，就更容易掉回这套腔调。",
            ]
        ).strip()
        manifest = {
            "topic": title,
            "audience": "大众读者",
            "direction": "",
            "source_urls": [],
            "author_memory": {
                "phrase_blacklist": ["说白了", "如果你最近"],
                "sentence_starters_to_avoid": ["如果你最近"],
            },
        }
        report = build_score_report(title, body, manifest, threshold=70)
        self.assertFalse(report.get("quality_gates", {}).get("de_ai_passed"))
        self.assertFalse(report.get("quality_gates", {}).get("template_penalty_passed"))
        smell_types = {item.get("type") for item in report.get("ai_smell_findings") or []}
        self.assertIn("author_phrase", smell_types)
        self.assertIn("author_starter", smell_types)

    def test_score_report_flags_prompt_leak_and_low_interaction(self):
        title = "AI 代码的维护成本为什么越来越像定时炸弹"
        body = "\n\n".join(
            [
                "这类题目最怕的，不是信息不够，而是写法太像模板。围绕“这个主题”，更值得展开的是：场景切口。",
                "最近很多团队都在加速上线 AI 功能，但真正让人心里发紧的，是后面没人敢接这堆代码。",
                "很多项目看上去都跑起来了，直到第二个人接手，才发现每个模块都像有人碰过、又像没人真正负责。",
                "## 成本会在什么时候一起冒出来",
                "问题通常不是写得慢，而是坏代码复制得太快、返工来得太晚。",
                "## 最后的判断",
                "AI 让写代码更快，但真正贵的是以后谁还敢改。",
            ]
        )
        report = build_score_report(
            title,
            body,
            {"topic": title, "audience": "大众读者", "direction": "", "source_urls": ["https://news.google.com/rss/articles/demo"]},
            threshold=70,
        )
        self.assertFalse(report.get("quality_gates", {}).get("prompt_leak_passed"))
        smell_types = {item.get("type") for item in report.get("ai_smell_findings") or []}
        self.assertIn("prompt_leak", smell_types)
        self.assertLessEqual(report.get("interaction_score") or 0, 5)

    def test_score_report_caps_dimension_scores_and_requires_new_hard_gates(self):
        title = "表面热闹但实际上很模板的稿子"
        body = "\n\n".join(
            [
                "很多人一上来就会说，这件事最重要的，不是工具，而是判断。",
                "换句话说，你以为问题在工具，真正的问题是判断顺序。",
                "更重要的是，真正的问题是大家都在用同一套句子写文章。",
                "## 为什么这件事会反复发生？",
                "不是信息太少，而是结构太像。",
                "## 为什么读起来越来越像任务作文？",
                "问题不在观点不够，而在中段根本没有展开。",
                "## 最后的判断",
                "如果是你，你会怎么选？欢迎留言。",
            ]
        )
        report = build_score_report(title, body, {"topic": title, "audience": "大众读者", "direction": "", "source_urls": []}, threshold=70)
        self.assertTrue(all(int(item["score"]) <= int(item["weight"]) for item in report.get("score_breakdown", [])))
        self.assertFalse(report.get("quality_gates", {}).get("naturalness_floor_passed"))
        self.assertFalse(report.get("quality_gates", {}).get("ending_naturalness_passed"))
        self.assertFalse(report.get("passed"))

    def test_score_report_exposes_material_signals_and_flags_missing_materials(self):
        title = "企业 AI 选型，别只看参数表面热闹"
        body = "\n\n".join(
            [
                "很多团队做 AI 选型时，最先看的往往是参数和榜单。",
                "但真正决定后续成本的，常常是接入方式、维护边界和谁来对结果负责。",
                "## 真正该比的是什么",
                "如果两套方案表面都能跑，差别往往不在 demo，而在落地后的代价。",
                "## 最后的判断",
                "别把短期顺手，当成长期靠谱。",
            ]
        )
        report = build_score_report(title, body, {"topic": title, "audience": "大众读者", "direction": "", "source_urls": []}, threshold=70)
        material = report.get("material_signals") or {}
        self.assertIn("coverage_count", material)
        self.assertFalse(material.get("has_table"))
        self.assertLess(int(material.get("analogy_count") or 0), 1)
        self.assertLess(int(material.get("comparison_count") or 0), 1)
        self.assertFalse(report.get("quality_gates", {}).get("material_coverage_passed"))
        self.assertTrue(any("表格" in item for item in report.get("mandatory_revisions") or []))
        self.assertTrue(any("类比分析" in item for item in report.get("mandatory_revisions") or []))

    def test_score_report_rewards_material_richness(self):
        title = "企业 AI 选型，别只看参数表面热闹"
        sparse = "\n\n".join(
            [
                "很多团队做 AI 选型时，最先看的往往是参数和榜单。",
                "真正决定后续成本的，常常是接入方式、维护边界和谁来对结果负责。",
                "## 最后的判断",
                "别把短期顺手，当成长期靠谱。",
            ]
        )
        rich = "\n\n".join(
            [
                "很多团队做 AI 选型时，最先看的往往是参数和榜单。",
                "真正决定后续成本的，常常是接入方式、维护边界和谁来对结果负责。",
                "根据 2026 年公开案例，迁移失败最常见的不是模型不够强，而是接入链路和权限边界没理顺 [1]。",
                "",
                "| 方案 | 上线速度 | 维护成本 | 风险点 |",
                "| --- | --- | --- | --- |",
                "| A | 快 | 高 | 返工多 |",
                "| B | 慢一点 | 更稳 | 边界清楚 |",
                "",
                "如果把选型看成租房，参数更像地段广告，真正长期贵不贵，更像物业、通勤和后续维修。",
                "表面都能住，实际差别在于后面每个月要不要持续还债。",
                "## 最后的判断",
                "别把短期顺手，当成长期靠谱。",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "references.json").write_text(
                json.dumps({"items": [{"index": 1, "url": "https://example.com/a", "title": "公开案例", "domain": "example.com"}]}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            manifest = {"topic": title, "audience": "大众读者", "direction": "", "source_urls": ["https://example.com/a"], "workspace": str(workspace), "references_path": "references.json"}
            sparse_report = build_score_report(title, sparse, manifest, threshold=70)
            rich_report = build_score_report(title, rich, manifest, threshold=70)
        self.assertGreater(int(rich_report.get("material_signals", {}).get("coverage_count") or 0), int(sparse_report.get("material_signals", {}).get("coverage_count") or 0))
        rich_item = next(item for item in rich_report.get("score_breakdown") or [] if item["dimension"] == "事实/案例/对比托底")
        sparse_item = next(item for item in sparse_report.get("score_breakdown") or [] if item["dimension"] == "事实/案例/对比托底")
        self.assertGreater(int(rich_item["score"]), int(sparse_item["score"]))

    def test_research_credibility_boost_recomputes_passed_consistently(self):
        report = {
            "threshold": 79,
            "total_score": 76,
            "score_breakdown": [
                {"dimension": "标题与首屏打开欲", "weight": 14, "score": 11, "note": ""},
                {"dimension": "核心判断与新鲜度", "weight": 12, "score": 10, "note": ""},
                {"dimension": "可转述谈资与金句质量", "weight": 10, "score": 8, "note": ""},
                {"dimension": "评论与传播触发", "weight": 8, "score": 5, "note": ""},
                {"dimension": "峰值时刻设计", "weight": 6, "score": 4, "note": ""},
                {"dimension": "中段推进与结构张力", "weight": 12, "score": 10, "note": ""},
                {"dimension": "事实/案例/对比托底", "weight": 10, "score": 3, "note": ""},
                {"dimension": "结尾收束自然度", "weight": 8, "score": 7, "note": ""},
                {"dimension": "模板腔控制", "weight": 8, "score": 7, "note": ""},
                {"dimension": "句式和段落节奏", "weight": 6, "score": 6, "note": ""},
                {"dimension": "具体处境/边界/反方", "weight": 6, "score": 5, "note": ""},
            ],
            "quality_gates": {
                "viral_blueprint_complete": True,
                "interaction_passed": True,
                "de_ai_passed": True,
                "credibility_passed": False,
                "title_integrity_passed": True,
                "evidence_minimum_passed": True,
                "prompt_leak_passed": True,
                "depth_passed": True,
                "structure_passed": True,
                "template_penalty_passed": True,
                "similarity_passed": True,
                "citation_policy_passed": True,
                "naturalness_floor_passed": True,
                "reading_flow_passed": True,
                "hook_quality_passed": True,
                "ending_naturalness_passed": True,
                "editorial_review_passed": True,
            },
            "weaknesses": ["事实/案例/对比托底偏弱：证据还不够。"],
            "passed": False,
        }
        boosted = apply_research_credibility_boost(report, {"sources": ["来源 1", "来源 2"], "evidence_items": ["证据 1", "证据 2"]})
        self.assertTrue(any(item["dimension"] == "事实/案例/对比托底" and item["score"] >= 6 for item in boosted.get("score_breakdown", [])))
        self.assertEqual(boosted.get("total_score"), sum(int(item["score"]) for item in boosted.get("score_breakdown", [])))
        self.assertTrue(boosted.get("passed"))

    def test_score_report_flags_stop_slop_patterns(self):
        title = "这篇稿子有明显的 AI 腔"
        body = "\n\n".join(
            [
                "换句话说，这件事不是工具不行，而是判断顺序出了错。",
                "更重要的是，真正的问题是很多人把热闹看成了结果。",
                "不是信息太少，而是动作太散。",
                "问题不在模型不够强，而在团队根本没有接住流程。",
                "真正危险的不是信息太少，而是大家一直在补错地方。",
                "数据告诉我们所有人都在焦虑。",
                "市场奖励那些更会包装的人。",
            ]
        )
        report = build_score_report(title, body, {"topic": title, "audience": "大众读者", "direction": "", "source_urls": []}, threshold=70)
        smell_types = {item.get("type") for item in report.get("ai_smell_findings") or []}
        self.assertIn("throat_clearing", smell_types)
        self.assertIn("binary_contrast", smell_types)
        self.assertIn("false_agency", smell_types)
        self.assertFalse(report.get("quality_gates", {}).get("de_ai_passed"))

    def test_collect_render_blockers_blocks_missing_evidence_and_title_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "最终标题",
                        "topic": "最终标题",
                        "audience": "大众读者",
                        "article_path": "article.md",
                        "score_passed": False,
                        "research_requirements": {
                            "requires_evidence": True,
                            "passed": False,
                            "reasons": ["来源不足：至少需要 2 条可回溯来源。"],
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("---\ntitle: 旧标题\nsummary: 摘要\n---\n\n正文。", encoding="utf-8")
            (workspace / "ideation.json").write_text(json.dumps({"selected_title": "另一个标题"}, ensure_ascii=False, indent=2), encoding="utf-8")
            (workspace / "score-report.json").write_text(
                json.dumps({"passed": False, "quality_gates": {"credibility_passed": False}, "score_breakdown": [], "total_score": 60}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            blockers = collect_render_blockers(workspace, legacy.load_manifest(workspace))
            self.assertTrue(any("调研门槛未通过" in item for item in blockers))
            self.assertTrue(any("标题与当前真源不一致" in item for item in blockers))

    def test_score_report_does_not_mistake_normal_subject_and_last_judgment_for_template(self):
        title = "Claude Code源码风波，为什么Claude这么牛"
        body = "\n\n".join(
            [
                "3月31日早上，几个开发者群同时炸了。",
                "Anthropic 官方本来就有公开的 claude-code 仓库。",
                "Anthropic 更厉害的地方，不是把模型做成聊天窗口，而是把终端、工具和工作流接成一条线。",
                "如果你也写过代码，你就知道最累的不是写，而是来回切上下文。",
                "## 最后的判断",
                "最后真正值得警惕的，不是看见了多少代码，而是 AI 开始接管开发流程。",
            ]
        )
        manifest = {"topic": title, "audience": "开发者", "direction": "", "source_urls": []}
        report = build_score_report(title, body, manifest, threshold=70)
        smell = report.get("ai_smell_findings") or []
        self.assertFalse(any(item.get("type") == "enumeration_voice" for item in smell))
        self.assertFalse(any(item.get("type") == "repeated_starter" and "Anthro" in str(item.get("pattern") or "") for item in smell))

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
            self.assertTrue(any("评分硬门槛未通过" in item or "评分未达阈值" in item for item in blockers))

    def test_publish_blockers_flag_stale_score_or_review_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {"selected_title": "测试标题", "article_path": "article.md", "source_urls": []}
            (workspace / "article.md").write_text("---\ntitle: 测试标题\nsummary: 摘要\n---\n\n新的正文。", encoding="utf-8")
            (workspace / "review-report.json").write_text(json.dumps({"body_signature": "old-review"}, ensure_ascii=False), encoding="utf-8")
            (workspace / "score-report.json").write_text(json.dumps({"body_signature": "old-score", "passed": True, "quality_gates": {}}, ensure_ascii=False), encoding="utf-8")
            blockers = collect_publish_blockers(workspace, manifest)
            self.assertTrue(any("review-report.json" in item for item in blockers))
            self.assertTrue(any("score-report.json" in item for item in blockers))

    def test_pipeline_readiness_uses_single_blocker_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {"selected_title": "测试标题", "article_path": "article.md", "source_urls": []}
            (workspace / "article.md").write_text("---\ntitle: 测试标题\nsummary: 摘要\n---\n\n正文。", encoding="utf-8")
            (workspace / "score-report.json").write_text(
                json.dumps({"body_signature": "old-score", "passed": False, "quality_gates": {"credibility_passed": False}, "score_breakdown": [{"dimension": "事实/案例/对比托底", "score": 2}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            readiness = build_pipeline_readiness(workspace, manifest)
            render_blockers = collect_render_blockers(workspace, manifest)
            publish_blockers = collect_publish_blockers(workspace, manifest)
            self.assertFalse(readiness.get("score_ready"))
            self.assertTrue(any("score-report.json" in item for item in render_blockers))
            self.assertTrue(any("score-report.json" in item for item in publish_blockers))

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
