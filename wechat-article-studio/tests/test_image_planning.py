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


def make_args(workspace: Path, **overrides):
    payload = {
        "workspace": str(workspace),
        "provider": "openai-image",
        "image_preset": None,
        "image_style_mode": None,
        "image_preset_cover": None,
        "image_preset_infographic": None,
        "image_preset_inline": None,
        "image_density": None,
        "image_layout_family": None,
        "image_theme": None,
        "image_style": None,
        "image_type": None,
        "image_mood": None,
        "custom_visual_brief": None,
        "inline_count": 0,
    }
    payload.update(overrides)
    return type("Args", (), payload)()


class ImagePlanningTests(unittest.TestCase):
    def test_resolve_image_controls_without_explicit_overrides_keeps_auto_mode(self):
        args = type(
            "Args",
            (),
            {
                "image_preset": None,
                "image_style_mode": None,
                "image_preset_cover": None,
                "image_preset_infographic": None,
                "image_preset_inline": None,
                "image_density": None,
                "image_layout_family": None,
                "image_theme": None,
                "image_style": None,
                "image_type": None,
                "image_mood": None,
                "custom_visual_brief": None,
            },
        )()
        controls = legacy.resolve_image_controls({}, args)
        self.assertEqual(controls.get("density"), "balanced")
        self.assertEqual(controls.get("style_mode"), "")
        self.assertEqual(controls.get("preset"), "")
        self.assertEqual(controls.get("layout_family"), "")
        self.assertEqual(controls.get("preset_cover"), "")
        self.assertEqual(controls.get("preset_infographic"), "")
        self.assertEqual(controls.get("preset_inline"), "")

    def test_opinion_article_defaults_to_editorial_inline_images(self):
        article = """---
title: AI 真正的拐点，不在参数而在产品判断
summary: 这是一次关于 AI 产品判断、竞争节奏与用户心智的分析。
---

## 一、为什么最近大家都在误判 AI 的真正变化？

很多人还盯着模型参数和榜单名次，但用户真正感知到的是产品是否顺手、是否可信、是否值得持续打开。

当行业进入下半场，决定成败的往往不是“更强一点”，而是“更好用很多”。

## 二、被忽略的一层，是产品怎么承接用户决策

真正拉开差距的是产品把复杂能力变成可理解的体验，而不是把技术堆在页面上。

用户不是来读架构图的，他们是来解决问题的。

## 三、这会怎样影响接下来的竞争？

下一阶段的赢家，更像是在争夺用户心智和默认入口，而不是再做一次参数军备竞赛。

所以这篇文章的重点，不是讲流程，而是讲判断。
"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text(article, encoding="utf-8")
            legacy.cmd_plan_images(make_args(workspace, inline_count=4))
            plan = json.loads((workspace / "image-plan.json").read_text(encoding="utf-8"))
            strategy = json.loads((workspace / "image-strategy.json").read_text(encoding="utf-8"))
            middle_items = [item for item in plan["items"] if item.get("insert_strategy") == "section_middle"]
            self.assertTrue(strategy.get("style_family"))
            self.assertGreaterEqual(sum(1 for item in middle_items if item["type"] == "正文插图"), 2)
            self.assertLessEqual(sum(1 for item in middle_items if item["type"] == "流程图"), 1)
            prompt_text = "\n".join(
                (workspace / item["prompt_path"]).read_text(encoding="utf-8")
                for item in json.loads((workspace / "image-outline.json").read_text(encoding="utf-8"))["items"]
            )
            self.assertLessEqual(prompt_text.count("Show a real sequence or operational path"), 1)

    def test_headingless_article_prompt_focus_skips_generated_section_labels(self):
        article = """第一段先把问题摆出来。

第二段继续补细节，让读者知道事情为什么会突然变糟。

第三段开始讲判断，不要把整篇文章写成说明书。

第四段收束结论，提醒读者真正该防的是什么。"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text(article, encoding="utf-8")
            legacy.cmd_plan_images(make_args(workspace, inline_count=2))
            outline = json.loads((workspace / "image-outline.json").read_text(encoding="utf-8"))
            prompt_text = "\n".join(
                (workspace / item["prompt_path"]).read_text(encoding="utf-8")
                for item in outline["items"]
            )
            self.assertNotIn("Section focus: 正文段落", prompt_text)
            inline_items = [item for item in outline["items"] if item["id"].startswith("inline-")]
            self.assertTrue(inline_items)
            self.assertTrue(all("正文段落" not in item["visual_content"] for item in inline_items))

    def test_tutorial_article_only_uses_flow_when_structure_is_real(self):
        article = """## 第一步：先整理输入

1. 列出原始需求。
2. 标注约束条件。
3. 明确目标读者。

## 第二步：把内容拆成执行步骤

1. 先生成标题候选。
2. 再生成大纲。
3. 然后补充正文与案例。

## 第三步：最后做发布前检查

1. 检查事实来源。
2. 检查配图位置。
3. 检查标题与摘要是否一致。
"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text(article, encoding="utf-8")
            legacy.cmd_plan_images(make_args(workspace, inline_count=3))
            plan = json.loads((workspace / "image-plan.json").read_text(encoding="utf-8"))
            middle_items = [item for item in plan["items"] if item.get("insert_strategy") == "section_middle"]
            self.assertGreaterEqual(sum(1 for item in middle_items if item["type"] == "流程图"), 1)

    def test_comparison_article_uses_comparison_graphic(self):
        article = """## 为什么免费模式和订阅模式的差异会越来越大？

免费模式更容易拉新，但对长期成本更敏感。

订阅模式更稳，但增长节奏未必更快。

当一个产品必须在广告与订阅之间取舍时，本质上是在权衡规模和信任。
"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text(article, encoding="utf-8")
            legacy.cmd_plan_images(make_args(workspace, inline_count=1))
            plan = json.loads((workspace / "image-plan.json").read_text(encoding="utf-8"))
            middle_items = [item for item in plan["items"] if item.get("insert_strategy") == "section_middle"]
            self.assertTrue(any(item["type"] == "对比图" for item in middle_items))

    def test_explicit_preset_and_directive_override_auto_strategy(self):
        article = """## 一、团队该怎么开始？

<!-- image:type=流程图 -->

先把目标拆出来，再决定角色分工，最后确定验收标准。

## 二、为什么这件事容易失败？

失败往往不是因为没有工具，而是因为一开始就没有统一预期。
"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text(article, encoding="utf-8")
            legacy.cmd_plan_images(make_args(workspace, image_preset="warm", inline_count=2))
            plan = json.loads((workspace / "image-plan.json").read_text(encoding="utf-8"))
            self.assertEqual(plan["image_controls"]["preset"], "warm")
            directive_item = next(
                item for item in plan["items"] if item.get("target_section") == "一、团队该怎么开始？" and item.get("insert_strategy") == "section_middle"
            )
            self.assertEqual(directive_item["type"], "流程图")
            self.assertEqual(directive_item["decision_source"], "directive")

    def test_discover_topics_no_longer_injects_fixed_preset_defaults(self):
        payload = {
            "provider": "auto",
            "focus": "ai-tech",
            "window_hours": 24,
            "candidates": [
                {
                    "recommended_topic": "测试选题",
                    "hot_title": "测试热点",
                    "recommended_title": "测试标题",
                    "recommended_title_score": 60,
                    "recommended_title_threshold": 56,
                    "recommended_title_gate_passed": True,
                    "angles": ["角度 1"],
                    "viewpoints": ["观点 1"],
                    "source": "测试来源",
                    "topic_type": "观点",
                    "why_now": "因为它是测试样例。",
                    "source_url": "https://example.com",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            with patch.object(legacy, "discover_recent_topics", return_value=payload):
                legacy.cmd_discover_topics(
                    type(
                        "Args",
                        (),
                        {
                            "workspace": str(workspace),
                            "window_hours": 24,
                            "limit": 8,
                            "provider": "auto",
                            "focus": "ai-tech",
                            "rss_url": [],
                        },
                    )()
                )
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            controls = manifest.get("image_controls") or {}
            self.assertEqual(controls.get("density"), "minimal")
            self.assertFalse(controls.get("preset"))
            self.assertFalse(controls.get("style_mode"))
            self.assertFalse(controls.get("preset_cover"))

    def test_plan_images_caps_inline_density_with_account_strategy(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "selected_title": "银行业 AI 竞争突然提速，真正该看的不是热闹，而是岗位和成本怎么被重写",
                        "summary": "先讲读者能感到疼的现实后果，再拆影响路径。",
                        "article_path": "article.md",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "account-strategy.json").write_text(
                json.dumps({"max_inline_images": 2, "image_density": "minimal"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text(
                "\n\n".join(
                    [
                        "最近很多银行内部都在重新算一笔账：AI 提速之后，哪些岗位会先被重写，哪些团队会先感到成本压力。",
                        "## 第一层影响",
                        "不是技术部门先热闹，而是业务和中台先要面对交付、预算和责任边界。",
                        "## 第二层影响",
                        "一旦流程开始重写，最先受冲击的往往不是工具，而是原有分工。",
                        "## 第三层影响",
                        "如果只看宣传口径，读者很容易忽略这波变化真正会落到谁身上。",
                        "## 最后的判断",
                        "这件事真正该看的，是岗位、成本和决策顺序一起被挪动。",
                    ]
                ),
                encoding="utf-8",
            )
            legacy.cmd_plan_images(make_args(workspace))
            plan = json.loads((workspace / "image-plan.json").read_text(encoding="utf-8"))
            self.assertLessEqual(int(plan.get("planned_inline_count") or 0), 3)

    def test_generate_images_falls_back_to_secondary_provider_on_gemini_web_error(self):
        article = """## 一、正文

这一段是正常正文，配一张图就够了。

## 二、结尾

最后用一句判断收住全文。"""
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "article.md").write_text(article, encoding="utf-8")
            legacy.cmd_plan_images(make_args(workspace, provider="gemini-web", inline_count=1))

            def fake_openai(prompt, output_path, model, aspect):
                legacy.make_placeholder_png(output_path)
                return {
                    "provider": "openai-image",
                    "prompt": prompt,
                    "revised_prompt": prompt,
                    "width": 1,
                    "height": 1,
                    "source_meta": {"mocked": True},
                }

            args = type(
                "Args",
                (),
                {
                    "workspace": str(workspace),
                    "provider": None,
                    "dry_run": False,
                    "gemini_model": None,
                    "openai_model": "gpt-image-1",
                },
            )()
            with patch.object(legacy, "generate_gemini_web_image", side_effect=SystemExit("unknown certificate verification error")):
                with patch.object(legacy, "fallback_image_provider", return_value="openai-image"):
                    with patch.object(legacy, "generate_openai_image", side_effect=fake_openai):
                        legacy.cmd_generate_images(args)

            plan = json.loads((workspace / "image-plan.json").read_text(encoding="utf-8"))
            cover_item = next(item for item in plan["items"] if item["id"] == "cover-01")
            inline_item = next(item for item in plan["items"] if item["id"].startswith("inline-"))
            self.assertEqual(cover_item["provider"], "openai-image")
            self.assertEqual(cover_item["source_meta"].get("fallback_from"), "gemini-web")
            self.assertIn("certificate", cover_item["source_meta"].get("fallback_reason", ""))
            self.assertEqual(inline_item["provider"], "openai-image")

    def test_assemble_skips_local_fallback_card_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps({"article_path": "article.md"}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (workspace / "article.md").write_text(
                "## 一、正文\n\n这里是一段正常正文。\n",
                encoding="utf-8",
            )
            image_path = workspace / "assets" / "images" / "inline-01.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            legacy.make_placeholder_png(image_path)
            (workspace / "image-plan.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "inline-01",
                                "type": "正文插图",
                                "target_section": "一、正文",
                                "target_section_index": 0,
                                "insert_strategy": "section_middle",
                                "placement_block_index": 0,
                                "asset_path": "assets/images/inline-01.png",
                                "alt": "测试插图",
                                "source_meta": {"fallback_local_card": True},
                            }
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            legacy.cmd_assemble(type("Args", (), {"workspace": str(workspace)})())

            assembled = (workspace / "assembled.md").read_text(encoding="utf-8")
            self.assertNotIn("![测试插图]", assembled)

    def test_comparison_prompt_explicitly_bans_readable_text(self):
        item = {
            "id": "inline-01",
            "type": "对比图",
            "section_heading": "这会把接下来的 Agent 竞争往哪推",
            "section_excerpt": "过去一段时间，大家都爱拿 Agent 的动作能力说事。",
            "anchor_block_excerpt": "过去一段时间，大家都爱拿 Agent 的动作能力说事。",
            "layout_variant_label": "卡片对照",
            "layout_variant_instruction": "Use parallel comparison cards with mirrored structure and icon cues, not dense wording.",
            "type_reason": "章节存在明显双边对照关系，适合用对比图表达。",
            "style_reason": "正文插图风格由整篇文章的自动视觉策略决定；若图片类型特殊，再按用途做轻微分化。",
            "article_visual_strategy": {"visual_direction": "测试方向", "style_family": "知识解释", "content_mode": "narrative"},
            "visual_theme": "知识解释与方法拆解",
            "visual_style": "清晰解释型插画",
            "visual_mood": "清楚友好",
            "visual_brief": "Favor clear teaching visuals.",
        }
        controls = {"preset": "fresh", "preset_label": "清新杂志", "style_mode": "uniform"}
        prompt = legacy.compose_prompt("测试标题", "测试摘要", controls, item, "测试读者")
        self.assertIn("Do not include any readable Chinese or English words", prompt)


if __name__ == "__main__":
    unittest.main()
