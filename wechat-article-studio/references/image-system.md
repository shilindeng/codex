# 图片系统

## 导航

- 四维控制参数
- 统一主题预设
- 风格模式
- 密度模式
- 布局家族
- 文内标记
- 自动规划
- Prompt 组成
- Provider 规则

## 四维控制参数

- `theme`：内容主题领域
- `style`：视觉风格
- `type`：图片用途
- `mood`：整体氛围

## 统一主题预设

可通过 `--image-preset` 为整篇文章的封面图、信息图、正文插图指定统一视觉主题。当前内置预设：

- `cute`：可爱手账
- `fresh`：清新杂志
- `warm`：温暖生活
- `bold`：高对比海报
- `minimal`：极简理性
- `retro`：复古印刷
- `pop`：流行拼贴
- `notion`：知识卡片
- `chalkboard`：黑板讲解
- `editorial-grain`：杂志颗粒
- `organic-natural`：自然有机
- `scientific-blueprint`：科学蓝图
- `professional-corporate`：专业商务
- `abstract-geometric`：抽象几何
- `luxury-minimal`：轻奢极简
- `illustrated-handdrawn`：手绘讲述
- `photoreal-sketch`：写实速写

预设一旦指定，会统一覆盖整篇文章的自动视觉策略里的 `theme/style/mood/custom_visual_brief`，从而让封面图、信息图、正文插图保持同一视觉语言。仍可用 `--image-theme`、`--image-style`、`--image-mood`、`--custom-visual-brief` 做少量覆盖。

如果用户没有显式指定 `--image-preset`，系统不会再默认写死某个预设，而是先分析文章内容、受众、文风和章节结构，再自动选择视觉方向。

## 风格模式

支持 `--image-style-mode`：

- `uniform`：整篇统一风格
- `mixed-by-type`：按图片类型混合风格（封面/信息图/正文插图），但保持整篇配色与母题一致

当 `--image-style-mode mixed-by-type` 时，可额外指定：

- `--image-preset-cover`：封面图预设
- `--image-preset-infographic`：信息图预设
- `--image-preset-inline`：正文插图预设（包含流程图/对比图/分隔图等正文内图片）

如果用户没有显式指定 `--image-style-mode`，系统会自动判断：

- 叙事/评论/趋势类文章优先 `uniform`
- 教程/解释/复盘/结构化分析类文章可切到 `mixed-by-type`

如果用户没有显式指定 `--image-preset-cover / --image-preset-infographic / --image-preset-inline`，系统会根据文章视觉策略自动决定；`discover-topics` 也不再预写固定 preset 组合。

## 密度模式

支持 `--image-density`：

- `minimal`：少量关键图
- `balanced`：均衡配图
- `per-section`：尽量按章节分布
- `rich`：更丰富的插图覆盖

当前默认使用 `balanced`，但仍会结合章节类型、信息密度和文内标记，避免无意义堆图。

## 布局家族

支持 `--image-layout-family`：

- `editorial`：更偏封面和正文插图的编辑式构图
- `process`：更偏流程图和步骤图
- `comparison`：更偏对比图
- `timeline`：更偏时间轴和线性推进
- `hierarchy`：更偏层级树与结构关系
- `dashboard`：更偏数据卡片、仪表板、矩阵
- `map`：更偏地理映射
- `radial`：更偏中心辐射
- `list`：更偏清单、卡片堆叠

布局家族不会破坏整篇文章的统一主题，只会影响每张图优先选哪组版式模板。

## 文内标记

支持在正文中通过 HTML 注释为某个章节声明配图约束。常用写法：

- `<!-- image:force -->`：强制该章节至少配 1 张图
- `<!-- image:skip -->`：跳过该章节的正文配图
- `<!-- image:type=流程图 -->`：强制该章节使用指定图型
- `<!-- image:count=2 -->`：要求该章节配 2 张图

可组合使用，例如：

```md
## 三步搭建自动化工作流

<!-- image:force type=流程图 count=2 -->

先梳理输入...
```

这些标记只用于规划，不会出现在最终渲染结果里。

## 中间产物

在 `plan-images` 阶段，除了 `image-plan.json`，还会额外生成：

- `image-strategy.json`：文章级图片策略与自动决策理由
- `image-outline.json`：结构化插图大纲
- `image-outline.md`：人可读插图大纲
- `prompts/images/*.md`：每张图单独的 prompt 文件

这套产物更接近 baoyu 的工作流，便于复查“哪张图为什么存在、画什么、放哪里”。

每张图现在会额外沉淀结构化规格：

- `decision_source`：该图型来自显式 directive、自动结构判定还是自动摘要判定
- `type_reason`：为什么这张图被判成当前图型
- `style_reason`：为什么这张图采用当前风格表达
- `visual_elements`：画面里应该出现的核心元素
- `layout_spec`：版式变体、构图规则、构图目标
- `label_strategy`：允许出现的极少量标签
- `text_budget`：文字预算
- `aspect_policy`：比例与裁切策略

`generate-images` 会优先回读 `prompts/images/*.md` 中的 `## Prompt` 段落。也就是说，你可以先人工微调 prompt 文件，再执行真实出图。

## 自动规划

- `1` 张封面图：仅用于封面和 `thumb_media_id`
- `1` 张收束图：优先放文末收束段；会根据结尾章节是否真的结构化，自动决定是 `信息图` 还是概念型收束插图
- 正文插图默认档位：
  - `< 1200` 字：`4` 张
  - `1200 - 2499` 字：`5` 张
  - `2500 - 3999` 字：`6` 张
  - `4000 - 5499` 字：`8` 张
  - `>= 5500` 字：`9` 张
- 当正文字数 `> 2000` 时，显式传入更低的 `--inline-count` 也会被抬到至少 `4` 张正文插图

自动规划不再只看字数，还会联合参考：

- 文章级视觉策略：`visual_direction / style_family / content_mode / type_bias`
- 章节类型：真实流程、真实对比、总结、框架、清单
- 信息密度：列表、引用、数据词、结论词
- 章节分布：尽量兼顾前半篇和后半篇
- 文内标记：`force / skip / type / count`

默认正文图优先是 `正文插图`。只有满足强结构化条件时，系统才会自动转成 `流程图 / 对比图 / 信息图`；如果用户显式写了 `<!-- image:type=... -->`，则始终以用户指定为准。

## Prompt 组成

每张图默认包含：

- 文章标题
- 目标读者
- 图片用途
- 文章级视觉方向 / 风格家族 / 内容模式
- 主题 / 风格 / 类型 / 氛围
- 章节焦点
- 目标章节真实正文片段
- 图型决策原因 / 风格决策原因
- 禁止事项：过多小字、水印、无关 logo、无请求的人脸

更细的 prompt 模块可参考 [`references/image-prompting.md`](./image-prompting.md)。

## Provider 规则

- 不指定图片 provider 时，默认使用 `gemini-web`
- 用户可以显式传入 `--provider gemini-web` 或 `--provider codex`
- 启用 `gemini-web` 之前必须先完成同意检查
- `gemini-web` 会优先尝试当前已知的 Gemini Web 图片模型；如果上游只返回文本、不返回图片，而本机又配置了 `gemini-api` 或 `openai-image`，系统会自动降级到官方图片接口
- `codex` 使用当前 Codex App 对话内置生图能力：先运行 `plan-images` 生成 `prompts/images/*.md`，再由当前 agent 调用内置 `image_gen` 逐张生成，保存到 `assets/images/<id>.png` 或 `codex-images/<id>.png`，最后运行 `generate-images --provider codex` 登记图片并继续 `assemble/render`
- `codex` 默认要求模型直接画出短字：封面图写 1~2 行短标题，其它图片写 2~4 个短中文标签；`required_text` 会写入 `image-plan.json`、`image-outline.*` 和 `codex-image-requests.*`
- 如果 `codex` 成图无字、缺字或乱码，必须重生，不允许直接登记进入后续排版或发布
- `gemini-api` 和 `openai-image` 仍可显式传入，但它们需要对应 API key，不作为免费默认路径
