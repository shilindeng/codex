import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


import legacy_studio as legacy  # noqa: E402
from core.editorial_strategy import (  # noqa: E402
    default_editorial_blueprint,
    generate_diverse_title_variants,
    normalize_editorial_blueprint,
    summarize_recent_corpus,
    title_template_key,
)
from core.workflow import detect_corpus_roots  # noqa: E402


class EditorialDiversityTests(unittest.TestCase):
    def test_title_template_key_detects_hot_template(self):
        title = "为什么大多数人做不好AI自动化？普通人一定要先想清这3件事"
        self.assertEqual(title_template_key(title), "why-think-clear")

    def test_generate_diverse_title_variants_avoids_recent_repetition(self):
        titles = generate_diverse_title_variants(
            topic="企业 AI Agent 落地",
            angle="交付链路",
            audience="创业者",
            editorial_blueprint={"style_key": "signal-briefing", "style_label": "信号简报"},
            recent_titles=["企业 AI Agent 落地这次真正的信号，不在表面热闹，而在更深一层"],
            recent_corpus_summary={"overused_title_patterns": [{"key": "why-think-clear", "label": "旧模板", "count": 8}]},
        )
        self.assertTrue(titles)
        self.assertFalse(any("先想清" in item["title"] and "为什么大多数人" in item["title"] for item in titles))
        self.assertFalse(any(item["title"] == "企业 AI Agent 落地这次真正的信号，不在表面热闹，而在更深一层" for item in titles))

    def test_generate_diverse_title_variants_blocks_overused_pattern_even_same_style(self):
        titles = generate_diverse_title_variants(
            topic="企业 AI Agent 常见误区",
            audience="运营负责人",
            editorial_blueprint={"style_key": "myth-buster", "style_label": "误区拆解"},
            recent_titles=[],
            recent_corpus_summary={
                "overused_title_patterns": [
                    {"key": "myth-buster", "label": "误区模板", "count": 12},
                    {"key": "not-but", "label": "不是…而是…", "count": 11},
                ]
            },
        )
        self.assertTrue(titles)
        keys = {title_template_key(item["title"]) for item in titles}
        self.assertNotIn("myth-buster", keys)
        self.assertNotIn("not-but", keys)

    def test_default_editorial_blueprint_penalizes_overused_templates(self):
        summary = {
            "overused_title_patterns": [
                {"key": "myth-buster", "label": "误区模板", "count": 15},
                {"key": "not-but", "label": "不是…而是…", "count": 14},
                {"key": "why-question", "label": "为什么问句", "count": 9},
            ],
            "overused_opening_patterns": [
                {"key": "many-people-misread", "label": "很多人误判", "count": 10},
                {"key": "reader-scene", "label": "你可能/你大概", "count": 8},
            ],
            "overused_ending_patterns": [
                {"key": "question-close", "label": "提问结尾", "count": 9},
            ],
            "overused_heading_patterns": [
                {"key": "why-heading", "label": "为什么小标题", "count": 20},
            ],
        }
        blueprint = default_editorial_blueprint(
            {
                "topic": "企业 AI 误区拆解",
                "selected_title": "企业 AI 误区拆解",
                "article_archetype": "commentary",
                "content_mode": "tech-balanced",
                "recent_corpus_summary": summary,
            }
        )
        self.assertNotIn(blueprint["style_key"], {"myth-buster", "counterintuitive-column"})

    def test_normalize_editorial_blueprint_honors_explicit_style(self):
        payload = {"style_key": "open-letter"}
        blueprint = normalize_editorial_blueprint(
            payload,
            {
                "topic": "写给正在焦虑的团队负责人",
                "selected_title": "写给正在焦虑的团队负责人",
                "article_archetype": "commentary",
                "content_mode": "viral",
                "recent_corpus_summary": {},
            },
        )
        self.assertEqual(blueprint["style_key"], "open-letter")
        self.assertEqual(blueprint["style_label"], "公开信")
        self.assertIn("对话感", blueprint["language_texture"])

    def test_rank_title_candidates_penalizes_overused_patterns(self):
        candidates = [
            {"title": "为什么大多数人做不好企业AI转型？普通人一定要先想清这3件事", "strategy": "", "audience_fit": "", "risk_note": ""},
            {"title": "企业AI转型真正值得聊的，不是表面答案，而是判断顺序", "strategy": "", "audience_fit": "", "risk_note": ""},
        ]
        ranked, selected = legacy.rank_title_candidates(
            candidates,
            topic="企业AI转型",
            audience="管理者",
            angle="",
            selected_title="",
            recent_titles=[],
            recent_title_patterns=["why-think-clear"],
        )
        self.assertIsNotNone(selected)
        self.assertEqual(selected["title"], "企业AI转型真正值得聊的，不是表面答案，而是判断顺序")
        hot = next(item for item in ranked if "为什么大多数人" in item["title"])
        self.assertGreaterEqual(int(hot.get("title_repeat_penalty") or 0), 6)

    def test_detect_corpus_roots_supports_multiple_env_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            root_a = Path(tmp) / "a"
            root_b = Path(tmp) / "b"
            workspace.mkdir(parents=True, exist_ok=True)
            root_a.mkdir(parents=True, exist_ok=True)
            root_b.mkdir(parents=True, exist_ok=True)

            old_env = os.environ.get("WECHAT_JOBS_ROOT")
            os.environ["WECHAT_JOBS_ROOT"] = f"{root_a};{root_b}"
            try:
                roots = detect_corpus_roots(workspace)
            finally:
                if old_env is None:
                    os.environ.pop("WECHAT_JOBS_ROOT", None)
                else:
                    os.environ["WECHAT_JOBS_ROOT"] = old_env

            root_values = {str(path) for path in roots}
            self.assertIn(str(root_a.resolve()), root_values)
            self.assertIn(str(root_b.resolve()), root_values)

    def test_summarize_recent_corpus_collects_pattern_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job1 = root / "job1"
            job2 = root / "job2"
            job1.mkdir()
            job2.mkdir()
            (job1 / "article.md").write_text(
                "\n".join(
                    [
                        "# 为什么大多数人做不好企业AI转型？普通人一定要先想清这3件事",
                        "",
                        "很多人对 AI 的焦虑，还是停在“它会不会写得比我好”。",
                        "",
                        "## 你该先想清的 3 件事",
                        "",
                        "留个问题：如果是你，你会怎么选？",
                    ]
                ),
                encoding="utf-8",
            )
            (job2 / "article.md").write_text(
                "\n".join(
                    [
                        "# 复盘企业AI转型：真正拉开差距的，不是资源，而是判断顺序",
                        "",
                        "很多人听到 AI 落地，第一反应是上工具。",
                        "",
                        "## 你该先想清的 3 件事",
                        "",
                        "留个问题：如果是你，你会怎么选？",
                    ]
                ),
                encoding="utf-8",
            )
            summary = summarize_recent_corpus([job1 / "article.md", job2 / "article.md"], limit=10)
            self.assertEqual(summary["article_count"], 2)
            self.assertTrue(summary["overused_ending_patterns"])
            self.assertTrue(summary["overused_heading_patterns"])


if __name__ == "__main__":
    unittest.main()
