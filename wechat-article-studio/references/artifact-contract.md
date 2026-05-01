# 工作目录产物契约

## 导航

- 必备产物
- 关键状态字段
- 产物之间的关系
- 缺失时的处理原则

## 必备产物

- `manifest.json`：状态机与路径索引
- `account-strategy.json`：账号定位、目标读者、首要目标、标题/配图偏好与最小证据要求
- `topic-discovery.json`：最近 12/24 小时热点选题发现结果
- `topic-discovery.md`：面向人读的热点选题建议
- `research.json`：调研输入、来源、证据摘录、信息缺口
- `ideation.json`：标题候选、选中标题、大纲、创作意图
- `title-report.json`：标题打开率评分、准入结果与候选摘要
- `title-decision-report.json`：标题家族、公式拆解、打开率评分、回炉轮次与入选/淘汰原因
- `title-report.md`：面向人读的标题评分摘要
- `content-enhancement.json`：写前增强结果（角度、细节、证据、边界、章节硬要求）
- `content-enhancement.md`：面向人读的写前增强摘要
- `editorial-anchor-plan.json`：建议人工最后补一句的关键位置清单
- `editorial-anchor-plan.md`：面向人读的锚点建议
- `article.md`：当前活跃正文
- `review-report.json`：编辑评审结果
- `review-report.md`：面向人读的评审摘要
- `score-report.json`：启发式评分结果
- `publication.md`：发布前整理后的公众号成品 Markdown
- `publication-report.json`：发布前整理报告（图片限制、技术词、结构化块等）
- `content-fingerprint.json`：当前稿件的结构与路线指纹
- `layout-plan.json`：大纲阶段生成的公众号版式规划
- `layout-plan.md`：面向人读的版式规划；正式发布前必须存在
- `acceptance-report.json`：发布前成品验收结果
- `reader_gate.json`：读者视角门禁，检查首屏、证据、评论点、转发动机与模板腔
- `visual_gate.json`：视觉门禁，检查图片密度、图片分工、首图位置、文字策略与图片资产
- `final_gate.json`：最终质量门禁，汇总评分、读者门、视觉门和验收结果
- `final-delivery-report.json`：最终交付报告，分开记录质量、发布和回读状态
- `final-delivery-report.md`：面向人读的最终交付报告
- `factory-acceptance-report.json` / `.md`：爆款工厂验收结果，明确区分“真合格成品”“已发布但不合格”“待返工”
- `topic-package.json`：选题包，记录热点理由、争议点、受众身份、素材潜力和重复风险
- `material-pack.json`：素材包，记录来源、引用、案例、对比、类比、反方边界和判断表格
- `viral-moment-map.json`：传播点地图，记录首屏钩子、分享句、评论引子、收藏模块和结尾带走内容
- `layout-render-audit.json`：排版与渲染观感检查，记录首图、标题层级、图片密度、表格和来源区块
- `factory-board.json`：可选的工厂看板快照，汇总多个工作目录的状态与批次指标
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

## 发布前硬门槛

正式发布默认必须同时满足：

- `score-report.json.passed = true`
- `acceptance-report.json.passed = true`
- `reader_gate.json.passed = true`
- `visual_gate.json.passed = true`
- `final_gate.json.passed = true`
- `final-delivery-report.json.quality_chain.status = passed`
- `final-delivery-report.json.batch_chain.status = passed`
- `factory-acceptance-report.json.status = passed`
- `layout-plan.json` 与 `layout-plan.md` 都存在
- `image-plan.json` 存在，且计划中的图片资产已落盘
- `publication.md` 与 `article.wechat.html` 都存在

如果用户明确要求强制发布，必须写入 `force_publish_reason`，并在 `final-delivery-report.json` / `final-delivery-report.md` 中标出“已发布但质量门未过”。

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
- `account_strategy_path`
- `account_strategy`
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
- `reader_gate_path`
- `visual_gate_path`
- `final_gate_path`
- `delivery_report_path`
- `delivery_report_markdown_path`
- `quality_chain_status`
- `publish_chain_status`
- `batch_chain_status`
- `canonical_job_id`
- `retry_round`
- `retry_reason`
- `batch_id`
- `batch_stage`
- `factory_board_status`
- `publication_path`
- `publication_report_path`
- `writing_persona`
- `content_enhancement_path`
- `editorial_anchor_plan_path`
- `humanness_signals`
- `research_requirements`
- `publish_intent`
- `force_publish_reason`
- `force_publish_at`
- `content_mode`
- `wechat_header_mode`
- `image_decision_source`
- `image_article_category`
- `image_auto_reason`
- `references_path`
- `corpus_root`
- `max_similarity`
- `fingerprint_findings`

注意：`publish_status=verified` 和 `verify_status=passed` 只说明草稿箱回读成功，不代表文章质量通过。最终对外汇报必须同时看 `final-delivery-report.json` 的 `quality_passed`、`published`、`readback_passed`。

当前还必须同时看三条链：

- `publish_chain.status`
- `quality_chain.status`
- `batch_chain.status`

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
- `opening_four_factors_passed`
- `share_lines`
- `share_line_score`
- `takeaway_module_type`
- `batch_uniqueness_inputs`
- `title_integrity`
- `evidence_readiness`
- `opening_continue_read_risk`
- `publish_blockers`
- `humanness_signals`
- `humanness_score`
- `humanness_findings`
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

当前 `topic-discovery.json` 的候选至少会补充：

- `audience_fit_score`
- `spread_potential_score`
- `consequence_score`
- `repeat_risk_score`
- `topic_package_type`
- `title_direction_candidates`

## 设计约束

- 所有 JSON 使用 UTF-8 和 `ensure_ascii=false`
- 所有平台共享同一套工作目录产物
- 发布器、provider、agent 适配器都不能改写产物契约
