import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core.layout import THEMES, apply_callout_blocks, markdown_to_html, sanitize_and_style_for_wechat, sanitize_html_fragment  # noqa: E402


class CalloutTests(unittest.TestCase):
    def test_callout_preprocess_and_sanitize_preview_keeps_tone(self):
        md = "> [!TIP] 先看结论\n> 这里是内容\n\n正文段落。"
        html_raw = markdown_to_html(md)
        html_callout = apply_callout_blocks(html_raw)
        self.assertIn('data-wx-tone="tip"', html_callout)
        self.assertIn("提示", html_callout)

        preview = sanitize_html_fragment(html_callout)
        self.assertIn('data-wx-tone="tip"', preview)

    def test_wechat_inline_style_uses_tone_but_does_not_output_attr(self):
        md = "> [!WARNING] 小心\n> 这里是内容"
        html_raw = markdown_to_html(md)
        html_callout = apply_callout_blocks(html_raw)
        theme = THEMES["clean"]
        wechat = sanitize_and_style_for_wechat(html_callout, theme=theme, accent="#0F766E")
        self.assertNotIn("data-wx-tone", wechat)
        self.assertIn("border-left:4px solid", wechat)


if __name__ == "__main__":
    unittest.main()

