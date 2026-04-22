import json
import sys
import tempfile
import unittest
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.publication import prepare_publication_artifacts  # noqa: E402
from core.render import cmd_render  # noqa: E402
import argparse  # noqa: E402


class PublicationPipelineTests(unittest.TestCase):
    def test_prepare_publication_rewrites_compare_stats_and_limits_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {
                "selected_title": "测试标题",
                "summary": "摘要",
                "article_path": "article.md",
                "viral_blueprint": {"article_archetype": "commentary"},
            }
            (workspace / "article.md").write_text(
                "\n\n".join(
                    [
                        "# 测试标题",
                        "问题不在模型数量，而在决策顺序。",
                        "接入后的回答准确率达到 76.10%，比原生记忆提升近 59%。",
                        "![图1](a.png)",
                        "![图2](b.png)",
                        "![图3](c.png)",
                    ]
                ),
                encoding="utf-8",
            )
            payload = prepare_publication_artifacts(workspace, manifest)
            publication = (workspace / "publication.md").read_text(encoding="utf-8")
            self.assertIn("| 容易误判 | 真正问题 |", publication)
            self.assertIn("- 回答准确率：76.10%", publication)
            self.assertEqual(publication.count("!["), 1)
            self.assertEqual(payload.get("removed_existing_image_blocks"), 2)

    def test_prepare_publication_preserves_existing_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {
                "selected_title": "测试标题",
                "summary": "摘要",
                "article_path": "article.md",
            }
            (workspace / "article.md").write_text("正文内容里有一个判断 [1]。", encoding="utf-8")
            (workspace / "references.json").write_text(
                json.dumps(
                    {"items": [{"index": 1, "url": "https://example.com/a", "title": "官方文档", "domain": "example.com", "note": "一条说明"}]},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            prepare_publication_artifacts(workspace, manifest)
            payload = json.loads((workspace / "references.json").read_text(encoding="utf-8"))
            self.assertEqual(len(payload.get("items") or []), 1)
            self.assertEqual((payload.get("items") or [])[0].get("title"), "官方文档")

    def test_prepare_publication_keeps_normal_summary_and_expands_inline_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            manifest = {
                "selected_title": "测试标题",
                "summary": "这篇文章真正要看的，不是模型热度，而是交付链路和谁在为返工买单。",
                "article_path": "article.md",
                "viral_blueprint": {"article_archetype": "commentary"},
            }
            (workspace / "article.md").write_text(
                "\n\n".join(
                    [
                        "---",
                        "title: 测试标题",
                        "summary: 这篇文章真正要看的，不是模型热度，而是交付链路和谁在为返工买单。",
                        "---",
                        "",
                        "团队今天最容易误判的，不是模型不够强，而是返工已经开始吞掉节奏。",
                        "",
                        "| 常见做法 | 真正有效的做法 | 后果差别 | | --- | --- | --- | | 先上工具 | 先改流程 | 一个忙得热闹，一个真的出结果 |",
                    ]
                ),
                encoding="utf-8",
            )
            payload = prepare_publication_artifacts(workspace, manifest)
            publication = (workspace / "publication.md").read_text(encoding="utf-8")
            self.assertIn("summary: 这篇文章真正要看的，不是模型热度，而是交付链路和谁在为返工买单。", publication)
            self.assertIn("| 常见做法 | 真正有效的做法 | 后果差别 |", publication)
            self.assertIn("| --- | --- | --- |", publication)
            self.assertNotIn("- 会上把这个尴尬点", publication)
            self.assertGreaterEqual(int(payload.get("lead_paragraph_count") or 0), 1)

    def test_render_uses_publication_whitelist_for_inline_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "测试标题",
                        "summary": "摘要",
                        "article_path": "article.md",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text("OpenAI 正在更新 API，先设置 OPENAI_API_KEY，再请求 /v1/chat/completions。", encoding="utf-8")
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    layout_skin=None,
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            preview_html = (workspace / "article.html").read_text(encoding="utf-8")
            self.assertIn("<code>OPENAI_API_KEY</code>", preview_html)
            self.assertIn("<code>/v1/chat/completions</code>", preview_html)
            self.assertNotIn("<code>OpenAI</code>", preview_html)

    def test_render_prefers_newer_publication_over_stale_assembled(self):
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
            (workspace / "article.md").write_text("问题不在模型数量，而在决策顺序。", encoding="utf-8")
            (workspace / "assembled.md").write_text("---\ntitle: 测试标题\nsummary: 摘要\n---\n\n旧图文稿。\n", encoding="utf-8")
            old_time = time.time() - 60
            os = __import__("os")
            os.utime(workspace / "assembled.md", (old_time, old_time))
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    layout_skin=None,
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            preview_html = (workspace / "article.html").read_text(encoding="utf-8")
            self.assertIn("真正问题", preview_html)
            self.assertNotIn("旧图文稿", preview_html)

    def test_render_uses_newer_assembled_with_inserted_images(self):
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
            (workspace / "article.md").write_text("原始正文。", encoding="utf-8")
            (workspace / "assembled.md").write_text(
                "---\ntitle: 测试标题\nsummary: 摘要\n---\n\n插图正文。\n\n![正文图](assets/images/inline-01.png)\n",
                encoding="utf-8",
            )
            now = time.time() + 60
            os = __import__("os")
            os.utime(workspace / "assembled.md", (now, now))
            cmd_render(
                argparse.Namespace(
                    workspace=str(workspace),
                    input=None,
                    output="article.html",
                    accent_color="#0F766E",
                    layout_style="auto",
                    layout_skin=None,
                    input_format="auto",
                    wechat_header_mode="drop-title",
                )
            )
            preview_html = (workspace / "article.html").read_text(encoding="utf-8")
            wechat_html = (workspace / "article.wechat.html").read_text(encoding="utf-8")
            self.assertIn("assets/images/inline-01.png", preview_html)
            self.assertIn("assets/images/inline-01.png", wechat_html)
            self.assertIn("插图正文", preview_html)
            self.assertNotIn("原始正文", preview_html)

    def test_render_theme_personality_is_distinct_for_wechat_output(self):
        article = "\n".join(
            [
                "> 这是一段引用文字。",
                "",
                "```bash",
                "python scripts/studio.py render --workspace demo",
                "```",
                "",
                "正文内容里有一个判断 [1]。",
            ]
        )
        refs = {
            "items": [
                {"index": 1, "url": "https://example.com/a", "title": "官方文档", "domain": "example.com", "note": "一条说明"}
            ]
        }
        expected_markers = {
            "magazine": ["font-family:Georgia", "border-top:1px solid #1f1a15", "阅读原文"],
            "business": ["border-left:4px solid #1d4ed8", "background:#eff6ff", "查看来源"],
            "warm": ["background:#fff8f1", "border:1px solid #f0dcc2", "继续阅读"],
            "tech": ["background:#0f172a", "color:#7dd3fc", "打开来源"],
        }
        for style, markers in expected_markers.items():
            with self.subTest(style=style):
                with tempfile.TemporaryDirectory() as tmp:
                    workspace = Path(tmp)
                    (workspace / "manifest.json").write_text(
                        json.dumps(
                            {"selected_title": "测试标题", "summary": "摘要", "article_path": "article.md", "references_path": "references.json"},
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    (workspace / "article.md").write_text(article, encoding="utf-8")
                    (workspace / "references.json").write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
                    cmd_render(
                        argparse.Namespace(
                            workspace=str(workspace),
                            input=None,
                            output="article.html",
                            accent_color="#0F766E",
                            layout_style=style,
                            layout_skin=style if style in {"magazine", "business", "warm", "tech"} else None,
                            input_format="auto",
                            wechat_header_mode="drop-title",
                        )
                    )
                    wechat_html = (workspace / "article.wechat.html").read_text(encoding="utf-8")
                    for marker in markers:
                        self.assertIn(marker, wechat_html)


if __name__ == "__main__":
    unittest.main()
