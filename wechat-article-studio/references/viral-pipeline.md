# 爆款采集链路

## 命令

- `discover-viral`
  - 作用：多平台搜索适合公众号二次创作的爆款样本
  - 主要参数：`--workspace --query [--platform ...] [--limit-per-platform 6]`
  - 输出：`viral-discovery.json`、`viral-discovery.md`
  - 额外行为：如果 query 变了，会自动清掉旧样本、旧正文、旧评分和 `versions/`

- `select-viral`
  - 作用：从发现结果里选中 1~5 篇样本
  - 主要参数：`--workspace [--index ...]`
  - 输出：回写 `manifest.json`

- `collect-viral`
  - 作用：批量抓取全文、字幕、评论和互动数据
  - 主要参数：`--workspace`
  - 输出：`source-corpus.json`

- `analyze-viral`
  - 作用：自动拆爆款基因，并回写写作底稿
  - 主要参数：`--workspace [--topic] [--angle] [--audience]`
  - 输出：`viral-dna.json`、`viral-dna.md`、`research.json`

- `adapt-platforms`
  - 作用：输出公众号版本
  - 主要参数：`--workspace`
  - 输出：
    - `versions/wechat.md`
    - `versions/manifest.json`

- `viral-run`
  - 作用：一键跑完整条“爆款发现 -> 采集 -> 拆解 -> 原创改写 -> 公众号版本”流程
  - 主要参数：`--workspace [--query] [--topic] [--platform ...] [--index ...] [--to render|publish]`

## 默认流程

1. `discover-viral`
2. `select-viral`
3. `collect-viral`
4. `analyze-viral`
5. `titles`
6. `outline`
7. `enhance`
8. `write`
9. `review + score + revise` 多轮回炉
10. `render`
11. `adapt-platforms`

## 关键产物

- `viral-discovery.json`：多平台候选池、推荐样本、渠道状态
- `source-corpus.json`：已选样本的全文、字幕、评论、互动数据
- `viral-dna.json`：标题公式、开头钩子、段落节拍、论证顺序、互动触发点、可借元素、禁用复用元素
- `research.json`：由样本拆解回写的写作底稿
- `similarity-report.json`：来源相似度闸门结果
- `versions/manifest.json`：公众号版本清单

## 相似度闸门

- 连续复用超过 24 个汉字：失败
- 任一来源 5-gram 重合率超过 0.18：失败
- 标题相似度超过 0.55：失败
- 结构路线相似度超过 0.68：失败

相似度闸门会在 `score` 阶段自动生效，并阻止继续进入正式渲染或发布。

## 重置规则

- 新 query 重新跑 `discover-viral` 或 `viral-run` 时，会自动重置旧任务状态
- 会清掉旧的样本池、爆款拆解、正文、评分、相似度报告和 `versions/`
- 这样可以避免上一轮选题残留混进新一轮创作
