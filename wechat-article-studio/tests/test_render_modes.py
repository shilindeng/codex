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


import legacy_studio as legacy  # noqa: E402
from core.editorial import enhance_content_html  # noqa: E402
from core.layout import analyze_content_signals, choose_layout_style, preview_css  # noqa: E402
from core.layout_skin import choose_layout_skin  # noqa: E402
from core.publication_cleanup import expand_compact_markdown_lists  # noqa: E402
from core.workflow import apply_reference_policy, build_parser, normalize_publication_body  # noqa: E402
from core.render import cmd_render, highlight_technical_terms_markdown  # noqa: E402
from core.wechat_fragment import build_header_module_html, choose_wechat_publication_style  # noqa: E402


class RenderModeTests(unittest.TestCase):
    def test_apply_reference_policy_preserves_markdown_breaks(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            body = "\n".join(
                [
                    "First paragraph with https://example.com/source",
                    "",
                    "## Section Two",
                    "",
                    "Second paragraph [1]",
                    "",
                    "Third paragraph【2】",
                ]
            )
            normalized, findings = apply_reference_policy(workspace, {}, "Test title", body)
            self.assertIn("First paragraph with example.com", normalized)
            self.assertIn("\n\n## Section Two\n\n", normalized)
            self.assertIn("Second paragraph", normalized)
            self.assertIn("Third paragraph", normalized)
            self.assertNotIn("https://example.com/source", normalized)
            self.assertEqual(findings["raw_urls_after"], 0)

    def test_highlight_technical_terms_is_conservative(self):
        source = "\n".join(
            [
                "设置 OPENAI_API_KEY 并调用 /v1/chat/completions。",
                "访问 https://example.com/api 保持原样。",
                "| key | value |",
                "| --- | --- |",
                "| env | OPENAI_API_KEY |",
                "```bash",
                "export OPENAI_API_KEY=test",
                "```",
            ]
        )
        rendered = highlight_technical_terms_markdown(source)
        self.assertIn("`OPENAI_API_KEY`", rendered)
        self.assertIn("`/v1/chat/completions`", rendered)
        self.assertIn("https://example.com/api", rendered)
        self.assertIn("| env | OPENAI_API_KEY |", rendered)
        self.assertIn("export OPENAI_API_KEY=test", rendered)

    def test_render_drop_title_keeps_summary_for_wechat(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "测试标题",
                        "summary": "这是一段摘要",
                        "article_path": "article.md",
                        "wechat_header_mode": "drop-title",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("正文提到 OPENAI_API_KEY 和 /v1/chat/completions。", encoding="utf-8")
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            preview_html = (workspace / "article.html").read_text(encoding="utf-8")
            wechat_html = (workspace / "article.wechat.html").read_text(encoding="utf-8")
            self.assertIn("测试标题", preview_html)
            self.assertIn("这是一段摘要", wechat_html)
            self.assertNotIn("<h1", wechat_html)
            self.assertIn("<code>OPENAI_API_KEY</code>", preview_html)
            self.assertIn("wx-hero", preview_html)

    def test_render_trims_hero_strap_for_mobile_first_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            long_summary = "银行业开始高频谈 AI，甚至出现“去年实现超 8000 人替代效率”这种说法。真正值得看的，不是一句口号，而是传统行业第一次把 AI 的效率红利直接折算进组织结构。"
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "银行业 AI 竞争突然提速",
                        "summary": long_summary,
                        "article_path": "article.md",
                        "wechat_header_mode": "drop-title",
                        "layout_plan": {"hero_module": "hero-checkpoint", "layout_archetype": "commentary"},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("正文第一段。\n\n正文第二段。", encoding="utf-8")
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            wechat_html = (workspace / "article.wechat.html").read_text(encoding="utf-8")
            self.assertIn("银行业开始高频谈 AI", wechat_html)
            self.assertNotIn("真正值得看的，不是一句口号，而是传统行业第一次把 AI 的效率红利直接折算进组织结构", wechat_html)

    def test_strip_leading_h1_is_tolerant(self):
        body = "# 《OpenAI：API-上手》\n\n正文内容"
        stripped = legacy.strip_leading_h1(body, "OpenAI API 上手")
        self.assertEqual(stripped, "正文内容")

    def test_auto_layout_uses_article_archetype(self):
        signals = analyze_content_signals("这是一个观点分析，包含一段引用。\n\n> 一句判断", "md")
        decision = choose_layout_style("auto", signals, {"viral_blueprint": {"article_archetype": "commentary"}})
        self.assertEqual(decision.style, "magazine")

    def test_commentary_with_inline_code_does_not_force_tech_theme(self):
        source = "这是一篇评论稿，讨论 `Chrome DevTools MCP`、`Playwright`、`CDP`、`Console`、`Network`、`DOM`、`Trace`、`Profiler`。"
        signals = analyze_content_signals(source, "md")
        decision = choose_layout_style("auto", signals, {"viral_blueprint": {"article_archetype": "commentary"}})
        self.assertEqual(decision.style, "magazine")

    def test_commentary_title_with_ru_he_is_not_misclassified_as_tutorial(self):
        signals = analyze_content_signals("这是一篇分析稿。", "md")
        decision = choose_layout_style(
            "auto",
            signals,
            {
                "selected_title": "APP已死，Agent当立：AI如何终结图标时代",
                "summary": "这不是教程，而是一次行业信号拆解。",
                "image_controls": {"preset": "editorial-grain"},
                "audience": "职场人/创业者/产品经理/开发者",
            },
        )
        self.assertEqual(decision.style, "magazine")

    def test_render_keeps_light_citations_and_appends_reference_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "测试标题",
                        "summary": "这是一段摘要",
                        "article_path": "article.md",
                        "wechat_header_mode": "drop-title",
                        "references_path": "references.json",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("正文内容里有一个判断 [1]。", encoding="utf-8")
            (workspace / "references.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {"index": 1, "url": "https://example.com/a", "title": "官方文档", "domain": "example.com", "note": "一条说明"}
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            wechat_html = (workspace / "article.wechat.html").read_text(encoding="utf-8")
            preview_html = (workspace / "article.html").read_text(encoding="utf-8")
            self.assertIn("参考资料", wechat_html)
            self.assertIn("查看原文", wechat_html)
            self.assertIn("正文内容里有一个判断", wechat_html)
            self.assertIn("<sup", wechat_html)
            self.assertIn("[1]", wechat_html)
            self.assertIn('data-wx-role="reference-card"', preview_html)

    def test_publication_cleanup_removes_quote_labels_and_manual_reference_block(self):
        body = "\n".join(
            [
                "正文开头",
                "",
                "> 金句 1：当用户把决定权交给你，你就不能只提供功能，你得提供解释。",
                "",
                "## 结尾",
                "",
                "留个问题：如果是你，你会怎么选？",
                "",
                "> [!TIP] 参考资料",
                "> 1) 某来源：[1]",
                "> 2) 某论文：[2]",
            ]
        )
        cleaned = normalize_publication_body("测试标题", body)
        self.assertNotIn("金句 1：", cleaned)
        self.assertIn("当用户把决定权交给你", cleaned)
        self.assertNotIn("[!TIP] 参考资料", cleaned)
        self.assertNotIn("某来源：[1]", cleaned)

    def test_publication_cleanup_strips_ai_label_phrases(self):
        body = "\n".join(
            [
                "## 行业判断",
                "",
                "行业判断：这段正文应该直接进入内容。",
                "",
                "### 事实/依据",
                "",
                "事实/依据：这里写真实内容，不要保留标签。",
                "",
                "边界/误判：这里也应该只保留后面的内容。",
            ]
        )
        cleaned = normalize_publication_body("测试标题", body)
        self.assertNotIn("## 行业判断", cleaned)
        self.assertNotIn("### 事实/依据", cleaned)
        self.assertNotIn("行业判断：", cleaned)
        self.assertNotIn("事实/依据：", cleaned)
        self.assertNotIn("边界/误判：", cleaned)
        self.assertIn("这段正文应该直接进入内容。", cleaned)
        self.assertIn("这里写真实内容，不要保留标签。", cleaned)
        self.assertIn("这里也应该只保留后面的内容。", cleaned)

    def test_publication_cleanup_expands_compact_bullet_lists(self):
        body = "- 第一条先说清楚。 - 第二条再补一句。 - 第三条最后收住。"
        cleaned = normalize_publication_body("测试标题", body)
        self.assertIn("- 第一条先说清楚。", cleaned)
        self.assertIn("\n- 第二条再补一句。\n", cleaned)
        self.assertIn("\n- 第三条最后收住。\n", cleaned)

    def test_header_module_avoids_industry_judgment_label(self):
        header = build_header_module_html(
            title="测试标题",
            summary="测试摘要",
            hero_module="hero-judgment",
            archetype="commentary",
        )
        self.assertNotIn("行业判断", header)
        self.assertIn("深度观察", header)

    def test_wechat_publication_style_preserves_explicit_theme_choice(self):
        style = choose_wechat_publication_style(
            "magazine",
            {"viral_blueprint": {"article_archetype": "commentary"}},
            rich_blocks=["quote"],
            publication_report={"suggested_wechat_style": "clean"},
        )
        self.assertEqual(style, "magazine")

    def test_render_strips_gold_quote_labels_and_manual_reference_blocks_from_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "测试标题",
                        "summary": "摘要",
                        "article_path": "article.md",
                        "assembled_path": "assembled.md",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "assembled.md").write_text(
                "\n".join(
                    [
                        "正文开头",
                        "",
                        "> 金句 1：一句重要判断。",
                        "",
                        "## 结尾",
                        "",
                        "留个问题：如果是你，你会怎么选？",
                        "",
                        "> [!TIP] 参考资料",
                        "> 1) 某来源：[1]",
                    ]
                ),
                encoding="utf-8",
            )
            (workspace / "references.json").write_text(
                json.dumps(
                    {"items": [{"index": 1, "url": "https://example.com/a", "title": "官方文档", "domain": "example.com", "note": ""}]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            wechat_html = (workspace / "article.wechat.html").read_text(encoding="utf-8")
            self.assertNotIn("金句 1：", wechat_html)
            self.assertNotIn("提示</strong> 参考资料", wechat_html)
            self.assertIn("参考资料", wechat_html)
            self.assertIn("查看原文", wechat_html)

    def test_render_drop_title_summary_hides_hero_strap(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "娴嬭瘯鏍囬",
                        "summary": "杩欐槸涓€娈垫憳瑕?锛岀敤鏉ユ祴璇曢灞忔憳瑕佹槸鍚︿細琚殣钘忋€?",
                        "article_path": "article.md",
                        "wechat_header_mode": "drop-title-summary",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("姝ｆ枃绗竴娈点€?", encoding="utf-8")
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    input_format="auto",
                    wechat_header_mode="drop-title-summary",
                )
            )
            wechat_html = (workspace / "article.wechat.html").read_text(encoding="utf-8")
            self.assertIn("娴嬭瘯鏍囬", wechat_html)
            self.assertNotIn("杩欐槸涓€娈垫憳瑕?", wechat_html)


    def test_auto_skin_prefers_comparison_family(self):
        signals = analyze_content_signals("A 和 B 的差异越来越明显。", "md")
        decision = choose_layout_skin("auto", "business", {"viral_blueprint": {"article_archetype": "comparison"}}, signals, rich_blocks=["compare"])
        self.assertIn(decision.key, {"aurora", "business", "morandi"})

    def test_preview_skin_css_covers_structured_modules(self):
        css = preview_css("business", "business", "#0F766E")
        self.assertIn('[data-wx-skin="business"] .wx-content table', css)
        self.assertIn('[data-wx-role="compare-header"]', css)
        self.assertIn('[data-wx-role="stat-card"]', css)
        self.assertIn('[data-wx-role="reference-card"]', css)

    def test_editorial_module_labels_avoid_aiish_terms(self):
        enhanced_html, _ = enhance_content_html(
            "<h2>第二部分</h2><p>这里是一段正文。</p>",
            {
                "layout_plan": {
                    "section_modules": [
                        {
                            "module_type": "boundary-card",
                            "heading_role": "section-label",
                        }
                    ]
                }
            },
        )
        self.assertNotIn("边界 / 误判", enhanced_html)
        self.assertNotIn("事实 / 依据", enhanced_html)
        self.assertIn("别急着下结论", enhanced_html)

    def test_render_persists_layout_skin(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "测试标题",
                        "summary": "这是一段摘要。",
                        "article_path": "article.md",
                        "viral_blueprint": {"article_archetype": "comparison"},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("## 对比\n\nA 和 B 的差异很明显。", encoding="utf-8")
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            preview_html = (workspace / "article.html").read_text(encoding="utf-8")
            self.assertTrue(manifest.get("layout_skin"))
            self.assertIn('data-wx-skin="', preview_html)

    def test_render_structured_modules_pick_up_skin_css(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "测试标题",
                        "summary": "测试摘要",
                        "article_path": "article.md",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text(
                "\n".join(
                    [
                        "## 数据对比",
                        "",
                        "| 指标 | 数值 |",
                        "| --- | --- |",
                        "| 转化率 | 12% |",
                    ]
                ),
                encoding="utf-8",
            )
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="business",
                    layout_skin="business",
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            preview_html = (workspace / "article.html").read_text(encoding="utf-8")
            self.assertIn('data-wx-skin="business"', preview_html)
            self.assertIn('.wx-article[data-wx-skin="business"] .wx-content table{', preview_html)
            self.assertIn('.wx-article[data-wx-skin="business"] .wx-content th{', preview_html)

    def test_render_uses_auto_skin_preference_instead_of_old_resolved_skin(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "AI 工作流上手指南",
                        "summary": "一篇偏实操的教程稿。",
                        "article_path": "article.md",
                        "layout_skin": "magazine",
                        "layout_skin_preference": "auto",
                        "layout_style_preference": "tech",
                        "layout_plan": {"layout_archetype": "tutorial", "hero_module": "hero-checkpoint", "module_types": ["checklist"]},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text(
                "\n".join(
                    [
                        "## 三步搭好工作流",
                        "",
                        "1. 先配置环境",
                        "2. 再执行脚本",
                        "3. 最后验收结果",
                        "",
                        "```bash",
                        "python scripts/studio.py render --workspace demo",
                        "```",
                    ]
                ),
                encoding="utf-8",
            )
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style=None,
                    layout_skin=None,
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            preview_html = (workspace / "article.html").read_text(encoding="utf-8")
            self.assertEqual(manifest.get("layout_style_preference"), "tech")
            self.assertEqual(manifest.get("layout_skin_preference"), "auto")
            self.assertEqual(manifest.get("layout_skin"), "tech")
            self.assertNotEqual(manifest.get("layout_skin"), "magazine")
            self.assertIn('data-wx-skin="tech"', preview_html)

    def test_compact_list_helper_supports_ordered_lists(self):
        expanded = expand_compact_markdown_lists("1. 第一步先准备。 2. 第二步再执行。 3. 第三步做检查。")
        self.assertIn("1. 第一步先准备。", expanded)
        self.assertIn("\n2. 第二步再执行。\n", expanded)
        self.assertIn("\n3. 第三步做检查。", expanded)

    def test_render_expands_compact_lists_and_avoids_old_module_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "测试标题",
                        "summary": "测试摘要",
                        "article_path": "article.md",
                        "layout_plan": {
                            "section_modules": [
                                {
                                    "module_type": "boundary-card",
                                    "heading_role": "section-label",
                                }
                            ]
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text(
                "\n".join(
                    [
                        "## 第二部分",
                        "",
                        "这段正文先铺垫一下。",
                        "",
                        "- 第一条先说清楚。 - 第二条再补一句。 - 第三条最后收住。",
                    ]
                ),
                encoding="utf-8",
            )
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="business",
                    layout_skin="business",
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            preview_html = (workspace / "article.html").read_text(encoding="utf-8")
            self.assertNotIn("边界 / 误判", preview_html)
            self.assertIn("别急着下结论", preview_html)
            self.assertIn("<li>第一条先说清楚。</li>", preview_html)
            self.assertIn("<li>第二条再补一句。</li>", preview_html)
            self.assertIn("<li>第三条最后收住。</li>", preview_html)


    def test_auto_skin_prefers_tech_for_tutorial_steps(self):
        source = "## 步骤\n\n1. 第一步先配置环境\n2. 第二步跑起来\n3. 第三步检查结果\n\n`OPENAI_API_KEY` 要先准备好。"
        signals = analyze_content_signals(source, "md")
        decision = choose_layout_skin(
            "auto",
            "tech",
            {"viral_blueprint": {"article_archetype": "tutorial"}, "selected_title": "AI 工作流上手指南"},
            signals,
            rich_blocks=["steps"],
        )
        self.assertEqual(decision.key, "tech")

    def test_auto_skin_prefers_morandi_for_calm_editorial(self):
        source = "> 这不是一句结论，而是一段复盘。\n\n> 真正值得看的，是长期边界。"
        signals = analyze_content_signals(source, "md")
        decision = choose_layout_skin(
            "auto",
            "magazine",
            {"viral_blueprint": {"article_archetype": "commentary"}, "selected_title": "行业复盘：从热闹回到长期边界"},
            signals,
            rich_blocks=["quote"],
        )
        self.assertEqual(decision.key, "morandi")

    def test_render_auto_skin_does_not_reuse_previous_resolved_skin(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "一线对话：银行团队怎么真正把 AI 用进去了",
                        "summary": "这是一篇偏叙事的文章。",
                        "article_path": "article.md",
                        "viral_blueprint": {"article_archetype": "narrative"},
                        "layout_skin": "business",
                        "layout_skin_reason": "stale_previous_render",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("> 第一段就是现场对话。\n\n那天我们在会议室里聊了很久。", encoding="utf-8")
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("layout_skin"), "warm")
            self.assertEqual(manifest.get("layout_skin_preference"), "auto")

    def test_render_explicit_layout_skin_updates_preference(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "测试标题",
                        "summary": "测试摘要",
                        "article_path": "article.md",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("正文内容", encoding="utf-8")
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    layout_skin="neon",
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("layout_skin"), "neon")
            self.assertEqual(manifest.get("layout_skin_preference"), "neon")

    def test_parser_accepts_layout_skin_for_main_commands(self):
        parser = build_parser()
        commands = [
            ["run", "--workspace", "job", "--layout-skin", "neon"],
            ["hosted-run", "--workspace", "job", "--layout-skin", "morandi"],
            ["render", "--workspace", "job", "--layout-skin", "business"],
            ["all", "--workspace", "job", "--layout-skin", "tech"],
        ]
        for argv in commands:
            with self.subTest(argv=argv):
                parsed = parser.parse_args(argv)
                self.assertTrue(hasattr(parsed, "layout_skin"))
                self.assertIsNotNone(parsed.layout_skin)


if __name__ == "__main__":
    unittest.main()
