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
from core.image_assembly import assemble_body  # noqa: E402


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
                                "suggested_text": ["责任边界"],
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
            self.assertEqual(request_payload["target_model"], "gpt-image-2")
            self.assertEqual(request_payload["items"][0]["target_path"], "assets/images/inline-01.png")
            self.assertEqual(request_payload["items"][0]["required_text"], ["责任边界"])
            self.assertEqual(request_payload["items"][0]["suggested_text"], ["责任边界"])
            request_md = (workspace / "codex-image-requests.md").read_text(encoding="utf-8")
            self.assertIn("gpt-image-2", request_md)
            self.assertIn("required_text: 责任边界", request_md)
            self.assertIn("suggested_text: 责任边界", request_md)
            self.assertIn("不能变成架构图", request_md)

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

    def test_codex_provider_requires_readable_short_text_by_image_type(self):
        for image_type in ["封面图", "正文插图", "流程图", "信息图", "对比图", "分隔图"]:
            item = {
                "id": "cover-01" if image_type == "封面图" else "inline-01",
                "type": image_type,
                "provider": "codex",
                "section_heading": "OpenAI 团队协作新变化",
                "section_excerpt": "团队把 AI Agent 接进流程后，最关键的是责任边界、验收和风险提醒。",
                "text_policy": "none",
            }
            policy = legacy.resolve_image_text_policy({"image_provider": "codex", "label_language": "zh-CN"}, item)
            self.assertIn(policy["mode"], {"short-zh", "short-zh-numeric"})
            self.assertTrue(policy["required_text"], image_type)
            if image_type in {"流程图", "信息图", "对比图"}:
                self.assertLessEqual(len(policy["required_text"]), 2)
            else:
                self.assertLessEqual(len(policy["required_text"]), 1 if image_type != "封面图" else 2)

    def test_codex_prompt_has_required_text_without_no_text_ban(self):
        item = {
            "id": "cover-01",
            "type": "封面图",
            "provider": "codex",
            "section_heading": "OpenAI 把 Agent 放进团队工作流",
            "section_excerpt": "团队流程开始被 Agent 重写。",
            "layout_variant_label": "中心主视觉",
            "layout_variant_instruction": "Use one dominant hero object.",
            "visual_theme": "组织流程变化",
            "visual_style": "高识别封面插画",
            "visual_mood": "克制清晰",
            "visual_brief": "让标题字清楚出现。",
            "text_policy": "none",
        }
        prompt = legacy.compose_prompt("OpenAI 把 Agent 放进团队工作流", "摘要", {"image_provider": "codex", "preset": "bold", "preset_label": "高对比海报"}, item, "公众号读者")
        self.assertIn("Required exact text:", prompt)
        self.assertIn("gpt-image-2", prompt)
        self.assertIn("WeChat cover poster", prompt)
        self.assertIn("clearly and legibly", prompt)
        self.assertNotIn("Do not include any readable Chinese or English text", prompt)
        self.assertNotIn("Allowed labels: none", prompt)
        self.assertNotIn("no headline baked", prompt)

    def test_assemble_promotes_first_inline_before_first_h2(self):
        body, inserted = assemble_body(
            ["首屏第一段。", "首屏第二段。"],
            [
                {"heading": "第一节", "level": 2, "blocks": ["章节正文。"]},
                {"heading": "第二节", "level": 2, "blocks": ["更多正文。"]},
            ],
            [
                {
                    "id": "inline-01",
                    "type": "正文插图",
                    "insert_strategy": "section_middle",
                    "target_section_index": 0,
                    "placement_block_index": 0,
                    "asset_path": "assets/images/inline-01.png",
                    "alt": "首屏图",
                }
            ],
        )
        self.assertEqual(inserted[0]["id"], "inline-01")
        self.assertLess(body.index("![首屏图]"), body.index("## 第一节"))


if __name__ == "__main__":
    unittest.main()
