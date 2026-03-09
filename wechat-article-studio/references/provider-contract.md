# Provider 契约

## 文本 provider

默认 provider：`openai-compatible`

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

无配置时要求：

- 命令仍可执行
- 产出占位结构或明确说明缺配置
- 不允许静默跳过

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

## OpenCode 兼容约定

OpenCode 不需要专有目录。只要平台能够：

- 运行 `python scripts/studio.py ...`
- 读取与写入标准工作目录产物
- 透传 provider 所需环境变量

就可以按同一契约接入。
