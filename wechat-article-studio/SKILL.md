---
name: wechat-article-studio
description: 高质量微信公众号图文内容创作与草稿发布技能。覆盖选题调研、标题提案、正文写作、编辑评审、启发式评分、配图规划、公众号排版、草稿箱发布与发布验收。Use when the user asks to create, improve, score, illustrate, format, verify, or publish a WeChat Official Account article / 公众号文章 / 公众号图文, or when the task involves 微信公众号草稿箱、封面图、信息图、插图、Markdown 转公众号 HTML、发布验收。
---

# WeChat Article Studio

面向微信公众号图文的端到端 skill。核心目标是把“选题 -> 写作 -> 评审 -> 评分 -> 配图 -> 排版 -> 草稿发布 -> 回读验收”沉淀成平台无关的标准工作目录与 CLI。

## 语言

- 匹配用户语言。
- 面向微信公众号时，默认产出简体中文内容。

## 快速规则

- 所有脚本位于 `scripts/`，统一入口是 `python {SKILL_DIR}/scripts/studio.py <subcommand> ...`
- 事实、数据、趋势、产品信息相关内容必须联网核验或基于用户提供来源。
- 在 Codex / ClaudeCode / OpenClaw 中，默认由宿主 agent 直接生成 research、标题、大纲、正文，不要求用户填写文本模型配置。
- 当用户没有明确主题、只说“开始 / 开启公众号创作”时：先跑 `discover-topics` 联网发现热点选题与评分；必须让用户先选定编号/方向，再进入后续写作与配图流程。
- 默认优先走 `hosted-run --to render`；只有在用户明确要求且文本 provider 已配置时，才优先走 `run --to render`。
- 只有在用户明确确认时才允许 `--to publish --confirmed-publish`。
- 正式发布前必须满足：
  - 工作目录已记录 `publish_intent=true`（仅在显式确认发布后才会写入）
  - 显式传入 `--confirmed-publish`
  - 已生成 `article.wechat.html`
- 当前工作目录不存在 placeholder research / review / article 回退痕迹
- `score-report.json` 必须过线，且 `quality_gates` 全部通过（含“情绪价值/刺痛/金句/去 AI 味/可信度”等硬门槛）
- `gemini-web` 仅可在用户明确同意后显式启用，不作为默认自动后端。
- `run/hosted-run` 默认启用多轮回炉（每轮 `review -> score -> revise(promote) -> 再 review/score`），上限可用 `--max-revision-rounds` 调整（默认 3）。
- 如需注入仿写风格/高表现样本，可用 `--style-sample path/to/sample.md`（可重复）。
- 如用户指定统一图片主题，优先使用 `--image-preset`，让封面图、信息图、正文插图共享同一风格预设。
- 若用户未明确指定图片主题、图片类型、风格模式或布局家族，不要擅自写死默认 preset / type / layout；应根据文章内容、文风、受众与章节语义自动决策。
- 默认图片密度使用 `balanced`；除非用户明确要求更少/更多图片，否则保持读者友好的图文密度。
- `--image-style-mode` 不再默认写死；未显式传入时，由系统自动在 `uniform` 与 `mixed-by-type` 之间选择。
- 如用户希望图片更偏流程图、对比图、时间轴、仪表板等版式，优先使用 `--image-layout-family` 约束布局家族。
- 如用户在正文中使用 `<!-- image:... -->` 标记，优先按文内标记控制某一章节的配图数量、跳过与图型。
- 不要在最终正文、HTML 预览或公众号 HTML 中自动附加“参考来源 / 参考与延伸”板块。
- 平台适配只影响触发与提示方式，不改变工作目录产物结构。

## 最小工作流

```bash
python {SKILL_DIR}/scripts/studio.py hosted-run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --to render
```

如需先找热点选题：

```bash
python {SKILL_DIR}/scripts/studio.py discover-topics \
  --workspace <job-dir> \
  --window-hours 24 \
  --limit 8 \
  --provider auto \
  --focus ai-tech
```

说明：

- `--provider auto` 回退顺序：Google News RSS -> Custom RSS -> Tavily（如有 `TAVILY_API_KEY`）。
- `custom-rss` 可用 `--rss-url ...` 或环境变量 `DISCOVERY_RSS_URLS`（逗号分隔）配置 RSS/Atom 源。
- `--focus ai-tech`（默认）只关注 AI/科技互联网热点；如需全量热点，用 `--focus all`。

选中候选后继续（写入 `manifest.json`，后续 `hosted-run/run` 会沿用）：

```bash
python {SKILL_DIR}/scripts/studio.py select-topic \
  --workspace <job-dir> \
  --index 1 \
  --angle-index 1
```

如需补强“可信度与检索支撑”，可运行：

```bash
python {SKILL_DIR}/scripts/studio.py evidence \
  --workspace <job-dir> \
  --auto-search
```

如果宿主 agent 已经写好了正文，也可以显式导入：

```bash
python {SKILL_DIR}/scripts/studio.py hosted-run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --article-file <agent-generated-markdown> \
  --to render
```

如需正式发布：

```bash
python {SKILL_DIR}/scripts/studio.py hosted-run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --article-file <agent-generated-markdown> \
  --to publish \
  --confirmed-publish
```

如果宿主环境明确提供文本 API 配置，才使用：

```bash
python {SKILL_DIR}/scripts/studio.py run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --to render
```

说明：

- 纯 CLI 场景下，`run / research / titles / outline / write` 缺少文本 API 配置会直接失败，不再静默产出 placeholder 稿。
- `review / score` 在无文本 API 时允许走本地启发式评审与评分，但不会达到发布门槛。
- `hosted-run` 只有在已提供正文（`article.md` 或 `--article-file`）时，才允许无文本 API 继续；若要自动补正文，仍需要可用文本 API。

## 核心命令

- `research`：生成 `research.json`
- `titles`：生成标题候选并更新 `ideation.json`
- `outline`：生成大纲并更新 `ideation.json`
- `write`：生成 `article.md`
- `review`：生成 `review-report.json` 和 `review-report.md`
- `score`：运行启发式评分 + `quality_gates`，并记录多轮回炉信息
- `revise`：生成改写稿（多轮回炉时为 `article-rewrite-rN.md`，同时保留 `article-rewrite.md` 指向最新一版）
- `select-topic`：从 `topic-discovery.json` 选择候选编号并写入 `manifest.json`
- `discover-topics`：联网发现最近 12/24 小时热点新闻与可写选题
- `evidence`：抽取/补齐来源证据句，生成 `evidence-report.json` 与 `evidence.md`
- `hosted-run`：宿主 agent 直出正文，再自动继续评分、改写、配图、排版、发布
- `run`：从 research 串到 render，必要时再进入 publish
- `publish` / `verify-draft`：微信草稿箱发布与回读验收
- `ideate` / `draft` / `all`：兼容模式入口

## 图片参数速查

- `--image-preset`：统一主题预设，决定整篇文章的风格母体。
- `--image-style-mode`：风格模式：`uniform`（统一）或 `mixed-by-type`（按类型混合）；未传时由系统自动判断。
- `--image-preset-cover / --image-preset-infographic / --image-preset-inline`：仅在 `mixed-by-type` 下生效，分别控制封面/信息图/正文插图的预设。
- `--image-density`：配图密度，默认 `balanced`。
- `--image-layout-family`：布局家族偏好，用于约束信息图/流程图/对比图的构图路径。
- `--image-theme / --image-style / --image-mood`：少量覆盖统一主题的局部视觉表达。
- `--custom-visual-brief`：补充额外视觉要求。
- `--inline-count`：显式要求正文插图数量。

## 排版参数速查

- `--layout-style`：排版主题：`auto|clean|cards|magazine|business|warm|poster|tech|blueprint`（默认 `auto`，会参考文章结构与 `manifest.image_controls` 自动选型）。
- `--input-format`：输入格式：`auto|md|html`（默认 `auto`；HTML 会抽取 `<body>` 并净化后再排版）。
- 主题排版在 `article.html` 与 `article.wechat.html` 均表现为外层底色 + 内层白卡（更接近流行公众号阅读体验）。

## 排版组件（可选）

在 Markdown 中用引用块标记信息卡片（更像公众号编辑稿），示例：

```md
> [!TAKEAWAY] 一句话结论
> 结论内容尽量短、可截图。

> [!TIP] 实操提示
> 给读者一个马上能做的动作。

> [!WARNING] 常见坑
> 提醒读者别踩坑。
```

支持标签：`TIP`、`TAKEAWAY`、`WARNING`、`CHECKLIST`、`MYTHFACT`（大小写不敏感）。

## 推荐操作习惯

1. 先用 `hosted-run --to render --dry-run-images` 验证整条链路。
2. 如果用户没有主题，先用 `discover-topics` 生成可选方向。
3. 标题不要直接等于 topic，优先看 `title-report.md` 中通过准入的标题。
4. 如果要精修图片，先看 `image-outline.md` 和 `prompts/images/*.md`。
5. 如果要判断为什么这篇文章会偏某种出图风格，先看 `image-strategy.json`。
6. 再执行真实 `generate-images`。
7. 发布前先 `--dry-run-publish`。

## 何时读 reference

- 流程与停点：读 `references/workflow.md`
- 命令输入输出矩阵：读 `references/command-matrix.md`
- 工作目录标准产物：读 `references/artifact-contract.md`
- 文本/图片/发布 provider 契约：读 `references/provider-contract.md`
- 评分标准：读 `references/scoring-rubric.md`
- 图片系统：读 `references/image-system.md`
- 图片 prompt 体系：读 `references/image-prompting.md`
- 微信草稿 API：读 `references/wechat-draft-api.md`
- 来源归因与引用：读 `references/attribution.md`

## 平台适配

- Codex：保留 `agents/openai.yaml`
- ClaudeCode：读 `scripts/adapters/claudecode.md`
- OpenClaw：读 `scripts/adapters/openclaw.md`
- OpenCode：不提供专有目录；只要平台能运行 Python CLI 并消费标准工作目录产物，即可按同一方式接入
