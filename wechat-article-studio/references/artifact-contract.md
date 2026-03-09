# 工作目录产物契约

## 必备产物

- `manifest.json`：状态机与路径索引
- `research.json`：调研输入、来源、证据摘录、信息缺口
- `ideation.json`：标题候选、选中标题、大纲、创作意图
- `article.md`：当前活跃正文
- `review-report.json`：编辑评审结果
- `review-report.md`：面向人读的评审摘要
- `score-report.json`：启发式评分结果
- `image-plan.json`：配图规划
- `image-outline.json`：结构化插图大纲
- `image-outline.md`：面向人读的插图大纲
- `prompts/images/`：每张图的独立 prompt 文件
- `assembled.md`：图文汇总稿
- `article.html`：普通 HTML 预览
- `article.wechat.html`：公众号兼容 HTML
- `publish-result.json`：发布结果
- `latest-draft-report.json`：草稿回读验收结果

## `manifest.json` 关键字段

- `stage`
- `research_status`
- `title_status`
- `outline_status`
- `draft_status`
- `review_status`
- `score_status`
- `image_status`
- `render_status`
- `publish_status`
- `verify_status`
- `topic`
- `direction`
- `audience`
- `selected_title`
- `source_urls`
- `article_path`
- `image_outline_path`
- `image_outline_markdown_path`
- `image_prompt_dir`
- `score_total`
- `score_passed`
- `publish_intent`

## `review-report.json` 关键字段

- `summary`
- `strengths`
- `issues`
- `platform_notes`

## 设计约束

- 所有 JSON 使用 UTF-8 和 `ensure_ascii=false`
- 所有平台共享同一套工作目录产物
- 发布器、provider、agent 适配器都不能改写产物契约
