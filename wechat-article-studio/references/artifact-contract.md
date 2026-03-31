# 工作目录产物契约

## 必备产物

- `manifest.json`：状态机与路径索引
- `topic-discovery.json`：最近 12/24 小时热点选题发现结果
- `topic-discovery.md`：面向人读的热点选题建议
- `research.json`：调研输入、来源、证据摘录、信息缺口
- `ideation.json`：标题候选、选中标题、大纲、创作意图
- `title-report.json`：标题多维评分与准入结果
- `title-decision-report.json`：标题五项联评与入选/淘汰原因
- `title-report.md`：面向人读的标题评分摘要
- `article.md`：当前活跃正文
- `review-report.json`：编辑评审结果
- `review-report.md`：面向人读的评审摘要
- `score-report.json`：启发式评分结果
- `content-fingerprint.json`：当前稿件的结构与路线指纹
- `layout-plan.json`：大纲阶段生成的公众号版式规划
- `acceptance-report.json`：发布前成品验收结果
- `references.json`：标准化引用清单与文末引用卡片数据
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
- `topic_discovery_path`
- `direction`
- `audience`
- `selected_title`
- `title_report_path`
- `title_decision_report_path`
- `title_score`
- `title_gate_passed`
- `source_urls`
- `article_path`
- `viral_blueprint`
- `style_sample_paths`
- `style_signals`
- `revision_round`
- `revision_rounds`
- `best_round`
- `stop_reason`
- `image_outline_path`
- `image_outline_markdown_path`
- `image_prompt_dir`
- `score_total`
- `score_passed`
- `content_fingerprint_path`
- `layout_plan_path`
- `acceptance_report_path`
- `publish_intent`
- `content_mode`
- `wechat_header_mode`
- `image_decision_source`
- `image_article_category`
- `image_auto_reason`
- `references_path`
- `corpus_root`
- `max_similarity`
- `fingerprint_findings`

## `review-report.json` 关键字段

- `summary`
- `strengths`
- `issues`
- `platform_notes`
- `viral_analysis`
- `emotion_value_sentences`
- `pain_point_sentences`
- `ai_smell_findings`
- `revision_priorities`
- `revision_round`
- `review_source`
- `confidence`

## `score-report.json` 关键字段

- `total_score`
- `passed`
- `score_breakdown`
- `quality_gates`
- `interaction_score`
- `score_profile`
- `mandatory_revisions`
- `suggestions`
- `viral_blueprint`
- `viral_analysis`
- `emotion_value_sentences`
- `pain_point_sentences`
- `ai_smell_hits`
- `template_penalty_hits`
- `max_similarity`
- `similar_articles`
- `repeated_phrases`
- `references_summary`
- `citation_findings`
- `similarity_findings`
- `interaction_findings`
- `term_render_issues`
- `layout_rigidity_notes`
- `title_leak_check`
- `revision_rounds`
- `best_round`
- `stop_reason`

## 设计约束

- 所有 JSON 使用 UTF-8 和 `ensure_ascii=false`
- 所有平台共享同一套工作目录产物
- 发布器、provider、agent 适配器都不能改写产物契约
