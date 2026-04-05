---
name: wechat-article-studio
description: 高质量微信公众号图文内容创作与草稿发布技能。覆盖选题发现、标题生成、作者风格记忆、正文写作、编辑评审、评分改写、配图规划、公众号排版、草稿箱发布与发布验收。Use when the user asks to create, improve, score, imitate a style for, de-AI, format, verify, or publish a WeChat Official Account article / 公众号文章 / 公众号图文，或当任务涉及热点选题、历史去重、风格作战卡、人工改稿学习、Markdown 转公众号 HTML、封面图/信息图/插图、公众号草稿箱与发布验收。
---

# WeChat Article Studio

面向微信公众号内容生产的端到端 skill。目标不是“写出一篇能看完的文章”，而是让系统稳定产出：

- 选题更有新意，不跟最近语料撞车
- 正文更像真人作者，不像统一模板
- 结构有呼吸感，不是固定句式和固定节奏
- 每次写完都能继续学习，而不是下次重新随机发挥

## 核心原则

- 先判断这篇该怎么写，再动笔。
- 先加载 `account-strategy.json`，再做选题、标题、大纲、正文、配图和验收。
- 先读近期语料和作者记忆，再决定标题、开头、小标题、正文推进和结尾。
- 不靠“多加几条禁止规则”赌结果；要显式建立 `editorial_blueprint`。
- 事实、数据、新闻、产品能力、政策变化，必须联网核验或基于用户给出的来源。
- 默认优先 `hosted-run --to render`；只有用户明确要求且文本 provider 已配置时，才优先 `run --to render`。
- 只有在用户明确确认时，才允许 `--to publish --confirmed-publish`。

## 完成标准

完成不是“写完正文”。

一篇可交付的稿子，至少同时满足：

- `account-strategy.json` 已存在且被当前流程读取
- 标题没有撞上最近高频标题模板
- 标题语义完整，没有残句、硬拼接或多份产物不一致
- 前 2~3 段里有具体场景、动作或瞬间
- 中段至少有一处案例、数据或事实托底
- 全文至少有一处反方、误判或适用边界
- 至少保留 1~2 段真正展开的分析段，不是整篇卡片句
- 多个段落起手和小标题句法没有明显重复
- 评论/案例类稿件满足最小证据要求：至少 2 条来源、至少 1 条证据卡
- 正文和首屏没有内部提示语、写作说明或蓝图口吻泄漏
- `review-report.json`、`score-report.json`、`quality_gates` 全部过线
- 发布前已实际跑通渲染、配图、验收链路

## 默认工作流

### 1. 先读作者记忆

进入工作区后，优先读取这些信息：

- 工作区中的 `account-strategy.json`
- 近期语料：自动扫描 `WECHAT_JOBS_ROOT`、`D:\vibe-coding\codex\.wechat-jobs`、`D:\vibe-coding\codex\wechat-jobs`
- 工作区中的 `style-playbook.json` / `style-playbook.md`
- 工作区中的 `author-lessons.json`
- 用户显式传入的 `--style-sample`

系统会自动把这些信息汇总成 `author_memory`，用于约束标题、结构、文风和改稿方向。
其中 `account-strategy.json` 用来约束账号定位、目标读者、首要目标、最小证据要求、默认配图密度和禁用标题套路。

### 2. 用户没给主题时，先做选题发现

如果用户只说“开始 / 开启公众号创作 / 帮我找选题”，先运行：

```bash
python {SKILL_DIR}/scripts/studio.py discover-topics \
  --workspace <job-dir> \
  --window-hours 24 \
  --limit 8 \
  --provider auto \
  --focus ai-tech
```

要求：

- 结合最近语料的标题、关键词和结构，自动给热点候选做“重复风险”降权
- 候选不仅看热度，也看讨论价值、证据潜力、是否值得展开
- 默认先让用户选编号/方向，再进入正文写作
- 如果用户明确说“你自己选”，再直接选综合分最高的一项

### 3. 用户给了样本时，先建风格作战卡

如果用户说“像这个账号写”“先学我的风格”“按这些样本来”，先运行：

```bash
python {SKILL_DIR}/scripts/studio.py build-playbook \
  --workspace <job-dir> \
  --style-sample path/to/sample-a.md \
  --style-sample path/to/sample-b.md
```

它会生成：

- `style-playbook.json`
- `style-playbook.md`

作用：

- 提取标题偏好、开头习惯、结尾习惯、文风指纹、重复句式风险
- 让后续标题、大纲、正文、评审、改写都优先服从这份作者记忆

### 4. 用户给了人工终稿时，先学习改稿偏好

如果用户说“这是我改过的版本，学一下”“以后按这个调性来”，运行：

```bash
python {SKILL_DIR}/scripts/studio.py learn-edits \
  --workspace <job-dir> \
  --draft <ai-draft.md> \
  --final <human-final.md>
```

它会把人工修改沉淀进：

- `author-lessons.json`

后续写作和改稿必须优先服从这些高频偏好，而不是回到通用“公众号爆款腔”。

### 5. 写前先定两份蓝图

每篇文章都要先明确：

- `viral_blueprint`
- `editorial_blueprint`

其中 `editorial_blueprint` 不是装饰字段，它必须决定：

- 标题气质
- 开头方式
- 正文推进
- 小标题写法
- 证据组织
- 结尾收束
- 本篇明确禁止复用的套路

### 6. 再进入正文、评审、改写、配图

默认流程：

```bash
python {SKILL_DIR}/scripts/studio.py hosted-run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --to render
```

系统会自动继续：

- 写前增强（角度、细节、证据、边界、写作人格）
- 评分
- 多轮回炉改写
- 图片规划
- 图片生成
- 汇总插图
- 渲染 `article.html` / `article.wechat.html`

只有当用户明确确认时，才继续：

```bash
python {SKILL_DIR}/scripts/studio.py hosted-run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --to publish \
  --confirmed-publish
```

## 写作硬约束

- 不要默认把每篇文章都写成“先说结论 + 三段方法 + 最后清单”
- 不要默认产出“为什么大多数人……”“真正危险的不是……而是……”“先想清 3 件事”这些旧模板
- 不要让多个段落反复用“很多人 / 你可能 / 如果你”起手
- 不要让整篇小标题都长成同一种问句、编号句或判断句
- 不要整篇只剩短句卡片，必须有展开分析段
- 不要堆裸 URL；正文只留轻引用 `[1][2]`，完整来源放文末参考资料卡片
- 不要手写“金句 1/2/3”标签，不要手写参考资料 callout
- 教程稿才优先动作化结尾；分析稿、评论稿、案例稿优先用判断、余味、风险提醒或趋势观察收束

## 常用命令

- `research`：写入 `research.json`
- `account-strategy.json`：账号定位、读者、目标、图文偏好与证据底线
- `discover-topics`：联网发现热点并生成可写候选
- `select-topic`：把选中的主题/角度写回 `manifest.json`
- `titles`：生成标题候选并自动做去重准入
- `outline`：生成大纲、`viral_blueprint`、`editorial_blueprint`
- `write`：生成 `article.md`
- `review`：生成编辑评审报告
- `score`：运行评分与质量门槛
- `revise`：按评审结果改写，支持 `de-ai`
- `build-playbook`：从风格样本生成作者风格作战卡
- `learn-edits`：从人工改稿里学习偏好
- `hosted-run`：宿主 agent 写正文，CLI 继续执行后半流程
- `run`：文本 provider 负责正文与后半流程
- `publish` / `verify-draft`：公众号草稿箱发布与回读验收

## 推荐操作习惯

1. 先用 `hosted-run --to render --dry-run-images` 跑通整条链路。
2. 如果用户强调“别再像 AI 写的”，优先补 `build-playbook` 或 `learn-edits`，不要只靠 `revise --mode de-ai`。
3. 如果近期文章开始越来越像，先看 `title-report.json`、`recent_corpus_summary`、`author_memory`，再决定是否重写。
4. 如果用户给了历史高表现样本，先把样本转成 `style-playbook`，再写正文。
5. 改稿后再跑一次 `review + score`，不要把第一次低分稿直接推进到配图和发布。

## 何时读 reference

- 流程与停点：读 `references/workflow.md`
- 命令输入输出矩阵：读 `references/command-matrix.md`
- 产物契约：读 `references/artifact-contract.md`
- 评分标准：读 `references/scoring-rubric.md`
- 来源归因与轻引用：读 `references/attribution.md`
- 图片系统与 prompt：读 `references/image-system.md`、`references/image-prompting.md`
- 微信草稿 API：读 `references/wechat-draft-api.md`

## 平台适配

- Codex：保留 `agents/openai.yaml`
- ClaudeCode：读 `scripts/adapters/claudecode.md`
- OpenClaw：读 `scripts/adapters/openclaw.md`
- 只要宿主平台能运行 Python CLI，并消费标准工作目录产物，就能接入
