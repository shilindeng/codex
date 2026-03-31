import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.content_fingerprint import build_article_fingerprint, compare_fingerprints, summarize_collisions  # noqa: E402


class ContentFingerprintTests(unittest.TestCase):
    def test_fingerprint_similarity_detects_route_collision(self):
        manifest = {
            "topic": "企业 AI 转型",
            "summary": "一篇评论稿",
            "editorial_blueprint": {"style_key": "case-memo"},
            "viral_blueprint": {"article_archetype": "case-study", "primary_interaction_goal": "share/comment", "secondary_interaction_goal": "like"},
        }
        body_a = "\n\n".join(
            [
                "我在办公室里反复看到同一个场景：需求会写，责任没人接。",
                "## 真正的分水岭",
                "案例真正值钱的地方，不是热闹，而是它能暴露决策里的分水岭。",
                "## 最后的判断",
                "最后真正该记住的，不是工具，而是判断顺序。",
            ]
        )
        body_b = "\n\n".join(
            [
                "我最近反复看到一种企业转型时刻，它比新闻本身更值得写。",
                "## 真正的分水岭",
                "案例真正值钱的地方，不是热闹，而是它能暴露决策里的分水岭。",
                "## 最后的判断",
                "最后真正该记住的，不是工具，而是判断顺序。",
            ]
        )
        current = build_article_fingerprint("复盘企业 AI 转型", body_a, manifest, layout_plan={"section_plans": [{"module_type": "summary-card"}, {"module_type": "case-card"}]})
        other = build_article_fingerprint("复盘另一家企业 AI 转型", body_b, manifest, layout_plan={"section_plans": [{"module_type": "summary-card"}, {"module_type": "case-card"}]})
        similarity = compare_fingerprints(current, other)
        summary = summarize_collisions(current, [other], threshold=0.6)
        self.assertGreaterEqual(similarity, 0.6)
        self.assertFalse(summary["route_similarity_passed"])


if __name__ == "__main__":
    unittest.main()
