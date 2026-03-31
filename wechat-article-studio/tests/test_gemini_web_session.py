import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from core import gemini_web_session  # noqa: E402
import legacy_studio as legacy  # noqa: E402


class GeminiWebSessionTests(unittest.TestCase):
    def test_prepare_session_env_prefers_saved_recovery_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recovery = root / "recovery.json"
            explicit = root / "explicit.json"
            legacy.write_cookie_payload(recovery, {"__Secure-1PSID": "a", "__Secure-1PSIDTS": "b"})
            legacy.write_cookie_payload(explicit, {"__Secure-1PSID": "x", "__Secure-1PSIDTS": "y"})
            with patch.object(gemini_web_session.legacy, "consent_dir", return_value=root):
                gemini_web_session.save_session_state({"active_cookie_path": str(recovery), "last_source": "shared-recovery"})
                env, info = gemini_web_session.prepare_session_env({"GEMINI_WEB_COOKIE_PATH": str(explicit)})
            self.assertEqual(info["active_source"], "shared-recovery")
            self.assertEqual(env["GEMINI_WEB_COOKIE_PATH"], str(recovery))

    def test_run_gemini_web_command_retries_with_browser_refresh(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calls = []

            def fake_run(command, **kwargs):
                calls.append(kwargs["env"].copy())
                if len(calls) == 1:
                    return gemini_web_session.subprocess.CompletedProcess(command, 1, stdout="", stderr="AuthError: login expired")
                cookie_path = Path(kwargs["env"]["GEMINI_WEB_DATA_DIR"]) / "cookies.json"
                legacy.write_cookie_payload(cookie_path, {"__Secure-1PSID": "a", "__Secure-1PSIDTS": "b"})
                return gemini_web_session.subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

            with patch.object(gemini_web_session.legacy, "consent_dir", return_value=root):
                with patch("core.gemini_web_session.subprocess.run", side_effect=fake_run):
                    completed, info = gemini_web_session.run_gemini_web_command(["bun", "main.ts"], cwd=str(root), label="gemini-web 测试")
            self.assertEqual(completed.stdout, "ok")
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[1]["GEMINI_WEB_LOGIN"], "1")
            self.assertNotIn("GEMINI_WEB_COOKIE_PATH", calls[1])
            state = json.loads((root / "session-state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["last_source"], "browser-refresh")
            self.assertEqual(info["active_source"], "browser-refresh")


if __name__ == "__main__":
    unittest.main()
