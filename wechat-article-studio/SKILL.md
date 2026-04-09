---
name: wechat-article-studio
description: 高质量微信公众号图文创作与草稿发布技能。用于热点选题、标题筛选、作者风格学习、正文写作、编辑评审、评分回炉、配图规划、公众号排版、草稿箱发布与验收。Use when the user asks to create, improve, score, de-AI, imitate a style for, format, verify, or publish a WeChat Official Account article / 公众号文章 / 公众号图文，或当任务涉及选题发现、历史去重、风格作战卡、人工改稿学习、Markdown 转公众号 HTML、封面图/信息图/插图、草稿箱发布与发布验收。
---

# WeChat Article Studio

面向微信公众号内容生产的端到端 skill。目标不是先凑出一篇稿子，而是把选题、写作、评审、配图、排版、发布整条链路做稳。

## 何时触发

- 用户要写、改、评、发微信公众号文章或图文。
- 用户要做热点选题、标题筛选、历史去重。
- 用户要模仿某个账号或作者风格，或先学习人工改稿偏好。
- 用户要把 Markdown 转成公众号 HTML，或要做配图、排版、草稿箱发布、回读验收。

## 核心原则

- 先判断这篇该怎么写，再动笔。
- 先加载 `account-strategy.json`、近期语料和作者记忆，再做标题、大纲、正文、配图和验收。
- 显式建立 `viral_blueprint` 和 `editorial_blueprint`，不要靠临时补禁用词赌结果。
- 事实、数据、新闻、产品能力、政策变化，必须联网核验或基于用户给出的来源。
- 默认优先 `hosted-run --to render`。只有用户明确要求且文本 provider 已配置时，才优先 `run --to render`。
- 只有在用户明确确认时，才允许 `--to publish --confirmed-publish`。

## 默认流程

### 1. 先读账号策略和作者记忆

优先读取：

- `account-strategy.json`
- `style-playbook.json` / `style-playbook.md`
- `author-lessons.json`
- `--style-sample`
- 近期语料汇总出的 `recent_corpus_summary` 与 `author_memory`

### 2. 用户没给主题时，先做选题发现

```bash
python {SKILL_DIR}/scripts/studio.py discover-topics --workspace <job-dir> --window-hours 24 --limit 8 --provider auto --focus ai-tech
```

- 选题要同时考虑热度、讨论价值、证据潜力和近期重复风险。
- 默认先让用户选方向；只有用户明确说“你直接定”时，才自动选分数最高的候选。

### 3. 用户给了风格样本时，先建风格作战卡

```bash
python {SKILL_DIR}/scripts/studio.py build-playbook --workspace <job-dir> --style-sample path/to/sample-a.md --style-sample path/to/sample-b.md
```

它会生成 `style-playbook.json` 和 `style-playbook.md`，后续标题、大纲、正文、评审、改写都优先服从这份作者记忆。

### 4. 用户给了人工终稿时，先学习改稿偏好

```bash
python {SKILL_DIR}/scripts/studio.py learn-edits --workspace <job-dir> --draft <ai-draft.md> --final <human-final.md>
```

它会把人工修改沉淀进 `author-lessons.json`，后续写作和改稿优先服从这些高频偏好。

### 5. 写前先定两份蓝图

每篇文章都要先明确 `viral_blueprint` 和 `editorial_blueprint`。其中 `editorial_blueprint` 必须决定标题气质、开头方式、正文推进、小标题写法、证据组织和结尾收束。

### 6. 再进入正文、评审、改写、配图、排版

默认优先：

```bash
python {SKILL_DIR}/scripts/studio.py hosted-run --workspace <job-dir> --topic "<主题>" --to render
```

系统会自动继续写前增强、评分、多轮回炉改写、图片规划、图片生成、插图回填和公众号渲染。

只有用户明确确认时，才继续：

```bash
python {SKILL_DIR}/scripts/studio.py hosted-run --workspace <job-dir> --topic "<主题>" --to publish --confirmed-publish
```

## 成品标准

- 标题不过度撞近期高频模板，语义完整，不硬拼。
- 前 2~3 段里要有具体场景、动作或瞬间。
- 中段至少有一处案例、数据或事实托底。
- 全文至少有一处反方、误判或适用边界。
- 至少保留 1~2 段真正展开的分析段。
- 正文和首屏不能泄漏内部提示语或写作说明。
- `review-report.json`、`score-report.json`、`quality_gates` 全部过线。
- 发布前要实际跑通渲染、配图和验收链路。

## 硬约束

- 不要默认写成“先说结论 + 三段方法 + 最后清单”。
- 不要反复复用“为什么大多数人……”“真正危险的不是……而是……”“先想清 3 件事”这类旧模板。
- 不要让多个段落反复用“很多人 / 你可能 / 如果你”起手。
- 不要让整篇小标题都长成同一种问句、编号句或判断句。
- 不要整篇只剩短句卡片，必须保留展开分析段。
- 不要裸贴 URL，也不要手写参考资料 callout。
- 教程稿才优先动作化结尾；分析稿、评论稿、案例稿优先用判断、余味、风险提醒或趋势观察收束。

## 图片策略

- 封面图、正文插图、分隔图默认无字。
- 流程图、信息图、对比图允许极少量短中文标签。
- 图片文字策略以账号策略和图片类型共同决定，不要一刀切。
- 默认保持整篇视觉语言一致；只有在用途明显不同的图型上，才允许轻微分化。

## 何时读 references

- 流程与停点：读 [references/workflow.md](references/workflow.md)
- 命令输入输出矩阵：读 [references/command-matrix.md](references/command-matrix.md)
- 产物契约：读 [references/artifact-contract.md](references/artifact-contract.md)
- 评分标准：读 [references/scoring-rubric.md](references/scoring-rubric.md)
- 来源归因与轻引用：读 [references/attribution.md](references/attribution.md)
- 发布前 Markdown 整理与公众号成品链路：读 [references/publication-pipeline.md](references/publication-pipeline.md)
- 图片系统与 prompt：读 [references/image-system.md](references/image-system.md)、[references/image-prompting.md](references/image-prompting.md)
- Provider 约束：读 [references/provider-contract.md](references/provider-contract.md)
- 微信草稿 API：读 [references/wechat-draft-api.md](references/wechat-draft-api.md)

## 平台适配

- Codex：使用 `agents/openai.yaml`
- ClaudeCode：读 `scripts/adapters/claudecode.md`
- OpenClaw：读 `scripts/adapters/openclaw.md`
- 只要宿主平台能运行 Python CLI，并消费标准工作目录产物，就能接入
