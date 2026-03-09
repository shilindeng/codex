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
- 当用户没有明确主题、只说“开始”时，优先先跑热点发现，而不是直接生成正文。
- 默认优先走 `hosted-run --to render`；只有在用户明确要求且文本 provider 已配置时，才优先走 `run --to render`。
- 只有在用户明确确认时才允许 `--to publish --confirmed-publish`。
- 正式发布前必须满足：
  - 工作目录已记录 `publish_intent=true`
  - 显式传入 `--confirmed-publish`
  - 已生成 `article.wechat.html`
- `gemini-web` 仅可在用户明确同意后显式启用，不作为默认自动后端。
- 如用户指定统一图片主题，优先使用 `--image-preset`，让封面图、信息图、正文插图共享同一风格预设。
- 默认图片密度使用 `rich`；除非用户明确要求更少图片，否则保持较丰富但有约束的图文覆盖。
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
  --limit 8
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

## 核心命令

- `research`：生成 `research.json`
- `titles`：生成标题候选并更新 `ideation.json`
- `outline`：生成大纲并更新 `ideation.json`
- `write`：生成 `article.md`
- `review`：生成 `review-report.json` 和 `review-report.md`
- `score`：运行启发式 lint + heuristic score
- `revise`：生成 `article-rewrite.md` 候选稿
- `discover-topics`：联网发现最近 12/24 小时热点新闻与可写选题
- `hosted-run`：宿主 agent 直出正文，再自动继续评分、改写、配图、排版、发布
- `run`：从 research 串到 render，必要时再进入 publish
- `publish` / `verify-draft`：微信草稿箱发布与回读验收
- `ideate` / `draft` / `all`：兼容模式入口

## 图片参数速查

- `--image-preset`：统一主题预设，决定整篇文章的风格母体。
- `--image-density`：配图密度，默认 `rich`。
- `--image-layout-family`：布局家族偏好，用于约束信息图/流程图/对比图的构图路径。
- `--image-theme / --image-style / --image-mood`：少量覆盖统一主题的局部视觉表达。
- `--custom-visual-brief`：补充额外视觉要求。
- `--inline-count`：显式要求正文插图数量。

## 推荐操作习惯

1. 先用 `hosted-run --to render --dry-run-images` 验证整条链路。
2. 如果用户没有主题，先用 `discover-topics` 生成可选方向。
3. 标题不要直接等于 topic，优先看 `title-report.md` 中通过准入的标题。
4. 如果要精修图片，先看 `image-outline.md` 和 `prompts/images/*.md`。
3. 再执行真实 `generate-images`。
4. 发布前先 `--dry-run-publish`。

## 何时读 reference

- 流程与停点：读 `references/workflow.md`
- 命令输入输出矩阵：读 `references/command-matrix.md`
- 工作目录标准产物：读 `references/artifact-contract.md`
- 文本/图片/发布 provider 契约：读 `references/provider-contract.md`
- 评分标准：读 `references/scoring-rubric.md`
- 图片系统：读 `references/image-system.md`
- 微信草稿 API：读 `references/wechat-draft-api.md`
- 来源归因与引用：读 `references/attribution.md`

## 平台适配

- Codex：保留 `agents/openai.yaml`
- ClaudeCode：读 `scripts/adapters/claudecode.md`
- OpenClaw：读 `scripts/adapters/openclaw.md`
- OpenCode：不提供专有目录；只要平台能运行 Python CLI 并消费标准工作目录产物，即可按同一方式接入
