import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.viral_pipeline import apply_source_similarity_gate, build_source_similarity_report, choose_discovery_selection, score_discovery_candidates  # noqa: E402
from core.workflow import cmd_adapt_platforms, cmd_analyze_viral, cmd_discover_viral, cmd_select_viral, cmd_viral_run  # noqa: E402


class ViralPipelineTests(unittest.TestCase):
    def test_discovery_ranking_prefers_account_fit_and_engagement(self):
        candidates = [
            {
                "platform": "wechat",
                "url": "https://mp.weixin.qq.com/s/a",
                "title": "AI 成本正在改写企业决策",
                "author": "案例库",
                "published_at": "2026-04-07T08:00:00+00:00",
                "engagement": {"likes": 120, "comments": 30, "shares": 12},
                "excerpt": "成本、风险、决策",
            },
            {
                "platform": "weibo",
                "url": "https://weibo.com/1",
                "title": "模型排行榜又更新了",
                "author": "热搜号",
                "published_at": "2026-04-07T08:00:00+00:00",
                "engagement": {"likes": 50, "comments": 10, "shares": 1},
                "excerpt": "参数、榜单、热搜",
            },
            {
                "platform": "bilibili",
                "url": "https://www.bilibili.com/video/BV1",
                "title": "AI 岗位变化复盘",
                "author": "研究员",
                "published_at": "2026-04-06T08:00:00+00:00",
                "engagement": {"views": 52000, "comments": 220, "shares": 60},
                "excerpt": "岗位、成本、案例",
            },
        ]
        ranked = score_discovery_candidates(
            candidates,
            "AI 成本 岗位 变化",
            {
                "discovery_priority_keywords": ["成本", "岗位", "案例"],
                "discovery_deprioritize_keywords": ["榜单", "热搜", "参数"],
            },
        )
        self.assertEqual(ranked[0]["platform"], "bilibili")
        selected = choose_discovery_selection(ranked)
        self.assertEqual(len([item for item in selected if item.get("selection_tier") == "primary"]), min(3, len(selected)))

    def test_select_viral_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "viral-discovery.json").write_text(
                json.dumps(
                    {
                        "query": "AI 成本",
                        "candidates": [
                            {
                                "source_id": "a1",
                                "platform": "wechat",
                                "url": "https://mp.weixin.qq.com/s/a1",
                                "title": "标题 A",
                            },
                            {
                                "source_id": "a2",
                                "platform": "bilibili",
                                "url": "https://www.bilibili.com/video/BV1",
                                "title": "标题 B",
                            },
                        ],
                        "recommended_selection": [
                            {
                                "source_id": "a1",
                                "platform": "wechat",
                                "url": "https://mp.weixin.qq.com/s/a1",
                                "title": "标题 A",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_select_viral(type("Args", (), {"workspace": str(workspace), "index": [1, 2]})())
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("viral_query"), "AI 成本")
            self.assertEqual(manifest.get("viral_selected_count"), 2)
            self.assertEqual(
                manifest.get("source_urls"),
                ["https://mp.weixin.qq.com/s/a1", "https://www.bilibili.com/video/BV1"],
            )

    def test_discover_viral_resets_old_query_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "topic": "旧选题",
                        "viral_query": "旧 query",
                        "selected_title": "旧标题",
                        "research_status": "done",
                        "title_status": "done",
                        "outline_status": "done",
                        "draft_status": "done",
                        "review_status": "done",
                        "score_status": "done",
                        "render_status": "done",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            for rel, content in {
                "research.json": "{}",
                "source-corpus.json": "{}",
                "viral-dna.json": "{}",
                "ideation.json": "{}",
                "article.md": "# 旧正文\n",
                "score-report.json": "{}",
            }.items():
                target = workspace / rel
                target.write_text(content, encoding="utf-8")
            versions = workspace / "versions"
            versions.mkdir()
            (versions / "wechat.md").write_text("旧版本", encoding="utf-8")

            fake_payload = {
                "query": "新 query",
                "platforms": ["wechat"],
                "platform_status": {"wechat": {"available": True, "mode": "fallback", "detail": "ok"}},
                "candidates": [{"source_id": "x1", "platform": "wechat", "url": "https://mp.weixin.qq.com/s/x1", "title": "新标题"}],
                "recommended_selection": [{"source_id": "x1", "platform": "wechat", "url": "https://mp.weixin.qq.com/s/x1", "title": "新标题"}],
            }
            with patch("core.workflow.discover_viral_candidates", return_value=fake_payload):
                cmd_discover_viral(type("Args", (), {"workspace": str(workspace), "query": "新 query", "topic": None, "platform": [], "limit_per_platform": 3})())
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("viral_query"), "新 query")
            self.assertEqual(manifest.get("topic"), "新 query")
            self.assertEqual(manifest.get("selected_title"), "")
            self.assertEqual(manifest.get("research_status"), "not_started")
            self.assertFalse((workspace / "source-corpus.json").exists())
            self.assertFalse((workspace / "article.md").exists())
            self.assertFalse((workspace / "versions").exists())

    def test_analyze_viral_writes_research_and_dna(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "source-corpus.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "platform": "wechat",
                                "url": "https://mp.weixin.qq.com/s/a1",
                                "title": "AI 成本不是热闹，而是决策分水岭",
                                "selection_tier": "primary",
                                "fulltext_markdown": "会议室里，大家盯着预算表。\n\n## 真正的分水岭\n\n问题不在模型数量，而在决策顺序。",
                                "comments": [{"content": "太真实了"}],
                            },
                            {
                                "platform": "bilibili",
                                "url": "https://www.bilibili.com/video/BV1",
                                "title": "岗位变化复盘",
                                "selection_tier": "support",
                                "fulltext_markdown": "最近团队最难的不是招人，而是先判断什么该停。\n\n## 最后的判断\n\n先停错动作，再谈效率。",
                                "comments": [{"content": "如果是你会先停哪一步？"}],
                            },
                        ],
                        "readable_count": 2,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_analyze_viral(
                    type(
                        "Args",
                        (),
                        {
                            "workspace": str(workspace),
                            "topic": "AI 成本与岗位变化",
                            "angle": "",
                            "audience": "大众读者",
                            "style_sample": [],
                        },
                    )()
                )
            research = json.loads((workspace / "research.json").read_text(encoding="utf-8"))
            dna = json.loads((workspace / "viral-dna.json").read_text(encoding="utf-8"))
            self.assertIn("rewrite_constraints", research)
            self.assertIn("viral_blueprint", research)
            self.assertIn("editorial_blueprint", research)
            self.assertIn("reusable_elements", dna)
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("research_path"), "research.json")
            self.assertEqual(manifest.get("viral_dna_path"), "viral-dna.json")

    def test_source_similarity_gate_blocks_near_copy(self):
        body = "会议室里，大家盯着预算表。问题不在模型数量，而在决策顺序。先停错动作，再谈效率。"
        corpus = {
            "items": [
                {
                    "platform": "wechat",
                    "url": "https://mp.weixin.qq.com/s/a1",
                    "title": "AI 成本不是热闹，而是决策分水岭",
                    "fulltext_markdown": body,
                }
            ]
        }
        report = build_source_similarity_report(
            "AI 成本不是热闹，而是决策分水岭",
            body,
            {"topic": "AI 成本", "summary": "摘要", "viral_blueprint": {"article_archetype": "commentary"}},
            corpus,
        )
        gated = apply_source_similarity_gate(
            {
                "total_score": 90,
                "threshold": 80,
                "quality_gates": {"credibility_passed": True},
                "mandatory_revisions": [],
                "weaknesses": [],
            },
            report,
        )
        self.assertFalse(report.get("passed"))
        self.assertFalse(gated.get("quality_gates", {}).get("source_similarity_passed"))
        self.assertFalse(gated.get("passed"))

    def test_adapt_platforms_writes_version_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text(
                "---\ntitle: AI 成本与岗位变化\nsummary: 先停错动作，再谈效率。\n---\n\n## 真正的分水岭\n\n先停错动作，再谈效率。\n",
                encoding="utf-8",
            )
            (workspace / "viral-dna.json").write_text(
                json.dumps(
                    {
                        "reusable_elements": ["先停错动作，再谈效率。"],
                        "viral_blueprint": {"interaction_prompts": ["如果是你，你会先停哪一步？"]},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                cmd_adapt_platforms(type("Args", (), {"workspace": str(workspace), "title": None, "summary": None})())
            self.assertTrue((workspace / "versions" / "wechat.md").exists())
            self.assertFalse((workspace / "versions" / "xiaohongshu.md").exists())
            self.assertFalse((workspace / "versions" / "weibo.md").exists())
            self.assertFalse((workspace / "versions" / "bilibili.md").exists())

    def test_viral_run_orchestrates_fake_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)

            def fake_discover(args):
                (workspace / "viral-discovery.json").write_text(
                    json.dumps(
                        {
                            "query": "AI 成本",
                            "candidates": [{"source_id": "a1", "platform": "wechat", "url": "https://mp.weixin.qq.com/s/a1", "title": "标题 A"}],
                            "recommended_selection": [{"source_id": "a1", "platform": "wechat", "url": "https://mp.weixin.qq.com/s/a1", "title": "标题 A"}],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                manifest = {"topic": "AI 成本", "viral_query": "AI 成本", "selected_title": "标题 A", "audience": "大众读者"}
                (workspace / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                return 0

            def fake_select(args):
                manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
                manifest["viral_selection"] = [{"source_id": "a1", "platform": "wechat", "url": "https://mp.weixin.qq.com/s/a1", "title": "标题 A", "selection_tier": "primary"}]
                manifest["source_urls"] = ["https://mp.weixin.qq.com/s/a1"]
                (workspace / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                return 0

            def fake_collect(args):
                (workspace / "source-corpus.json").write_text(
                    json.dumps(
                        {
                            "items": [
                                {
                                    "platform": "wechat",
                                    "url": "https://mp.weixin.qq.com/s/a1",
                                    "title": "标题 A",
                                    "selection_tier": "primary",
                                    "fulltext_markdown": "首屏场景。\n\n## 分水岭\n\n真正关键的是决策顺序。",
                                }
                            ]
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return 0

            def fake_analyze(args):
                (workspace / "research.json").write_text(
                    json.dumps(
                        {
                            "topic": "AI 成本",
                            "angle": "",
                            "audience": "大众读者",
                            "sources": [{"url": "https://mp.weixin.qq.com/s/a1"}],
                            "evidence_items": ["样本强调决策顺序"],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                (workspace / "viral-dna.json").write_text(
                    json.dumps({"reusable_elements": ["真正关键的是决策顺序。"], "viral_blueprint": {"interaction_prompts": ["如果是你会怎么做？"]}}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
                manifest["research_path"] = "research.json"
                manifest["source_corpus_path"] = "source-corpus.json"
                manifest["viral_dna_path"] = "viral-dna.json"
                manifest["selected_title"] = "标题 A"
                (workspace / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                return 0

            def fake_titles(args):
                (workspace / "ideation.json").write_text(
                    json.dumps({"titles": [{"title": "标题 A"}], "selected_title": "标题 A"}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return 0

            def fake_outline(args):
                (workspace / "ideation.json").write_text(
                    json.dumps({"titles": [{"title": "标题 A"}], "selected_title": "标题 A", "outline": ["分水岭"], "outline_meta": {"sections": [{"heading": "分水岭", "goal": "展开", "evidence_need": "案例"}]}}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                return 0

            def fake_enhance(args):
                return 0

            def fake_write(args):
                (workspace / "article.md").write_text("---\ntitle: 标题 A\nsummary: 摘要\n---\n\n## 分水岭\n\n真正关键的是决策顺序。\n", encoding="utf-8")
                return 0

            def fake_revision(*args, **kwargs):
                return {"total_score": 90, "passed": True, "quality_gates": {"credibility_passed": True}, "score_breakdown": [], "threshold": 80}

            def fake_finalize(*args, **kwargs):
                manifest_obj = args[1]
                manifest_obj["stage"] = "score"
                manifest_obj["score_status"] = "done"
                manifest_obj["score_passed"] = True
                manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
                manifest["stage"] = "score"
                manifest["score_status"] = "done"
                manifest["score_passed"] = True
                (workspace / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                (workspace / "acceptance-report.json").write_text(
                    json.dumps(
                        {
                            "passed": True,
                            "gates": {
                                "acceptance_ready_passed": True,
                                "publish_ready": True,
                            },
                            "failed_gates": [],
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                return {}

            def fake_render(*args, **kwargs):
                return {}

            def fake_adapt(args):
                versions = workspace / "versions"
                versions.mkdir(exist_ok=True)
                (versions / "manifest.json").write_text(json.dumps({"items": []}, ensure_ascii=False, indent=2), encoding="utf-8")
                return 0

            with patch("core.workflow.cmd_discover_viral", side_effect=fake_discover), patch("core.workflow.cmd_select_viral", side_effect=fake_select), patch("core.workflow.cmd_collect_viral", side_effect=fake_collect), patch("core.workflow.cmd_analyze_viral", side_effect=fake_analyze), patch("core.workflow.cmd_titles", side_effect=fake_titles), patch("core.workflow.cmd_outline", side_effect=fake_outline), patch("core.workflow.cmd_enhance", side_effect=fake_enhance), patch("core.workflow.cmd_write", side_effect=fake_write), patch("core.workflow._run_revision_loop", side_effect=fake_revision), patch("core.workflow._finalize_after_score", side_effect=fake_finalize), patch("core.workflow._run_image_render_pipeline", side_effect=fake_render), patch("core.workflow.cmd_adapt_platforms", side_effect=fake_adapt):
                result = cmd_viral_run(
                    type(
                        "Args",
                        (),
                        {
                            "workspace": str(workspace),
                            "query": "AI 成本",
                            "topic": "AI 成本",
                            "angle": "",
                            "audience": "大众读者",
                            "title": None,
                            "title_count": 10,
                            "index": [],
                            "platform": [],
                            "limit_per_platform": 3,
                            "content_mode": "tech-balanced",
                            "wechat_header_mode": "drop-title",
                            "max_revision_rounds": 1,
                            "style_sample": [],
                            "to": "render",
                            "image_provider": None,
                            "image_preset": None,
                            "image_style_mode": None,
                            "image_preset_cover": None,
                            "image_preset_infographic": None,
                            "image_preset_inline": None,
                            "image_density": "balanced",
                            "image_layout_family": None,
                            "image_theme": None,
                            "image_style": None,
                            "image_type": None,
                            "image_mood": None,
                            "image_text_policy": None,
                            "image_label_language": None,
                            "custom_visual_brief": None,
                            "inline_count": 0,
                            "dry_run_images": True,
                            "dry_run_publish": True,
                            "confirmed_publish": False,
                            "gemini_model": "x",
                            "openai_model": "y",
                            "accent_color": "#0F766E",
                            "layout_style": None,
                            "layout_skin": None,
                            "input_format": "auto",
                        },
                    )()
                )
            self.assertEqual(result, 0)
            self.assertTrue((workspace / "article.md").exists())
            self.assertTrue((workspace / "versions" / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
