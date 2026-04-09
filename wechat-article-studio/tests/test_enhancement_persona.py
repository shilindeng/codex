import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.author_memory import append_lesson_payload, build_author_memory_bundle, compute_edit_lesson_payload  # noqa: E402
from core.content_enhancement import build_content_enhancement, enhancement_strategy_for_archetype  # noqa: E402
from core.persona import normalize_writing_persona  # noqa: E402
from core.workflow import cmd_enhance  # noqa: E402


class EnhancementAndPersonaTests(unittest.TestCase):
    def test_compute_edit_lessons_emits_structured_rules_and_promotes_strength(self):
        draft = "\n".join(
            [
                "# 为什么大多数人做不好 AI 自动化？",
                "",
                "首先，我们来看看这件事。",
                "",
                "其次，这非常重要。",
                "",
                "最后，综上所述，你需要行动。",
            ]
        )
        final = "\n".join(
            [
                "# AI 自动化这件事，真正难在判断顺序",
                "",
                "我第一次在客户现场听到那句“先接个模型再说”时，就知道后面会出问题。",
                "",
                "问题不在工具，而在谁来为结果负责。",
                "",
                "真正该收住的一句判断是：别把流程自动化当成组织判断的替代品。",
            ]
        )
        payload = compute_edit_lesson_payload(draft, final)
        self.assertTrue(payload.get("rules"))
        keys = {item.get("key") for item in payload.get("rules") or []}
        self.assertIn("remove-template-connectors", keys)
        self.assertIn("open-with-scene", keys)

        with tempfile.TemporaryDirectory() as tmp:
            lesson_path = Path(tmp) / "author-lessons.json"
            append_lesson_payload(lesson_path, payload)
            summary = append_lesson_payload(lesson_path, payload)
            hard_rules = {item.get("key"): item for item in summary.get("rules") or [] if item.get("strength") == "hard"}
            self.assertIn("remove-template-connectors", hard_rules)
            self.assertGreaterEqual(int(hard_rules["remove-template-connectors"].get("occurrences") or 0), 2)

    def test_build_author_memory_bundle_returns_rules_and_examples(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            sample = workspace / "sample.md"
            sample.write_text(
                "\n".join(
                    [
                        "# 写给做 AI 产品的人：别急着追热闹",
                        "",
                        "我昨天开完会出来，脑子里一直卡着一件事。",
                        "",
                        "不过话又说回来，真正麻烦的不是参数，而是责任没有人接。",
                        "",
                        "最后真正该记住的，不是热闹，而是判断顺序。",
                    ]
                ),
                encoding="utf-8",
            )
            lesson_payload = {
                "generated_at": "2026-04-01T12:00:00+00:00",
                "rules": [
                    {
                        "key": "remove-template-connectors",
                        "type": "expression",
                        "rule": "删掉模板连接词和篇章自述。",
                        "confidence": 0.8,
                        "occurrences": 3,
                        "last_seen": "2026-04-01T12:00:00+00:00",
                        "strength": "hard",
                        "examples": ["首先，我们来看看这件事。"],
                    }
                ],
            }
            (workspace / "author-lessons.json").write_text(json.dumps(lesson_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            manifest = {"style_sample_paths": [str(sample)]}
            bundle = build_author_memory_bundle(workspace, manifest)
            self.assertTrue(bundle.get("hard_rules"))
            self.assertTrue(bundle.get("example_snippets"))

    def test_persona_and_enhancement_follow_archetype(self):
        persona = normalize_writing_persona({}, {"article_archetype": "narrative", "content_mode": "tech-balanced", "author_memory": {}})
        self.assertEqual(persona.get("name"), "warm-editor")
        strategy_persona = normalize_writing_persona(
            {},
            {
                "article_archetype": "commentary",
                "content_mode": "tech-balanced",
                "author_memory": {},
                "account_strategy": {"target_reader": "general-tech", "primary_goal": "open-and-read", "preferred_persona": "warm-editor"},
            },
        )
        self.assertEqual(strategy_persona.get("name"), "warm-editor")
        self.assertEqual(enhancement_strategy_for_archetype("tutorial"), "density-strengthening")

        payload = build_content_enhancement(
            title="RAG 实战指南",
            outline_meta={
                "viral_blueprint": {"article_archetype": "tutorial", "core_viewpoint": "顺序没理清，方法就会白做。"},
                "sections": [
                    {"heading": "先别急着上工具", "goal": "先把误区讲清", "evidence_need": "失败案例"},
                    {"heading": "真正该先做哪一步", "goal": "拆解顺序", "evidence_need": "步骤与数字"},
                ],
            },
            manifest={"topic": "RAG 实战指南"},
            research={
                "sources": [
                    {"title": "GitHub 官方示例", "url": "https://example.com/a", "note": "官方"},
                    {"title": "生产环境复盘", "url": "https://example.com/b", "note": "案例"},
                ],
                "evidence_items": [
                    {"page_title": "GitHub 官方示例", "sentence": "示例里第一步不是调参，而是先把数据入口理顺。", "url": "https://example.com/a"},
                    {"page_title": "生产环境复盘", "sentence": "一次真实项目里，团队卡住的并不是模型，而是同步链路。", "url": "https://example.com/b"},
                ],
            },
            author_memory={"example_snippets": [{"slot": "opening", "text": "我第一次上线时，问题并不在模型。"}]},
            writing_persona=persona,
        )
        self.assertEqual(payload.get("strategy_key"), "density-strengthening")
        self.assertTrue(payload.get("section_enhancements"))
        self.assertTrue(payload["section_enhancements"][0].get("must_include"))
        self.assertTrue(payload["section_enhancements"][0].get("support_quotes"))
        self.assertTrue(payload["section_enhancements"][0].get("table_targets"))
        self.assertTrue(payload["section_enhancements"][0].get("analogy_targets"))
        self.assertTrue(payload["section_enhancements"][0].get("comparison_targets"))
        self.assertTrue(payload["section_enhancements"][0].get("citation_targets"))
        self.assertTrue(payload.get("shared_materials", {}).get("source_cards"))
        material_requirements = payload.get("shared_materials", {}).get("material_requirements") or []
        self.assertTrue(any("表格" in item for item in material_requirements))
        self.assertTrue(any("类比" in item for item in material_requirements))

    def test_cmd_enhance_writes_artifacts_and_persona(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "manifest.json").write_text(
                json.dumps(
                    {
                        "topic": "AI 选型",
                        "selected_title": "AI 选型",
                        "audience": "大众读者",
                        "direction": "",
                        "content_mode": "tech-balanced",
                        "style_sample_paths": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            (workspace / "ideation.json").write_text(
                json.dumps(
                    {
                        "selected_title": "AI 选型",
                        "outline_meta": {
                            "title": "AI 选型",
                            "sections": [
                                {"heading": "先别急着看参数", "goal": "先讲误判", "evidence_need": "案例"},
                                {"heading": "真正该比的是什么", "goal": "讲比较维度", "evidence_need": "对比"},
                            ],
                            "viral_blueprint": {"article_archetype": "commentary", "core_viewpoint": "别被表面参数带着走。"},
                            "editorial_blueprint": {"style_key": "case-memo", "style_label": "案例备忘"},
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            cmd_enhance(type("Args", (), {"workspace": str(workspace), "title": None, "style_sample": [], "content_mode": None, "wechat_header_mode": None})())
            self.assertTrue((workspace / "content-enhancement.json").exists())
            self.assertTrue((workspace / "content-enhancement.md").exists())
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("content_enhancement_path"), "content-enhancement.json")
            self.assertTrue(isinstance(manifest.get("writing_persona"), dict))


if __name__ == "__main__":
    unittest.main()
