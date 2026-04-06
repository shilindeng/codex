from __future__ import annotations

import json
import os
from typing import Any

import legacy_studio as legacy
from core.gemini_web_session import describe_session_source, has_session_material, run_gemini_web_command
from core.viral import normalize_outline_payload, normalize_review_payload
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

    def configured(self) -> bool:
        return has_session_material(os.environ.copy())

    def _bun_command(self) -> list[str]:
        return legacy.resolve_bun_command()

    def _main_ts(self) -> Path:
        return legacy.ensure_gemini_web_vendor() / "main.ts"

    def _run_prompt(self, prompt: str, expect_json: bool) -> str:
        if not self.configured():
            raise SystemExit("gemini-web 文本 provider 未配置。请先准备可复用的登录态，或先完成一次 gemini-web 登录。")
        legacy.ensure_gemini_web_consent()
        command = self._bun_command() + [str(self._main_ts()), "--model", self.model, "--prompt", prompt]
        if expect_json:
            command.append("--json")
        completed, session_info = run_gemini_web_command(
            command,
            cwd=str(self._main_ts().parent),
            label="gemini-web 文本生成",
        )
        output = (completed.stdout or "").strip()
        if not output:
            raise SystemExit(f"gemini-web 未返回文本内容。当前登录态来源：{describe_session_source(session_info)}")
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
            "必须同时给出不同气质的标题，不要 3 个标题只是同一模板换词。"
            "如果输入里带有 editorial_blueprint，标题风格必须服从它；如果 recent_corpus_summary 显示某类标题模式已经高频出现，禁止继续复用。"
            "不要默认产出“为什么大多数人…”“真正危险的不是…而是…”“先想清 3 件事”这类熟模板。"
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
            "你是资深微信公众号总编。只输出 JSON 对象，不要解释。"
            "字段必须是 title, angle, sections, viral_blueprint, editorial_blueprint。"
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
            "如果输入包含 fingerprint_collision_notes，必须主动换开头路数、证据组织、互动目标或结尾收束，不能只换词。"
            "大纲必须主动分配深度：至少有一个“现场/案例/具体瞬间”章节，一个“误判/反方/边界”章节，一个“最后判断/收束”章节。"
            "不要让所有小标题都长得像同一类问句、编号句或判断句。"
            f"\n输入：{json.dumps(context, ensure_ascii=False)}"
        )
        text = self._run_prompt(prompt, expect_json=True)
        payload = self._parse_json(text)
        if isinstance(payload, dict) and "text" in payload and isinstance(payload["text"], str):
            payload = self._parse_json(payload["text"])
        return ProviderResult(payload=normalize_outline_payload(payload, context), provider=self.provider_name, model=self.model)

    def generate_article(self, context: dict[str, Any]) -> ProviderResult:
        prompt = (
            "你是写 10w+ 公众号长文的资深作者兼总编。输出 Markdown 正文，不要解释。"
            "必须消费输入里的 outline 与 viral_blueprint，但不能把它们机械翻译成模板文章。"
            "输入里的 editorial_blueprint 是硬约束：标题气质、开头方式、正文推进、小标题写法、证据组织和结尾方式都要服从它。"
            "如果输入带有 layout_plan，正文必须给这些版式模块留出自然材料，不要写到最后只剩空洞判断。"
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
            "14. 不要把小标题、段首提示或段落标签写成“行业判断”“事实/依据”“边界/误判”这类元标签，直接进入内容本身。"
            "15. 正文必须至少满足这些硬要求：前 2~3 段里出现一个具体场景/动作/瞬间；中段至少出现一处案例、数据或实际支撑；全文可以出现反向看法或使用前提，但不要把这些词直接写成标签。"
            "16. 至少保留 1~2 段真正展开的分析段，不要所有段落都短到像提纲卡片。"
            "16. 不要让多个段落反复用“很多人/你可能/如果你”起手；同一篇里这种起手最多各用一次。"
            "17. 小标题之间要有句法变化，不要整篇都是同一类问句、同一类编号句或同一类判断句。"
            f"\n输入：{json.dumps(context, ensure_ascii=False)}"
        )
        text = self._run_prompt(prompt, expect_json=False)
        return ProviderResult(payload=_strip_fences(text).strip() + "\n", provider=self.provider_name, model=self.model)

    def review_article(self, context: dict[str, Any]) -> ProviderResult:
        prompt = (
            "你是微信公众号爆款编辑。只输出 JSON 对象，不要解释。"
            "字段必须包含 summary, findings, strengths, issues, platform_notes, viral_analysis, "
            "emotion_value_sentences, pain_point_sentences, ai_smell_findings, revision_priorities, editorial_review, template_findings, similarity_findings, citation_findings, interaction_findings。"
            "viral_analysis 必须包含 core_viewpoint, secondary_viewpoints, persuasion_strategies, emotion_triggers, "
            "signature_lines, emotion_curve, emotion_layers, argument_diversity, perspective_shifts, style_traits, "
            "like_triggers, comment_triggers, share_triggers, social_currency_points, identity_labels, controversy_anchors, peak_moment, ending_interaction_design。"
            "emotion_value_sentences 和 pain_point_sentences 必须输出对象数组，每项包含 text, section_heading, reason, strength。"
            "请重点识别：文章是否落入固定模板（如先说结论、篇章自我说明、结尾万能清单、每节都同一种句式起手）。"
            "如果输入 recent_corpus_summary 显示这篇稿子的标题、开头、结尾或小标题模式撞上近期高频套路，要明确指出。"
            "如果输入包含 layout_plan，要判断正文是否给既定版式模块留够事实、案例、对比或结论材料。"
            "还要重点判断：有没有具体场景/动作/瞬间，有没有事实或案例托底，有没有反方或适用边界，段落是否过碎像提纲，多个段落是否反复同一种起手。"
            "同时判断：这篇文章为什么值得点赞、为什么会引发评论、为什么会被转发；如果缺失，请明确指出。"
            "editorial_review 必须包含 reading_desire, professional_tone, novelty_of_viewpoint, template_risk, citation_restraint, ending_naturalness, interaction_naturalness, summary。"
            f"\n输入：{json.dumps(context, ensure_ascii=False)}"
        )
        text = self._run_prompt(prompt, expect_json=True)
        payload = self._parse_json(text)
        if isinstance(payload, dict) and "text" in payload and isinstance(payload["text"], str):
            payload = self._parse_json(payload["text"])
        normalized = normalize_review_payload(
            payload,
            title=str(context.get("title") or "未命名标题"),
            body=str(context.get("article_body") or ""),
            manifest={
                "topic": context.get("topic") or context.get("title") or "",
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
        prompt = (
            "你是微信公众号深度改稿编辑。只输出修订后的 Markdown 正文，不要解释。"
            "优先修复最影响阅读完成度和传播力的 3 个问题，但不要用固定模板去“提分”。"
            "如果输入给了 editorial_blueprint，就按它改，不要改回最常见的分析评论腔。"
            "如果输入给了 layout_plan，改稿时要顺手补足对应版式模块需要的材料。"
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
            "9. 如果原稿缺少现场、案例或反向看法，请优先补这些内容，但不要写成“行业判断”“事实/依据”“边界/误判”这类标签。"
            "10. 如果原稿段落过碎，请合并出一两段真正展开的分析段；如果多个段落起手一样，请重写起手。"
            f"\n输入：{json.dumps(context, ensure_ascii=False)}"
        )
        text = self._run_prompt(prompt, expect_json=False)
        return ProviderResult(payload=_strip_fences(text).strip() + "\n", provider=self.provider_name, model=self.model)
