from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from core.viral import default_viral_blueprint, normalize_outline_payload, normalize_review_payload
from providers.text.base import ProviderResult, TextProvider


def _strip_fences(text: str) -> str:
    value = (text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
    return value


def _extract_json_substring(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return value
    first_obj = value.find("{")
    last_obj = value.rfind("}")
    if 0 <= first_obj < last_obj:
        return value[first_obj : last_obj + 1]
    first_arr = value.find("[")
    last_arr = value.rfind("]")
    if 0 <= first_arr < last_arr:
        return value[first_arr : last_arr + 1]
    return value


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
    context = {"topic": title, "selected_title": title, "title": title, "audience": "大众读者", "direction": ""}
    return normalize_outline_payload(
        {
            "title": title,
            "angle": "从问题、误区、方法、行动四段展开",
            "sections": [
                {"heading": "为什么这个问题现在必须重视", "goal": "建立阅读动机", "evidence_need": "趋势或场景证据"},
                {"heading": "大多数人真正卡住的地方", "goal": "拆解常见误区", "evidence_need": "案例或对比"},
                {"heading": "一套可复用的执行框架", "goal": "给出方法论", "evidence_need": "步骤或清单"},
                {"heading": "把方法变成接下来 7 天的动作", "goal": "收束并行动引导", "evidence_need": "行动建议"},
            ],
            "viral_blueprint": default_viral_blueprint(
                topic=title,
                title=title,
                angle="从问题、误区、方法、行动四段展开",
                audience="大众读者",
                research={},
                style_signals=[],
            ),
        },
        context,
    )


def placeholder_article(title: str, outline: dict[str, Any], audience: str) -> str:
    normalized_outline = normalize_outline_payload(
        outline if isinstance(outline, dict) else {"title": title},
        {"topic": title, "selected_title": title, "title": title, "audience": audience or "公众号读者", "direction": ""},
    )
    blueprint = normalized_outline.get("viral_blueprint", {})
    editorial = normalized_outline.get("editorial_blueprint", {})
    lines = [
        f"写给{audience or '公众号读者'}的一篇骨架稿。当前环境未配置文本模型，因此这里先产出可继续编辑、带爆款蓝图的结构化初稿。",
        "",
        f"先说结论：{blueprint.get('core_viewpoint') or '真正决定传播效果的，不是信息堆积，而是判断、刺痛和行动感同时到位。'}",
        "",
        "很多人写公众号文章时，明明信息不少，却还是没人转发。问题通常不在信息量，而在于没有把读者真正卡住的地方说透，也没有让读者觉得“这说的就是我”。",
        "",
        "> 你不是内容不够多，而是还没有把真正能打到人心里的那句话说出来。",
        "",
    ]
    if editorial.get("key_terms"):
        lines.extend(
            [
                f"这一稿建议优先把这些术语写成可渲染格式：{'、'.join(f'`{item}`' for item in editorial.get('key_terms')[:5])}。",
                "",
            ]
        )
    for section in (normalized_outline.get("sections") or []):
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
                "写这一节时，至少补一处对比、一处读者视角、一句能让人截图的判断。",
                "",
            ]
        )
    lines.extend(
        [
            "## 结尾",
            "",
            "真正有传播力的公众号文章，结尾不会停在观点，而会停在一个读者愿意马上保存或转发的动作上。",
            "",
            "- 先复述一句核心判断。",
            "- 再给读者一个今天就能做的动作。",
            "- 最后留下一句能被带走的金句。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def placeholder_review(title: str) -> dict[str, Any]:
    base = normalize_review_payload(
        {
            "summary": f"《{title}》当前为骨架稿，结构完整，但离真正的爆款稿还差情绪价值、刺痛句和更强的传播表达。",
            "findings": [
                "开头需要更强的结果预期或反差钩子。",
                "中段需要至少 1 组案例、数据或对比支撑。",
                "结尾需要更明确的行动建议或收藏点。",
            ],
            "platform_notes": [
                "微信公众号更适合短段落、加粗重点和 2~4 个清晰小标题。",
                "事实型内容发布前应补齐来源区。",
            ],
        },
        title=title,
        body=placeholder_article(title, placeholder_outline(title), "公众号读者"),
        manifest={"topic": title, "audience": "公众号读者", "direction": ""},
        blueprint=default_viral_blueprint(topic=title, title=title, angle="", audience="公众号读者", research={}, style_signals=[]),
        revision_round=1,
        review_source="placeholder",
    )
    base["placeholder"] = True
    return base


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

        def do_request(request_payload: dict[str, Any]) -> dict[str, Any]:
            body = json.dumps(request_payload).encode("utf-8")
            request = urllib.request.Request(
                f"{self.base_url.rstrip('/')}/chat/completions",
                data=body,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))

        try:
            raw = do_request(payload)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            # Some OpenAI-compatible gateways don't support response_format on /chat/completions.
            if response_format and exc.code in {400, 422}:
                lowered = detail.lower()
                if "response_format" in lowered or "json_object" in lowered or "unsupported" in lowered or "invalid" in lowered:
                    fallback_payload = dict(payload)
                    fallback_payload.pop("response_format", None)
                    try:
                        raw = do_request(fallback_payload)
                    except urllib.error.HTTPError as fallback_exc:
                        fallback_detail = fallback_exc.read().decode("utf-8", errors="replace")
                        raise SystemExit(f"文本模型调用失败：{fallback_detail}") from fallback_exc
                else:
                    raise SystemExit(f"文本模型调用失败：{detail}") from exc
            else:
                raise SystemExit(f"文本模型调用失败：{detail}") from exc
        content = (((raw.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
        if not content:
            raise SystemExit(f"文本模型未返回内容：{json.dumps(raw, ensure_ascii=False)}")
        return content

    def _json_result(self, content: str) -> Any:
        value = _strip_fences(content)
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            extracted = _extract_json_substring(value)
            try:
                return json.loads(extracted)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"文本模型返回的 JSON 无法解析：{value}") from exc

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
                "content": "你是微信公众号标题编辑。只输出 JSON 对象，字段 candidates 为数组；每项包含 title, strategy, audience_fit, risk_note。",
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt, {"type": "json_object"})
        payload = self._json_result(content)
        candidates: Any = []
        if isinstance(payload, list):
            candidates = payload
        elif isinstance(payload, dict):
            if isinstance(payload.get("candidates"), list):
                candidates = payload["candidates"]
            elif isinstance(payload.get("titles"), list):
                candidates = payload["titles"]
        return ProviderResult(payload=candidates, provider=self.provider_name, model=self.model)

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
                "content": (
                    "你是微信公众号爆款文章总编。只输出 JSON。"
                    "字段必须包含 title, angle, sections, viral_blueprint, editorial_blueprint。"
                    "sections 每项包含 heading, goal, evidence_need。"
                    "viral_blueprint 必须包含 core_viewpoint, secondary_viewpoints, persuasion_strategies, emotion_triggers, "
                    "target_quotes, emotion_curve, emotion_layers, argument_modes, perspective_shifts, style_traits, pain_points, emotion_value_goals。"
                    "editorial_blueprint 必须包含 key_terms, evidence_requirements, reader_questions, render_hints, visual_storyline。"
                ),
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt, {"type": "json_object"})
        payload = self._json_result(content)
        normalized = normalize_outline_payload(payload, context)
        return ProviderResult(payload=normalized, provider=self.provider_name, model=self.model)

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
                "content": (
                    "你是微信公众号技术编辑。输出 Markdown 正文，不要解释，不要输出顶层 # 标题。"
                    "必须消费输入里的 viral_blueprint 和 editorial_blueprint。"
                    "默认按技术传播平衡写法：先保证技术可信、结构清晰、术语准确，再追求传播力。"
                    "要求：1 个主观点、2~4 个副观点、至少 3 种论证方式、至少 2 次视角切换、至少 3 句可截图金句、"
                    "段落短、句长有波动、禁用首先/其次/最后/综上所述等模板连接词。"
                    "命令、包名、环境变量、路径、接口名、模型名、代码符号、英文专有名词优先用反引号。"
                    "开头先说明价值，结尾必须给读者可执行动作。"
                ),
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
                "content": (
                    "你是微信公众号技术编辑。只输出 JSON，不要解释。"
                    "字段必须包含 summary, findings, strengths, issues, platform_notes, viral_analysis, "
                    "emotion_value_sentences, pain_point_sentences, ai_smell_findings, revision_priorities, "
                    "term_render_issues, layout_rigidity_notes, title_leak_check。"
                    "viral_analysis 必须包含 core_viewpoint, secondary_viewpoints, persuasion_strategies, emotion_triggers, "
                    "signature_lines, emotion_curve, emotion_layers, argument_diversity, perspective_shifts, style_traits。"
                    "emotion_value_sentences 和 pain_point_sentences 必须输出对象数组，每项包含 text, section_heading, reason, strength。"
                ),
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt, {"type": "json_object"})
        payload = self._json_result(content)
        normalized = normalize_review_payload(
            payload,
            title=title,
            body=str(context.get("article_body") or ""),
            manifest={
                "topic": context.get("topic") or title,
                "audience": context.get("audience") or "大众读者",
                "direction": context.get("direction") or "",
                "viral_blueprint": context.get("viral_blueprint"),
            },
            blueprint=context.get("viral_blueprint"),
            revision_round=int(context.get("revision_round") or 1),
            review_source=self.provider_name,
        )
        return ProviderResult(payload=normalized, provider=self.provider_name, model=self.model)

    def revise_article(self, context: dict[str, Any]) -> ProviderResult:
        if not self.configured():
            article = context.get("article_body", "")
            if not article:
                article = placeholder_article(context.get("title", "未命名标题"), context.get("outline") or {}, context.get("audience", "大众读者"))
            return ProviderResult(payload=article, provider=self.provider_name, model=self.model or "placeholder", placeholder=True)
        prompt = [
            {
                "role": "system",
                "content": (
                    "你是微信公众号技术改稿编辑。输出修订后的 Markdown 正文，不要输出解释，也不要输出顶层 # 标题。"
                    "改稿优先级固定为：结构与价值 -> 证据 -> 术语渲染 -> 传播表达 -> 去 AI 味。"
                    "命令、包名、环境变量、路径、接口名、模型名、代码符号、英文专有名词优先用反引号。"
                    "必须保留原文事实边界，不要编造数据。"
                ),
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt)
        return ProviderResult(payload=content.strip() + "\n", provider=self.provider_name, model=self.model)
