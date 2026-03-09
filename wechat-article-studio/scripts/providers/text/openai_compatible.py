from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from providers.text.base import ProviderResult, TextProvider


def placeholder_titles(topic: str, audience: str, count: int) -> list[dict[str, str]]:
    titles = []
    for index in range(count):
        titles.append(
            {
                "title": f"{topic}：第 {index + 1} 个可执行选题角度",
                "strategy": "结果导向 + 认知反差",
                "audience_fit": audience or "大众读者",
                "risk_note": "占位标题；配置文本模型后可替换为正式提案。",
            }
        )
    return titles


def placeholder_outline(title: str) -> dict[str, Any]:
    return {
        "title": title,
        "angle": "从问题、误区、方法、行动四段展开",
        "sections": [
            {"heading": "为什么这个问题现在必须重视", "goal": "建立阅读动机", "evidence_need": "趋势或场景证据"},
            {"heading": "大多数人真正卡住的地方", "goal": "拆解常见误区", "evidence_need": "案例或对比"},
            {"heading": "一套可复用的执行框架", "goal": "给出方法论", "evidence_need": "步骤或清单"},
            {"heading": "把方法变成接下来 7 天的动作", "goal": "收束并行动引导", "evidence_need": "行动建议"},
        ],
    }


def placeholder_article(title: str, outline: dict[str, Any], audience: str) -> str:
    lines = [
        f"# {title}",
        "",
        f"写给{audience or '公众号读者'}的一篇骨架稿。当前环境未配置文本模型，因此这里先产出可继续编辑的结构化初稿。",
        "",
        "如果你要把这篇文章真正写出传播力，重点不是把信息堆满，而是先把读者为什么要继续看下去这件事讲清楚。",
        "",
    ]
    for section in outline.get("sections") or []:
        lines.extend(
            [
                f"## {section.get('heading') or '未命名章节'}",
                "",
                f"这一节的目标是：{section.get('goal') or '展开核心论点'}。",
                "",
                f"建议补充：{section.get('evidence_need') or '案例、数据或对比'}。",
                "",
                "把这一段写实，写到读者能立刻理解问题、判断代价、看到可执行动作。",
                "",
            ]
        )
    lines.extend(
        [
            "## 结尾",
            "",
            "真正有传播力的公众号文章，结尾不会停在观点，而会停在一个读者愿意马上保存或转发的动作上。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def placeholder_review(title: str) -> dict[str, Any]:
    return {
        "summary": f"《{title}》当前为骨架稿，结构完整但仍需补充事实支撑和更强的传播表达。",
        "findings": [
            "开头需要更强的结果预期或反差钩子。",
            "中段需要至少 1 组案例、数据或对比支撑。",
            "结尾需要更明确的行动建议或收藏点。",
        ],
        "platform_notes": [
            "微信公众号更适合短段落、加粗重点和 2~4 个清晰小标题。",
            "事实型内容发布前应补齐来源区。",
        ],
        "placeholder": True,
    }


class OpenAICompatibleTextProvider(TextProvider):
    provider_name = "openai-compatible"

    def __init__(self) -> None:
        self.base_url = os.getenv("ARTICLE_STUDIO_TEXT_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.model = os.getenv("ARTICLE_STUDIO_TEXT_MODEL", "")

    def configured(self) -> bool:
        return bool(self.api_key and self.model)

    def _request(self, messages: list[dict[str, str]], response_format: dict[str, str] | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.6,
        }
        if response_format:
            payload["response_format"] = response_format
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"文本模型调用失败：{detail}") from exc
        content = (((raw.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        if not content:
            raise SystemExit(f"文本模型未返回内容：{json.dumps(raw, ensure_ascii=False)}")
        return content

    def _json_result(self, content: str) -> Any:
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"文本模型返回的 JSON 无法解析：{content}") from exc

    def generate_research_pack(self, context: dict[str, Any]) -> ProviderResult:
        if not self.configured():
            payload = {
                "topic": context.get("topic", ""),
                "angle": context.get("angle", ""),
                "audience": context.get("audience", ""),
                "sources": [{"url": item, "credibility": "user-provided"} for item in context.get("source_urls", [])],
                "evidence_items": [],
                "information_gaps": ["未配置文本模型，仅完成来源规范化；请补充联网调研结果。"],
                "forbidden_claims": ["不要把未验证数据写成确定事实。"],
                "placeholder": True,
            }
            return ProviderResult(payload=payload, provider=self.provider_name, model=self.model or "placeholder", placeholder=True)
        prompt = [
            {
                "role": "system",
                "content": "你是微信公众号选题研究助手。只输出 JSON，字段为 topic, angle, audience, sources, evidence_items, information_gaps, forbidden_claims。",
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt, {"type": "json_object"})
        return ProviderResult(payload=self._json_result(content), provider=self.provider_name, model=self.model)

    def generate_titles(self, context: dict[str, Any]) -> ProviderResult:
        count = int(context.get("count", 3) or 3)
        if not self.configured():
            return ProviderResult(
                payload=placeholder_titles(context.get("topic", "未命名主题"), context.get("audience", "大众读者"), count),
                provider=self.provider_name,
                model=self.model or "placeholder",
                placeholder=True,
            )
        prompt = [
            {
                "role": "system",
                "content": "你是微信公众号标题编辑。只输出 JSON 数组，每项包含 title, strategy, audience_fit, risk_note。",
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt)
        return ProviderResult(payload=self._json_result(content), provider=self.provider_name, model=self.model)

    def generate_outline(self, context: dict[str, Any]) -> ProviderResult:
        title = context.get("selected_title") or context.get("title") or context.get("topic") or "未命名标题"
        if not self.configured():
            return ProviderResult(
                payload=placeholder_outline(title),
                provider=self.provider_name,
                model=self.model or "placeholder",
                placeholder=True,
            )
        prompt = [
            {
                "role": "system",
                "content": "你是微信公众号大纲编辑。只输出 JSON，字段为 title, angle, sections，sections 每项包含 heading, goal, evidence_need。",
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt, {"type": "json_object"})
        return ProviderResult(payload=self._json_result(content), provider=self.provider_name, model=self.model)

    def generate_article(self, context: dict[str, Any]) -> ProviderResult:
        title = context.get("title") or context.get("selected_title") or context.get("topic") or "未命名标题"
        if not self.configured():
            return ProviderResult(
                payload=placeholder_article(title, context.get("outline") or {}, context.get("audience", "大众读者")),
                provider=self.provider_name,
                model=self.model or "placeholder",
                placeholder=True,
            )
        prompt = [
            {
                "role": "system",
                "content": "你是微信公众号写作编辑。输出 Markdown 正文，包含 H2/H3 结构、短段落、明确开头钩子、结尾行动建议。",
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt)
        return ProviderResult(payload=content.strip() + "\n", provider=self.provider_name, model=self.model)

    def review_article(self, context: dict[str, Any]) -> ProviderResult:
        title = context.get("title") or "未命名标题"
        if not self.configured():
            return ProviderResult(
                payload=placeholder_review(title),
                provider=self.provider_name,
                model=self.model or "placeholder",
                placeholder=True,
            )
        prompt = [
            {
                "role": "system",
                "content": "你是微信公众号资深编辑。只输出 JSON，字段为 summary, findings, platform_notes。",
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt, {"type": "json_object"})
        return ProviderResult(payload=self._json_result(content), provider=self.provider_name, model=self.model)

    def revise_article(self, context: dict[str, Any]) -> ProviderResult:
        if not self.configured():
            article = context.get("article_body", "")
            if not article:
                article = placeholder_article(context.get("title", "未命名标题"), context.get("outline") or {}, context.get("audience", "大众读者"))
            return ProviderResult(payload=article, provider=self.provider_name, model=self.model or "placeholder", placeholder=True)
        prompt = [
            {
                "role": "system",
                "content": "你是微信公众号改稿编辑。输出修订后的 Markdown 正文，不要输出解释。",
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt)
        return ProviderResult(payload=content.strip() + "\n", provider=self.provider_name, model=self.model)
