# Provider 契约

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
- `generate_outline(context) -> dict`
- `generate_article(context) -> str`
- `review_article(context) -> dict`
- `revise_article(context) -> str`

说明：

- 为了兼容 JSON 模式，部分 provider 的 `generate_titles` 可能返回 `{"candidates":[...]}`；CLI 会自动归一化为候选列表。

标题生成要求：

- `topic` 不等于最终标题
- 生成标题后必须经过本地标题评分与准入
- 未通过准入的标题不能优先作为默认 `selected_title`

无配置时要求：

- 在宿主 agent 场景，优先走 `hosted-run`
- 在纯 CLI 场景，`research / titles / outline / write / review / run` 缺配置时必须直接失败，不允许静默产出 placeholder 稿
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
  - “可信度与检索支撑”维度达到最小阈值
  - 当前工作目录不存在 placeholder research / review / article 回退痕迹

## OpenCode 兼容约定

OpenCode 不需要专有目录。只要平台能够：

- 运行 `python scripts/studio.py ...`
- 读取与写入标准工作目录产物
- 透传 provider 所需环境变量

就可以按同一契约接入。
