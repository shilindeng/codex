# 命令矩阵

## `research`

- 输入：`--workspace --topic [--angle] [--audience] [--source-url ...]`
- 依赖：可选文本 provider；无 provider 时产出占位研究包
- 输出：`research.json`
- 失败条件：缺 `--topic`

## `titles`

- 输入：`--workspace [--count 3]`
- 依赖：`research.json` 推荐存在；缺失时用 manifest 信息兜底
- 输出：更新 `ideation.json`
- 失败条件：工作目录不可写

## `outline`

- 输入：`--workspace [--title "..."]`
- 依赖：`research.json`、`ideation.json`
- 输出：更新 `ideation.json`
- 失败条件：工作目录不可写

## `write`

- 输入：`--workspace [--title "..."] [--outline-file ...]`
- 依赖：`research.json`、`ideation.json`
- 输出：`article.md`
- 失败条件：工作目录不可写

## `review`

- 输入：`--workspace`
- 依赖：`article.md`
- 输出：`review-report.json`、`review-report.md`
- 失败条件：找不到文章

## `score`

- 输入：`--workspace [--input ...]`
- 依赖：`article.md` 或指定输入
- 输出：`score-report.json`、`score-report.md`
- 失败条件：找不到文章

## `revise`

- 输入：`--workspace`
- 依赖：`article.md`，推荐先有 `score-report.json`
- 输出：`article-rewrite.md`
- 失败条件：找不到文章

## `run`

- 输入：`--workspace [--topic] [--to render|publish]`
- 依赖：工作目录可写；发布时需要微信凭证
- 输出：从 `research.json` 到 `article.wechat.html`，必要时追加发布产物
- 失败条件：发布前置条件不满足

## `hosted-run`

- 输入：`--workspace --topic [--article-file] [--title] [--outline-file] [--to render|publish]`
- 依赖：优先使用宿主 agent 已生成正文；若缺失则回退到当前 provider 自动补全；发布时需要微信凭证
- 输出：写入 research/ideation/article/review/score/image/render/publish 相关产物
- 失败条件：发布前置条件不满足，或自动补全过程失败

## 兼容命令

- `ideate`：兼容旧版选题初始化
- `draft`：兼容旧版正文落盘
- `all`：兼容别名，行为等价于 `run`
- `publish` / `verify-draft`：兼容旧版微信发布链路
