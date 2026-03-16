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
from core.layout import analyze_content_signals, choose_layout_style  # noqa: E402
from core.render import cmd_render, highlight_technical_terms_markdown  # noqa: E402


class RenderModeTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
