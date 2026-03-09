---
name: wechat-article-studio
description: 高质量微信公众号图文内容创作与草稿发布技能。覆盖选题调研、联网搜索、3 个爆款标题、创作方向确认、正文撰写、多维评分、封面图/信息图/插图规划与生成、Markdown/HTML 汇总、公众号精美排版、草稿箱发布、发布后草稿回读验收。Use when the user asks to create, improve, score, illustrate, format, verify, or publish a WeChat Official Account article / 公众号文章 / 公众号图文, or when the task involves 微信公众号草稿箱、公众号封面图、信息图、插图、Markdown 转公众号 HTML、发布验收、AppID/Secret 发布流程。
---

# WeChat Article Studio

为微信公众号长文创作提供端到端工作流：`选题 → 正文 → 评分 → 配图 → 汇总 → 排版 → 草稿发布 → 草稿回读验收`。

## 语言

- 匹配用户语言。
- 面向微信公众号时，默认产出简体中文内容。

## 脚本目录

- 所有脚本位于 `scripts/` 子目录。
- 先确定本 `SKILL.md` 所在目录为 `SKILL_DIR`。
- 主脚本路径：`{SKILL_DIR}/scripts/studio.py`
- 统一调用方式：`python {SKILL_DIR}/scripts/studio.py <subcommand> ...`

## 关键规则

- 先确认标题和方向，再写正文。
- 涉及事实、数据、行业趋势、产品信息时，必须联网检索。
- 评分未达阈值前，不进入配图与发布。
- 未经用户明确确认，不得发布到公众号草稿箱。
- 正式发布时必须显式传入 `--confirmed-publish`。
- 正式发布前，工作目录必须已经记录 `publish_intent=true`。
- 发布后必须运行或确认 `verify-draft` 验收结果。
- 封面图默认只用于 `thumb_media_id`，不进入正文。
- 默认自动图片后端只选择官方接口：`gemini-api` 优先，其次 `openai-image`。
- `gemini-web` 仅在用户显式传入 `--provider gemini-web` 时启用，且必须先说明它是非官方 best-effort 方案并取得明确同意。

## 支持矩阵

- `Windows / macOS / Linux`：稳定支持 `ideate`、`draft`、`score`、`plan-images`、`assemble`、`render`、`doctor`。
- `gemini-api`：稳定路径，推荐优先使用。
- `openai-image`：稳定路径，推荐作为备选。
- `gemini-web`：非官方路径，仅显式启用，不作为自动默认。

## 推荐工作流

### 1. 初始化与方向确认

至少收集这些字段：

- `topic`
- `direction`
- `audience`
- `goal`
- `source_urls`（可选）
- `score_threshold`（默认 `85`）
- `image_theme`
- `image_style`
- `image_type`
- `image_mood`
- `custom_visual_brief`（可选）
- 是否最终发布到公众号草稿箱

初始化工作目录：

```bash
python {SKILL_DIR}/scripts/studio.py ideate \
  --workspace <job-dir> \
  --topic "<主题>" \
  --direction "<方向>" \
  --audience "<读者>" \
  --goal "<目标>" \
  --score-threshold 85 \
  --image-theme "科技" \
  --image-style "未来科技" \
  --image-type "封面图" \
  --image-mood "专业理性"
```

用户确认要正式发布时，再把发布意图写进工作目录：

```bash
python {SKILL_DIR}/scripts/studio.py ideate --workspace <job-dir> --topic "<主题>" --publish-intent
```

### 2. 正文与评分闭环

- 在用户确认标题与方向之前停止，不要提前写正文。
- 文章必须有强开头、强钩子、清晰结构、真实支撑、结尾行动引导。
- 涉及事实信息时在文末加入来源区。

```bash
python {SKILL_DIR}/scripts/studio.py draft --workspace <job-dir> --input <article.md>
python {SKILL_DIR}/scripts/studio.py score --workspace <job-dir>
```

- 默认阈值 `85`。
- 低于阈值时，先按报告修订，再重新评分。
- 达标或用户明确放行后，才进入配图。

### 3. 图片规划与生成

```bash
python {SKILL_DIR}/scripts/studio.py plan-images --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py generate-images --workspace <job-dir>
```

默认规划：

- `1` 张封面图
- `1` 张信息图
- `2~4` 张正文插图

默认自动后端优先级：

1. 用户显式指定 `--provider`
2. 检测到 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`
3. 检测到 `OPENAI_API_KEY`

如果要走 `gemini-web`，必须显式传参：

```bash
python {SKILL_DIR}/scripts/studio.py consent --accept
python {SKILL_DIR}/scripts/studio.py generate-images --workspace <job-dir> --provider gemini-web
```

### 4. 汇总、排版与预览

```bash
python {SKILL_DIR}/scripts/studio.py assemble --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py render --workspace <job-dir>
```

- 输出 `assembled.md`、`article.html`、`article.wechat.html`。
- HTML 仅使用公众号兼容标签与内联样式。
- 发布前先给用户预览排版结果。

### 5. 发布与验收

正式发布：

```bash
python {SKILL_DIR}/scripts/studio.py publish --workspace <job-dir> --confirmed-publish
```

发布后单独验收：

```bash
python {SKILL_DIR}/scripts/studio.py verify-draft --workspace <job-dir>
```

发布时会自动：

- 上传封面图并生成 `thumb_media_id`
- 上传正文内本地图片到微信
- 落盘 `article.wechat.uploaded.html`
- 调用草稿箱接口
- 回读最新草稿并校验图片数量、本地路径残留、`thumb_media_id`
- 产出 `publish-result.json`

## 推荐子命令顺序

```bash
python {SKILL_DIR}/scripts/studio.py ideate --workspace <job-dir> ...
python {SKILL_DIR}/scripts/studio.py draft --workspace <job-dir> --input <article.md>
python {SKILL_DIR}/scripts/studio.py score --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py plan-images --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py generate-images --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py assemble --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py render --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py publish --workspace <job-dir> --confirmed-publish
python {SKILL_DIR}/scripts/studio.py verify-draft --workspace <job-dir>
```

## 常用辅助命令

环境自检：

```bash
python {SKILL_DIR}/scripts/studio.py doctor
```

一键串联：

```bash
python {SKILL_DIR}/scripts/studio.py all --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py all --workspace <job-dir> --publish --confirmed-publish
```

## 统一产物

每个工作目录至少保留：

- `manifest.json`
- `ideation.json`
- `article.md`
- `score-report.json`
- `score-report.md`
- `image-plan.json`
- `assembled.md`
- `article.html`
- `article.wechat.html`
- `article.wechat.uploaded.html`（发布后）
- `publish-result.json`（发布后）
- `draft-batchget.json`（验收后）
- `latest-draft-content.html`（验收后）

## 参考资料

- `references/workflow.md`
- `references/scoring-rubric.md`
- `references/image-system.md`
- `references/wechat-draft-api.md`
- `references/attribution.md`
