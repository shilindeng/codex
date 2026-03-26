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
            "angle": "从被误读的信号、真正的分水岭和最后的判断展开",
            "viral_blueprint": default_viral_blueprint(
                topic=title,
                title=title,
                angle="从被误读的信号、真正的分水岭和最后的判断展开",
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
    lines = [
        f"# {title}",
        "",
        f"写给{audience or '公众号读者'}的一篇骨架稿。当前环境未配置文本模型，因此这里只先给出一版可继续编辑的结构化长文起稿。",
        "",
        blueprint.get('core_viewpoint') or '真正决定传播效果的，不是信息堆积，而是文章有没有带出新的判断。',
        "",
        "很多公众号稿件的问题，不是信息不够，而是写法太像模板：开头一眼能猜到，结尾一眼能看穿，读完没有余味。",
        "",
        "真正能留下来的文章，往往不是上来就把答案喊出来，而是先把读者带进那个具体的问题和处境。",
        "",
    ]
    for section in (normalized_outline.get("sections") or []):
        lines.extend(
            [
                f"## {section.get('heading') or '未命名章节'}",
                "",
                f"这一节的目标是：{section.get('goal') or '展开核心论点'}。",
                "",
                f"建议补充：{section.get('evidence_need') or '案例、数据或对比'}。",
                "",
                "把这一段写实，写到读者能立刻看见场景、理解代价，并带走一个更稳的判断。",
                "",
                "写这一节时，尽量补一处具体细节、一处对比或案例，以及一句值得被记住的判断。",
                "",
            ]
        )
    lines.extend(
        [
            "## 结尾",
            "",
            "真正有传播力的公众号文章，结尾不会只剩一个清单，它通常会把全文判断收束到一句读者愿意带走的话。",
            "",
            "如果这是方法文，可以给一个真的能开始的动作；如果这是分析稿，更适合留下一个值得反复想的判断。",
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
                "content": (
                    "你是微信公众号标题编辑。只输出 JSON 对象，字段 candidates 为数组；每项包含 title, strategy, audience_fit, risk_note。"
                    "必须同时给出不同气质的标题，不要 3 个标题只是同一模板换词。"
                    "如果输入里带有 editorial_blueprint，标题风格必须服从它；如果 recent_corpus_summary 显示某类标题模式已经高频出现，禁止继续复用。"
                    "不要默认产出“为什么大多数人…”“真正危险的不是…而是…”“先想清 3 件事”这类熟模板。"
                ),
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
                    "你是资深微信公众号总编。只输出 JSON。"
                    "字段必须包含 title, angle, sections, viral_blueprint, editorial_blueprint。"
                    "sections 每项包含 heading, goal, evidence_need。"
                    "同时尽量补充 article_archetype, opening_mode, ending_mode, voice_guardrails, avoid_patterns。"
                    "editorial_blueprint 必须包含 style_key, style_label, summary, title_strategy, opening_strategy, body_strategy, heading_strategy, evidence_strategy, ending_strategy, paragraph_rhythm, language_texture, forbidden_moves, preferred_devices。"
                    "viral_blueprint 必须包含 core_viewpoint, secondary_viewpoints, persuasion_strategies, emotion_triggers, "
                    "target_quotes, emotion_curve, emotion_layers, argument_modes, perspective_shifts, style_traits, pain_points, emotion_value_goals, "
                    "like_triggers, comment_triggers, share_triggers, social_currency_points, identity_labels, controversy_anchors, interaction_prompts, "
                    "interaction_formula, peak_moment_design, ending_interaction_design。"
                    "不要把所有文章都规划成“一句话结论 + 三段方法 + 执行清单”。要根据题材判断是分析评论、教程指南、案例拆解还是叙事观察。"
                    "如果输入已经给了 editorial_blueprint，必须沿用其中的 style_key、style_label 和核心策略，只能补齐，不能改回你最熟悉的评论模板。"
                    "规划时显式思考：点赞靠什么、评论靠什么、转发靠什么，以及中段的峰值时刻和结尾的互动收束如何设计。"
                    "必须给出 primary_interaction_goal 和 secondary_interaction_goal，禁止三种互动目标同时拉满。"
                    "必须避开输入中的 recent_phrase_blacklist；如果 recent_corpus_summary 提示某种标题模式、开头模式、结尾模式或小标题模式已经过度出现，就不要再复用。"
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
                    "你是写 10w+ 公众号长文的资深作者兼总编。输出 Markdown 正文，不要解释。"
                    "必须消费输入里的 outline 与 viral_blueprint，但不能把它们机械翻译成模板文章。"
                    "输入里的 editorial_blueprint 是硬约束：标题气质、开头方式、正文推进、小标题写法、证据组织和结尾方式都要服从它。"
                    "牢记：高互动文章 = 情绪价值（共鸣/争议） + 社交货币（谈资/身份） + 峰终体验。"
                    "优先服务输入中的 primary_interaction_goal，只把 secondary_interaction_goal 作为辅助，不要三种互动全开。"
                    "写作要求："
                    "1. 允许用场景、新闻、反差、细节、人物、问题等不同方式开头，不要默认使用“先说结论”“如果你只想记住一句话”“这篇文章会”。"
                    "2. 结尾不默认给 checklist；只有当题材明显是教程/方法文时，才给动作。分析稿、评论稿、案例稿优先用判断、余味、风险提醒或趋势观察收束。"
                    "3. 不要硬凑固定配方；不要把每一节都写成先下判断再解释；要有节奏变化、具体细节和真实编辑感。"
                    "4. 段落短但不能碎，句式要有长短变化；禁用首先/其次/最后/综上所述等模板连接词。"
                    "5. 多用具体场景、案例、对比、引用和事实支撑，不要空喊观点。"
                    "6. 不要自我解释写作结构，不要出现“接下来我会”“下面我们来看”。"
                    "7. 中段必须设计一个让读者想停下来划线、点赞或争辩的峰值时刻。"
                    "8. 结尾要么升华成一句值得点赞/转发的判断，要么留下一个和读者自身强相关、会激发评论的问题。"
                    "9. 让文章至少提供一个可转述的社交谈资和一个可贴身份的表达点，但不要低级钓鱼。"
                    "10. 必须遵守引用策略：正文不要裸贴 URL；只允许在关键事实段落后用 [1][2] 这类轻引用，完整来源放文末参考资料。"
                    "11. 必须避开输入 recent_phrase_blacklist 里的高频套话和结构。"
                    "12. 如果 recent_corpus_summary 提示某种标题模式、开头模式、结尾模式或小标题模式已经过度出现，必须主动换路数。"
                    "13. 不要输出“金句 1：”“金句 2：”这类标签，也不要手写“参考资料”区块或 [!TIP] 参考资料 callout。"
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
                    "你是微信公众号爆款编辑。只输出 JSON，不要解释。"
                    "字段必须包含 summary, findings, strengths, issues, platform_notes, viral_analysis, "
                    "emotion_value_sentences, pain_point_sentences, ai_smell_findings, revision_priorities, editorial_review, template_findings, similarity_findings, citation_findings, interaction_findings。"
                    "viral_analysis 必须包含 core_viewpoint, secondary_viewpoints, persuasion_strategies, emotion_triggers, "
                    "signature_lines, emotion_curve, emotion_layers, argument_diversity, perspective_shifts, style_traits, "
                    "like_triggers, comment_triggers, share_triggers, social_currency_points, identity_labels, controversy_anchors, peak_moment, ending_interaction_design。"
                    "emotion_value_sentences 和 pain_point_sentences 必须输出对象数组，每项包含 text, section_heading, reason, strength。"
                    "请重点识别：文章是否落入固定模板（如先说结论、篇章自我说明、结尾万能清单、每节都同一种句式起手）。"
                    "如果输入 recent_corpus_summary 显示这篇稿子的标题、开头、结尾或小标题模式撞上近期高频套路，要明确指出。"
                    "同时判断：这篇文章为什么值得点赞、为什么会引发评论、为什么会被转发；如果缺失，请明确指出。"
                    "editorial_review 必须包含 reading_desire, professional_tone, novelty_of_viewpoint, template_risk, citation_restraint, ending_naturalness, interaction_naturalness, summary。"
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
                    "你是微信公众号深度改稿编辑。输出修订后的 Markdown 正文，不要输出解释。"
                    "必须保留原文事实边界，不要编造数据。"
                    "优先修复最影响阅读完成度和传播力的 3 个问题，但不要用固定模板去“提分”。"
                    "如果输入给了 editorial_blueprint，就按它改，不要改回最常见的分析评论腔。"
                    "禁止默认补“先说结论”“最后给你一个可执行清单”“如果你只想记住一句话”。"
                    "如果原稿更适合做分析稿或评论稿，就保留判断与余味；如果原稿明显是教程，再考虑动作化结尾。"
                    "改稿时必须补足互动设计："
                    "1. 至少一个让人想点赞的金句或升华句。"
                    "2. 至少一个自然触发评论的问题、站队点或经验补充点。"
                    "3. 至少一个值得转发的谈资、身份标签或可复述判断。"
                    "4. 中段要有峰值，结尾要有收束。"
                    "5. 必须去掉正文裸 URL，改成关键节点轻引用或文末参考资料卡片。"
                    "6. 必须避开输入 recent_phrase_blacklist 中的开头、结尾和桥接套话。"
                    "7. 如果 recent_corpus_summary 显示标题、开头、结尾或小标题模式撞上近期高频套路，必须顺手换骨架。"
                    "8. 删除“金句 1/2/3”标签，不要手写参考资料段或参考资料 callout。"
                ),
            },
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        content = self._request(prompt)
        return ProviderResult(payload=content.strip() + "\n", provider=self.provider_name, model=self.model)
