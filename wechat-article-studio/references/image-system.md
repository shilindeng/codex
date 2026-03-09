# 图片系统

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

预设一旦指定，会统一覆盖整篇文章的默认 `theme/style/mood/custom_visual_brief`，从而让封面图、信息图、正文插图保持同一视觉语言。仍可用 `--image-theme`、`--image-style`、`--image-mood`、`--custom-visual-brief` 做少量覆盖。

## 密度模式

支持 `--image-density`：

- `minimal`：少量关键图
- `balanced`：均衡配图
- `per-section`：尽量按章节分布
- `rich`：更丰富的插图覆盖，默认值

当前 skill 默认使用 `rich`，但仍会结合章节类型、信息密度和文内标记，避免无意义堆图。

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

## 默认规划

- `1` 张封面图：仅用于封面和 `thumb_media_id`
- `1` 张信息图：优先放文末收束段
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
- 禁止事项：过多小字、水印、无关 logo、无请求的人脸

## Provider 规则

- 自动默认只选官方图片后端：`gemini-api`、`openai-image`
- `gemini-web` 只在显式传入 `--provider gemini-web` 时启用
- 启用 `gemini-web` 之前必须先完成同意检查
