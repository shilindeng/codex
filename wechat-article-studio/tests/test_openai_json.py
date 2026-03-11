import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from providers.text.openai_compatible import OpenAICompatibleTextProvider  # noqa: E402


class OpenAICompatibleJsonTests(unittest.TestCase):
    def test_json_result_strips_fences(self):
        provider = OpenAICompatibleTextProvider()
        content = """```json
{"candidates":[{"title":"A","strategy":"s","audience_fit":"x","risk_note":""}]}
```"""
        payload = provider._json_result(content)
        self.assertIsInstance(payload, dict)
        self.assertIn("candidates", payload)

    def test_json_result_extracts_substring_with_noise(self):
        provider = OpenAICompatibleTextProvider()
        content = '前言\\n{"ok":true,"n":1}\\n后记'
        payload = provider._json_result(content)
        self.assertEqual(payload.get("ok"), True)

    def test_json_result_supports_array(self):
        provider = OpenAICompatibleTextProvider()
        content = """```json
[{"a":1}]
```"""
        payload = provider._json_result(content)
        self.assertIsInstance(payload, list)
        self.assertEqual(payload[0]["a"], 1)


if __name__ == "__main__":
    unittest.main()

