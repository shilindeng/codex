# 图片系统

## 四维控制参数

- `theme`：内容主题领域
- `style`：视觉风格
- `type`：图片用途
- `mood`：整体氛围

## 统一主题预设

可通过 `--image-preset` 为整篇文章的封面图、信息图、正文插图指定统一视觉主题。若用户未显式指定，则系统会根据文章内容、分类和章节语义自动选择主题。当前内置预设：

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

预设一旦指定，会统一覆盖整篇文章的默认 `theme/style/mood/custom_visual_brief`，从而让封面图、信息图、正文插图保持同一视觉语言。仍可用 `--image-theme`、`--image-style`、`--image-mood`、`--custom-visual-brief` 做少量覆盖。

## 风格模式

支持 `--image-style-mode`：

- `uniform`：整篇统一风格
- `mixed-by-type`：按图片类型混合风格（封面/信息图/正文插图），但保持整篇配色与母题一致

默认不再固定某一种模式；在用户未显式指定时，系统会根据文章内容和章节异质性自动决定。

当 `--image-style-mode mixed-by-type` 时，可额外指定：

- `--image-preset-cover`：封面图预设
- `--image-preset-infographic`：信息图预设
- `--image-preset-inline`：正文插图预设（包含流程图/对比图/分隔图等正文内图片）

若用户显式指定 `mixed-by-type`，但未单独传入 cover/infographic/inline 预设，则默认沿用文章级 preset，不再强行固定 `bold/notion/editorial-grain`。

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

- `image-outline.json`：结构化插图大纲
- `image-outline.md`：人可读插图大纲
- `prompts/images/*.md`：每张图单独的 prompt 文件

这套产物更接近 baoyu 的工作流，便于复查“哪张图为什么存在、画什么、放哪里”。

每张图现在会额外沉淀结构化规格：

- `visual_elements`：画面里应该出现的核心元素
- `layout_spec`：版式变体、构图规则、构图目标
- `label_strategy`：允许出现的极少量标签
- `text_budget`：文字预算
- `aspect_policy`：比例与裁切策略

`generate-images` 会优先回读 `prompts/images/*.md` 中的 `## Prompt` 段落。也就是说，你可以先人工微调 prompt 文件，再执行真实出图。

## 默认规划

- `1` 张封面图：仅用于封面和 `thumb_media_id`，默认 `3:2`
- `1` 张信息图：优先放文末收束段，默认 `2:3` 竖版
- 正文插图默认档位：
  - `< 1200` 字：`4` 张
  - `1200 - 2499` 字：`5` 张
  - `2500 - 3999` 字：`6` 张
  - `4000 - 5499` 字：`8` 张
  - `>= 5500` 字：`9` 张
- 当正文字数 `> 2000` 时，显式传入更低的 `--inline-count` 也会被抬到至少 `4` 张正文插图

自动规划不再只看字数，还会联合参考：

- 章节类型：流程、对比、总结、框架、清单
- 信息密度：列表、引用、数据词、结论词
- 章节分布：尽量兼顾前半篇和后半篇
- 文内标记：`force / skip / type / count`

## Prompt 组成

每张图默认包含：

- 文章标题
- 目标读者
- 图片用途
- 主题 / 风格 / 类型 / 氛围
- 章节焦点
- 目标章节真实正文片段
- 语义焦点 `semantic_focus`
- 关键词词表 `keyword_glossary`
- 安全裁切策略 `safe_crop_policy`
- 禁止事项：过多小字、水印、无关 logo、无请求的人脸

## Provider 规则

- 自动默认只选官方图片后端：`gemini-api`、`openai-image`
- `gemini-web` 只在显式传入 `--provider gemini-web` 时启用
- 启用 `gemini-web` 之前必须先完成同意检查
- `gemini-web` 会优先尝试当前已知的 Gemini Web 图片模型；如果上游只返回文本、不返回图片，而本机又配置了 `gemini-api` 或 `openai-image`，系统会自动降级到官方图片接口
## 自动内容分类

在没有显式 `--image-*` 参数时，系统会先按文章内容自动分类：

- 教程实操
- 技术解析
- 行业观察
- 观点评论
- 案例复盘
- 生活叙事

再根据分类选择主题候选和布局家族，并把原因写入 `manifest.json.image_auto_reason` 与 `image-plan.json.auto_reason`。

比例策略：

- 封面图：`3:2`
- 信息图 / 流程图 / 对比图：`2:3`
- 正文插图 / 分隔图：`3:2`

封面图 prompt 会额外加入公众号封面裁切安全区约束；信息图默认优先竖版长图。
