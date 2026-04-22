import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


import legacy_studio as legacy  # noqa: E402


def _image_args(**overrides):
    base = {
        "workspace": "",
        "provider": "openai-image",
        "image_preset": None,
        "image_style_mode": None,
        "image_preset_cover": None,
        "image_preset_infographic": None,
        "image_preset_inline": None,
        "image_density": None,
        "allow_closing_image": None,
        "image_layout_family": None,
        "image_theme": None,
        "image_style": None,
        "image_type": None,
        "image_mood": None,
        "custom_visual_brief": None,
        "inline_count": 0,
    }
    base.update(overrides)
    return argparse.Namespace(**base)


class ImageControlTests(unittest.TestCase):
    def test_default_image_provider_is_gemini_web(self):
        self.assertEqual(legacy.image_provider_from_env(None), "gemini-web")

    def test_explicit_image_preset_wins_over_auto(self):
        controls = legacy.resolve_image_controls(
            {},
            _image_args(image_preset="bold"),
            title="如何部署 API 网关",
            summary="三步搭建",
            body="## 第一步\n\n先配置 OPENAI_API_KEY。",
        )
        self.assertEqual(controls.get("decision_source"), "explicit")
        self.assertEqual(controls.get("preset"), "bold")

    def test_plan_images_auto_category_and_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "三步搭建 API 自动化流程",
                        "summary": "从环境变量到接口调用的实操教程",
                        "article_path": "article.md",
                        "audience": "开发者",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text(
                "\n".join(
                    [
                        "## 第一步：配置环境变量",
                        "",
                        "先设置 OPENAI_API_KEY，然后确认接口路径 /v1/chat/completions。",
                        "",
                        "## 第二步：按步骤调用 API",
                        "",
                        "1. 发送请求。",
                        "2. 检查返回。",
                        "3. 记录日志。",
                        "",
                        "## 最后整理成清单",
                        "",
                        "把整个流程做成一张图，方便团队复用。",
                    ]
                ),
                encoding="utf-8",
            )
            args = _image_args(workspace=str(workspace))
            legacy.cmd_plan_images(args)
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            plan = json.loads((workspace / "image-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("image_decision_source"), "auto")
            self.assertEqual(plan.get("decision_source"), "auto")
            self.assertEqual(plan.get("article_category"), "教程实操")
            self.assertTrue(plan.get("auto_reason"))
            self.assertTrue(plan["items"][0].get("semantic_focus"))
            self.assertTrue(plan["items"][0].get("keyword_glossary"))
            self.assertIn(plan["items"][0].get("native_aspect_ratio"), {"3:2", "2:3"})
            self.assertTrue(plan["items"][0].get("safe_crop_policy"))
            self.assertTrue(plan["items"][0].get("visual_reason"))
            self.assertEqual(plan["image_controls"].get("preset"), "notion")
            self.assertEqual(plan["image_controls"].get("preset_label"), "知识卡片")
            self.assertIn(plan["article_visual_strategy"].get("visual_route"), {"cold-hard", "people-emotion", "data-explainer", "conflict-alert"})
            self.assertEqual(plan["items"][0].get("text_policy"), "none")

    def test_generate_images_falls_back_to_local_card_when_gemini_web_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "image-plan.json").write_text(
                json.dumps(
                    {
                        "provider": "gemini-web",
                        "items": [
                            {
                                "id": "inline-01",
                                "type": "正文插图",
                                "prompt": "test prompt",
                                "asset_path": "assets/images/inline-01.png",
                                "section_heading": "测试章节",
                                "section_excerpt": "测试说明",
                                "aspect_ratio": "16:9",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            with patch.object(legacy, "generate_gemini_web_image", side_effect=SystemExit("gemini-web 图片生成失败")):
                legacy.cmd_generate_images(
                    type(
                        "Args",
                        (),
                        {
                            "workspace": str(workspace),
                            "provider": "gemini-web",
                            "dry_run": False,
                            "gemini_model": "gemini-2.0-flash-preview-image-generation",
                            "openai_model": "gpt-image-1",
                        },
                    )()
                )
            plan = json.loads((workspace / "image-plan.json").read_text(encoding="utf-8"))
            generated = plan["items"][0]
            self.assertEqual(generated["provider"], "local-card")
            self.assertTrue((workspace / "assets" / "images" / "inline-01.png").exists())

    def test_generate_images_codex_writes_request_when_image_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "image-plan.json").write_text(
                json.dumps(
                    {
                        "provider": "codex",
                        "items": [
                            {
                                "id": "inline-01",
                                "type": "正文插图",
                                "prompt": "draw a compact editorial illustration",
                                "aspect_ratio": "16:9",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            with self.assertRaises(SystemExit):
                legacy.cmd_generate_images(
                    type(
                        "Args",
                        (),
                        {
                            "workspace": str(workspace),
                            "provider": "codex",
                            "dry_run": False,
                            "gemini_model": "gemini-2.0-flash-preview-image-generation",
                            "openai_model": "gpt-image-1",
                        },
                    )()
                )
            self.assertTrue((workspace / "codex-image-requests.md").exists())
            request_payload = json.loads((workspace / "codex-image-requests.json").read_text(encoding="utf-8"))
            self.assertEqual(request_payload["items"][0]["target_path"], "assets/images/inline-01.png")

    def test_generate_images_codex_registers_existing_workspace_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "image-plan.json").write_text(
                json.dumps(
                    {
                        "provider": "codex",
                        "items": [
                            {
                                "id": "inline-01",
                                "type": "正文插图",
                                "prompt": "draw a compact editorial illustration",
                                "aspect_ratio": "16:9",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            image_path = workspace / "assets" / "images" / "inline-01.png"
            legacy.make_placeholder_png(image_path)
            legacy.cmd_generate_images(
                type(
                    "Args",
                    (),
                    {
                        "workspace": str(workspace),
                        "provider": "codex",
                        "dry_run": False,
                        "gemini_model": "gemini-2.0-flash-preview-image-generation",
                        "openai_model": "gpt-image-1",
                    },
                )()
            )
            plan = json.loads((workspace / "image-plan.json").read_text(encoding="utf-8"))
            generated = plan["items"][0]
            self.assertEqual(generated["provider"], "codex")
            self.assertEqual(generated["asset_path"], "assets/images/inline-01.png")
            self.assertTrue(generated["source_meta"].get("codex_app_image"))


if __name__ == "__main__":
    unittest.main()
