import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


import legacy_studio as legacy  # noqa: E402
from core.workflow import rerank_discovery_candidates  # noqa: E402


class TopicDiscoveryTests(unittest.TestCase):
    def test_content_kind_classifier(self):
        self.assertEqual(legacy.classify_discovery_content_kind("一份 RAG 入门教程"), "教程/工具")
        self.assertEqual(legacy.classify_discovery_content_kind("发布 v2.0：新功能上线"), "产品更新")
        self.assertEqual(legacy.classify_discovery_content_kind("一篇 arXiv 论文"), "研究/论文")

    def test_source_tier_classifier(self):
        self.assertEqual(legacy.classify_discovery_source_tier("https://github.com/foo/bar"), "开源")
        self.assertEqual(legacy.classify_discovery_source_tier("https://news.ycombinator.com/item?id=1"), "社区")
        self.assertEqual(legacy.classify_discovery_source_tier("https://openai.com/blog/x"), "官方")

    def test_build_candidates_has_hit_count_and_fields(self):
        items = [
            {
                "title": "OpenAI 教程：如何用 API 做一个 Agent",
                "link": "https://openai.com/blog/agent",
                "source": "OpenAI",
                "published_at": "2026-03-11T00:00:00+00:00",
                "query": "AI",
            },
            {
                "title": "OpenAI 教程：如何用 API 做一个 Agent",
                "link": "https://openai.com/blog/agent",
                "source": "OpenAI",
                "published_at": "2026-03-11T00:00:00+00:00",
                "query": "科技",
            },
            {
                "title": "GitHub 开源：一个新的 RAG 框架",
                "link": "https://github.com/example/rag",
                "source": "GitHub",
                "published_at": "2026-03-11T00:00:00+00:00",
                "query": "AI",
            },
        ]
        candidates = legacy.build_topic_candidates_from_news(items, limit=10, audience="大众读者")
        self.assertGreaterEqual(len(candidates), 2)

        first = candidates[0]
        self.assertIn("hit_count", first)
        self.assertIn("content_kind", first)
        self.assertIn("source_tier", first)

        # The duplicated title should be merged with hit_count >= 2.
        merged = next(item for item in candidates if item["recommended_topic"].startswith("OpenAI 教程"))
        self.assertGreaterEqual(int(merged.get("hit_count") or 0), 2)
        self.assertEqual(merged.get("content_kind"), "教程/工具")
        self.assertEqual(merged.get("source_tier"), "官方")

    def test_rerank_discovery_candidates_adds_100_point_topic_score(self):
        candidates = [
            {
                "recommended_topic": "霍尔木兹航运风险推高普通人账单",
                "hot_title": "霍尔木兹航运风险",
                "recommended_title": "霍尔木兹一堵，普通人的账单会先从这三处抬头",
                "recommended_title_score": 80,
                "recommended_title_threshold": 68,
                "recommended_title_gate_passed": True,
                "angles": ["油价、运费和小企业订单"],
                "viewpoints": ["外部风险最终会写进账单"],
                "source_tier": "官方",
                "hit_count": 2,
                "content_kind": "事件解读",
            }
        ]
        reranked = rerank_discovery_candidates(candidates, [], {}, {}, {})
        first = reranked[0]
        self.assertIn("topic_score_100", first)
        self.assertIn("topic_score_dimensions", first)
        self.assertEqual(set(first["topic_score_dimensions"].keys()), {"时效和证据", "冲突和代价", "目标读者清晰度", "判断卡沉淀能力", "互动传播潜力"})
        self.assertGreaterEqual(first["topic_score_100"], 70)
        self.assertTrue(first["topic_gate_passed"])


if __name__ == "__main__":
    unittest.main()

