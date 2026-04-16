# 评分细则

默认满分 `100`。当前正式评分口径已经改成三组分数和硬门槛联合判定。

## 分组与权重

- 爆款潜力 `50`
- 阅读完成度 `30`
- 去 AI 味与真人感 `20`

### 爆款潜力

- 标题与首屏打开欲 `14`
- 核心判断与新鲜度 `12`
- 可转述谈资与金句质量 `10`
- 评论与传播触发 `8`
- 峰值时刻设计 `6`

### 阅读完成度

- 中段推进与结构张力 `12`
- 事实/案例/对比托底 `10`
- 结尾收束自然度 `8`

### 去 AI 味与真人感

- 模板腔控制 `8`
- 句式和段落节奏 `6`
- 具体处境/边界/反方 `6`

## 硬门槛

正式通过不只看总分，还必须同时满足：

- `total_score >= threshold`
- `hook_layer_passed = true`
- `insight_layer_passed = true`
- `takeaway_layer_passed = true`
- `title_integrity_passed = true`
- `credibility_passed = true`
- `evidence_minimum_passed = true`
- `prompt_leak_passed = true`
- `similarity_passed = true`
- `citation_policy_passed = true`
- `editorial_review_passed = true`
- `naturalness_floor_passed = true`
- `reading_flow_passed = true`
- `hook_quality_passed = true`
- `ending_naturalness_passed = true`
- `material_coverage_passed = true`
- 如果启用了来源相似度闸门，还要 `source_similarity_passed = true`

## 素材覆盖门槛

评论稿、案例稿、分析稿默认要满足：

- 至少 `4` 类素材
- 至少 `1` 个 Markdown 表格
- 至少 `2` 处来源化表达或引用
- 至少 `1` 段类比分析
- 至少 `1` 段对比分析

素材覆盖信号会单独写进 `material_signals`，并直接影响修改建议。

## 报告字段

当前 `score-report.json` 至少会输出：

- `schema_version`
- `body_signature`
- `score_groups`
- `virality_score`
- `publishability_score`
- `naturalness_score`
- `persona_fit_score`
- `hook_layer_score`
- `insight_layer_score`
- `takeaway_layer_score`
- `layer_score_breakdown`
- `three_layer_diagnostics`
- `material_signals`
- `ai_fingerprint_summary`
- `quality_gates`
- `mandatory_revisions`
- `publish_blockers`

## AI 指纹口径

- 评分不再只看“有没有模板词”，还会看更像 `dbskill` 的 AI 指纹。
- 强信号优先打：开头先自我介绍、开头三件套、替读者预设观点再纠正、结尾祝福腔、用身体感受代替论证。
- 中信号继续压：翻译腔、连接词过密、概念命名仪式、深刻感用力过猛、故事只有壳没有细节。
- 如果 `ai_fingerprint_summary.strong_count >= 1`，默认把这篇稿子视为还没过真人感底线，优先回炉，不要急着提分。

## 低分处理顺序

1. 先修标题、首屏和中段推进
2. 再补表格、引用、类比、对比、边界
3. 再补 takeaway，让结尾有可收藏、可复用的带走内容
4. 再清理模板腔和句式节奏
5. 最后才补自然传播点和结尾收束

## 三层结构直判

- `hook`：标题 + 前两段是否能让人停下来。
- `认知增量`：中段是否交付新判断、信息差或可复用方法。
- `takeaway`：最后 15%~20% 正文里是否落下可收藏、可复用、可转发的带走内容。

当前通过标准不是“整体看着像篇完整文章”，而是三层都必须能明确指出落点。

## 选最优版本

多轮回炉时，不再优先选“更炸”的版本，固定按这个顺序选：

1. 先看硬门槛是否通过
2. 再看阅读完成度
3. 再看去 AI 味与真人感
4. 最后才看爆款潜力
