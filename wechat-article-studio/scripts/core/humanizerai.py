from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request


HUMANIZERAI_BASE_URL = "https://humanizerai.com/api/v1"
HUMANIZERAI_INTENSITIES = ("light", "medium", "aggressive")


class HumanizerAIError(RuntimeError):
    pass


@dataclass(frozen=True)
class HumanizerAIClient:
    api_key: str
    base_url: str = HUMANIZERAI_BASE_URL
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "HumanizerAIClient":
        api_key = (os.getenv("HUMANIZERAI_API_KEY") or "").strip()
        base_url = (os.getenv("HUMANIZERAI_BASE_URL") or HUMANIZERAI_BASE_URL).strip().rstrip("/")
        timeout_seconds = int(os.getenv("HUMANIZERAI_TIMEOUT_SECONDS") or "30")
        return cls(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)

    def configured(self) -> bool:
        return bool(self.api_key)

    def doctor_status(self) -> dict[str, Any]:
        return {
            "configured": self.configured(),
            "base_url": self.base_url,
            "required_env": ["HUMANIZERAI_API_KEY"],
            "notes": [
                "Detection 免费，humanize 按词数消耗额度。",
                "只在 de-ai 改稿时才会尝试调用外部 humanize。",
            ],
        }

    def detect(self, text: str) -> dict[str, Any]:
        payload = self._post_json("/detect", {"text": text or ""})
        score = payload.get("score") or {}
        overall = _to_int(score.get("overall"))
        return {
            "score_overall": overall,
            "verdict": str(payload.get("verdict") or "").strip().lower(),
            "word_count": _to_int(payload.get("wordCount")),
            "sentence_count": _to_int(payload.get("sentenceCount")),
            "score": {
                "overall": overall,
                "perplexity": _to_int(score.get("perplexity")),
                "burstiness": _to_int(score.get("burstiness")),
                "readability": _to_int(score.get("readability")),
                "sat_percent": _to_int(score.get("satPercent")),
                "simplicity": _to_int(score.get("simplicity")),
                "ngram_score": _to_int(score.get("ngramScore")),
                "average_sentence_length": _to_int(score.get("averageSentenceLength")),
            },
            "raw": payload,
        }

    def humanize(self, text: str, intensity: str) -> dict[str, Any]:
        chosen = normalize_humanizerai_intensity(intensity)
        payload = self._post_json("/humanize", {"text": text or "", "intensity": chosen})
        humanized_text = _pick_humanized_text(payload)
        if not humanized_text.strip():
            raise HumanizerAIError("HumanizerAI 返回成功，但没有拿到可用正文。")
        return {
            "text": humanized_text.strip() + "\n",
            "intensity": chosen,
            "credits_remaining": _to_int(
                payload.get("creditsRemaining")
                or payload.get("remainingCredits")
                or payload.get("credits")
            ),
            "raw": payload,
        }

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.configured():
            raise HumanizerAIError("HUMANIZERAI_API_KEY 未配置。")
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            self.base_url + path,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise HumanizerAIError(f"HTTP {exc.code}: {detail or exc.reason}") from exc
        except error.URLError as exc:
            raise HumanizerAIError(f"网络请求失败：{exc.reason}") from exc
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HumanizerAIError(f"返回不是合法 JSON：{raw[:200]}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise HumanizerAIError(str(payload.get("error")))
        return payload if isinstance(payload, dict) else {"raw": payload}


def normalize_humanizerai_intensity(value: str | None, *, score_overall: int | None = None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in HUMANIZERAI_INTENSITIES:
        return normalized
    if score_overall is None:
        return "medium"
    if score_overall >= 81:
        return "aggressive"
    if score_overall >= 61:
        return "medium"
    return "light"


def _to_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _pick_humanized_text(payload: dict[str, Any]) -> str:
    for key in ("humanizedText", "humanized_text", "text", "output", "result", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("humanizedText", "humanized_text", "text", "output", "result", "content"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return ""
