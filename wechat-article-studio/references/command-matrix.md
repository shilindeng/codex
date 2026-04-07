# 命令矩阵

## 导航

- `research`
- `titles`
- `outline`
- `enhance`
- `write`
- `review`
- `score`
- `revise`
- `run` / `hosted-run`
- `plan-images` / `generate-images` / `assemble` / `render`
- `publish` / `verify-draft`

## `research`

- 输入：`--workspace --topic [--angle] [--audience] [--source-url ...]`
- 依赖：文本 provider（纯 CLI 场景缺配置会直接失败；宿主模式请改用 `hosted-run` 并由宿主写入 research）
- 输出：`research.json`
- 失败条件：缺 `--topic`

## `titles`

- 输入：`--workspace [--count 10]`
- 依赖：`research.json` 推荐存在；缺失时用 manifest 信息兜底
- 输出：更新 `ideation.json`、`title-report.json`、`title-report.md`
- 失败条件：工作目录不可写
- 说明：
  - 默认生成 10 个候选标题，再自动选择最优标题
  - 候选会带 `title_family / title_formula_components / title_open_rate_score / title_gate_reason`
  - 如果前 3 名都没过线，会自动触发一轮标题专用回炉，再重新决策 `selected_title`

## `outline`

- 输入：`--workspace [--title "..."] [--style-sample ...]`
- 依赖：`research.json`、`ideation.json`
- 输出：更新 `ideation.json`（包含 `outline_meta.viral_blueprint` 与 `viral_blueprint`）
- 失败条件：工作目录不可写

## `enhance`

- 输入：`--workspace [--title "..."] [--style-sample ...]`
- 依赖：`ideation.json` 中最好已有 `outline_meta`
- 输出：
  - `content-enhancement.json`
  - `content-enhancement.md`
- 失败条件：工作目录不可写
- 说明：
  - 自动按篇型选择增强策略：角度发现 / 密度强化 / 细节锚定 / 真实体感
  - 同时写入 `writing_persona`
  - `run` / `hosted-run` 会自动包含这一步

## `write`

- 输入：`--workspace [--title "..."] [--outline-file ...] [--style-sample ...]`
- 依赖：`research.json`、`ideation.json`
- 输出：`article.md`
- 失败条件：工作目录不可写
- 说明：
  - 默认会消费 `writing_persona` 与 `content-enhancement`
  - 如果缺少 `content-enhancement.json`，会先自动补齐

## `review`

- 输入：`--workspace [--style-sample ...]`
- 依赖：`article.md`
- 输出：`review-report.json`、`review-report.md`
- 失败条件：找不到文章
- 说明：
  - 会顺手生成 `editorial-anchor-plan.*`
  - 用来告诉人工如果还想再压一层 AI 味，最后该补哪几句最值钱

## `score`

- 输入：`--workspace [--input ...] [--style-sample ...]`
- 依赖：`article.md` 或指定输入
- 输出：`score-report.json`、`score-report.md`
- 失败条件：找不到文章
- 说明：
  - 额外输出 `humanness_signals / humanness_score / humanness_findings`
  - 不再只查套话，还会检查句长波动、段落节奏、起手重复、章节单一等真人感信号

## `revise`

- 输入：`--workspace [--mode improve-score|explosive-score|de-ai] [--style-sample ...]`
- 依赖：`article.md`，推荐先有 `score-report.json`
- 输出：多轮回炉时会生成 `article-rewrite-rN.md`（并保持 `article-rewrite.md` 指向最新一版），同时生成对应的 `.report.md/.rewrite.json`
- 失败条件：找不到文章
- 补充说明：
  - 当 `--mode de-ai` 且已配置 `HUMANIZERAI_API_KEY` 时，会先走一轮外部 AI 痕迹检测与去味初改，再回到当前 skill 的改稿链路。
  - 外部去味只在 `de-ai` 模式下尝试，不会影响日常 `improve-score` 回炉。

## `run`

- 输入：`--workspace [--topic] [--max-revision-rounds 3] [--style-sample ...] [--to render|publish]`
- 依赖：工作目录可写；需要已配置文本 provider；发布时需要微信凭证
- 输出：从 `research.json` 到 `article.wechat.html`，必要时追加发布产物
- 失败条件：发布前置条件不满足
- 特殊行为：
  - 默认顺序为：`research -> titles -> outline -> enhance -> write -> 多轮回炉 -> render`
  - 多轮回炉：每轮 `review -> score -> revise(promote) -> 再 review/score`，最多 `--max-revision-rounds` 轮；最终保留最佳稿并在 `score-report` 中记录 `revision_rounds/best_round/stop_reason`
- 常用图片参数：
  - `--image-preset`
  - `--image-style-mode`
  - `--image-density`
  - `--image-layout-family`
  - `--inline-count`
  - `--dry-run-images`
- 常用排版参数：
  - `--layout-style auto|clean|cards|magazine|business|warm|poster|tech|blueprint`
  - `--layout-skin auto|elegant|business|warm|sunrise|tech|chinese|magazine|forest|aurora|morandi|mint|neon`
  - `--input-format auto|md|html`

## `hosted-run`

- 输入：`--workspace --topic [--article-file] [--title] [--outline-file] [--max-revision-rounds 3] [--style-sample ...] [--to render|publish]`
- 依赖：优先使用宿主 agent 已生成正文；若缺失且需要自动补全正文，则必须已配置文本 provider；发布时需要微信凭证
- 输出：写入 research/ideation/article/review/score/image/render/publish 相关产物
- 失败条件：发布前置条件不满足，或自动补全过程失败
- 常用图片参数：
  - `--image-preset`
  - `--image-style-mode`
  - `--image-density`
  - `--image-layout-family`
  - `--inline-count`
  - `--dry-run-images`
- 常用排版参数：
  - `--layout-style auto|clean|cards|magazine|business|warm|poster|tech|blueprint`
  - `--layout-skin auto|elegant|business|warm|sunrise|tech|chinese|magazine|forest|aurora|morandi|mint|neon`
  - `--input-format auto|md|html`
- 特殊行为：
  - 若 `--topic` 为空或为“开始”，会先走热点发现并输出选题建议
  - 即使正文来自宿主，也会自动补 `enhance` 并执行更严格的导入预修

## `render`

- 输入：`--workspace [--input] [--output article.html] [--accent-color] [--layout-style] [--layout-skin] [--input-format]`
- 说明：
  - `--layout-style auto` 会根据文章结构（代码/表格/列表等）与 `manifest.image_controls` 自动选型。
  - `--layout-skin auto` 会根据小标题节奏、引用、步骤清单、对比结构和文章气质自动选皮肤；显式传入具体皮肤后会沿用该偏好。
  - `--input-format auto` 会按后缀或内容特征识别 Markdown/HTML；HTML 会抽取 `<body>` 后净化再套用主题。
  - 支持信息卡片标记（Markdown 引用块）：`> [!TIP]`、`> [!TAKEAWAY]`、`> [!WARNING]`、`> [!CHECKLIST]`、`> [!MYTHFACT]`。
- 输出：
  - `article.html`
  - `article.wechat.html`（公众号发布用，内联样式）

## `discover-topics`

- 输入：`--workspace [--window-hours 12|24] [--limit 8] [--provider auto|google-news-rss|custom-rss|tavily] [--rss-url ...] [--focus ai-tech|all]`
- 依赖：
  - `google-news-rss`：可联网访问 Google News RSS
  - `custom-rss`：读取 RSS/Atom 源（可用 `--rss-url` 或环境变量 `DISCOVERY_RSS_URLS` 配置）
  - `tavily/auto`：若需 Tavily 回退，配置环境变量 `TAVILY_API_KEY`
- 输出：
  - `topic-discovery.json`
  - `topic-discovery.md`
- 失败条件：数据源不可用或返回为空
- 说明：
  - 用于“无主题启动”，抓最近 12/24 小时热点新闻并给出可写角度、观点提示与标题传播力评分
  - `--provider auto` 回退顺序：Google RSS -> Custom RSS -> Tavily（如有 `TAVILY_API_KEY`）
  - `--focus ai-tech`（默认）只输出 AI/科技互联网领域；`--focus all` 恢复全量热点

## `select-topic`

- 输入：`--workspace --index [--angle-index] [--angle] [--audience]`
- 依赖：`topic-discovery.json`
- 输出：更新 `manifest.json`、`ideation.json`
- 失败条件：找不到 `topic-discovery.json` 或编号越界
- 说明：
  - 用于“无主题启动”后选择候选编号，并把 `topic/direction/selected_title/source_urls` 写入工作目录
  - 若新选题与旧产物不一致，会重置 `*_status`，避免后续 `run/hosted-run` 因文件存在跳过阶段

## `evidence`

- 输入：`--workspace [--source-url ...] [--limit 6] [--max-items 6] [--auto-search]`
- 依赖：
  - 默认仅基于已有 `manifest.source_urls` 与显式 `--source-url` 抽取证据句
  - `--auto-search`：需要 `TAVILY_API_KEY`，用于自动搜索补齐来源
- 输出：
  - `evidence-report.json`
  - `evidence.md`
  - 回写 `manifest.json/source_urls` 与 `research.json`（补齐 sources/evidence_items）
- 失败条件：无任何来源 URL

## `plan-images`

- 输入：`--workspace [--provider] [--image-preset] [--image-style-mode] [--image-density] [--image-layout-family] [--inline-count]`
- 依赖：`article.md` 或当前活跃正文存在
- 输出：
  - `image-strategy.json`
  - `image-plan.json`
  - `image-outline.json`
  - `image-outline.md`
  - `prompts/images/*.md`
- 失败条件：找不到正文，或图片 provider 不可用
- 说明：
  - 未显式传入图片主题/风格/类型时，会先自动生成文章级视觉策略，再决定整篇图片的视觉方向、风格家族、内容模式与类型倾向。
  - `image-plan.json` 中会写入 `article_visual_strategy`，并为每张图补充 `decision_source / type_reason / style_reason`。

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
