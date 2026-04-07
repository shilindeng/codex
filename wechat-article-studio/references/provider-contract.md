# Provider 契约

## 导航

- 文本 provider
- 大纲与蓝图要求
- 正文生成要求
- 结构化评审要求
- 无配置时的行为
- 图片 provider

## 文本 provider

默认接入模式：

1. 宿主 agent 模式：Codex / ClaudeCode / OpenClaw 直接使用当前对话模型生成 research、标题、大纲、正文与编辑意见
2. API 模式：`openai-compatible`

宿主 agent 模式下：

- 不要求用户填写 `OPENAI_API_KEY`
- 不要求用户填写 `ARTICLE_STUDIO_TEXT_MODEL`
- agent 负责把生成结果写入标准工作目录，再调用 `hosted-run`

环境变量：

- `ARTICLE_STUDIO_TEXT_PROVIDER=openai-compatible`
- `ARTICLE_STUDIO_TEXT_MODEL=<model>`
- `ARTICLE_STUDIO_TEXT_BASE_URL=<optional>`
- `OPENAI_API_KEY=<required when calling live model>`

统一接口：

- `generate_research_pack(context) -> dict`
- `generate_titles(context) -> list[dict]`
  - 每项至少包含：`title`, `strategy`, `audience_fit`, `risk_note`
  - 新标题链路推荐补充：`title_family`, `title_formula_components`, `title_emotion_mode`
- `generate_outline(context) -> dict`
- `generate_article(context) -> str`
- `review_article(context) -> dict`
- `revise_article(context) -> str`

说明：

- 为了兼容 JSON 模式，部分 provider 的 `generate_titles` 可能返回 `{"candidates":[...]}`；CLI 会自动归一化为候选列表。

### 大纲与爆款蓝图（强制）

- `generate_outline` 必须返回 `viral_blueprint`，字段必须包含：
  - `core_viewpoint`
  - `secondary_viewpoints`
  - `persuasion_strategies`
  - `emotion_triggers`
  - `target_quotes`
  - `emotion_curve`
  - `emotion_layers`
  - `argument_modes`
  - `perspective_shifts`
  - `style_traits`
  - `pain_points`
  - `emotion_value_goals`

### 正文生成（强制消费蓝图）

- `generate_article` 的输入会包含 `viral_blueprint`；正文必须消费该蓝图并体现：
  - 1 个主观点 + 2~4 个副观点
  - 至少 3 种论证方式（案例/对比/步骤/数据/场景）
  - 至少 2 次视角切换
  - 至少 3 句可截图金句
  - 段落短、句长有波动、避免模板连接词（如：首先/其次/最后/综上所述）

### 结构化评审（强制）

- `review_article` 必须返回结构化字段（用于驱动回炉与硬门槛）：
  - `viral_analysis`（包含核心观点/副观点/说服策略/情绪触发点/金句/情感曲线/情感层次/论证多样性/视角转化/语言风格）
  - `emotion_value_sentences`（对象数组：`text/section_heading/reason/strength`）
  - `pain_point_sentences`（对象数组：`text/section_heading/reason/strength`）
  - `ai_smell_findings`
  - `revision_priorities`

标题生成要求：

- `topic` 不等于最终标题
- 生成标题后必须经过本地标题评分与准入
- 未通过准入的标题不能优先作为默认 `selected_title`

无配置时要求：

- 在宿主 agent 场景，优先走 `hosted-run`
- 在纯 CLI 场景，`research / titles / outline / write / run` 缺配置时必须直接失败，不允许静默产出 placeholder 稿
- `review / score` 在无配置时允许走本地启发式评审与评分，但不会达到发布门槛
- `hosted-run` 只有在宿主已提供 `article.md` / `--article-file` 时才允许无文本 API 继续；若要自动补正文，仍必须有可用文本 API

## 图片 provider

默认自动选择顺序：

1. 用户显式 `--provider`
2. `gemini-api`
3. `openai-image`

`gemini-web` 只能显式启用，且要求用户同意。

## 发布 provider

当前只内置微信发布器：

- 环境变量：`WECHAT_APP_ID`、`WECHAT_APP_SECRET`
- 发布前必须有：
  - `publish_intent=true`
  - `--confirmed-publish`
  - `article.wechat.html`
  - `score-report.json.passed=true`
  - `score-report.json.quality_gates` 全部通过
  - “可信度与检索支撑”维度达到最小阈值
  - 当前工作目录不存在 placeholder research / review / article 回退痕迹

## OpenCode 兼容约定

OpenCode 不需要专有目录。只要平台能够：

- 运行 `python scripts/studio.py ...`
- 读取与写入标准工作目录产物
- 透传 provider 所需环境变量

就可以按同一契约接入。
