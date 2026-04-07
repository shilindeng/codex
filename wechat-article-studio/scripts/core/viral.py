from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from core.editorial_strategy import (
    ending_pattern_key,
    heading_pattern_key,
    normalize_editorial_blueprint,
    opening_pattern_key,
    title_template_key,
)
from core.title_decision import title_integrity_report


VIRAL_BLUEPRINT_FIELDS = [
    "core_viewpoint",
    "secondary_viewpoints",
    "persuasion_strategies",
    "emotion_triggers",
    "target_quotes",
    "emotion_curve",
    "emotion_layers",
    "argument_modes",
    "perspective_shifts",
    "style_traits",
    "pain_points",
    "emotion_value_goals",
]

SCORE_WEIGHTS: list[tuple[str, int]] = [
    ("标题与开头爆点", 10),
    ("核心观点与副观点", 10),
    ("说服策略与论证多样性", 10),
    ("情绪触发与刺痛感", 10),
    ("金句与传播句密度", 10),
    ("互动参与与社交货币", 10),
    ("情感曲线与节奏", 8),
    ("情感层次与共鸣", 8),
    ("视角转化与认知增量", 8),
    ("语言风格自然度", 8),
    ("可信度与检索支撑", 8),
]

DEFAULT_THRESHOLD = 86

EMOTION_VALUE_THRESHOLD = 6
PAIN_POINT_THRESHOLD = 4
SIGNATURE_LINE_THRESHOLD = 3
ARGUMENT_MODE_THRESHOLD = 3
PERSPECTIVE_SHIFT_THRESHOLD = 2
AI_SMELL_THRESHOLD = 1
CREDIBILITY_THRESHOLD = 6
KNOWN_TEMPLATE_PHRASES = [
    "这很正常，你不是一个人",
    "最难受的是",
    "真正值得带走的判断只有一个",
    "如果你最近",
    "别急着把",
    "说白了",
    "以后真正靠谱的 AI，可能不是",
]

PROMPT_LEAK_PATTERNS = [
    "这类题目最怕的",
    "围绕“这个主题”",
    "围绕这个主题",
    "更值得展开的是",
    "先把主判断立住",
    "先给一个可代入的处境",
    "先把比较对象和判断方向亮出来",
    "正文由宿主 agent",
    "editorial_blueprint",
    "viral_blueprint",
    "写作要求",
]

STOP_SLOP_THROAT_CLEARING_PATTERNS: list[tuple[str, str]] = [
    (r"(?:^|[。！？!?；;\n]\s*)(先说结论)(?:[，,:：\s])", "先说结论"),
    (r"(?:^|[。！？!?；;\n]\s*)(换句话说|说白了|说到底)(?:[，,:：\s])", "先铺垫再说重点"),
    (r"(?:^|[。！？!?；;\n]\s*)(更重要的是|更关键的是|值得注意的是|需要注意的是)(?:[，,:：\s])", "先铺垫再说重点"),
    (r"(?:^|[。！？!?；;\n]\s*)(真正的问题是|这里有个问题|我们先来看|接下来我们看)(?:[，,:：\s])", "自我领读式起手"),
]

STOP_SLOP_BINARY_CONTRAST_PATTERNS: list[tuple[str, str]] = [
    (r"不是[^。！？!?；;\n]{1,24}而是[^。！？!?；;\n]{1,24}", "不是X，而是Y"),
    (r"问题不在[^。！？!?；;\n]{1,24}而在[^。！？!?；;\n]{1,24}", "问题不在X，而在Y"),
    (r"真正[^。！？!?；;\n]{0,10}不是[^。！？!?；;\n]{1,24}而是[^。！？!?；;\n]{1,24}", "真正的不是X，而是Y"),
]

STOP_SLOP_FALSE_AGENCY_PATTERNS: list[tuple[str, str]] = [
    (r"(?:数据|图表|报告)[^。！？!?；;\n]{0,6}告诉(?:我们|你)?", "让抽象信息替人下判断"),
    (r"市场[^。！？!?；;\n]{0,4}(奖励|惩罚)", "让抽象系统替人行动"),
    (r"趋势[^。！？!?；;\n]{0,4}(要求|逼着|告诉|教会)", "让抽象趋势替人行动"),
    (r"(?:AI|模型|系统)[^。！？!?；;\n]{0,4}(知道|理解|记住|想要|决定)", "让工具像人一样思考"),
]

EMOTION_VALUE_MARKERS = [
    "你不是",
    "你会发现",
    "别急着",
    "没关系",
    "这很正常",
    "不是你",
    "你并不",
    "可以先",
    "至少",
    "先别",
    "真正让人",
    "其实你",
    "放心",
    "说白了",
]

PAIN_POINT_MARKERS = [
    "焦虑",
    "卡住",
    "被淘汰",
    "越学越",
    "代价",
    "吃亏",
    "误判",
    "浪费",
    "没结果",
    "拖住",
    "困住",
    "不甘心",
    "刺痛",
    "害怕",
    "不敢",
    "最难受",
]

PERSUASION_MARKERS: dict[str, list[str]] = {
    "数据论证": [r"\d+(?:\.\d+)?%?", r"\d{4}年", r"\d+倍", r"\d+个"],
    "案例论证": [r"案例", r"比如", r"例如", r"有人", r"一个朋友", r"某家公司"],
    "对比论证": [r"不是.+而是", r"一边.+一边", r"对比", r"反而", r"但真正"],
    "拆解论证": [r"拆开看", r"拆解", r"分成", r"底层", r"本质"],
    "步骤论证": [r"第一", r"第二", r"第三", r"步骤", r"清单", r"先.+再"],
    "权威论证": [r"官方", r"报告", r"研究", r"数据显示", r"文档"],
    "场景论证": [r"场景", r"故事", r"那一刻", r"如果你", r"想象一下"],
}

EMOTION_LAYER_MARKERS: dict[str, list[str]] = {
    "焦虑层": ["焦虑", "担心", "害怕", "慌", "不安"],
    "自证层": ["不是你不行", "你不是", "这很正常", "别急着否定自己"],
    "理解层": ["真正的问题", "先把话说清楚", "本质上", "说白了"],
    "行动层": ["先做", "现在就", "今天", "接下来", "至少先"],
    "希望层": ["机会", "还有空间", "来得及", "能做到", "长期优势"],
}

STYLE_TRAIT_PATTERNS: list[tuple[str, list[str]]] = [
    ("短句推进", [r"。", r"！", r"？"]),
    ("场景切口", [r"你可能", r"某天", r"那一刻", r"刷到", r"看到", r"消息", r"视频"]),
    ("对比感强", [r"不是.+而是", r"但", r"却", r"反而"]),
    ("读者对话", [r"你", r"我们", r"别急", r"你会发现"]),
    ("证据穿插", [r"比如", r"例如", r"数据显示", r"报告", r"文档", r"https?://"]),
]

BLUEPRINT_EXTRA_LIST_FIELDS = [
    "opening_modes",
    "ending_modes",
    "voice_guardrails",
    "avoid_patterns",
    "like_triggers",
    "comment_triggers",
    "share_triggers",
    "social_currency_points",
    "identity_labels",
    "controversy_anchors",
    "interaction_prompts",
]

SCENE_MARKERS = [
    "那一刻",
    "当时",
    "会议室",
    "办公室",
    "工位",
    "屏幕",
    "白板",
    "消息弹出来",
    "刚坐下",
    "凌晨",
    "晚上",
    "中午",
    "有人",
    "一个团队",
    "一个同事",
    "那天",
]

DETAIL_MARKERS = [
    "邮件",
    "表格",
    "链接",
    "文档",
    "截图",
    "工单",
    "客户",
    "老板",
    "同事",
    "群里",
    "版本",
    "按钮",
    "流程",
    "页面",
    "表单",
]

COUNTERPOINT_MARKERS = [
    "但这不代表",
    "但这不等于",
    "但问题是",
    "可真正的问题",
    "另一面是",
    "反过来",
    "例外是",
    "边界在于",
    "前提是",
    "误区在于",
    "别把",
]

EVIDENCE_MARKERS = [
    "数据显示",
    "研究",
    "报告",
    "官方",
    "案例",
    "复盘",
    "例如",
    "比如",
    "根据",
]

COMMON_PARAGRAPH_STARTERS = {
    "很多人",
    "你可能",
    "如果你",
    "真正的",
    "问题是",
    "这件事",
    "先说",
    "接下来",
    "换句话说",
    "更重要的是",
    "真正的问题是",
}

COMMON_SENTENCE_OPENERS = {
    "很多人",
    "你可能",
    "如果你",
    "真正的",
    "问题是",
    "说白了",
    "换句话说",
    "这件事",
    "先说",
    "但真正",
    "与此同时",
    "换句话说",
    "更重要的是",
    "值得注意的是",
    "真正的问题是",
}

COMMON_ADVERBS = {
    "非常",
    "十分",
    "特别",
    "相当",
    "尤其",
    "更加",
    "逐渐",
    "不断",
    "一直",
    "已经",
    "正在",
    "可能",
    "大概",
    "显然",
    "明显",
    "确实",
    "居然",
    "竟然",
    "几乎",
    "完全",
}

SEVERE_AI_SMELL_TYPES = {
    "template_phrase",
    "enumeration_voice",
    "outline_like",
    "repeated_starter",
    "repeated_sentence_opener",
    "throat_clearing",
    "heading_monotony",
    "author_phrase",
    "author_starter",
    "prompt_leak",
}
BLUEPRINT_EXTRA_TEXT_FIELDS = [
    "article_archetype",
    "primary_interaction_goal",
    "secondary_interaction_goal",
    "interaction_formula",
    "peak_moment_design",
    "ending_interaction_design",
]

ARCHETYPE_KEYWORDS: dict[str, list[str]] = {
    "tutorial": ["教程", "指南", "手把手", "实操", "上手", "怎么做", "如何", "方法", "SOP", "清单", "流程", "模板"],
    "case-study": ["案例", "复盘", "拆解", "公司", "项目", "产品", "团队", "人物", "故事"],
    "narrative": ["故事", "经历", "焦虑", "关系", "成长", "生活", "日常", "情绪", "家庭", "职场"],
    "commentary": ["为什么", "真相", "趋势", "误区", "判断", "拐点", "变现", "竞争", "机会", "风险", "信号"],
}

ARCHETYPE_PROFILES: dict[str, dict[str, Any]] = {
    "commentary": {
        "label": "分析评论",
        "persuasion_strategies": ["反常识判断", "趋势拆解", "案例或数据支撑", "对比论证"],
        "argument_modes": ["对比", "拆解", "案例", "趋势"],
        "emotion_curve": [
            {"stage": "开头", "emotion": "悬念", "goal": "把读者带进正在发生的变化"},
            {"stage": "中段", "emotion": "识别", "goal": "讲清被误读的地方"},
            {"stage": "后段", "emotion": "判断", "goal": "给出比信息更重要的视角"},
            {"stage": "结尾", "emotion": "余味", "goal": "留下值得复述的判断"},
        ],
        "emotion_layers": ["警觉层", "理解层", "判断层", "余味层"],
        "style_traits": ["具体场景起笔", "判断克制", "证据穿插", "少自我解释", "段落有呼吸"],
        "pain_points": [
            "读者最容易被热闹牵着走，却忽略真正决定结果的那层变化。",
            "很多文章信息很多，但判断很少，读完之后什么都带不走。",
            "一旦只盯表面信号，就会在关键分水岭上慢半拍。",
        ],
        "emotion_value_goals": ["让读者觉得被点醒", "让读者获得新判断", "让读者愿意转发给同类人"],
        "opening_modes": ["场景切口", "反差判断", "新闻切口"],
        "ending_modes": ["判断收束", "余味回扣", "风险提醒"],
        "voice_guardrails": ["少自我解释", "少模板连接词", "别把文章写成讲义", "让判断落在具体事实上"],
        "avoid_patterns": ["先说结论", "接下来我会", "最后给你一个可执行清单", "如果你只想记住一句话"],
        "like_triggers": ["文末判断升华", "可截图金句", "让人点头的认知拨云见日"],
        "comment_triggers": ["给出可站队的判断", "抛出一个真实会分歧的问题", "让读者忍不住补充自己的经验"],
        "share_triggers": ["提供比热点更深一层的谈资", "帮读者表达身份与价值观", "用一句判断替读者完成表态"],
        "social_currency_points": ["一个能在聊天里复述的新判断", "一个值得拿去解释热点的视角"],
        "identity_labels": ["行业观察者", "普通用户", "同类决策者"],
        "controversy_anchors": ["不要中性总结，要给一个可以被讨论甚至被反驳的靶子", "关键判断要让支持者愿意附和，反对者愿意开口"],
        "interaction_prompts": ["如果是你，你会怎么判断？", "你更认同哪一边？"],
        "primary_interaction_goal": "comment/share",
        "secondary_interaction_goal": "like",
        "interaction_formula": "点赞靠文末升华和金句，评论靠鲜明判断与提问，转发靠谈资和身份认同。",
        "peak_moment_design": "中段安排一次反常识判断或趋势反转，让读者想停下来划线或转发。",
        "ending_interaction_design": "结尾先收束判断，再留一个能让读者站队或补充经验的问题。",
        "default_sections": [
            {"heading": "大家真正误判了什么", "goal": "先把被忽略的信号说透", "evidence_need": "新闻、案例或现象对比"},
            {"heading": "真正拉开差距的分水岭", "goal": "提出主判断并拆解逻辑", "evidence_need": "数据、案例或结构拆解"},
            {"heading": "这会怎样改写接下来的结果", "goal": "把趋势和代价讲明白", "evidence_need": "对比、风险或机会"},
            {"heading": "最后的判断", "goal": "收束全文并留下可复述观点", "evidence_need": "一句有记忆点的判断"},
        ],
    },
    "tutorial": {
        "label": "方法指南",
        "persuasion_strategies": ["误区澄清", "步骤拆解", "案例支撑", "关键提醒"],
        "argument_modes": ["拆解", "步骤", "案例", "提醒"],
        "emotion_curve": [
            {"stage": "开头", "emotion": "卡点共鸣", "goal": "说出读者为什么总是做不顺"},
            {"stage": "中段", "emotion": "掌控感", "goal": "把关键动作拆清楚"},
            {"stage": "后段", "emotion": "确定感", "goal": "让读者知道先做什么后做什么"},
            {"stage": "结尾", "emotion": "行动", "goal": "给读者一个真的能动手的起点"},
        ],
        "emotion_layers": ["焦虑层", "理解层", "掌控层", "行动层"],
        "style_traits": ["问题先行", "步骤清楚", "提醒具体", "少官话", "用场景解释抽象动作"],
        "pain_points": [
            "很多人不是不想做，而是不知道第一步该落在哪。",
            "方法文最怕看起来全对，做起来全乱。",
            "如果关键顺序没理清，努力只会继续消耗耐心。",
        ],
        "emotion_value_goals": ["让读者觉得终于讲明白了", "让读者知道先做哪一步", "让读者愿意保存备用"],
        "opening_modes": ["卡点共鸣", "误区切口", "场景切口"],
        "ending_modes": ["行动提示", "关键提醒", "适用边界"],
        "voice_guardrails": ["讲步骤但别像说明书", "每个动作都要解释为什么", "别堆砌空泛 checklist"],
        "avoid_patterns": ["先说结论", "这篇文章将", "综上所述", "万能清单"],
        "like_triggers": ["讲清楚读者一直没弄明白的关键卡点", "在结尾给一个低门槛获得感", "把复杂动作说简单"],
        "comment_triggers": ["问读者卡在哪一步", "邀请读者补充自己的踩坑经历", "留下适用边界让读者对号入座"],
        "share_triggers": ["提供可直接转给同事/朋友的操作判断", "让读者拿去证明自己是懂门道的人", "一张可转述的方法框架"],
        "social_currency_points": ["一套比清单更值钱的判断顺序", "一个能解释为什么做不顺的卡点视角"],
        "identity_labels": ["新手", "实操者", "团队执行者"],
        "controversy_anchors": ["指出常见误区，不要假装所有做法都对", "必要时让读者在两种路径之间做选择"],
        "interaction_prompts": ["你最容易卡在哪一步？", "如果是你，你会先改哪一个动作？"],
        "primary_interaction_goal": "like/save",
        "secondary_interaction_goal": "comment",
        "interaction_formula": "点赞靠低门槛获得感，评论靠卡点提问，转发靠实用框架和圈层认同。",
        "peak_moment_design": "中段要出现一次“原来我一直做反了”的醒悟时刻。",
        "ending_interaction_design": "结尾只留一两个最关键动作，并用提问促使读者说出自己的卡点。",
        "default_sections": [
            {"heading": "先别急着上手，真正的卡点在这里", "goal": "先拆误区和卡点", "evidence_need": "场景或失败案例"},
            {"heading": "把顺序理清，事情就简单了", "goal": "给出关键步骤和先后关系", "evidence_need": "步骤、示例或操作说明"},
            {"heading": "最容易做错的几个地方", "goal": "提前讲清边界和风险", "evidence_need": "反例或注意事项"},
            {"heading": "最后只记住这一个动作", "goal": "收束到最关键的一步", "evidence_need": "一句简短提醒"},
        ],
    },
    "case-study": {
        "label": "案例拆解",
        "persuasion_strategies": ["案例复盘", "对比论证", "结果回看", "可迁移判断"],
        "argument_modes": ["案例", "对比", "拆解", "判断"],
        "emotion_curve": [
            {"stage": "开头", "emotion": "代入", "goal": "把读者带进具体场景"},
            {"stage": "中段", "emotion": "理解", "goal": "讲清事情怎么一步步变化"},
            {"stage": "后段", "emotion": "醒悟", "goal": "指出案例真正说明了什么"},
            {"stage": "结尾", "emotion": "带走判断", "goal": "把个案提升为通用洞察"},
        ],
        "emotion_layers": ["代入层", "理解层", "醒悟层", "判断层"],
        "style_traits": ["案例开路", "细节说话", "判断后置", "少空话", "用结果反推过程"],
        "pain_points": [
            "读者常常看过案例，却没看懂案例真正说明了什么。",
            "复盘一旦只剩过程罗列，就很难长出真正可迁移的判断。",
            "最可惜的不是没看见案例，而是只看见热闹没有看见方法。",
        ],
        "emotion_value_goals": ["让读者觉得案例真的有启发", "让读者带走一层更稳的判断", "让读者愿意转给同类同行"],
        "opening_modes": ["人物/场景切口", "结果倒叙", "关键细节起笔"],
        "ending_modes": ["判断回扣", "迁移建议", "风险提醒"],
        "voice_guardrails": ["别把案例写成流水账", "先抓关键细节再下判断", "避免硬凑 checklist"],
        "avoid_patterns": ["先说结论", "第一第二第三机械平铺", "最后给你一个清单"],
        "like_triggers": ["案例细节说到位", "关键判断说得准", "结尾有一记回扣"],
        "comment_triggers": ["让读者站队案例中的关键选择", "让同行补充自己的经历", "指出一个容易争论的决策点"],
        "share_triggers": ["提供可转述的案例洞察", "帮助读者表达自己所属圈层的判断", "给同行一个拿得出手的复盘视角"],
        "social_currency_points": ["一个比案例本身更值得讲的判断", "一个可以迁移到别处的方法"],
        "identity_labels": ["同行", "操盘者", "案例复盘者"],
        "controversy_anchors": ["指出案例里最值得争议的一步", "不要只讲过程，要敢讲谁做对了谁做错了"],
        "interaction_prompts": ["如果换成你，会在哪一步做不同选择？", "你见过更典型的类似案例吗？"],
        "primary_interaction_goal": "share/comment",
        "secondary_interaction_goal": "like",
        "interaction_formula": "点赞靠细节与判断，评论靠站队与复盘欲，转发靠同行谈资和方法迁移。",
        "peak_moment_design": "案例中段要有一个让读者情绪抬起来的关键转折或失误点。",
        "ending_interaction_design": "结尾把个案抬升成通用判断，并留一个让同行想补充经历的问题。",
        "default_sections": [
            {"heading": "事情是怎么开始变味的", "goal": "给读者一个能代入的场景", "evidence_need": "案例细节"},
            {"heading": "真正的分水岭出现在这里", "goal": "拆解案例中的关键决策点", "evidence_need": "过程或对比"},
            {"heading": "这个案例真正说明了什么", "goal": "把个案提炼成通用判断", "evidence_need": "对照或总结"},
            {"heading": "把这个判断带回你自己的处境", "goal": "收束并完成迁移", "evidence_need": "场景映射"},
        ],
    },
    "narrative": {
        "label": "叙事观察",
        "persuasion_strategies": ["场景代入", "情绪递进", "反差回看", "判断点题"],
        "argument_modes": ["场景", "对比", "判断"],
        "emotion_curve": [
            {"stage": "开头", "emotion": "代入", "goal": "让读者感觉这就是自己会遇到的场景"},
            {"stage": "中段", "emotion": "共鸣", "goal": "把表面情绪背后的原因讲出来"},
            {"stage": "后段", "emotion": "松动", "goal": "给读者一个重新理解自己的角度"},
            {"stage": "结尾", "emotion": "余温", "goal": "留下不生硬的回响"},
        ],
        "emotion_layers": ["代入层", "共鸣层", "理解层", "余温层"],
        "style_traits": ["具体细节起笔", "少口号", "对话感", "句式有长短落差", "判断别喊出来"],
        "pain_points": [
            "很多人真正难受的，不是问题本身，而是一直没人把那种感受说清楚。",
            "越是贴身的问题，越怕被写成一篇正确但没有温度的稿子。",
            "读者要的不是说教，而是被看见之后再被轻轻推一把。",
        ],
        "emotion_value_goals": ["让读者觉得被理解", "让读者放下自责", "让读者愿意收藏给以后看"],
        "opening_modes": ["场景切口", "人物细节", "一句不响亮但刺心的话"],
        "ending_modes": ["轻回扣", "余味", "温和提醒"],
        "voice_guardrails": ["少大词", "少立刻下定义", "少做教练式发号施令"],
        "avoid_patterns": ["先说结论", "最后给你一个可执行清单", "鸡汤式鼓励"],
        "like_triggers": ["一句替读者说中心事的话", "结尾温柔但不廉价的回扣", "细节共鸣"],
        "comment_triggers": ["问一个和读者经历直接相关的问题", "让读者补充自己的类似瞬间", "让读者表达站在谁的处境里"],
        "share_triggers": ["替读者完成情绪表达", "让读者借文章表达‘这就是我’", "贴上圈层身份标签"],
        "social_currency_points": ["一段能代表读者心声的表述", "一个能让人转给同类人的处境判断"],
        "identity_labels": ["打工人", "父母", "伴侣", "同类处境中的人"],
        "controversy_anchors": ["不用强行制造对立，但可以给出让人想回应的价值判断", "让读者觉得自己的立场被看见"],
        "interaction_prompts": ["你有没有过类似的瞬间？", "如果是你，你会怎么理解这件事？"],
        "primary_interaction_goal": "like/comment",
        "secondary_interaction_goal": "share",
        "interaction_formula": "点赞靠被说中，评论靠补充经历，转发靠替读者表达‘我是谁’。",
        "peak_moment_design": "中段安排一次情绪爆点或被说中的瞬间，让读者想停下来截图。",
        "ending_interaction_design": "结尾轻回扣全文情绪，再留一个与读者自身经历直接相关的问题。",
        "default_sections": [
            {"heading": "那个让人一下子沉下去的瞬间", "goal": "建立代入感", "evidence_need": "具体场景或细节"},
            {"heading": "真正让人难受的，不是表面那件事", "goal": "把情绪背后的原因讲出来", "evidence_need": "对比或经历"},
            {"heading": "当你换个角度看，很多事会开始松动", "goal": "给读者新的理解方式", "evidence_need": "判断或故事回看"},
            {"heading": "最后留给你一句不那么生硬的话", "goal": "收束而不过度说教", "evidence_need": "一句带余温的判断"},
        ],
    },
}


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for raw in values:
        value = re.sub(r"\s+", " ", str(raw or "")).strip(" -•\n\t")
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _ensure_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if not text:
        return ""
    if text[-1] not in "。！？!?；;":
        text += "。"
    return text


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return _dedupe([str(item) for item in value])
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if "\n" in raw:
            parts = []
            for line in raw.splitlines():
                cleaned = re.sub(r"^[\-\*\d\.、\s]+", "", line).strip()
                if cleaned:
                    parts.append(cleaned)
            return _dedupe(parts)
        parts = [item.strip() for item in re.split(r"[；;。]\s*", raw) if item.strip()]
        return _dedupe(parts)
    return []


def _first_paragraphs(body: str, limit: int = 2) -> list[str]:
    paragraphs = []
    for block in legacy.list_paragraphs(body):
        if block.startswith("#"):
            continue
        paragraphs.append(block)
        if len(paragraphs) >= limit:
            break
    return paragraphs


def _clean_sentence(sentence: str) -> str:
    text = re.sub(r"^[-*>\d\.\s]+", "", sentence or "").strip()
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _section_heading_for_offset(body: str, sentence: str) -> str:
    current = "导语"
    for block in body.splitlines():
        line = block.strip()
        if re.match(r"^#{2,4}\s+", line):
            current = re.sub(r"^#{2,4}\s+", "", line).strip()
        if sentence[:12] and sentence[:12] in line:
            return current
    return current


def _sentence_objects(body: str, sentences: list[str], reason: str) -> list[dict[str, Any]]:
    payload = []
    for index, sentence in enumerate(_dedupe(sentences), start=1):
        cleaned = _ensure_sentence(_clean_sentence(sentence))
        if not cleaned:
            continue
        strength = min(1.0, round((legacy.cjk_len(cleaned) / 28), 2))
        payload.append(
            {
                "text": cleaned,
                "section_heading": _section_heading_for_offset(body, cleaned),
                "reason": reason,
                "strength": max(0.2, strength),
                "rank": index,
            }
        )
    return payload


def infer_article_archetype(*, topic: str, title: str, angle: str, research: dict[str, Any] | None = None) -> str:
    research = research or {}
    corpus = " ".join(
        [
            str(topic or ""),
            str(title or ""),
            str(angle or ""),
            " ".join(str(item or "") for item in research.get("information_gaps") or []),
            " ".join(str(item or "") for item in research.get("evidence_items") or []),
        ]
    )
    scores: dict[str, int] = {}
    for archetype, keywords in ARCHETYPE_KEYWORDS.items():
        scores[archetype] = sum(1 for keyword in keywords if keyword and keyword in corpus)
    if scores.get("tutorial", 0) >= 2:
        return "tutorial"
    if scores.get("case-study", 0) >= 2:
        return "case-study"
    if scores.get("narrative", 0) >= 2 and scores.get("tutorial", 0) == 0:
        return "narrative"
    if scores.get("commentary", 0) >= 1:
        return "commentary"
    return "commentary"


def archetype_profile(*, topic: str, title: str, angle: str, research: dict[str, Any] | None = None) -> dict[str, Any]:
    archetype = infer_article_archetype(topic=topic, title=title, angle=angle, research=research)
    return {"article_archetype": archetype, **ARCHETYPE_PROFILES.get(archetype, ARCHETYPE_PROFILES["commentary"])}


def default_outline_sections(archetype: str) -> list[dict[str, str]]:
    profile = ARCHETYPE_PROFILES.get(archetype, ARCHETYPE_PROFILES["commentary"])
    return json.loads(json.dumps(profile.get("default_sections") or ARCHETYPE_PROFILES["commentary"]["default_sections"], ensure_ascii=False))


def default_viral_blueprint(
    *,
    topic: str,
    title: str,
    angle: str,
    audience: str,
    research: dict[str, Any] | None = None,
    style_signals: list[str] | None = None,
) -> dict[str, Any]:
    research = research or {}
    style_signals = style_signals or []
    key_phrase = angle or topic or title or "这个主题"
    audience_text = audience or "公众号读者"
    profile = archetype_profile(topic=topic, title=title, angle=angle, research=research)
    archetype = profile["article_archetype"]
    style_defaults = _dedupe([*style_signals, *profile.get("style_traits", []), "少模板连接词", "像真人编辑一样推进"])
    core_viewpoint_map = {
        "commentary": f"{key_phrase} 真正值得警惕的，不是表面的热闹变化，而是它背后那条正在改写结果的分水岭",
        "tutorial": f"{key_phrase} 最难的不是信息不够，而是顺序没理清；一旦顺序对了，动作就会一下子轻很多",
        "case-study": f"{key_phrase} 真正值得拆的，不是表面结果，而是它一路变化里那个最关键的决策点",
        "narrative": f"{key_phrase} 最让人反复卡住的，往往不是表面那件事，而是一直没人把更深一层的感受和逻辑说透",
    }
    secondary_viewpoints_map = {
        "commentary": [
            f"{audience_text} 最容易被表面信号牵着走，忽略真正起作用的底层变化",
            "一篇能被转发的分析稿，不是观点更大，而是判断更准、例子更贴、结尾更有余味",
            "真正有价值的文章，应该帮读者重新组织看问题的方式，而不是只补几条信息",
        ],
        "tutorial": [
            f"{audience_text} 不是不想做，而是常常卡在第一步就用错了力气",
            "方法文真正有用，不是因为清单多，而是它能讲清楚为什么先做这一步",
            "越是看起来简单的动作，越需要边界、顺序和反例来托住",
        ],
        "case-study": [
            "案例真正值钱的地方，不是热闹，而是它能暴露决策里的分水岭",
            "复盘如果只剩过程回放，读者带不走判断，也不会真的记住",
            "真正好的案例稿，最后一定能把个案提炼成一种看问题的方法",
        ],
        "narrative": [
            "贴身的问题一旦写成正确废话，读者会立刻划走，因为他感觉不到自己被看见",
            "真正打动人的，不是大词，而是那些被说准了的小处境和小念头",
            "好文章不会急着给答案，它会先把那种说不清的感受安顿下来",
        ],
    }
    target_quotes_map = {
        "commentary": [
            f"{key_phrase} 真正可怕的，从来不是消息本身，而是你还在拿旧判断理解新变化。",
            "一篇分析稿真正值钱的地方，不是信息密度，而是它替你省掉了多少误判。",
            "读者愿意转发的，不是正确结论，而是那个让他突然看清局势的判断。",
        ],
        "tutorial": [
            f"{key_phrase} 最怕的不是不会，而是一上来就把顺序做反了。",
            "真正能用的方法，不是步骤更多，而是关键动作更少、更准。",
            "一篇指南真正有用，不是看完点头，而是做的时候不再慌。",
        ],
        "case-study": [
            "案例真正厉害的地方，不是赢了，而是它把为什么赢讲得足够明白。",
            "复盘不是把过程再走一遍，而是把关键分水岭单独拎出来看。",
            "个案一旦能长出判断，它就不再只是个案了。",
        ],
        "narrative": [
            "很多时候，真正困住人的，不是事情本身，而是你一直不知道该怎么理解自己。",
            "被说中的感觉，往往比被安慰更重要。",
            "一篇有温度的文章，不会催你立刻改变，它会先让你不再那么孤单。",
        ],
    }
    return {
        "core_viewpoint": _ensure_sentence(core_viewpoint_map.get(archetype, core_viewpoint_map["commentary"])),
        "secondary_viewpoints": [_ensure_sentence(item) for item in secondary_viewpoints_map.get(archetype, secondary_viewpoints_map["commentary"])],
        "persuasion_strategies": list(profile.get("persuasion_strategies") or []),
        "emotion_triggers": ["怕误判", "怕做了很多却没抓到关键", "想找到更稳的判断", "想带走真正有用的东西"],
        "target_quotes": [_ensure_sentence(item) for item in target_quotes_map.get(archetype, target_quotes_map["commentary"])],
        "emotion_curve": json.loads(json.dumps(profile.get("emotion_curve") or [], ensure_ascii=False)),
        "emotion_layers": list(profile.get("emotion_layers") or []),
        "argument_modes": list(profile.get("argument_modes") or []),
        "perspective_shifts": ["读者视角", "旁观者视角", "编辑判断视角"],
        "style_traits": style_defaults[:5],
        "pain_points": [_ensure_sentence(item) for item in profile.get("pain_points") or []],
        "emotion_value_goals": list(profile.get("emotion_value_goals") or []),
        "article_archetype": archetype,
        "opening_modes": list(profile.get("opening_modes") or []),
        "ending_modes": list(profile.get("ending_modes") or []),
        "voice_guardrails": list(profile.get("voice_guardrails") or []),
        "avoid_patterns": list(profile.get("avoid_patterns") or []),
        "like_triggers": list(profile.get("like_triggers") or []),
        "comment_triggers": list(profile.get("comment_triggers") or []),
        "share_triggers": list(profile.get("share_triggers") or []),
        "social_currency_points": list(profile.get("social_currency_points") or []),
        "identity_labels": _dedupe([audience_text, *list(profile.get("identity_labels") or [])])[:5],
        "controversy_anchors": list(profile.get("controversy_anchors") or []),
        "interaction_prompts": list(profile.get("interaction_prompts") or []),
        "primary_interaction_goal": str(profile.get("primary_interaction_goal") or ""),
        "secondary_interaction_goal": str(profile.get("secondary_interaction_goal") or ""),
        "interaction_formula": str(profile.get("interaction_formula") or "高互动文章 = 情绪价值 + 社交货币 + 峰终体验"),
        "peak_moment_design": str(profile.get("peak_moment_design") or ""),
        "ending_interaction_design": str(profile.get("ending_interaction_design") or ""),
    }


def blueprint_complete(blueprint: dict[str, Any] | None) -> bool:
    if not blueprint:
        return False
    for field in VIRAL_BLUEPRINT_FIELDS:
        value = blueprint.get(field)
        if isinstance(value, str):
            if not value.strip():
                return False
        elif isinstance(value, list):
            if not any(str(item).strip() for item in value):
                return False
        else:
            return False
    return True


def normalize_viral_blueprint(payload: Any, context: dict[str, Any]) -> dict[str, Any]:
    base = default_viral_blueprint(
        topic=str(context.get("topic") or context.get("selected_title") or context.get("title") or ""),
        title=str(context.get("selected_title") or context.get("title") or context.get("topic") or ""),
        angle=str(context.get("direction") or context.get("angle") or ""),
        audience=str(context.get("audience") or "大众读者"),
        research=context.get("research") or {},
        style_signals=context.get("style_signals") or [],
    )
    if isinstance(payload, dict):
        source = payload
    else:
        source = {}
    merged = dict(base)
    for field in VIRAL_BLUEPRINT_FIELDS:
        if field not in source:
            continue
        if isinstance(base[field], str):
            text = str(source.get(field) or "").strip()
            if text:
                merged[field] = _ensure_sentence(text)
        else:
            items = _normalize_list(source.get(field))
            if items:
                if field == "emotion_curve":
                    merged[field] = [
                        {"stage": f"阶段 {index}", "emotion": item, "goal": item}
                        for index, item in enumerate(items, start=1)
                    ]
                else:
                    merged[field] = [_ensure_sentence(item) if field in {"secondary_viewpoints", "target_quotes", "pain_points"} else item for item in items]
    curve = source.get("emotion_curve")
    if isinstance(curve, list) and curve:
        normalized_curve = []
        for entry in curve:
            if isinstance(entry, dict):
                stage = str(entry.get("stage") or entry.get("section") or entry.get("phase") or "").strip() or f"阶段 {len(normalized_curve) + 1}"
                emotion = str(entry.get("emotion") or entry.get("feeling") or entry.get("value") or "").strip() or stage
                goal = str(entry.get("goal") or entry.get("purpose") or emotion).strip() or emotion
                normalized_curve.append({"stage": stage, "emotion": emotion, "goal": goal})
            else:
                text = str(entry).strip()
                if text:
                    normalized_curve.append({"stage": f"阶段 {len(normalized_curve) + 1}", "emotion": text, "goal": text})
        if normalized_curve:
            merged["emotion_curve"] = normalized_curve
    for field in BLUEPRINT_EXTRA_LIST_FIELDS:
        items = _normalize_list(source.get(field))
        if items:
            merged[field] = items[:6]
    for field in BLUEPRINT_EXTRA_TEXT_FIELDS:
        text = str(source.get(field) or "").strip()
        if text:
            merged[field] = text
    return merged


def normalize_outline_payload(payload: Any, context: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        output = dict(payload)
    else:
        output = {}
    title = str(output.get("title") or context.get("selected_title") or context.get("title") or context.get("topic") or "未命名标题")
    angle = str(output.get("angle") or context.get("direction") or context.get("angle") or "")
    sections = output.get("sections")
    profile = archetype_profile(
        topic=str(context.get("topic") or output.get("title") or ""),
        title=str(context.get("selected_title") or output.get("title") or ""),
        angle=str(context.get("direction") or output.get("angle") or ""),
        research=context.get("research") or {},
    )
    normalized_sections: list[dict[str, Any]] = []
    if isinstance(sections, list):
        for item in sections:
            if isinstance(item, dict):
                heading = str(item.get("heading") or item.get("title") or "").strip()
                if not heading:
                    continue
                normalized_sections.append(
                    {
                        "heading": heading,
                        "goal": str(item.get("goal") or item.get("purpose") or "展开该章节").strip(),
                        "evidence_need": str(item.get("evidence_need") or item.get("evidence") or "补充案例或事实支撑").strip(),
                    }
                )
            else:
                heading = str(item or "").strip()
                if heading:
                    normalized_sections.append({"heading": heading, "goal": "展开该章节", "evidence_need": "补充案例或事实支撑"})
    if not normalized_sections:
        normalized_sections = default_outline_sections(profile["article_archetype"])
    output["title"] = title
    output["angle"] = angle
    output["sections"] = normalized_sections
    output["viral_blueprint"] = normalize_viral_blueprint(output.get("viral_blueprint"), context | {"selected_title": title, "angle": angle})
    output["editorial_blueprint"] = normalize_editorial_blueprint(
        output.get("editorial_blueprint") or context.get("editorial_blueprint"),
        context
        | {
            "topic": str(context.get("topic") or title),
            "selected_title": title,
            "title": title,
            "direction": angle,
            "article_archetype": output["viral_blueprint"].get("article_archetype") or profile["article_archetype"],
        },
    )
    author_memory = context.get("author_memory") or {}
    output.setdefault("article_archetype", output["viral_blueprint"].get("article_archetype") or profile["article_archetype"])
    output.setdefault("opening_mode", (output["viral_blueprint"].get("opening_modes") or profile.get("opening_modes") or ["场景切口"])[0])
    output.setdefault("ending_mode", (output["viral_blueprint"].get("ending_modes") or profile.get("ending_modes") or ["判断收束"])[0])
    output.setdefault("voice_guardrails", output["viral_blueprint"].get("voice_guardrails") or profile.get("voice_guardrails") or [])
    output.setdefault("avoid_patterns", output["viral_blueprint"].get("avoid_patterns") or profile.get("avoid_patterns") or [])
    output.setdefault("interaction_formula", output["viral_blueprint"].get("interaction_formula") or profile.get("interaction_formula") or "")
    output.setdefault("peak_moment_design", output["viral_blueprint"].get("peak_moment_design") or profile.get("peak_moment_design") or "")
    output.setdefault("ending_interaction_design", output["viral_blueprint"].get("ending_interaction_design") or profile.get("ending_interaction_design") or "")
    output.setdefault(
        "must_have_elements",
        [
            "前 2~3 段里必须出现一个具体场景、动作或瞬间。",
            "中段必须出现一处案例、数据或事实托底。",
            "全文必须出现一处反方、误判或适用边界。",
            "至少保留一段真正展开的分析段，不要整篇卡片化。",
        ],
    )
    output.setdefault(
        "heading_variation_rule",
        "小标题至少用两种不同句法，不要整篇都是问句、整篇都是编号句，或整篇都用同一起手。",
    )
    output.setdefault(
        "paragraph_variation_rule",
        "不要让多个段落重复用“很多人 / 如果你 / 你可能 / 说白了”这类熟起手。",
    )
    output.setdefault(
        "generation_guardrails",
        _dedupe(
            _normalize_list(output.get("voice_guardrails"))
            + _normalize_list(output.get("avoid_patterns"))
            + _normalize_list(author_memory.get("playbook_summary"))
            + [f"延续这种判断方式：{item}" for item in _normalize_list((author_memory.get("editorial_preferences") or {}).get("judgment_preferences"))[:3]]
            + [f"优先使用这种证据：{item}" for item in _normalize_list((author_memory.get("editorial_preferences") or {}).get("evidence_preferences"))[:3]]
            + ([f"正文节奏偏向：{str((author_memory.get('rhythm_preferences') or {}).get('preferred_rhythm') or '').strip()}"] if str((author_memory.get("rhythm_preferences") or {}).get("preferred_rhythm") or "").strip() else [])
            + [f"避免使用：{item}" for item in _normalize_list(author_memory.get("phrase_blacklist"))[:4]]
            + [f"避免这种起手：{item}" for item in _normalize_list(author_memory.get("sentence_starters_to_avoid"))[:4]]
        )[:12],
    )
    output.setdefault(
        "preflight_checklist",
        _dedupe(
            [
                "检查是否复用了固定开头、固定结尾或固定小标题模式。",
                "检查是否出现作者记忆里明确避开的句式。",
                "检查是否有具体场景、证据托底、反方边界和展开分析段。",
                "检查段落起手是否在打转。",
                "检查小标题是否至少有两种句法。",
            ]
            + _normalize_list(author_memory.get("lesson_patterns"))
        )[:10],
    )
    return output


def _extract_signatures(body: str) -> list[str]:
    quotes = list(legacy.extract_candidate_quotes(body))
    for match in re.findall(r"\*\*(.+?)\*\*", body, flags=re.S):
        cleaned = _clean_sentence(match)
        if 10 <= legacy.cjk_len(cleaned) <= 42:
            quotes.append(cleaned)
    for block in re.findall(r"^>\s*(.+)$", body, flags=re.M):
        cleaned = _clean_sentence(block)
        if 10 <= legacy.cjk_len(cleaned) <= 42:
            quotes.append(cleaned)
    return [_ensure_sentence(item) for item in _dedupe(quotes)[:8]]


INTERACTION_IDENTITY_MARKERS = [
    "打工人", "普通人", "宝妈", "家长", "开发者", "产品经理", "运营", "创业者",
    "管理者", "学生", "北上广深", "00后", "90后", "中年人", "职场人", "创作者",
]


def _extract_comment_questions(body: str, blueprint: dict[str, Any] | None = None) -> list[str]:
    hits: list[str] = []
    for sentence in legacy.sentence_split(body):
        cleaned = _clean_sentence(sentence)
        if legacy.cjk_len(cleaned) < 8:
            continue
        if "？" in cleaned or "?" in cleaned or any(marker in cleaned for marker in ["你呢", "如果是你", "评论区", "你会怎么", "你怎么看"]):
            hits.append(cleaned)
    return _dedupe(hits)[:6]


def _extract_social_currency_points(body: str, signature_lines: list[dict[str, Any]], blueprint: dict[str, Any] | None = None) -> list[str]:
    hits: list[str] = []
    for item in signature_lines[:4]:
        text = str(item.get("text") or "").strip()
        if text:
            hits.append(text)
    for sentence in legacy.sentence_split(body):
        cleaned = _clean_sentence(sentence)
        if legacy.cjk_len(cleaned) < 12:
            continue
        if any(marker in cleaned for marker in ["真正", "误判", "信号", "分水岭", "判断", "真相", "你以为", "看起来"]):
            hits.append(cleaned)
    return _dedupe(hits)[:6]


def _extract_identity_labels(body: str, blueprint: dict[str, Any] | None = None) -> list[str]:
    labels: list[str] = []
    for marker in INTERACTION_IDENTITY_MARKERS:
        if marker in body:
            labels.append(marker)
    return _dedupe(labels)[:6]


def _extract_controversy_anchors(body: str, blueprint: dict[str, Any] | None = None) -> list[str]:
    anchors: list[str] = []
    for sentence in legacy.sentence_split(body):
        cleaned = _clean_sentence(sentence)
        if legacy.cjk_len(cleaned) < 10:
            continue
        if any(re.search(pattern, cleaned) for pattern in [r"不是.+而是", r"别再", r"大多数人", r"你以为", r"看起来.+其实", r"真正"]):
            anchors.append(cleaned)
    return _dedupe(anchors)[:6]


def _interaction_design(body: str, blueprint: dict[str, Any] | None, signature_lines: list[dict[str, Any]]) -> dict[str, Any]:
    body = body or ""
    paragraphs = [block.strip() for block in legacy.list_paragraphs(body) if block.strip()]
    ending_blocks = paragraphs[-2:] if paragraphs else []
    ending_snapshot = " ".join(ending_blocks)
    like_triggers = _dedupe([item.get("text") or "" for item in signature_lines[:3]] + ([ending_blocks[-1]] if ending_blocks else []))[:6]
    comment_triggers = _extract_comment_questions(body, blueprint)
    share_triggers = _extract_social_currency_points(body, signature_lines, blueprint)[:6]
    social_currency_points = _extract_social_currency_points(body, signature_lines, blueprint)
    identity_labels = _extract_identity_labels(body, blueprint)
    controversy_anchors = _extract_controversy_anchors(body, blueprint)
    peak_hint = str((blueprint or {}).get("peak_moment_design") or "").strip()
    if not peak_hint or peak_hint == str((blueprint or {}).get("peak_moment_design") or "").strip():
        peak_hint = signature_lines[0]["text"] if signature_lines else legacy.extract_summary(body, 80)
    ending_design = str((blueprint or {}).get("ending_interaction_design") or "").strip()
    if not ending_design or ending_design == str((blueprint or {}).get("ending_interaction_design") or "").strip():
        ending_design = ending_snapshot or "结尾需要把情绪和判断收束到最值得互动的一点上。"
    peak_end_present = bool(peak_hint and ending_snapshot)
    return {
        "like_triggers": like_triggers,
        "comment_triggers": comment_triggers,
        "share_triggers": share_triggers,
        "social_currency_points": social_currency_points,
        "identity_labels": identity_labels,
        "controversy_anchors": controversy_anchors,
        "peak_moment": peak_hint,
        "ending_interaction_design": ending_design,
        "peak_end_present": peak_end_present,
    }


def _extract_sentences_by_markers(body: str, markers: list[str], *, require_you: bool = False) -> list[str]:
    hits: list[str] = []
    clean_body = re.sub(r"^#{1,6}\s+", "", body, flags=re.M)
    for sentence in legacy.sentence_split(clean_body):
        cleaned = _clean_sentence(sentence)
        if legacy.cjk_len(cleaned) < 12:
            continue
        if require_you and "你" not in cleaned and "读者" not in cleaned:
            continue
        if any(marker in cleaned for marker in markers):
            hits.append(cleaned)
    return _dedupe(hits)


def _emotion_curve_from_body(body: str, headings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = _first_paragraphs(body, limit=3)
    curve: list[dict[str, Any]] = []
    intro = " ".join(blocks)
    if intro:
        if any(word in intro for word in PAIN_POINT_MARKERS):
            curve.append({"stage": "开头", "emotion": "刺痛", "goal": "让读者意识到问题不只是表面现象"})
        elif "?" in intro or "？" in intro or any(word in intro for word in ["为什么", "到底", "怎么会", "突然"]):
            curve.append({"stage": "开头", "emotion": "悬念", "goal": "让读者继续往下读"})
        else:
            curve.append({"stage": "开头", "emotion": "代入", "goal": "让读者先进入具体场景或处境"})
    for heading in headings[:2]:
        text = heading.get("text") or "正文"
        emotion = "理解"
        if re.search(r"方法|怎么|如何|步骤|清单", text):
            emotion = "掌控感"
        elif re.search(r"为什么|本质|真相|误区|分水岭|信号|判断", text):
            emotion = "醒悟"
        curve.append({"stage": text, "emotion": emotion, "goal": "推进认知增量"})
    if re.search(r"方法|怎么|如何|步骤|清单|SOP", body):
        curve.append({"stage": "结尾", "emotion": "行动", "goal": "让读者知道可以先从哪一步开始"})
    else:
        curve.append({"stage": "结尾", "emotion": "余味", "goal": "留下值得复述的判断或提醒"})
    return curve[:4]


def _emotion_layers(body: str) -> list[str]:
    hits = []
    for name, markers in EMOTION_LAYER_MARKERS.items():
        if any(marker in body for marker in markers):
            hits.append(name)
    return hits or ["理解层", "行动层"]


def _argument_modes(body: str, blueprint: dict[str, Any] | None = None) -> list[str]:
    text = body or ""
    modes: list[str] = []
    for name, patterns in PERSUASION_MARKERS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                modes.append(name)
                break
    if blueprint:
        modes.extend(_normalize_list(blueprint.get("argument_modes")))
        modes.extend(_normalize_list(blueprint.get("persuasion_strategies")))
    return _dedupe(modes)


def _perspective_shifts(body: str, blueprint: dict[str, Any] | None = None) -> list[str]:
    shifts: list[str] = []
    if "你" in body or "读者" in body:
        shifts.append("读者视角")
    if "我们" in body:
        shifts.append("同行/群体视角")
    if any(word in body for word in ["很多人", "大多数人", "普通人"]):
        shifts.append("旁观者视角")
    if any(word in body for word in ["编辑", "运营", "作者", "我更想提醒"]):
        shifts.append("编辑判断视角")
    if blueprint:
        shifts.extend(_normalize_list(blueprint.get("perspective_shifts")))
    return _dedupe(shifts)


def _style_traits(body: str, blueprint: dict[str, Any] | None = None) -> list[str]:
    traits: list[str] = []
    for name, patterns in STYLE_TRAIT_PATTERNS:
        if any(re.search(pattern, body) for pattern in patterns):
            traits.append(name)
    if blueprint:
        traits.extend(_normalize_list(blueprint.get("style_traits")))
    return _dedupe(traits)[:6]


def _clean_block_text(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text.strip())
    text = re.sub(r"^>\s*", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _body_paragraphs(body: str) -> list[str]:
    return [_clean_block_text(block) for block in legacy.list_paragraphs(body) if _clean_block_text(block)]


def _paragraph_start_token(paragraph: str) -> str:
    value = _clean_block_text(paragraph)
    for starter in sorted(COMMON_PARAGRAPH_STARTERS, key=len, reverse=True):
        if value.startswith(starter):
            return starter
    match = re.match(r"[\u4e00-\u9fffA-Za-z0-9]{2,6}", value)
    return (match.group(0) if match else value[:4]).strip()


def _sentence_opening_token(sentence: str) -> str:
    value = _clean_block_text(sentence)
    for starter in sorted(COMMON_SENTENCE_OPENERS, key=len, reverse=True):
        if value.startswith(starter):
            return starter
    match = re.match(r"[\u4e00-\u9fffA-Za-z0-9]{2,6}", value)
    return (match.group(0) if match else value[:4]).strip()


def _subject_tokens_from_manifest(manifest: dict[str, Any] | None) -> set[str]:
    payload = manifest or {}
    corpus = " ".join(
        [
            str(payload.get("selected_title") or ""),
            str(payload.get("title") or ""),
            str(payload.get("topic") or ""),
        ]
    )
    tokens = {item.lower() for item in re.findall(r"[\u4e00-\u9fffA-Za-z]{2,12}", corpus) if len(item.strip()) >= 2}
    return tokens


def _starter_is_subject_entity(token: str, manifest: dict[str, Any] | None) -> bool:
    compact = str(token or "").strip().lower()
    if not compact:
        return False
    for item in _subject_tokens_from_manifest(manifest):
        if compact == item or compact.startswith(item) or item.startswith(compact):
            if re.fullmatch(r"[a-z]{3,12}", compact) or re.fullmatch(r"[\u4e00-\u9fff]{2,6}", compact):
                return True
    return False


def _author_memory(manifest: dict[str, Any]) -> dict[str, Any]:
    payload = manifest.get("author_memory") or {}
    return payload if isinstance(payload, dict) else {}


def _content_enhancement(manifest: dict[str, Any]) -> dict[str, Any]:
    payload = manifest.get("content_enhancement") or {}
    return payload if isinstance(payload, dict) else {}


def _contains_scene_signal(paragraph: str) -> bool:
    value = _clean_block_text(paragraph)
    if not value:
        return False
    strong_markers = [marker for marker in SCENE_MARKERS if marker in value]
    if any(marker in value for marker in ["会议室", "办公室", "工位", "白板", "群里", "凌晨", "晚上", "中午", "那天"]):
        return True
    if any(marker in value for marker in ["这种时刻", "那种时刻", "如果你也有过", "你可能也有过", "第一次", "刚开始"]):
        return True
    if re.search(r"\d{1,2}月\d{1,2}日|\d{4}年|\d{1,2}点", value):
        return True
    if any(marker in value for marker in ["看到", "听到", "发消息", "弹出来", "刚坐下", "盯着", "回了句", "说：", "他说", "她说"]):
        return True
    return len(strong_markers) >= 2


def _contains_counterpoint_signal(paragraph: str) -> bool:
    value = _clean_block_text(paragraph)
    if not value:
        return False
    if re.search(r"不是.{1,20}而是", value) and any(word in value for word in ["问题", "关键", "真正", "误判", "边界", "判断", "风险", "难点"]):
        return True
    if re.search(r"并不.{1,20}而是", value) and any(word in value for word in ["问题", "关键", "真正", "误判", "边界", "判断", "风险", "难点"]):
        return True
    if re.search(r"不在.{1,20}而在", value):
        return True
    return any(marker in value for marker in COUNTERPOINT_MARKERS)


def _paragraph_lengths(paragraphs: list[str]) -> list[int]:
    return [legacy.cjk_len(item) for item in paragraphs if legacy.cjk_len(item) > 0]


def build_humanness_signals(body: str, manifest: dict[str, Any] | None = None, review: dict[str, Any] | None = None) -> dict[str, Any]:
    paragraphs = _body_paragraphs(body)
    paragraph_lengths = _paragraph_lengths(paragraphs)
    sentences = [sentence for sentence in legacy.sentence_split(body) if sentence.strip()]
    sentence_lengths = [legacy.cjk_len(sentence) for sentence in sentences if legacy.cjk_len(sentence) > 0]
    depth = (review or {}).get("depth_signals") or _depth_signals(body, manifest if isinstance(manifest, dict) else None)
    adverb_hits = sum(sum(item.count(word) for word in COMMON_ADVERBS) for item in paragraphs)
    total_chars = max(1, legacy.cjk_len(body))
    self_corrections = len(re.findall(r"不对[，,]|准确说|更准确地说|算了|话说回来|不过话又说回来|——", body or ""))
    paragraph_range = (max(paragraph_lengths) - min(paragraph_lengths)) if paragraph_lengths else 0
    sentence_range = (max(sentence_lengths) - min(sentence_lengths)) if sentence_lengths else 0
    style_drift = 0
    if len(paragraphs) >= 3:
        first = paragraphs[: max(1, len(paragraphs) // 2)]
        second = paragraphs[max(1, len(paragraphs) // 2) :]
        first_you = sum(item.count("你") + item.count("我们") for item in first)
        second_you = sum(item.count("你") + item.count("我们") for item in second)
        first_data = sum(len(re.findall(r"\d{4}年|\d+(?:\.\d+)?%|\[\d+\]", item)) for item in first)
        second_data = sum(len(re.findall(r"\d{4}年|\d+(?:\.\d+)?%|\[\d+\]", item)) for item in second)
        if abs(first_you - second_you) >= 2 or abs(first_data - second_data) >= 2:
            style_drift = 1
    risk_findings = []
    if sentence_range < 12 and len(sentences) >= 5:
        risk_findings.append("句长波动偏小，容易显得太齐。")
    if paragraph_range < 28 and len(paragraphs) >= 5:
        risk_findings.append("段落长度过于整齐。")
    if adverb_hits / total_chars > 0.035:
        risk_findings.append("副词密度偏高。")
    if depth.get("outline_like"):
        risk_findings.append("段落像提纲拼接。")
    if depth.get("repeated_starter_count", 0) >= 2 or depth.get("repeated_sentence_opener_count", 0) >= 2:
        risk_findings.append("起手重复，容易暴露模板腔。")
    return {
        "sentence_length_range": sentence_range,
        "paragraph_length_range": paragraph_range,
        "adverb_density": round(adverb_hits / total_chars, 4),
        "style_drift_detected": bool(style_drift),
        "self_correction_hits": self_corrections,
        "scene_anchor_count": int(depth.get("scene_paragraph_count") or 0),
        "evidence_anchor_count": int(depth.get("evidence_paragraph_count") or 0),
        "counterpoint_anchor_count": int(depth.get("counterpoint_paragraph_count") or 0),
        "outline_like": bool(depth.get("outline_like")),
        "import_outline_risk": bool(depth.get("outline_like") and not review),
        "risk_findings": risk_findings[:6],
    }


def _humanness_score(signals: dict[str, Any], persona: dict[str, Any] | None = None) -> tuple[int, list[str]]:
    persona = persona or {}
    persona_name = str(persona.get("name") or "").strip()
    score = 6
    findings: list[str] = []
    sentence_range = int(signals.get("sentence_length_range") or 0)
    paragraph_range = int(signals.get("paragraph_length_range") or 0)
    if sentence_range >= 18:
        score += 1
    else:
        score -= 1
        findings.append("句长变化不够。")
    if paragraph_range >= 40:
        score += 1
    else:
        score -= 1
        findings.append("段落节奏过齐。")
    if float(signals.get("adverb_density") or 0) > 0.035:
        score -= 1
        findings.append("副词密度偏高。")
    if bool(signals.get("style_drift_detected")):
        score += 1
    if int(signals.get("self_correction_hits") or 0) >= 1:
        score += 1
    if bool(signals.get("outline_like")):
        score -= 2
        findings.append("正文像提纲拼接。")
    if int(signals.get("scene_anchor_count") or 0) < 1:
        score -= 1
        findings.append("缺少场景锚。")
    if int(signals.get("evidence_anchor_count") or 0) < 1:
        score -= 1
        findings.append("缺少证据锚。")
    if int(signals.get("counterpoint_anchor_count") or 0) < 1:
        score -= 1
        findings.append("缺少反方锚。")
    if persona_name == "cold-analyst" and float(signals.get("adverb_density") or 0) <= 0.035:
        score += 1
    return max(0, min(score, 10)), findings[:6]


def _persona_alignment_findings(body: str, depth: dict[str, Any], persona: dict[str, Any]) -> list[str]:
    persona_name = str((persona or {}).get("name") or "").strip()
    findings: list[str] = []
    if not persona_name:
        return findings
    if persona_name == "cold-analyst":
        if any(word in body for word in ["DNA动了", "杀疯了", "遥遥领先", "卷不动", "格局打开"]):
            findings.append("当前写法偏离了冷静研究员的人格，网络腔过重。")
    elif persona_name == "warm-editor":
        if depth.get("scene_paragraph_count", 0) < 1:
            findings.append("当前写法偏离了温和编辑的人格，首屏缺少具体处境。")
    elif persona_name == "sharp-journalist":
        if depth.get("long_paragraph_count", 0) >= 3:
            findings.append("当前写法偏离了锐评记者的人格，段落过长不够利落。")
    elif persona_name == "industry-observer":
        if depth.get("evidence_paragraph_count", 0) < 1:
            findings.append("当前写法偏离了行业观察者的人格，关键判断还缺事实托底。")
    return findings


def _enhancement_alignment_findings(depth: dict[str, Any], enhancement: dict[str, Any]) -> list[str]:
    if not enhancement:
        return []
    findings: list[str] = []
    sections = list(enhancement.get("section_enhancements") or [])
    if sections and depth.get("evidence_paragraph_count", 0) < 1 and any(item.get("support_quotes") or item.get("support_sources") for item in sections):
        findings.append("写前准备好的来源材料还没真正落进正文。")
    if sections and depth.get("scene_paragraph_count", 0) < 1 and any(item.get("detail_anchors") for item in sections):
        findings.append("写前规划的场景细节还没在首屏落下来。")
    if sections and depth.get("counterpoint_paragraph_count", 0) < 1 and any(item.get("counterpoint_targets") for item in sections):
        findings.append("写前规划的反方或边界提醒还没被正文消费。")
    return findings


def _ai_smell_gate_hits(findings: list[dict[str, Any]]) -> int:
    hits = 0
    for item in findings or []:
        finding_type = str(item.get("type") or "")
        if finding_type in SEVERE_AI_SMELL_TYPES:
            hits += 1
    return hits


def _heading_monotony(headings: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_clean_block_text(item.get("text") or "") for item in headings if _clean_block_text(item.get("text") or "")]
    if len(values) < 3:
        return {"monotony": False, "reason": "", "count": 0}
    pattern_keys = [heading_pattern_key(item) for item in values]
    question_like = sum(1 for item in pattern_keys if item in {"why-heading", "reader-question-heading"})
    enumerated = sum(1 for item in pattern_keys if item in {"numbered-insight", "enumerated-class"})
    starter_counts = Counter(token for token in (_paragraph_start_token(item) for item in values) if token)
    top_token, top_count = starter_counts.most_common(1)[0]
    if question_like >= max(2, len(values) - 1):
        return {"monotony": True, "reason": "小标题连续使用“为什么/问句”推进", "count": question_like}
    if enumerated >= max(2, len(values) - 1):
        return {"monotony": True, "reason": "小标题连续使用编号/枚举推进", "count": enumerated}
    if top_count >= len(values) and top_token not in {"最后", "真正", "大家"}:
        return {"monotony": True, "reason": f"小标题起手过于一致：{top_token}", "count": top_count}
    return {"monotony": False, "reason": "", "count": 0}


def _depth_signals(body: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    paragraphs = _body_paragraphs(body)
    headings = legacy.extract_headings(body)
    sentences = [sentence for sentence in legacy.sentence_split(body) if sentence.strip()]
    sentence_lengths = [legacy.cjk_len(sentence) for sentence in sentences]
    scene_paragraphs = [item for item in paragraphs if _contains_scene_signal(item)]
    detail_paragraphs = [
        item
        for item in paragraphs
        if any(marker in item for marker in DETAIL_MARKERS) or re.search(r"\d{4}年|\d+(?:\.\d+)?%|\d+倍|\[\d+\]", item)
    ]
    evidence_paragraphs = [
        item
        for item in paragraphs
        if any(marker in item for marker in EVIDENCE_MARKERS) or re.search(r"\[\d+\]|\d{4}年|\d+(?:\.\d+)?%|\d+倍", item)
    ]
    counterpoint_paragraphs = [item for item in paragraphs if _contains_counterpoint_signal(item)]
    long_paragraphs = [item for item in paragraphs if 55 <= legacy.cjk_len(item) <= 180]
    short_paragraphs = [item for item in paragraphs if legacy.cjk_len(item) <= 18]
    starters = Counter(_paragraph_start_token(item) for item in paragraphs if _paragraph_start_token(item))
    repeated_starters = [
        {"token": token, "count": count}
        for token, count in starters.most_common()
        if (((token in COMMON_PARAGRAPH_STARTERS and count >= 2) or count >= 3) and not _starter_is_subject_entity(token, context or {}))
    ]
    sentence_openers = Counter(_sentence_opening_token(item) for item in sentences if _sentence_opening_token(item))
    repeated_sentence_openers = [
        {"token": token, "count": count}
        for token, count in sentence_openers.most_common()
        if (((token in COMMON_SENTENCE_OPENERS and count >= 2) or count >= 4) and not _starter_is_subject_entity(token, context or {}))
    ]
    heading_monotony = _heading_monotony(headings)
    outline_like = len(paragraphs) >= 5 and len(short_paragraphs) >= max(3, int(len(paragraphs) * 0.45)) and len(long_paragraphs) <= 1
    sentence_range = (max(sentence_lengths) - min(sentence_lengths)) if sentence_lengths else 0
    paragraph_lengths = _paragraph_lengths(paragraphs)
    paragraph_range = (max(paragraph_lengths) - min(paragraph_lengths)) if paragraph_lengths else 0
    return {
        "paragraph_count": len(paragraphs),
        "scene_paragraph_count": len(scene_paragraphs),
        "detail_paragraph_count": len(detail_paragraphs),
        "evidence_paragraph_count": len(evidence_paragraphs),
        "counterpoint_paragraph_count": len(counterpoint_paragraphs),
        "long_paragraph_count": len(long_paragraphs),
        "short_paragraph_count": len(short_paragraphs),
        "sentence_length_range": sentence_range,
        "paragraph_length_range": paragraph_range,
        "repeated_starters": repeated_starters[:5],
        "repeated_starter_count": len(repeated_starters),
        "repeated_sentence_openers": repeated_sentence_openers[:5],
        "repeated_sentence_opener_count": len(repeated_sentence_openers),
        "heading_monotony": bool(heading_monotony.get("monotony")),
        "heading_monotony_reason": str(heading_monotony.get("reason") or ""),
        "outline_like": outline_like,
        "scene_examples": scene_paragraphs[:2],
        "evidence_examples": evidence_paragraphs[:2],
        "counterpoint_examples": counterpoint_paragraphs[:2],
        "editorial_style_hint": str(((context or {}).get("style_key") or ((context or {}).get("editorial_blueprint") or {}).get("style_key") or "")),
    }


def _prompt_leak_findings(body: str) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for phrase in PROMPT_LEAK_PATTERNS:
        hits = body.count(phrase)
        if not hits:
            continue
        findings.append({"type": "prompt_leak", "pattern": phrase, "count": hits, "evidence": f"成稿里泄漏内部提示语：{phrase}"})
    return findings


def _ai_smell_findings(body: str, manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for phrase in getattr(legacy, "AI_STYLE_PHRASES", []) or []:
        if str(phrase) in {"首先", "其次", "最后"}:
            continue
        hit_count = body.count(phrase)
        if not hit_count:
            continue
        if len(str(phrase)) <= 2 and hit_count < 2:
            continue
        findings.append({"type": "template_phrase", "pattern": phrase, "count": hit_count, "evidence": phrase})
    throat_clearing_hits = 0
    throat_clearing_labels: list[str] = []
    direct_conclusion_hits = 0
    for pattern, label in STOP_SLOP_THROAT_CLEARING_PATTERNS:
        hit_count = len(re.findall(pattern, body))
        if not hit_count:
            continue
        throat_clearing_hits += hit_count
        throat_clearing_labels.append(label)
        if label == "先说结论":
            direct_conclusion_hits += hit_count
    if throat_clearing_hits >= 2 or direct_conclusion_hits >= 1:
        findings.append(
            {
                "type": "throat_clearing",
                "pattern": "throat-clearing",
                "count": throat_clearing_hits,
                "evidence": " / ".join(dict.fromkeys(throat_clearing_labels)) or "先铺垫再说重点",
            }
        )
    binary_hits = 0
    binary_labels: list[str] = []
    for pattern, label in STOP_SLOP_BINARY_CONTRAST_PATTERNS:
        hit_count = len(re.findall(pattern, body))
        if not hit_count:
            continue
        binary_hits += hit_count
        binary_labels.append(label)
    if binary_hits >= 3:
        findings.append(
            {
                "type": "binary_contrast",
                "pattern": "not-but-chain",
                "count": binary_hits,
                "evidence": " / ".join(dict.fromkeys(binary_labels)) or "不是X，而是Y",
            }
        )
    false_agency_hits = 0
    false_agency_labels: list[str] = []
    for pattern, label in STOP_SLOP_FALSE_AGENCY_PATTERNS:
        hit_count = len(re.findall(pattern, body))
        if not hit_count:
            continue
        false_agency_hits += hit_count
        false_agency_labels.append(label)
    if false_agency_hits:
        findings.append(
            {
                "type": "false_agency",
                "pattern": "false-agency",
                "count": false_agency_hits,
                "evidence": " / ".join(dict.fromkeys(false_agency_labels)) or "让抽象概念替人行动",
            }
        )
    sentence_lengths = [legacy.cjk_len(sentence) for sentence in legacy.sentence_split(body)]
    if sentence_lengths:
        long_sentences = [length for length in sentence_lengths if length >= 55]
        if len(long_sentences) >= 3:
            findings.append({"type": "long_sentence_cluster", "pattern": "long_sentence", "count": len(long_sentences), "evidence": f"{len(long_sentences)} 个长句"})
    enumeration_hits = re.findall(r"(?:^|[。！？!?]\s*|\n\s*)(首先|其次|最后)(?:[，,:：\s])", body)
    if len(enumeration_hits) >= 2:
        findings.append({"type": "enumeration_voice", "pattern": "首先/其次/最后", "count": len(enumeration_hits), "evidence": "枚举式模板推进"})
    signals = _depth_signals(body, manifest if isinstance(manifest, dict) else None)
    if signals.get("outline_like"):
        findings.append({"type": "outline_like", "pattern": "outline_like", "count": 1, "evidence": "段落过碎，像提纲或卡片拼接"})
    repeated_starters = signals.get("repeated_starters") or []
    for sample in repeated_starters[:2]:
        if _starter_is_subject_entity(str(sample.get("token") or ""), manifest):
            continue
        findings.append(
            {
                "type": "repeated_starter",
                "pattern": str(sample.get("token") or "repeated-starter"),
                "count": int(sample.get("count") or 0),
                "evidence": f"段落起手重复：{sample.get('token')}",
            }
        )
    repeated_sentence_openers = signals.get("repeated_sentence_openers") or []
    for sample in repeated_sentence_openers[:2]:
        if _starter_is_subject_entity(str(sample.get("token") or ""), manifest):
            continue
        findings.append(
            {
                "type": "repeated_sentence_opener",
                "pattern": str(sample.get("token") or "repeated-sentence-opener"),
                "count": int(sample.get("count") or 0),
                "evidence": f"句子起手重复：{sample.get('token')}",
            }
        )
    if signals.get("heading_monotony"):
        findings.append(
            {
                "type": "heading_monotony",
                "pattern": "heading_monotony",
                "count": 1,
                "evidence": str(signals.get("heading_monotony_reason") or "小标题模式过于单一"),
            }
        )
    memory = _author_memory(manifest or {})
    for phrase in memory.get("phrase_blacklist") or []:
        compact = str(phrase or "").strip()
        hits = body.count(compact)
        if not compact or not hits:
            continue
        findings.append({"type": "author_phrase", "pattern": compact, "count": hits, "evidence": f"作者记忆明确避开：{compact}"})
    paragraphs = _body_paragraphs(body)
    for starter in memory.get("sentence_starters_to_avoid") or []:
        compact = str(starter or "").strip()
        if not compact:
            continue
        hits = sum(1 for item in paragraphs if _clean_block_text(item).startswith(compact))
        if hits:
            findings.append({"type": "author_starter", "pattern": compact, "count": hits, "evidence": f"作者记忆明确避开这种起手：{compact}"})
    findings.extend(_prompt_leak_findings(body))
    return findings


def _workspace_from_manifest(manifest: dict[str, Any]) -> Path | None:
    raw = str(manifest.get("workspace") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def _recent_corpus_articles(manifest: dict[str, Any], limit: int = 20) -> list[Path]:
    roots_raw = manifest.get("corpus_roots")
    roots: list[Path] = []
    if isinstance(roots_raw, list):
        for raw in roots_raw:
            item = str(raw or "").strip()
            if item:
                roots.append(Path(item))
    if not roots:
        root_raw = str(manifest.get("corpus_root") or "").strip()
        if root_raw:
            roots.append(Path(root_raw))
    if not roots:
        return []
    current_workspace = _workspace_from_manifest(manifest)
    items: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("article.md"):
            resolved = path.resolve()
            if current_workspace and current_workspace.resolve() in resolved.parents:
                continue
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            items.append(resolved)
    items.sort(key=lambda item: item.stat().st_mtime if item.exists() else 0, reverse=True)
    return items[:limit]


def _normalize_similarity_text(text: str) -> str:
    value = re.sub(r"https?://[^\s)>\]]+", " ", text or "")
    value = re.sub(r"\[[^\]]+\]\([^)]+\)", " ", value)
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "", value).lower()
    return value


def _char_ngrams(text: str, n: int = 4) -> set[str]:
    normalized = _normalize_similarity_text(text)
    if len(normalized) <= n:
        return {normalized} if normalized else set()
    return {normalized[index : index + n] for index in range(len(normalized) - n + 1)}


def _jaccard_similarity(left: str, right: str) -> float:
    left_set = _char_ngrams(left)
    right_set = _char_ngrams(right)
    if not left_set or not right_set:
        return 0.0
    return round(len(left_set & right_set) / max(1, len(left_set | right_set)), 3)


def _template_findings(title: str, body: str, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    memory = _author_memory(manifest)
    phrases = list(
        dict.fromkeys(
            [
                *KNOWN_TEMPLATE_PHRASES,
                *list(manifest.get("recent_phrase_blacklist") or []),
                *list(memory.get("phrase_blacklist") or []),
            ]
        )
    )
    findings: list[dict[str, Any]] = []
    for phrase in phrases:
        compact = str(phrase or "").strip()
        if not compact:
            continue
        hits = body.count(compact)
        if hits:
            findings.append({"pattern": compact, "count": hits, "evidence": compact})
    summary = manifest.get("recent_corpus_summary") or {}
    if isinstance(summary, dict):
        title_pattern = title_template_key(title or manifest.get("selected_title") or "")
        paragraphs = _body_paragraphs(body)
        opening_patterns = [opening_pattern_key(item) for item in paragraphs[:2] if opening_pattern_key(item) not in {"none", "generic"}]
        ending_pattern = ending_pattern_key(paragraphs[-1]) if paragraphs else "none"
        heading_patterns = [
            heading_pattern_key(item.get("text") or "")
            for item in legacy.extract_headings(body)[:6]
            if heading_pattern_key(item.get("text") or "") not in {"none", "generic"}
        ]
        for item in summary.get("overused_title_patterns") or []:
            key = str(item.get("key") or "").strip()
            label = str(item.get("label") or key).strip()
            if key and key == title_pattern:
                findings.append({"pattern": f"title-pattern:{key}", "count": int(item.get("count") or 0), "evidence": label})
        for item in summary.get("overused_opening_patterns") or []:
            key = str(item.get("key") or "").strip()
            label = str(item.get("label") or key).strip()
            if key and key in opening_patterns:
                findings.append({"pattern": f"opening-pattern:{key}", "count": int(item.get("count") or 0), "evidence": label})
        for item in summary.get("overused_ending_patterns") or []:
            key = str(item.get("key") or "").strip()
            label = str(item.get("label") or key).strip()
            if key and key == ending_pattern:
                findings.append({"pattern": f"ending-pattern:{key}", "count": int(item.get("count") or 0), "evidence": label})
        for item in summary.get("overused_heading_patterns") or []:
            key = str(item.get("key") or "").strip()
            label = str(item.get("label") or key).strip()
            if key and key in heading_patterns:
                findings.append({"pattern": f"heading-pattern:{key}", "count": int(item.get("count") or 0), "evidence": label})
    for starter in memory.get("sentence_starters_to_avoid") or []:
        compact = str(starter or "").strip()
        if not compact:
            continue
        hits = sum(1 for item in _body_paragraphs(body) if _clean_block_text(item).startswith(compact))
        if hits:
            findings.append({"pattern": f"author-starter:{compact}", "count": hits, "evidence": compact})
    return findings


def _similarity_findings(title: str, body: str, manifest: dict[str, Any]) -> dict[str, Any]:
    current_intro = " ".join(_first_paragraphs(body, limit=2))
    current_end = " ".join(legacy.list_paragraphs(body)[-2:])
    current_headings = " ".join(item.get("text") or "" for item in legacy.extract_headings(body)[:6])
    similar_articles: list[dict[str, Any]] = []
    repeated_phrases = [item["pattern"] for item in _template_findings(title, body, manifest)]
    max_similarity = 0.0
    for path in _recent_corpus_articles(manifest):
        try:
            raw = legacy.read_text(path)
        except OSError:
            continue
        meta, other_body = legacy.split_frontmatter(raw)
        other_title = meta.get("title") or legacy.extract_title_from_body(other_body) or path.parent.name
        intro_score = _jaccard_similarity(current_intro, " ".join(_first_paragraphs(other_body, limit=2)))
        end_score = _jaccard_similarity(current_end, " ".join(legacy.list_paragraphs(other_body)[-2:]))
        heading_score = _jaccard_similarity(current_headings, " ".join(item.get("text") or "" for item in legacy.extract_headings(other_body)[:6]))
        body_score = _jaccard_similarity(body, other_body)
        score = max(intro_score, end_score, heading_score, body_score)
        max_similarity = max(max_similarity, score)
        if score >= 0.25:
            similar_articles.append({"title": other_title, "path": str(path.parent), "score": score})
    similar_articles.sort(key=lambda item: item["score"], reverse=True)
    return {
        "max_similarity": round(max_similarity, 3),
        "similar_articles": similar_articles[:5],
        "repeated_phrases": repeated_phrases[:10],
        "similarity_passed": max_similarity <= 0.38 and len(repeated_phrases) <= 1,
    }


def _references_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    workspace = _workspace_from_manifest(manifest)
    if workspace is None:
        return {"reference_count": 0, "items": []}
    path = workspace / str(manifest.get("references_path") or "references.json")
    payload = legacy.read_json(path, default={}) or {}
    items = payload.get("items") or []
    return {"reference_count": len(items), "items": items}


def _citation_findings(body: str, manifest: dict[str, Any]) -> dict[str, Any]:
    refs = _references_summary(manifest)
    raw_urls = re.findall(r"https?://[^\s)>\]]+", body or "")
    markers = re.findall(r"\[(\d+)\]", body or "")
    marker_ids = sorted({int(item) for item in markers if str(item).isdigit()})
    valid_ids = {int(item.get("index") or 0) for item in refs.get("items") or []}
    dangling = [item for item in marker_ids if item not in valid_ids]
    return {
        "raw_url_count": len(raw_urls),
        "inline_citation_count": len(marker_ids),
        "dangling_citations": dangling,
        "reference_count": refs["reference_count"],
        "citation_policy_passed": len(raw_urls) == 0 and not dangling,
    }


def _heuristic_editorial_review(
    title: str,
    body: str,
    review: dict[str, Any],
    template_findings: list[dict[str, Any]],
    similarity: dict[str, Any],
    citation: dict[str, Any],
) -> dict[str, Any]:
    intro = " ".join(_first_paragraphs(body, limit=2))
    depth = review.get("depth_signals") or _depth_signals(body, review.get("manifest_context") or {})
    prompt_leaks = _prompt_leak_findings(body)
    reading_desire = "high" if ("？" in intro or any(word in intro for word in ["你可能", "最近", "刷到", "某天", "为什么"]) or depth.get("scene_paragraph_count", 0) >= 1) else "medium"
    if legacy.cjk_len(intro) < 40:
        reading_desire = "low"
    if prompt_leaks:
        reading_desire = "low"
    professional_tone = "high" if len(template_findings) <= 1 and not depth.get("outline_like") else "medium"
    novelty = "high" if any(word in body for word in ["误判", "分水岭", "真相", "被忽略", "拐点"]) and depth.get("counterpoint_paragraph_count", 0) >= 1 else "medium"
    template_risk = (
        "high"
        if len(template_findings) >= 2
        or similarity.get("max_similarity", 0) > 0.38
        or depth.get("repeated_starter_count", 0) >= 2
        or depth.get("repeated_sentence_opener_count", 0) >= 2
        or depth.get("heading_monotony")
        or bool(prompt_leaks)
        else "medium" if template_findings else "low"
    )
    citation_restraint = "high" if citation.get("raw_url_count", 0) == 0 else "low"
    ending = " ".join(legacy.list_paragraphs(body)[-2:])
    ending_naturalness = "high" if ending and not re.search(r"最后给你一个可执行清单|如果你只想记住一句话", ending) else "low"
    interaction_naturalness = "high" if re.search(r"(如果是你|你会怎么|你更认同|欢迎留言|评论区)", ending) else "low"
    return {
        "reading_desire": reading_desire,
        "professional_tone": professional_tone,
        "novelty_of_viewpoint": novelty,
        "template_risk": template_risk,
        "citation_restraint": citation_restraint,
        "ending_naturalness": ending_naturalness,
        "interaction_naturalness": interaction_naturalness,
        "summary": "高分稿必须让人想读下去、像专业编辑写的，并且不靠套路完成互动设计。",
    }


def build_heuristic_review(
    title: str,
    body: str,
    manifest: dict[str, Any],
    *,
    blueprint: dict[str, Any] | None = None,
    revision_round: int = 1,
    review_source: str = "heuristic",
    confidence: float = 0.58,
) -> dict[str, Any]:
    body = legacy.strip_image_directives(body)
    headings = legacy.extract_headings(body)
    intro = " ".join(_first_paragraphs(body, limit=2))
    blueprint = normalize_viral_blueprint(
        blueprint or manifest.get("viral_blueprint"),
        {
            "topic": manifest.get("topic") or title,
            "selected_title": title,
            "direction": manifest.get("direction") or "",
            "audience": manifest.get("audience") or "大众读者",
            "research": {},
            "style_signals": manifest.get("style_signals") or [],
        },
    )
    core_viewpoint = _ensure_sentence(
        blueprint.get("core_viewpoint")
        or intro
        or f"{title} 真正要说明的，是别再被表面信息带着跑，而要抓住真正决定结果的动作"
    )
    secondary_viewpoints = _dedupe(
        [_ensure_sentence(item) for item in _normalize_list(blueprint.get("secondary_viewpoints"))]
        + [_ensure_sentence(re.sub(r"[#*]", "", item.get("text") or "")) for item in headings[:3]]
    )[:4]
    argument_modes = _argument_modes(body, blueprint)
    emotion_value_sentences = _sentence_objects(body, _extract_sentences_by_markers(body, EMOTION_VALUE_MARKERS, require_you=True), "给读者情绪价值")
    pain_point_sentences = _sentence_objects(body, _extract_sentences_by_markers(body, PAIN_POINT_MARKERS), "刺痛读者处境")
    signature_lines = _sentence_objects(body, _extract_signatures(body), "可截图传播")
    ai_smell_findings = _ai_smell_findings(body, manifest)
    template_findings = _template_findings(title, body, manifest)
    perspective_shifts = _perspective_shifts(body, blueprint)
    emotion_curve = _emotion_curve_from_body(body, headings)
    emotion_layers = _emotion_layers(body)
    style_traits = _style_traits(body, blueprint)
    depth_signals = _depth_signals(
        body,
        {
            "selected_title": title,
            "topic": manifest.get("topic") or title,
            "title": title,
            "viral_blueprint": blueprint,
            "editorial_blueprint": manifest.get("editorial_blueprint") or {},
        },
    )
    humanness_signals = build_humanness_signals(body, manifest, {"depth_signals": depth_signals})
    humanness_score, humanness_findings = _humanness_score(humanness_signals, manifest.get("writing_persona") or {})
    enhancement_findings = _enhancement_alignment_findings(depth_signals, _content_enhancement(manifest))
    persona_findings = _persona_alignment_findings(body, depth_signals, manifest.get("writing_persona") or {})
    interaction_design = _interaction_design(body, blueprint, signature_lines)
    similarity_findings = _similarity_findings(title, body, manifest)
    citation_findings = _citation_findings(body, manifest)
    strengths: list[str] = []
    issues: list[str] = []
    if len(signature_lines) >= SIGNATURE_LINE_THRESHOLD:
        strengths.append("文中已有可截图传播的金句密度。")
    else:
        issues.append("金句和传播句密度不够，缺少能单独流通的判断句。")
    if len(emotion_value_sentences) >= EMOTION_VALUE_THRESHOLD:
        strengths.append("文章能给读者明确的理解感和被安顿感。")
    else:
        issues.append("情绪价值不足，读者容易只看到信息，看不到被理解。")
    if len(pain_point_sentences) >= PAIN_POINT_THRESHOLD:
        strengths.append("文章能刺到读者真实处境，具备停留点。")
    else:
        issues.append("刺痛句不足，开头和中段还不够扎心。")
    if len(argument_modes) >= ARGUMENT_MODE_THRESHOLD:
        strengths.append("论证方式不是单一说教，具备拆解与对比。")
    else:
        issues.append("论证方式偏单一，需要补案例、对比或步骤。")
    if depth_signals.get("scene_paragraph_count", 0) >= 1 and depth_signals.get("detail_paragraph_count", 0) >= 2:
        strengths.append("文中有具体现场和细节，读者更容易代入。")
    else:
        issues.append("缺少能让人看见画面的现场和细节，读起来更像观点提纲。")
    if depth_signals.get("evidence_paragraph_count", 0) >= 2:
        strengths.append("关键判断有事实、案例或数字托底，不容易飘。")
    else:
        issues.append("事实、案例或数字支撑偏少，文章容易只剩态度没有抓手。")
    if depth_signals.get("counterpoint_paragraph_count", 0) >= 1:
        strengths.append("文章有反方、误判或边界讨论，层次更完整。")
    else:
        issues.append("缺少反方、误判或适用边界，整篇容易显得单向输出。")
    if not depth_signals.get("outline_like"):
        strengths.append("段落不是纯卡片式罗列，正文展开感还在。")
    else:
        issues.append("段落过碎，像提纲拼接，缺少真正展开后的分析段。")
    if len(interaction_design.get("comment_triggers") or []) >= 1 and len(interaction_design.get("share_triggers") or []) >= 1:
        strengths.append("文章已经具备评论触发点和转发谈资。")
    else:
        issues.append("互动设计偏弱，缺少让读者想评论、想转发的明确触发点。")
    if ai_smell_findings:
        issues.append("模板化表达仍然明显，需要进一步去 AI 味。")
    else:
        strengths.append("整体语言相对自然，没有明显模板腔堆积。")
    if humanness_findings:
        issues.append("真人感还不够稳，句长、段落或锚点分布仍然偏齐。")
    else:
        strengths.append("正文在句长、段落和锚点上更接近真人写作节奏。")
    if enhancement_findings:
        issues.append("写前增强准备好的材料还没有被正文充分消费。")
    else:
        strengths.append("写前增强给出的角度、证据和边界基本被正文接住了。")
    if persona_findings:
        issues.append("正文语气和节奏还没有完全贴住这篇既定的人格。")
    elif manifest.get("writing_persona"):
        strengths.append("正文语气和节奏基本贴住了既定写作人格。")
    if depth_signals.get("repeated_starter_count", 0) >= 3:
        issues.append("段落起手反复撞在同一类句式上，读者很容易闻到 AI 味。")
    if similarity_findings.get("max_similarity", 0) > 0.42:
        issues.append("与近期已生成文章相似度过高，存在明显同质化风险。")
    if citation_findings.get("raw_url_count", 0) > 0:
        issues.append("正文仍然存在裸 URL，引用策略不符合公众号阅读体验。")
    summary = (
        f"《{title}》当前稿件已经围绕“{core_viewpoint.rstrip('。')}”展开，"
        f"但仍需重点补强{('、'.join(item.rstrip('。') for item in issues[:3])) or '传播爆点与情绪价值'}。"
    )
    revision_priorities = _dedupe(
        [
            "补开头爆点与首屏刺痛感" if len(pain_point_sentences) < PAIN_POINT_THRESHOLD else "",
            "补情绪价值句，让读者感到被理解" if len(emotion_value_sentences) < EMOTION_VALUE_THRESHOLD else "",
            "补案例/对比/步骤，提升论证多样性" if len(argument_modes) < ARGUMENT_MODE_THRESHOLD else "",
            "补金句与可截图传播句" if len(signature_lines) < SIGNATURE_LINE_THRESHOLD else "",
            "补一个具体场景和几个带画面的细节，别让正文只剩观点" if depth_signals.get("scene_paragraph_count", 0) < 1 or depth_signals.get("detail_paragraph_count", 0) < 2 else "",
            "补真实案例、数字或来源，让关键判断有托底" if depth_signals.get("evidence_paragraph_count", 0) < 2 else "",
            "补反方、误判或适用边界，别把文章写成单向宣讲" if depth_signals.get("counterpoint_paragraph_count", 0) < 1 else "",
            "重写段落节奏，至少保留一两段真正展开的分析段" if depth_signals.get("outline_like") else "",
            "清理模板连接词，继续去 AI 味" if ai_smell_findings else "",
            "把写前增强准备好的来源材料、场景细节和边界提醒真正写进正文" if enhancement_findings else "",
            "把语气、证据摆法和节奏重新拉回这篇既定的人格" if persona_findings else "",
            "打散固定开头和结尾套路，别再回到一句话结论 + 万能清单" if any("先说结论" in str(item.get("evidence") or "") or "最后给你一个可执行清单" in str(item.get("evidence") or "") for item in ai_smell_findings) else "",
            "去掉正文裸链接，把来源自然融进句子里，不要再挂 [1][2] 或文末参考资料尾卡" if citation_findings.get("raw_url_count", 0) else "",
            "重写开头和结尾，避开近期高频套路句与结构" if not similarity_findings.get("similarity_passed", True) else "",
        ]
    )
    editorial_review = _heuristic_editorial_review(title, body, {"viral_analysis": interaction_design}, template_findings, similarity_findings, citation_findings)
    return {
        "summary": summary,
        "findings": strengths + issues,
        "strengths": strengths,
        "issues": issues,
        "platform_notes": [
            "公众号正文优先短段落和有呼吸感的节奏，但不等于所有段落都要碎成判断句。",
            "不要把爆款理解成固定模板，而是要让读者被带进问题、被点醒、再带走一个更稳的判断。",
        ],
        "viral_analysis": {
            "core_viewpoint": core_viewpoint,
            "secondary_viewpoints": secondary_viewpoints[:4],
            "persuasion_strategies": _dedupe(_normalize_list(blueprint.get("persuasion_strategies")) + argument_modes)[:5],
            "emotion_triggers": _dedupe(_normalize_list(blueprint.get("emotion_triggers")) + ["怕掉队" if pain_point_sentences else "", "想找到抓手" if emotion_value_sentences else ""])[:5],
            "signature_lines": signature_lines[:6],
            "emotion_curve": emotion_curve,
            "emotion_layers": emotion_layers,
            "argument_diversity": argument_modes[:6],
            "perspective_shifts": perspective_shifts[:5],
            "style_traits": style_traits[:6],
            "like_triggers": interaction_design["like_triggers"],
            "comment_triggers": interaction_design["comment_triggers"],
            "share_triggers": interaction_design["share_triggers"],
            "social_currency_points": interaction_design["social_currency_points"],
            "identity_labels": interaction_design["identity_labels"],
            "controversy_anchors": interaction_design["controversy_anchors"],
            "peak_moment": interaction_design["peak_moment"],
            "ending_interaction_design": interaction_design["ending_interaction_design"],
        },
        "emotion_value_sentences": emotion_value_sentences[:8],
        "pain_point_sentences": pain_point_sentences[:8],
        "ai_smell_findings": ai_smell_findings,
        "template_findings": template_findings,
        "similarity_findings": similarity_findings,
        "citation_findings": citation_findings,
        "interaction_findings": interaction_design,
        "depth_signals": depth_signals,
        "humanness_signals": humanness_signals,
        "humanness_score": humanness_score,
        "humanness_findings": humanness_findings,
        "enhancement_findings": enhancement_findings,
        "persona_findings": persona_findings,
        "editorial_review": editorial_review,
        "revision_priorities": revision_priorities,
        "manifest_context": {
            "selected_title": title,
            "topic": manifest.get("topic") or title,
            "title": title,
            "viral_blueprint": blueprint,
            "editorial_blueprint": manifest.get("editorial_blueprint") or {},
            "writing_persona": manifest.get("writing_persona") or {},
        },
        "revision_round": revision_round,
        "review_source": review_source,
        "source": review_source,
        "confidence": confidence,
        "generated_at": legacy.now_iso(),
    }


def normalize_review_payload(
    payload: Any,
    *,
    title: str,
    body: str,
    manifest: dict[str, Any],
    blueprint: dict[str, Any] | None = None,
    revision_round: int = 1,
    review_source: str = "provider",
) -> dict[str, Any]:
    heuristic = build_heuristic_review(
        title,
        body,
        manifest,
        blueprint=blueprint,
        revision_round=revision_round,
        review_source=review_source,
        confidence=0.72 if review_source != "heuristic" else 0.58,
    )
    if not isinstance(payload, dict):
        return heuristic
    result = json.loads(json.dumps(heuristic, ensure_ascii=False))
    value = str(payload.get("summary") or "").strip()
    if value:
        result["summary"] = value
    findings = _normalize_list(payload.get("findings"))
    strengths = _normalize_list(payload.get("strengths"))
    issues = _normalize_list(payload.get("issues"))
    platform_notes = _normalize_list(payload.get("platform_notes"))
    if findings:
        result["findings"] = findings
    if strengths:
        result["strengths"] = strengths
    if issues:
        result["issues"] = issues
    if platform_notes:
        result["platform_notes"] = platform_notes
    provider_analysis = payload.get("viral_analysis") if isinstance(payload.get("viral_analysis"), dict) else {}
    merged_analysis = dict(result["viral_analysis"])
    for field, base_value in merged_analysis.items():
        provider_value = provider_analysis.get(field) if provider_analysis else payload.get(field)
        if isinstance(base_value, str):
            text = str(provider_value or "").strip()
            if text:
                merged_analysis[field] = _ensure_sentence(text)
        elif field == "signature_lines":
            extra = []
            if isinstance(provider_value, list):
                for item in provider_value:
                    if isinstance(item, dict):
                        extra.append(str(item.get("text") or ""))
                    else:
                        extra.append(str(item))
            merged_analysis[field] = _sentence_objects(body, extra + [item["text"] for item in base_value], "可截图传播")[:8]
        elif field == "emotion_curve":
            if isinstance(provider_value, list):
                normalized_curve = []
                for entry in provider_value:
                    if isinstance(entry, dict):
                        stage = str(entry.get("stage") or entry.get("section") or "").strip() or f"阶段 {len(normalized_curve) + 1}"
                        emotion = str(entry.get("emotion") or entry.get("value") or stage).strip()
                        goal = str(entry.get("goal") or emotion).strip()
                        normalized_curve.append({"stage": stage, "emotion": emotion, "goal": goal})
                    else:
                        text = str(entry).strip()
                        if text:
                            normalized_curve.append({"stage": f"阶段 {len(normalized_curve) + 1}", "emotion": text, "goal": text})
                if normalized_curve:
                    merged_analysis[field] = normalized_curve[:6]
        else:
            items = _normalize_list(provider_value)
            if items:
                merged_analysis[field] = items[:6]
    result["viral_analysis"] = merged_analysis
    emotion_value_sentences = payload.get("emotion_value_sentences")
    if emotion_value_sentences:
        values = []
        for item in emotion_value_sentences:
            if isinstance(item, dict):
                values.append(str(item.get("text") or ""))
            else:
                values.append(str(item))
        result["emotion_value_sentences"] = _sentence_objects(body, values, "给读者情绪价值")[:8]
    pain_point_sentences = payload.get("pain_point_sentences")
    if pain_point_sentences:
        values = []
        for item in pain_point_sentences:
            if isinstance(item, dict):
                values.append(str(item.get("text") or ""))
            else:
                values.append(str(item))
        result["pain_point_sentences"] = _sentence_objects(body, values, "刺痛读者处境")[:8]
    ai_smell = payload.get("ai_smell_findings")
    if isinstance(ai_smell, list) and ai_smell:
        normalized_findings = []
        for item in ai_smell:
            if isinstance(item, dict):
                normalized_findings.append(
                    {
                        "type": str(item.get("type") or item.get("kind") or "provider").strip() or "provider",
                        "pattern": str(item.get("pattern") or item.get("label") or item.get("text") or "").strip(),
                        "count": int(item.get("count") or 1),
                        "evidence": str(item.get("evidence") or item.get("text") or item.get("pattern") or "").strip(),
                    }
                )
            else:
                text = str(item).strip()
                if text:
                    normalized_findings.append({"type": "provider", "pattern": text, "count": 1, "evidence": text})
        if normalized_findings:
            result["ai_smell_findings"] = normalized_findings
    priorities = _normalize_list(payload.get("revision_priorities"))
    if priorities:
        result["revision_priorities"] = priorities
    for field in ["template_findings", "citation_findings", "interaction_findings"]:
        value = payload.get(field)
        if isinstance(value, list):
            result[field] = value
        elif isinstance(value, dict):
            result[field] = value
    similarity = payload.get("similarity_findings")
    if isinstance(similarity, dict):
        result["similarity_findings"] = similarity
    editorial_review = payload.get("editorial_review")
    if isinstance(editorial_review, dict):
        merged_editorial = dict(result.get("editorial_review") or {})
        merged_editorial.update({key: value for key, value in editorial_review.items() if value not in (None, "")})
        result["editorial_review"] = merged_editorial
    humanness_signals = payload.get("humanness_signals")
    if isinstance(humanness_signals, dict):
        result["humanness_signals"] = humanness_signals
    humanness_findings = _normalize_list(payload.get("humanness_findings"))
    if humanness_findings:
        result["humanness_findings"] = humanness_findings
    if payload.get("humanness_score") not in (None, ""):
        try:
            result["humanness_score"] = int(payload.get("humanness_score") or 0)
        except (TypeError, ValueError):
            pass
    result["review_source"] = review_source
    result["source"] = review_source
    result["confidence"] = float(payload.get("confidence") or result.get("confidence") or 0.72)
    result["revision_round"] = int(payload.get("revision_round") or revision_round)
    result["generated_at"] = legacy.now_iso()
    return result


def _score_hot_intro(title: str, body: str, review: dict[str, Any]) -> tuple[int, str]:
    intro = legacy.intro_text(body)
    depth = review.get("depth_signals") or _depth_signals(body, review.get("manifest_context") or {})
    score = 3
    score += min(3, legacy.count_occurrences(title, getattr(legacy, "TITLE_CURIOSITY_WORDS", [])))
    score += min(2, legacy.count_occurrences(intro, getattr(legacy, "HOOK_WORDS", [])))
    if any(word in intro for word in PAIN_POINT_MARKERS):
        score += 2
    if any(word in intro for word in ["你可能", "刷到", "某天", "看到", "结果是", "但真正", "多数人"]):
        score += 1
    if depth.get("scene_paragraph_count", 0) >= 1:
        score += 1
    if "?" in intro or "？" in intro:
        score += 1
    if review.get("pain_point_sentences"):
        score += 1
    return min(10, score), "好的开头不靠固定模板，可以是场景、反差、问题、新闻切口或延迟亮观点，但必须把读者迅速带进问题。"


def _score_viewpoints(review: dict[str, Any]) -> tuple[int, str]:
    core = str(review.get("viral_analysis", {}).get("core_viewpoint") or "").strip()
    secondary = _normalize_list(review.get("viral_analysis", {}).get("secondary_viewpoints"))
    score = 3
    if core:
        score += 3
    score += min(4, len(secondary))
    return min(10, score), "文章需要一个主观点打穿全文，并有 2~4 个副观点负责展开。"


def _score_argument_diversity(review: dict[str, Any]) -> tuple[int, str]:
    modes = _normalize_list(review.get("viral_analysis", {}).get("argument_diversity"))
    strategies = _normalize_list(review.get("viral_analysis", {}).get("persuasion_strategies"))
    depth = review.get("depth_signals") or {}
    score = min(10, 1 + len(_dedupe(modes + strategies)) * 2)
    score += min(2, int(depth.get("evidence_paragraph_count") or 0))
    score += 1 if depth.get("counterpoint_paragraph_count", 0) else 0
    score += 1 if depth.get("scene_paragraph_count", 0) else 0
    return score, "爆款稿不靠单向说教，至少要能在拆解、对比、案例、趋势、场景、步骤里切换 3 种以上。"


def _score_emotion_trigger(review: dict[str, Any]) -> tuple[int, str]:
    emotion_count = len(review.get("emotion_value_sentences") or [])
    pain_count = len(review.get("pain_point_sentences") or [])
    score = min(10, 2 + min(4, emotion_count // 2) + min(4, pain_count))
    return score, "既要刺痛现实，也要给读者被理解和被托住的感觉。"


def _score_signature(review: dict[str, Any]) -> tuple[int, str]:
    count = len(review.get("viral_analysis", {}).get("signature_lines") or [])
    score = min(10, 1 + count * 3)
    return score, "金句要足够短、够准、能被截图和复述。"


def _score_interaction_design(review: dict[str, Any], body: str) -> tuple[int, str]:
    analysis = review.get("viral_analysis", {}) or {}
    like_triggers = _normalize_list(analysis.get("like_triggers"))
    comment_triggers = _normalize_list(analysis.get("comment_triggers"))
    share_triggers = _normalize_list(analysis.get("share_triggers"))
    social_currency = _normalize_list(analysis.get("social_currency_points"))
    identity_labels = _normalize_list(analysis.get("identity_labels"))
    controversy = _normalize_list(analysis.get("controversy_anchors"))
    peak = str(analysis.get("peak_moment") or "").strip()
    ending = str(analysis.get("ending_interaction_design") or "").strip()
    ending_text = " ".join(legacy.list_paragraphs(body)[-2:])
    comment_prompt_hits = len(re.findall(r"(如果是你|你会怎么|你更认同|你遇到过|欢迎留言|评论区|你最想|你会先)", ending_text))
    ending_question = len(re.findall(r"[？?]", ending_text))
    identity_hits = len(re.findall(r"(普通人|团队|老板|创业者|开发者|从业者|管理者)", body))
    quote_count = len(review.get("viral_analysis", {}).get("signature_lines") or [])
    score = 1
    score += min(2, quote_count // 2)
    score += 2 if len(like_triggers) >= 2 and quote_count >= 1 else 0
    score += min(3, comment_prompt_hits + min(1, ending_question))
    score += 1 if share_triggers and social_currency and quote_count >= 1 else 0
    score += 1 if identity_labels and identity_hits >= 2 else 0
    score += 1 if controversy and re.search(r"(争议|站队|到底|谁更|该不该)", ending_text + body) else 0
    score += 1 if peak and ending and (comment_prompt_hits or ending_question) else 0
    if not comment_prompt_hits and not ending_question:
        score = min(score, 4)
    if not share_triggers and not social_currency:
        score = min(score, 5)
    return min(10, score), "高互动内容要同时具备点赞共鸣、评论触发、转发谈资，以及峰终体验。"


def _score_emotion_curve(review: dict[str, Any], body: str) -> tuple[int, str]:
    curve_count = len(review.get("viral_analysis", {}).get("emotion_curve") or [])
    paragraph_count = len(legacy.list_paragraphs(body))
    depth = review.get("depth_signals") or _depth_signals(body, review.get("manifest_context") or {})
    score = 2
    if curve_count >= 3:
        score += 4
    if 6 <= paragraph_count <= 20:
        score += 2
    if depth.get("long_paragraph_count", 0) >= 1 and depth.get("short_paragraph_count", 0) >= 2:
        score += 1
    if not depth.get("outline_like"):
        score += 1
    return min(8, score), "情绪推进要有起伏，可以从悬念/刺痛/代入走向理解，再落到判断、余味或行动。"


def _score_emotion_layers(review: dict[str, Any]) -> tuple[int, str]:
    layers = _normalize_list(review.get("viral_analysis", {}).get("emotion_layers"))
    score = min(8, 2 + len(layers))
    return score, "不要只有一种情绪，至少要能看到代入、理解、判断、余味或行动中的多层推进。"


def _score_perspective(review: dict[str, Any]) -> tuple[int, str]:
    shifts = _normalize_list(review.get("viral_analysis", {}).get("perspective_shifts"))
    score = min(8, 2 + len(shifts) * 2)
    return score, "视角切换会带来认知增量，避免全文只站在一个角度说话。"


def _score_style(review: dict[str, Any], body: str) -> tuple[int, str]:
    findings = review.get("ai_smell_findings") or []
    ai_hits = len(findings)
    sentence_lengths = [legacy.cjk_len(sentence) for sentence in legacy.sentence_split(body)]
    depth = review.get("depth_signals") or _depth_signals(body, review.get("manifest_context") or {})
    penalty = 0
    for item in findings:
        finding_type = str(item.get("type") or "")
        count = int(item.get("count") or 0)
        if finding_type in {
            "repeated_starter",
            "repeated_sentence_opener",
            "heading_monotony",
            "author_phrase",
            "author_starter",
            "throat_clearing",
        }:
            penalty += max(2, min(3, count))
        elif finding_type in {"outline_like", "enumeration_voice", "false_agency", "binary_contrast"}:
            penalty += 2
        else:
            penalty += 1
    score = 8 - min(7, penalty)
    if sentence_lengths and max(sentence_lengths) - min(sentence_lengths) >= 12:
        score += 1
    if any(word in body for word in ["你", "我们", "别急", "说白了"]):
        score += 1
    if depth.get("repeated_starter_count", 0) >= 2:
        score -= 2
    if depth.get("repeated_sentence_opener_count", 0) >= 2:
        score -= 2
    if depth.get("heading_monotony"):
        score -= 2
    if depth.get("outline_like"):
        score -= 2
    return int(legacy.clamp(score, 0, 8)), "像真人写出来的稿子，应该有判断感、节奏感和去模板腔的表达。"


def _score_credibility(body: str, manifest: dict[str, Any], review: dict[str, Any]) -> tuple[int, str]:
    citation = _citation_findings(body, manifest)
    refs = _references_summary(manifest)
    source_urls = manifest.get("source_urls") or []
    evidence_bonus = min(3, max(citation.get("inline_citation_count", 0), refs.get("reference_count", 0)))
    data_bonus = len(re.findall(r"\d{4}年|\d+(?:\.\d+)?%|\d+倍|第\d+", body))
    argument_modes = _normalize_list(review.get("viral_analysis", {}).get("argument_diversity"))
    depth = review.get("depth_signals") or _depth_signals(body, review.get("manifest_context") or {})
    score = min(
        8,
        min(3, len(source_urls))
        + min(2, evidence_bonus)
        + min(2, data_bonus)
        + (1 if "权威论证" in argument_modes else 0)
        + (1 if refs.get("reference_count", 0) else 0)
        + (1 if depth.get("evidence_paragraph_count", 0) >= 2 else 0),
    )
    if citation.get("raw_url_count", 0):
        score = max(0, score - 2)
    return score, "事实型内容必须经得起回溯，正文里不要裸贴链接；系统保留来源记录用于校验和回看。"


def _evidence_readiness(manifest: dict[str, Any], body: str, review: dict[str, Any]) -> dict[str, Any]:
    existing = manifest.get("research_requirements")
    if isinstance(existing, dict) and existing:
        return existing
    refs = _references_summary(manifest)
    depth = review.get("depth_signals") or _depth_signals(body, review.get("manifest_context") or {})
    source_count = len(manifest.get("source_urls") or [])
    evidence_count = max(refs.get("reference_count", 0), int(depth.get("evidence_paragraph_count") or 0))
    requires_evidence = str((manifest.get("viral_blueprint") or {}).get("article_archetype") or manifest.get("article_archetype") or "commentary").lower() != "tutorial"
    reasons: list[str] = []
    if requires_evidence and source_count < 2:
        reasons.append("可回溯来源不足 2 条")
    if requires_evidence and evidence_count < 1:
        reasons.append("还没有可落进正文的证据卡")
    return {
        "requires_evidence": requires_evidence,
        "source_count": source_count,
        "evidence_count": evidence_count,
        "passed": not reasons,
        "reasons": reasons,
    }


def _image_fit_expectation(title: str, body: str, manifest: dict[str, Any]) -> dict[str, Any]:
    strategy = manifest.get("account_strategy") or {}
    blocked = [str(item).strip() for item in (strategy.get("blocked_image_presets") or []) if str(item).strip()]
    density = str(strategy.get("image_density") or "minimal").strip() or "minimal"
    max_inline = int(strategy.get("max_inline_images") or 2)
    pressure_keywords = ["成本", "岗位", "风险", "算力", "危机", "封杀", "银行", "租赁费", "H100"]
    pressure = any(keyword in f"{title}\n{body}" for keyword in pressure_keywords)
    return {
        "preferred_density": density,
        "max_inline_images": max_inline,
        "blocked_presets": blocked,
        "visual_focus": "贴题解释优先" if pressure else "解释和承接优先",
    }


def _build_quality_gates(
    review: dict[str, Any],
    blueprint: dict[str, Any],
    credibility_score: int,
    *,
    interaction_score: int,
    template_penalty_hits: int,
    similarity_findings: dict[str, Any],
    citation_findings: dict[str, Any],
    evidence_readiness: dict[str, Any],
    title_integrity: dict[str, Any],
) -> dict[str, bool]:
    ai_smell_hits = _ai_smell_gate_hits(review.get("ai_smell_findings") or [])
    editorial = review.get("editorial_review") or {}
    depth = review.get("depth_signals") or {}
    prompt_leak_hits = [item for item in (review.get("ai_smell_findings") or []) if str(item.get("type") or "") == "prompt_leak"]
    return {
        "viral_blueprint_complete": blueprint_complete(blueprint),
        "interaction_passed": interaction_score >= 6,
        "de_ai_passed": ai_smell_hits <= AI_SMELL_THRESHOLD,
        "credibility_passed": credibility_score >= 5,
        "title_integrity_passed": bool(title_integrity.get("passed")),
        "evidence_minimum_passed": bool(evidence_readiness.get("passed", True)),
        "prompt_leak_passed": not prompt_leak_hits,
        "depth_passed": bool(
            depth.get("scene_paragraph_count", 0) >= 1
            and depth.get("evidence_paragraph_count", 0) >= 1
            and depth.get("counterpoint_paragraph_count", 0) >= 1
            and not depth.get("outline_like")
        ),
        "structure_passed": bool(
            depth.get("repeated_starter_count", 0) <= 1
            and depth.get("repeated_sentence_opener_count", 0) <= 1
            and not depth.get("heading_monotony")
            and (depth.get("long_paragraph_count", 0) >= 1 or depth.get("paragraph_count", 0) <= 4)
        ),
        "template_penalty_passed": template_penalty_hits <= 1,
        "similarity_passed": bool(similarity_findings.get("similarity_passed", True)),
        "citation_policy_passed": bool(citation_findings.get("citation_policy_passed", True)),
        "editorial_review_passed": editorial.get("reading_desire") != "low" and editorial.get("template_risk") != "high" and editorial.get("interaction_naturalness") != "low",
    }


def build_score_report(
    title: str,
    body: str,
    manifest: dict[str, Any],
    threshold: int | None = None,
    review: dict[str, Any] | None = None,
    revision_rounds: list[dict[str, Any]] | None = None,
    stop_reason: str = "",
) -> dict[str, Any]:
    threshold = int(threshold or manifest.get("score_threshold") or DEFAULT_THRESHOLD)
    blueprint = normalize_viral_blueprint(
        manifest.get("viral_blueprint"),
        {
            "topic": manifest.get("topic") or title,
            "selected_title": title,
            "direction": manifest.get("direction") or "",
            "audience": manifest.get("audience") or "大众读者",
            "research": {},
            "style_signals": manifest.get("style_signals") or [],
        },
    )
    review = review or build_heuristic_review(title, body, manifest, blueprint=blueprint)
    title_integrity = title_integrity_report(title, topic=manifest.get("topic") or title, account_strategy=manifest.get("account_strategy") or {})
    hot_intro, hot_intro_note = _score_hot_intro(title, body, review)
    viewpoint_score, viewpoint_note = _score_viewpoints(review)
    argument_score, argument_note = _score_argument_diversity(review)
    emotion_score, emotion_note = _score_emotion_trigger(review)
    signature_score, signature_note = _score_signature(review)
    interaction_score, interaction_note = _score_interaction_design(review, body)
    curve_score, curve_note = _score_emotion_curve(review, body)
    layers_score, layers_note = _score_emotion_layers(review)
    perspective_score, perspective_note = _score_perspective(review)
    style_score, style_note = _score_style(review, body)
    credibility_score, credibility_note = _score_credibility(body, manifest, review)
    template_findings = review.get("template_findings") or _template_findings(title, body, manifest)
    similarity_findings = review.get("similarity_findings") or _similarity_findings(title, body, manifest)
    citation_findings = review.get("citation_findings") or _citation_findings(body, manifest)
    interaction_findings = review.get("interaction_findings") or review.get("viral_analysis") or {}
    editorial_review = review.get("editorial_review") or _heuristic_editorial_review(title, body, review, template_findings, similarity_findings, citation_findings)
    depth_signals = review.get("depth_signals") or _depth_signals(
        body,
        {
            "selected_title": title,
            "topic": manifest.get("topic") or title,
            "title": title,
            "viral_blueprint": blueprint,
        },
    )
    humanness_signals = review.get("humanness_signals") or build_humanness_signals(body, manifest, {"depth_signals": depth_signals})
    humanness_score, derived_humanness_findings = _humanness_score(humanness_signals, manifest.get("writing_persona") or {})
    humanness_findings = _dedupe(_normalize_list(review.get("humanness_findings")) + derived_humanness_findings)
    evidence_readiness = _evidence_readiness(manifest, body, review | {"depth_signals": depth_signals})
    image_fit_expectation = _image_fit_expectation(title, body, manifest)
    template_penalty_hits = sum(max(1, min(2, int(item.get("count") or 1))) for item in template_findings) + len(
        similarity_findings.get("repeated_phrases") or []
    )
    breakdown = [
        {"dimension": "标题与开头爆点", "weight": 10, "score": hot_intro, "note": hot_intro_note},
        {"dimension": "核心观点与副观点", "weight": 10, "score": viewpoint_score, "note": viewpoint_note},
        {"dimension": "说服策略与论证多样性", "weight": 10, "score": argument_score, "note": argument_note},
        {"dimension": "情绪触发与刺痛感", "weight": 10, "score": emotion_score, "note": emotion_note},
        {"dimension": "金句与传播句密度", "weight": 10, "score": signature_score, "note": signature_note},
        {"dimension": "互动参与与社交货币", "weight": 10, "score": interaction_score, "note": interaction_note},
        {"dimension": "情感曲线与节奏", "weight": 8, "score": curve_score, "note": curve_note},
        {"dimension": "情感层次与共鸣", "weight": 8, "score": layers_score, "note": layers_note},
        {"dimension": "视角转化与认知增量", "weight": 8, "score": perspective_score, "note": perspective_note},
        {"dimension": "语言风格自然度", "weight": 8, "score": style_score, "note": style_note},
        {"dimension": "可信度与检索支撑", "weight": 8, "score": credibility_score, "note": credibility_note},
    ]
    humanness_adjustment = 1 if humanness_score >= 8 else -2 if humanness_score <= 4 else -1 if humanness_score <= 6 else 0
    total = max(0, min(100, sum(item["score"] for item in breakdown) + humanness_adjustment))
    quality_gates = _build_quality_gates(
        review | {"editorial_review": editorial_review, "depth_signals": depth_signals},
        blueprint,
        credibility_score,
        interaction_score=interaction_score,
        template_penalty_hits=template_penalty_hits,
        similarity_findings=similarity_findings,
        citation_findings=citation_findings,
        evidence_readiness=evidence_readiness,
        title_integrity=title_integrity,
    )
    strengths = []
    weaknesses = []
    for item in breakdown:
        ratio = item["score"] / max(1, item["weight"])
        if ratio >= 0.8:
            strengths.append(f"{item['dimension']}表现较强：{item['note']}")
        elif ratio < 0.65:
            weaknesses.append(f"{item['dimension']}偏弱：{item['note']}")
    failed_gates = [name for name, ok in quality_gates.items() if not ok]
    mandatory_revisions = _dedupe(
        [
            "补齐爆款蓝图，先把主观点、副观点、情绪触发点和论证方式定下来。" if not quality_gates["viral_blueprint_complete"] else "",
            "补互动设计：显式安排点赞共鸣点、评论问题和可转发谈资。" if interaction_score < 7 else "",
            "继续清理模板腔，压低 AI 痕迹。" if not quality_gates["de_ai_passed"] else "",
            "补来源、数据或官方依据，提升可信度。" if not quality_gates["credibility_passed"] else "",
            "重写标题，先保证语义完整、句法顺和首屏可读。" if not quality_gates["title_integrity_passed"] else "",
            "补足最小证据要求：至少 2 条来源、至少 1 条可写进正文的证据卡。" if not quality_gates["evidence_minimum_passed"] else "",
            "删除成稿里泄漏的内部提示语、写作说明和蓝图口吻。" if not quality_gates["prompt_leak_passed"] else "",
            "补现场、案例和反方边界，让文章真正立起来。" if not quality_gates["depth_passed"] else "",
            "打散段落起手和小标题模式，避免整篇像同一套模板复印。" if not quality_gates["structure_passed"] else "",
            "重写篇章结构和句法节奏，压低模板惩罚。" if not quality_gates["template_penalty_passed"] else "",
            "根据真人感信号补句长落差、段落节奏和自我修正痕迹。" if humanness_score <= 6 else "",
            "重写开头/结尾和标题层级，主动拉开与最近文章的差异。" if not quality_gates["similarity_passed"] else "",
            "把正文裸链接改成自然来源表述，不要再挂 [1][2] 或文末参考资料尾卡。" if not quality_gates["citation_policy_passed"] else "",
            "先把阅读欲望、专业感和结尾自然度拉上来，再谈提分。" if not quality_gates["editorial_review_passed"] else "",
        ]
        + list(review.get("revision_priorities") or [])
    )
    opening_continue_read_risk = (
        "high"
        if editorial_review.get("reading_desire") == "low" or hot_intro <= 5
        else "medium"
        if hot_intro <= 7
        else "low"
    )
    publish_blockers = _dedupe(
        list(title_integrity.get("issues") or [])
        + list(evidence_readiness.get("reasons") or [])
        + [f"质量门槛未通过：{name}" for name in failed_gates]
    )
    suggestions = {
        "opening_directions": _dedupe(
            _normalize_list(blueprint.get("opening_modes"))
            + [
                "从一个具体场景或最近发生的细节切入",
                "用反差判断切开问题，但别直接喊口号",
                "如果主题够强，也可以延迟亮观点，先把悬念立住",
            ]
        )[:4],
        "ending_directions": _dedupe(
            _normalize_list(blueprint.get("ending_modes"))
            + [
                "用判断收束，而不是默认上 checklist",
                "如果是教程，才考虑给动作；如果是分析稿，优先留余味或风险提醒",
            ]
        )[:4],
        "sample_gold_quotes": [item["text"] for item in (review.get("viral_analysis", {}).get("signature_lines") or [])[:3]]
        or _normalize_list(blueprint.get("target_quotes"))[:3],
        "sample_comment_prompts": _normalize_list(review.get("viral_analysis", {}).get("comment_triggers"))
        or _normalize_list(blueprint.get("interaction_prompts"))[:3],
        "share_points": _normalize_list(review.get("viral_analysis", {}).get("social_currency_points"))
        or _normalize_list(blueprint.get("social_currency_points"))[:3],
        "style_adjustments": _dedupe(
            [
                "不同小节换不同进入方式，别把整篇写成同一套判断句模板。",
                "让每一节至少出现一句能刺痛读者、点醒读者或安顿读者的话。",
                "补对比、案例或细节，避免只讲观点不讲场景。",
                "至少留一段真正展开的分析段，不要所有段落都像卡片。",
                "主动写出反方、误判或适用边界，文章才会更像真人判断。",
            ]
            + humanness_findings
        ),
        "failed_quality_gates": failed_gates,
        "revision_priorities": list(review.get("revision_priorities") or []),
    }
    ai_smell_hits = _ai_smell_gate_hits(review.get("ai_smell_findings") or [])
    passed = total >= threshold and all(quality_gates.values())
    return {
        "title": title,
        "threshold": threshold,
        "total_score": total,
        "passed": passed,
        "score_breakdown": breakdown,
        "strengths": strengths[:5],
        "weaknesses": weaknesses[:5],
        "mandatory_revisions": mandatory_revisions[:7],
        "suggestions": suggestions,
        "candidate_quotes": [item["text"] for item in (review.get("viral_analysis", {}).get("signature_lines") or [])[:6]],
        "quality_gates": quality_gates,
        "title_integrity": title_integrity,
        "evidence_readiness": evidence_readiness,
        "image_fit_expectation": image_fit_expectation,
        "opening_continue_read_risk": opening_continue_read_risk,
        "publish_blockers": publish_blockers,
        "viral_blueprint": blueprint,
        "viral_analysis": review.get("viral_analysis") or {},
        "editorial_review": editorial_review,
        "emotion_value_sentences": review.get("emotion_value_sentences") or [],
        "pain_point_sentences": review.get("pain_point_sentences") or [],
        "ai_smell_findings": review.get("ai_smell_findings") or [],
        "ai_smell_hits": ai_smell_hits,
        "interaction_score": interaction_score,
        "template_penalty_hits": template_penalty_hits,
        "template_findings": template_findings,
        "similarity_findings": similarity_findings,
        "citation_findings": citation_findings,
        "interaction_findings": interaction_findings,
        "depth_signals": depth_signals,
        "humanness_signals": humanness_signals,
        "humanness_score": humanness_score,
        "humanness_findings": humanness_findings,
        "humanness_adjustment": humanness_adjustment,
        "max_similarity": similarity_findings.get("max_similarity", 0),
        "similar_articles": similarity_findings.get("similar_articles", []),
        "repeated_phrases": similarity_findings.get("repeated_phrases", []),
        "references_summary": _references_summary(manifest),
        "revision_rounds": revision_rounds or [],
        "best_round": max((item.get("round", 0) for item in revision_rounds or []), default=int(review.get("revision_round") or 1)),
        "stop_reason": stop_reason,
        "generated_at": legacy.now_iso(),
    }


def markdown_review_report(review: dict[str, Any]) -> str:
    analysis = review.get("viral_analysis") or {}
    lines = [
        "# 编辑评审报告",
        "",
        review.get("summary", ""),
        "",
        "## 爆款拆解",
        "",
        f"- 核心观点：{analysis.get('core_viewpoint') or '无'}",
    ]
    for label, key in [
        ("副观点", "secondary_viewpoints"),
        ("说服策略", "persuasion_strategies"),
        ("情绪触发点", "emotion_triggers"),
        ("情感层次", "emotion_layers"),
        ("论证方式多样性", "argument_diversity"),
        ("视角转化分析", "perspective_shifts"),
        ("语言风格特征", "style_traits"),
    ]:
        items = _normalize_list(analysis.get(key))
        lines.append(f"- {label}：{'、'.join(items) if items else '无'}")
    lines.extend(["", "## 金句", ""])
    for item in analysis.get("signature_lines") or []:
        lines.append(f"> {item.get('text') if isinstance(item, dict) else item}")
    lines.extend(["", "## 互动设计", ""])
    for label, key in [
        ("点赞触发点", "like_triggers"),
        ("评论触发点", "comment_triggers"),
        ("转发触发点", "share_triggers"),
        ("社交谈资", "social_currency_points"),
        ("身份标签", "identity_labels"),
        ("争议靶点", "controversy_anchors"),
    ]:
        items = _normalize_list(analysis.get(key))
        lines.append(f"- {label}：{'、'.join(items) if items else '无'}")
    if analysis.get("peak_moment"):
        lines.append(f"- 峰值时刻：{analysis.get('peak_moment')}")
    if analysis.get("ending_interaction_design"):
        lines.append(f"- 结尾互动设计：{analysis.get('ending_interaction_design')}")
    editorial = review.get("editorial_review") or {}
    if editorial:
        lines.extend(["", "## 编辑二审", ""])
        for key in [
            "reading_desire",
            "professional_tone",
            "novelty_of_viewpoint",
            "template_risk",
            "citation_restraint",
            "ending_naturalness",
            "interaction_naturalness",
        ]:
            if editorial.get(key):
                lines.append(f"- {key}：{editorial.get(key)}")
        if editorial.get("summary"):
            lines.append(f"- 结论：{editorial.get('summary')}")
    lines.extend(["", "## 情感曲线分析", ""])
    for item in analysis.get("emotion_curve") or []:
        if isinstance(item, dict):
            lines.append(f"- {item.get('stage') or '阶段'}：{item.get('emotion') or ''}｜{item.get('goal') or ''}")
        else:
            lines.append(f"- {item}")
    lines.extend(["", "## 情绪价值句式", ""])
    for item in review.get("emotion_value_sentences") or []:
        lines.append(f"- {item.get('text')}｜{item.get('reason')}｜强度 {item.get('strength')}")
    lines.extend(["", "## 刺痛句式", ""])
    for item in review.get("pain_point_sentences") or []:
        lines.append(f"- {item.get('text')}｜{item.get('reason')}｜强度 {item.get('strength')}")
    lines.extend(["", "## AI 味检查", ""])
    for item in review.get("ai_smell_findings") or []:
        lines.append(f"- {item.get('type')}：{item.get('evidence')}（{item.get('count')}）")
    lines.extend(["", "## 修改优先级", ""])
    for item in review.get("revision_priorities") or ["当前结构完整，可进入下一步。"]:
        lines.append(f"- {item}")
    if review.get("strengths"):
        lines.extend(["", "## 当前亮点", ""])
        for item in review.get("strengths") or []:
            lines.append(f"- {item}")
    if review.get("issues"):
        lines.extend(["", "## 当前问题", ""])
        for item in review.get("issues") or []:
            lines.append(f"- {item}")
    return "\n".join(line for line in lines if line is not None).rstrip() + "\n"


def markdown_score_report(report: dict[str, Any]) -> str:
    lines = [
        f"# 文章评分报告：{report.get('title') or '未命名文章'}",
        "",
        f"- 总分：`{report.get('total_score', 0)}` / 100",
        f"- 阈值：`{report.get('threshold', DEFAULT_THRESHOLD)}`",
        f"- 结果：`{'通过' if report.get('passed') else '未通过'}`",
    ]
    stop_reason = str(report.get("stop_reason") or "").strip()
    if stop_reason:
        lines.append(f"- 停止原因：`{stop_reason}`")
    lines.extend(["", "## 分项得分", ""])
    for item in report.get("score_breakdown") or []:
        lines.append(f"- {item['dimension']}：`{item['score']}` / `{item['weight']}` - {item['note']}")
    if report.get("humanness_score") not in (None, ""):
        lines.extend(["", "## 真人感信号", ""])
        lines.append(f"- 真人感分：`{report.get('humanness_score', 0)}` / 10")
        lines.append(f"- 调整分：`{report.get('humanness_adjustment', 0)}`")
        for item in report.get("humanness_findings") or []:
            lines.append(f"- {item}")
    lines.extend(["", "## 质量门槛", ""])
    for name, ok in (report.get("quality_gates") or {}).items():
        lines.append(f"- {name}：`{'通过' if ok else '未通过'}`")
    lines.extend(["", "## 失败原因与必须修改项", ""])
    for item in report.get("mandatory_revisions") or ["当前版本已达发布线。"]:
        lines.append(f"- {item}")
    if report.get("template_findings") or report.get("repeated_phrases") or report.get("citation_findings"):
        lines.extend(["", "## 风险信号", ""])
        lines.append(f"- 模板惩罚计数：`{report.get('template_penalty_hits', 0)}`")
        for item in report.get("template_findings") or []:
            lines.append(f"- 模板句：{item.get('pattern')}（{item.get('count')}）")
        for item in report.get("repeated_phrases") or []:
            lines.append(f"- 高相似短语：{item}")
        citation = report.get("citation_findings") or {}
        if citation:
            lines.append(
                f"- 引用策略：raw_urls={citation.get('raw_url_count', 0)} / inline_refs={citation.get('inline_citation_count', 0)} / refs={citation.get('reference_count', 0)}"
            )
    suggestions = report.get("suggestions") or {}
    if suggestions.get("sample_comment_prompts") or suggestions.get("share_points"):
        lines.extend(["", "## 互动建议", ""])
        for item in suggestions.get("sample_comment_prompts") or []:
            lines.append(f"- 评论引导：{item}")
        for item in suggestions.get("share_points") or []:
            lines.append(f"- 转发谈资：{item}")
    lines.extend(["", "## 下一轮改稿优先级", ""])
    for item in (report.get("suggestions") or {}).get("revision_priorities") or ["优先守住当前爆点和节奏。"]:
        lines.append(f"- {item}")
    lines.extend(["", "## 爆款句密度", ""])
    lines.append(f"- 情绪价值句：`{len(report.get('emotion_value_sentences') or [])}`")
    lines.append(f"- 刺痛句：`{len(report.get('pain_point_sentences') or [])}`")
    lines.append(f"- 金句：`{len(report.get('candidate_quotes') or [])}`")
    lines.append(f"- AI 味命中：`{report.get('ai_smell_hits', 0)}`")
    lines.append(f"- 重复起手信号：`{(report.get('depth_signals') or {}).get('repeated_starter_count', 0)}` 段落 / `{(report.get('depth_signals') or {}).get('repeated_sentence_opener_count', 0)}` 句子")
    revision_rounds = report.get("revision_rounds") or []
    if revision_rounds:
        lines.extend(["", "## 多轮修正记录", ""])
        for item in revision_rounds:
            lines.append(
                f"- Round {item.get('round')}：`{item.get('score')}` 分｜`{'通过' if item.get('passed') else '未通过'}`｜{item.get('article_path')}"
            )
    if report.get("candidate_quotes"):
        lines.extend(["", "## 已识别金句", ""])
        for quote in report["candidate_quotes"]:
            lines.append(f"> {quote}")
    if report.get("rewrite"):
        rewrite = report["rewrite"]
        lines.extend(["", "## 自动改写稿", ""])
        lines.append(f"- 改写稿：`{rewrite.get('output_path')}`")
        lines.append(f"- 模式：`{rewrite.get('mode')}`")
        lines.append(f"- 预评分：`{rewrite.get('preview_score')}` / 100")
        lines.append(f"- 预评分是否过线：`{'是' if rewrite.get('preview_passed') else '否'}`")
        for action in rewrite.get("applied_actions") or []:
            lines.append(f"- 已应用：{action}")
    return "\n".join(lines).rstrip() + "\n"
