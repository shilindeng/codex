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


from core.editorial import enhance_content_html  # noqa: E402
from core.layout import analyze_content_signals, choose_layout_style, markdown_to_html, sanitize_html_fragment  # noqa: E402
from core.render import cmd_render  # noqa: E402


class EditorialLayoutTests(unittest.TestCase):
    def test_steps_block_drives_tech_layout(self):
        md = "\n".join(
            [
                "1. 打开工作目录",
                "2. 调整排版参数",
                "3. 生成最终稿件",
            ]
        )
        enhanced, rich_blocks = enhance_content_html(markdown_to_html(md), {})
        preview = sanitize_html_fragment(enhanced)
        decision = choose_layout_style(
            "auto",
            analyze_content_signals(md, "md"),
            {"viral_blueprint": {"article_archetype": "tutorial"}},
            rich_blocks=rich_blocks,
        )
        self.assertIn("steps", rich_blocks)
        self.assertIn('data-wx-role="steps"', preview)
        self.assertEqual(decision.style, "tech")

    def test_compare_block_drives_business_layout(self):
        md = "\n".join(
            [
                "| 旧方案 | 新方案 |",
                "| --- | --- |",
                "| 手工发稿 | 自动排版 |",
                "| 审核慢 | 一次出稿 |",
            ]
        )
        enhanced, rich_blocks = enhance_content_html(markdown_to_html(md), {})
        preview = sanitize_html_fragment(enhanced)
        decision = choose_layout_style(
            "auto",
            analyze_content_signals(md, "md"),
            {
                "viral_blueprint": {"article_archetype": "case-study"},
                "audience": "运营 / 管理者 / 老板",
            },
            rich_blocks=rich_blocks,
        )
        self.assertIn("compare", rich_blocks)
        self.assertIn('data-wx-role="compare"', preview)
        self.assertEqual(decision.style, "business")

    def test_dialogue_block_drives_warm_layout(self):
        md = "\n".join(
            [
                "小王：今天还要继续改吗？",
                "",
                "老周：先把最影响结果的地方改掉。",
                "",
                "小王：那就先把最终排版做好。",
            ]
        )
        enhanced, rich_blocks = enhance_content_html(markdown_to_html(md), {})
        preview = sanitize_html_fragment(enhanced)
        decision = choose_layout_style(
            "auto",
            analyze_content_signals(md, "md"),
            {"viral_blueprint": {"article_archetype": "narrative"}},
            rich_blocks=rich_blocks,
        )
        self.assertIn("dialogue", rich_blocks)
        self.assertIn('data-wx-role="dialogue"', preview)
        self.assertEqual(decision.style, "warm")

    def test_stats_block_can_drive_poster_layout(self):
        md = "\n".join(
            [
                "- 留存：52%",
                "- 转化：3倍",
                "- 周期：7天",
            ]
        )
        enhanced, rich_blocks = enhance_content_html(markdown_to_html(md), {})
        preview = sanitize_html_fragment(enhanced)
        decision = choose_layout_style(
            "auto",
            analyze_content_signals(md, "md"),
            {"viral_blueprint": {"article_archetype": "commentary"}},
            rich_blocks=rich_blocks,
        )
        self.assertIn("stats", rich_blocks)
        self.assertIn('data-wx-role="stats-grid"', preview)
        self.assertEqual(decision.style, "poster")

    def test_quote_cleanup_removes_blank_quote_placeholder(self):
        md = "\n".join(
            [
                "> 真正拉开差距的，不是你用了多少工具，而是你有没有先把判断排成顺序。",
                ">",
                "> - 某运营负责人",
            ]
        )
        enhanced, rich_blocks = enhance_content_html(markdown_to_html(md), {})
        preview = sanitize_html_fragment(enhanced)
        self.assertIn("quote", rich_blocks)
        self.assertNotIn("&gt;", preview)
        self.assertIn('data-wx-role="quote-card"', preview)

    def test_render_pipeline_persists_rich_blocks_and_outputs_inline_styles(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "排版自动化清单",
                        "summary": "三步完成最终排版。",
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
                        "1. 整理正文结构",
                        "2. 选择最合适的版式",
                        "3. 生成可发布成品",
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
                    layout_style="auto",
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )

            preview_html = (workspace / "article.html").read_text(encoding="utf-8")
            wechat_html = (workspace / "article.wechat.html").read_text(encoding="utf-8")
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))

            self.assertIn('data-wx-role="steps"', preview_html)
            self.assertIn("display:inline-flex", wechat_html)
            self.assertNotIn("data-wx-role", wechat_html)
            self.assertEqual(manifest.get("layout_style"), "tech")
            self.assertEqual(manifest.get("layout_rich_blocks"), ["steps"])


if __name__ == "__main__":
    unittest.main()
