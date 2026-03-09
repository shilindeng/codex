from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from providers.text.base import ProviderResult, TextProvider


def _strip_fences(text: str) -> str:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return value


class GeminiWebTextProvider(TextProvider):
    provider_name = "gemini-web"

    def __init__(self) -> None:
        self.model = os.getenv("ARTICLE_STUDIO_TEXT_MODEL") or "gemini-3-pro"
        self.cookie_path = os.getenv("GEMINI_WEB_COOKIE_PATH") or ""
        self.chrome_profile_dir = os.getenv("GEMINI_WEB_CHROME_PROFILE_DIR") or ""
        self.cookie_inline = os.getenv("GEMINI_WEB_COOKIE") or ""

    def configured(self) -> bool:
        return bool(self.cookie_path or self.chrome_profile_dir or self.cookie_inline)

    def _cookie_path(self) -> Path | None:
        if self.cookie_path:
            path = Path(self.cookie_path).expanduser().resolve()
            if path.exists():
                return path
        if self.cookie_inline:
            target = legacy.consent_dir() / "gemini-web-text-cookie.json"
            legacy.ensure_dir(target.parent)
            cookie_map = legacy.parse_cookie_string(self.cookie_inline)
            legacy.write_cookie_payload(target, cookie_map)
            return target
        return None

    def _bun_command(self) -> list[str]:
        return legacy.resolve_bun_command()

    def _main_ts(self) -> Path:
        return legacy.ensure_gemini_web_vendor() / "main.ts"

    def _run_prompt(self, prompt: str, expect_json: bool) -> str:
        if not self.configured():
            raise SystemExit("gemini-web 文本 provider 未配置。请设置 GEMINI_WEB_COOKIE_PATH 或 GEMINI_WEB_CHROME_PROFILE_DIR。")
        legacy.ensure_gemini_web_consent()
        command = self._bun_command() + [str(self._main_ts()), "--model", self.model, "--prompt", prompt]
        if expect_json:
            command.append("--json")
        cookie_path = self._cookie_path()
        if cookie_path:
            command.extend(["--cookie-path", str(cookie_path)])
        elif self.chrome_profile_dir:
            command.extend(["--profile-dir", self.chrome_profile_dir])
        env = os.environ.copy()
        if self.chrome_profile_dir:
            env["GEMINI_WEB_CHROME_PROFILE_DIR"] = self.chrome_profile_dir
        completed = subprocess.run(
            command,
            cwd=str(self._main_ts().parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            env=env,
        )
        if completed.returncode != 0:
            detail = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
            raise SystemExit(f"gemini-web 文本生成失败：{detail}")
        output = (completed.stdout or "").strip()
        if not output:
            raise SystemExit("gemini-web 未返回文本内容。")
        return output

    def _parse_json(self, text: str) -> Any:
        raw = _strip_fences(text)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            try:
                wrapper = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"gemini-web 返回的 JSON 无法解析：{raw}") from exc
            payload = wrapper
        if isinstance(payload, dict) and "text" in payload and isinstance(payload["text"], str):
            nested = _strip_fences(payload["text"])
            try:
                return json.loads(nested)
            except json.JSONDecodeError:
                return payload
        return payload

    def generate_research_pack(self, context: dict[str, Any]) -> ProviderResult:
        prompt = (
            "你是微信公众号选题研究助手。只输出 JSON 对象，不要解释。"
            "字段必须是 topic, angle, audience, sources, evidence_items, information_gaps, forbidden_claims。"
            f"\n输入：{json.dumps(context, ensure_ascii=False)}"
        )
        text = self._run_prompt(prompt, expect_json=True)
        payload = self._parse_json(text)
        if isinstance(payload, dict) and "text" in payload and isinstance(payload["text"], str):
            payload = self._parse_json(payload["text"])
        return ProviderResult(payload=payload, provider=self.provider_name, model=self.model)

    def generate_titles(self, context: dict[str, Any]) -> ProviderResult:
        prompt = (
            "你是微信公众号标题编辑。只输出 JSON 数组，不要解释。"
            "每项字段必须是 title, strategy, audience_fit, risk_note。"
            f"\n输入：{json.dumps(context, ensure_ascii=False)}"
        )
        text = self._run_prompt(prompt, expect_json=True)
        payload = self._parse_json(text)
        if isinstance(payload, dict) and "candidates" in payload:
            payload = payload["candidates"]
        if isinstance(payload, dict) and "text" in payload and isinstance(payload["text"], str):
            payload = self._parse_json(payload["text"])
        return ProviderResult(payload=payload, provider=self.provider_name, model=self.model)

    def generate_outline(self, context: dict[str, Any]) -> ProviderResult:
        prompt = (
            "你是微信公众号大纲编辑。只输出 JSON 对象，不要解释。"
            "字段必须是 title, angle, sections，sections 每项包含 heading, goal, evidence_need。"
            f"\n输入：{json.dumps(context, ensure_ascii=False)}"
        )
        text = self._run_prompt(prompt, expect_json=True)
        payload = self._parse_json(text)
        if isinstance(payload, dict) and "text" in payload and isinstance(payload["text"], str):
            payload = self._parse_json(payload["text"])
        return ProviderResult(payload=payload, provider=self.provider_name, model=self.model)

    def generate_article(self, context: dict[str, Any]) -> ProviderResult:
        prompt = (
            "你是微信公众号写作编辑。输出 Markdown 正文，不要解释。"
            "要求：强开头、短段落、清晰 H2/H3、小标题自然、结尾有行动建议。"
            f"\n输入：{json.dumps(context, ensure_ascii=False)}"
        )
        text = self._run_prompt(prompt, expect_json=False)
        return ProviderResult(payload=_strip_fences(text).strip() + "\n", provider=self.provider_name, model=self.model)

    def review_article(self, context: dict[str, Any]) -> ProviderResult:
        prompt = (
            "你是微信公众号资深编辑。只输出 JSON 对象，不要解释。"
            "字段必须是 summary, findings, platform_notes。"
            f"\n输入：{json.dumps(context, ensure_ascii=False)}"
        )
        text = self._run_prompt(prompt, expect_json=True)
        payload = self._parse_json(text)
        if isinstance(payload, dict) and "text" in payload and isinstance(payload["text"], str):
            payload = self._parse_json(payload["text"])
        return ProviderResult(payload=payload, provider=self.provider_name, model=self.model)

    def revise_article(self, context: dict[str, Any]) -> ProviderResult:
        prompt = (
            "你是微信公众号改稿编辑。只输出修订后的 Markdown 正文，不要解释。"
            f"\n输入：{json.dumps(context, ensure_ascii=False)}"
        )
        text = self._run_prompt(prompt, expect_json=False)
        return ProviderResult(payload=_strip_fences(text).strip() + "\n", provider=self.provider_name, model=self.model)
