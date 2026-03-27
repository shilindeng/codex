import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.author_memory import build_playbook_payload, compute_edit_lesson_payload  # noqa: E402
from core.workflow import rerank_discovery_candidates  # noqa: E402
import legacy_studio as legacy  # noqa: E402


class AuthorMemoryTests(unittest.TestCase):
    def test_build_playbook_payload_extracts_voice_and_starters(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a.md"
            b = root / "b.md"
            a.write_text(
                "\n".join(
                    [
                        "# 写给做 AI 产品的人：别急着追热闹",
                        "",
                        "我昨天开完会出来，脑子里一直卡着一件事。",
                        "",
                        "很多团队一聊 AI，就先聊模型参数。",
                        "",
                        "## 真正的分水岭",
                        "",
                        "真正拉开差距的，是你到底准备拿什么结果去换用户信任。",
                    ]
                ),
                encoding="utf-8",
            )
            b.write_text(
                "\n".join(
                    [
                        "# 复盘 AI Agent 上线这件事",
                        "",
                        "我在办公室里反复看到同一个场景：需求会写，责任没人接。",
                        "",
                        "很多团队一提到自动化，就想先把流程铺满。",
                        "",
                        "## 不是工具多少，而是判断顺序",
                        "",
                        "官方文档、案例和数据都在提醒你，真正的成本并不在界面层。",
                    ]
                ),
                encoding="utf-8",
            )
            payload = build_playbook_payload([a, b])
            self.assertEqual(payload["source_count"], 2)
            self.assertTrue(payload["voice_fingerprint"])
            self.assertIn("很多团队", "".join(payload["sentence_starters_to_avoid"]))
            self.assertTrue(payload["playbook_summary"])

    def test_compute_edit_lesson_payload_detects_de_ai_preferences(self):
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
        joined = " ".join(payload.get("patterns") or [])
        self.assertIn("删掉模板连接词", joined)
        self.assertTrue(payload.get("title_changed"))

    def test_rerank_discovery_candidates_penalizes_recent_overlap(self):
        candidates = [
            {
                "recommended_topic": "AI Agent 终于进入企业落地阶段",
                "recommended_title": "AI Agent 终于进入企业落地阶段",
                "recommended_title_score": 70,
                "recommended_title_gate_passed": True,
                "angles": ["行业信号", "产品机会", "组织影响"],
                "viewpoints": ["别只看热闹"],
                "content_kind": "趋势观点",
                "source_tier": "官方",
                "hit_count": 2,
            },
            {
                "recommended_topic": "浏览器原生 Agent 正在改变自动化入口",
                "recommended_title": "浏览器原生 Agent 正在改变自动化入口",
                "recommended_title_score": 66,
                "recommended_title_gate_passed": True,
                "angles": ["入口变化", "用户行为", "产品机会"],
                "viewpoints": ["真正的变量是入口"],
                "content_kind": "产品更新",
                "source_tier": "官方",
                "hit_count": 2,
            },
        ]
        reranked = rerank_discovery_candidates(
            candidates,
            recent_titles=["AI Agent 落地，为什么大家又开始焦虑了"],
            recent_corpus_summary={"overused_title_patterns": []},
            author_memory={},
        )
        self.assertEqual(reranked[0]["recommended_topic"], "浏览器原生 Agent 正在改变自动化入口")
        self.assertGreaterEqual(int(reranked[0].get("novelty_score") or 0), int(reranked[1].get("novelty_score") or 0))

    def test_generate_hot_title_variants_avoids_old_template(self):
        titles = legacy.generate_hot_title_variants("OpenAI 发布新的 Agent 工具链", audience="开发者")
        self.assertTrue(titles)
        self.assertFalse(any("为什么大多数人" in item["title"] for item in titles))
        self.assertFalse(any("先想清这3件事" in item["title"] for item in titles))


if __name__ == "__main__":
    unittest.main()
