# 工作流总览

## 阶段顺序

1. 收集需求与素材
2. 联网调研与标题提案
3. 用户确认方向
4. 正文写作
5. 多维评分与改写
6. 图片规划与生成
7. 图文汇总与排版
8. 用户确认是否发布
9. 发布到公众号草稿箱
10. 草稿回读验收

## 必须停下来确认的节点

- 标题与方向确认前
- 评分未达标时
- `gemini-web` 非官方方式使用前
- 最终正式发布前

## 默认工作目录结构

```text
job/
├─ manifest.json
├─ ideation.json
├─ article.md
├─ score-report.json
├─ score-report.md
├─ image-plan.json
├─ assembled.md
├─ article.html
├─ article.wechat.html
├─ article.wechat.uploaded.html
├─ publish-result.json
├─ draft-batchget.json
├─ latest-draft-content.html
└─ assets/
   └─ images/
```

## 写作要求

- 开头 2~4 段内建立阅读动机
- 至少有一个清晰主张
- 至少有一个案例、数据、对比或拆解
- 至少有 2 句可划线金句
- 结尾有行动建议、方法总结或价值升维

## 证据与检索

- 提供了 `source_urls` 时，评分与改写阶段要尽量生成 `evidence-report.json`。
- 事实型内容要优先使用外部证据补强，而不是只凭模型自由发挥。

## 图片策略

- 封面图默认只用于公众号封面和 `thumb_media_id`，不进入正文。
- 信息图优先放在总结段或收束段后面。
- 正文插图优先按章节权重、段落密度和信息密度选择 2~4 个位置。
- 自动默认只选官方图片后端：`gemini-api` 优先，其次 `openai-image`。
- `gemini-web` 仅在显式指定 `--provider gemini-web` 时使用。

## 发布策略

- 正式发布必须同时满足：用户明确确认、`publish_intent=true`、命令显式带 `--confirmed-publish`。
- 发布前先预览 `article.wechat.html`。
- 发布时要把正文里的本地图片上传到微信，并把上传后的 HTML 落盘成 `article.wechat.uploaded.html`。
- 发布后必须回读草稿，检查图片数量是否达标、是否残留本地路径、是否生成 `thumb_media_id`。
