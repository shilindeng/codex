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
            self.assertEqual(controls.get("density"), "balanced")
            self.assertFalse(controls.get("preset"))
            self.assertFalse(controls.get("style_mode"))
            self.assertFalse(controls.get("preset_cover"))


if __name__ == "__main__":
    unittest.main()
