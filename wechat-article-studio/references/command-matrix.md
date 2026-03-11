# 命令矩阵

## `research`

- 输入：`--workspace --topic [--angle] [--audience] [--source-url ...]`
- 依赖：文本 provider（纯 CLI 场景缺配置会直接失败；宿主模式请改用 `hosted-run` 并由宿主写入 research）
- 输出：`research.json`
- 失败条件：缺 `--topic`

## `titles`

- 输入：`--workspace [--count 3]`
- 依赖：`research.json` 推荐存在；缺失时用 manifest 信息兜底
- 输出：更新 `ideation.json`、`title-report.json`、`title-report.md`
- 失败条件：工作目录不可写
- 说明：候选标题会做多维爆款评分，并优先选择通过阈值的标题作为 `selected_title`

## `outline`

- 输入：`--workspace [--title "..."]`
- 依赖：`research.json`、`ideation.json`
- 输出：更新 `ideation.json`
- 失败条件：工作目录不可写

## `write`

- 输入：`--workspace [--title "..."] [--outline-file ...]`
- 依赖：`research.json`、`ideation.json`
- 输出：`article.md`
- 失败条件：工作目录不可写

## `review`

- 输入：`--workspace`
- 依赖：`article.md`
- 输出：`review-report.json`、`review-report.md`
- 失败条件：找不到文章

## `score`

- 输入：`--workspace [--input ...]`
- 依赖：`article.md` 或指定输入
- 输出：`score-report.json`、`score-report.md`
- 失败条件：找不到文章

## `revise`

- 输入：`--workspace`
- 依赖：`article.md`，推荐先有 `score-report.json`
- 输出：`article-rewrite.md`
- 失败条件：找不到文章

## `run`

- 输入：`--workspace [--topic] [--to render|publish]`
- 依赖：工作目录可写；需要已配置文本 provider；发布时需要微信凭证
- 输出：从 `research.json` 到 `article.wechat.html`，必要时追加发布产物
- 失败条件：发布前置条件不满足
- 常用图片参数：
  - `--image-preset`
  - `--image-density`
  - `--image-layout-family`
  - `--inline-count`
  - `--dry-run-images`
- 常用排版参数：
  - `--layout-style auto|clean|cards|magazine|business|warm|poster|tech|blueprint`
  - `--input-format auto|md|html`

## `hosted-run`

- 输入：`--workspace --topic [--article-file] [--title] [--outline-file] [--to render|publish]`
- 依赖：优先使用宿主 agent 已生成正文；若缺失且需要自动补全正文，则必须已配置文本 provider；发布时需要微信凭证
- 输出：写入 research/ideation/article/review/score/image/render/publish 相关产物
- 失败条件：发布前置条件不满足，或自动补全过程失败
- 常用图片参数：
  - `--image-preset`
  - `--image-density`
  - `--image-layout-family`
  - `--inline-count`
  - `--dry-run-images`
- 常用排版参数：
  - `--layout-style auto|clean|cards|magazine|business|warm|poster|tech|blueprint`
  - `--input-format auto|md|html`
- 特殊行为：
  - 若 `--topic` 为空或为“开始”，会先走热点发现并输出选题建议

## `render`

- 输入：`--workspace [--input] [--output article.html] [--accent-color] [--layout-style] [--input-format]`
- 说明：
  - `--layout-style auto` 会根据文章结构（代码/表格/列表等）与 `manifest.image_controls` 自动选型。
  - `--input-format auto` 会按后缀或内容特征识别 Markdown/HTML；HTML 会抽取 `<body>` 后净化再套用主题。
- 输出：
  - `article.html`
  - `article.wechat.html`（公众号发布用，内联样式）

## `discover-topics`

- 输入：`--workspace [--window-hours 12|24] [--limit 8] [--provider auto|google-news-rss|tavily]`
- 依赖：
  - `google-news-rss`：可联网访问 Google News RSS
  - `tavily/auto`：若需 Tavily 回退，配置环境变量 `TAVILY_API_KEY`
- 输出：
  - `topic-discovery.json`
  - `topic-discovery.md`
- 失败条件：数据源不可用或返回为空
- 说明：
  - 用于“无主题启动”，抓最近 12/24 小时热点新闻并给出可写角度、观点提示与标题传播力评分
  - `--provider auto` 默认先用 RSS；RSS 不可用或无结果时，若检测到 `TAVILY_API_KEY` 则自动回退 Tavily

## `plan-images`

- 输入：`--workspace [--provider] [--image-preset] [--image-density] [--image-layout-family] [--inline-count]`
- 依赖：`article.md` 或当前活跃正文存在
- 输出：
  - `image-plan.json`
  - `image-outline.json`
  - `image-outline.md`
  - `prompts/images/*.md`
- 失败条件：找不到正文，或图片 provider 不可用

## `generate-images`

- 输入：`--workspace [--provider] [--dry-run]`
- 依赖：`image-plan.json`
- 执行逻辑：优先读取 `prompts/images/*.md` 中的 `## Prompt` 段落作为最终 Prompt；若缺失则回退到 `image-plan.json`
- 输出：图片文件写入 `assets/images/`，并回写 `image-plan.json`
- 失败条件：找不到 `image-plan.json`，或图片接口调用失败

## 兼容命令

- `ideate`：兼容旧版选题初始化
- `draft`：兼容旧版正文落盘
- `all`：兼容别名，行为等价于 `run`
- `publish` / `verify-draft`：兼容旧版微信发布链路
