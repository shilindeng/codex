---
name: wechat-article-studio
description: 高质量微信公众号图文内容创作与草稿发布技能。覆盖选题调研、联网搜索、3 个爆款标题、创作方向确认、正文撰写、多维评分、封面图/信息图/插图规划与生成、Markdown/HTML 汇总、公众号精美排版与微信公众号草稿箱发布。Use when the user asks to create, improve, score, illustrate, format, or publish a WeChat Official Account article / 公众号文章 / 公众号图文, or when the task involves 微信公众号草稿箱、公众号封面图、信息图、插图、Markdown 转公众号 HTML、AppID/Secret 发布流程。
---

# WeChat Article Studio

为微信公众号长文创作提供端到端工作流：`选题 → 正文 → 评分 → 配图 → 汇总 → 排版 → 草稿发布`。

## 语言

- 匹配用户语言。
- 面向微信公众号时，默认产出简体中文内容。

## 脚本目录

- 所有脚本位于 `scripts/` 子目录。
- 先确定本 `SKILL.md` 所在目录为 `SKILL_DIR`。
- 主脚本路径：`{SKILL_DIR}/scripts/studio.py`
- 统一调用方式：`python {SKILL_DIR}/scripts/studio.py <subcommand> ...`

## 核心原则

- 先确认标题和方向，再写正文。
- 涉及事实、数据、行业趋势、产品信息时，必须联网检索。
- 评分未达阈值前，不进入配图与发布。
- 未经用户明确确认，不得发布到公众号草稿箱。
- 若使用 `gemini-web` 图片后端，必须先告知其为非官方方式，并取得用户明确同意。

## 工作流

### 1. 收集输入

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

创建工作目录并保存基础元信息：

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

### 2. 选题与方向确认

- 联网搜索并分析用户主题。
- 输出 3 个爆款标题。
- 输出创作方向建议和文章提纲。
- 在用户确认标题与方向之前停止，不要提前写正文。

把选题结果回填到工作目录：

```bash
python {SKILL_DIR}/scripts/studio.py ideate \
  --workspace <job-dir> \
  --topic "<主题>" \
  --title "<标题1>" \
  --title "<标题2>" \
  --title "<标题3>" \
  --selected-title "<用户确认标题>" \
  --outline-file <outline.txt>
```

### 3. 正文创作

- 文章必须有强开头、强钩子、清晰结构、真实支撑、结尾行动引导。
- 优先兼顾深度、传播性、可读性和公众号阅读习惯。
- 涉及事实信息时在文末加入来源区。

把正文写入工作目录：

```bash
python {SKILL_DIR}/scripts/studio.py draft \
  --workspace <job-dir> \
  --input <article.md> \
  --selected-title "<用户确认标题>"
```

### 4. 评分闭环

运行评分脚本，读取 `score-report.json` 与 `score-report.md`：

```bash
python {SKILL_DIR}/scripts/studio.py score --workspace <job-dir>
```

- 默认阈值 `85`。
- 重点检查：开头吸引力、钩子设计、金句质量、文风适配度。
- 低于阈值时，先按报告修订，再重新评分。
- 达标或用户明确放行后，才进入配图。

评分细则见 `references/scoring-rubric.md`。

### 5. 图片规划与生成

先生成图片规划：

```bash
python {SKILL_DIR}/scripts/studio.py plan-images --workspace <job-dir>
```

默认规划：

- `1` 张封面图
- `1` 张开局信息图
- `2~4` 张正文插图

图片四维参数：

- `theme`：科技 / 商业 / 职场 / 教育 / 财经 / 健康 / 品牌 / 生活方式
- `style`：极简扁平 / 高级摄影 / 杂志封面 / 手绘插画 / 国潮 / 未来科技 / 3D / 信息可视化
- `type`：封面图 / 正文插图 / 信息图 / 分隔图
- `mood`：专业理性 / 温暖治愈 / 高能激励 / 悬念冲突 / 高级克制 / 轻松幽默

然后生成图片：

```bash
python {SKILL_DIR}/scripts/studio.py generate-images --workspace <job-dir>
```

支持三种图片后端：

- `gemini-web`
- `gemini-api`
- `openai-image`

默认优先级：

1. 用户显式指定 `--provider`
2. 检测到 `GEMINI_WEB_COOKIE` / `GEMINI_WEB_COOKIE_PATH` / `GEMINI_WEB_CHROME_PROFILE_DIR`
3. 检测到 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`
4. 检测到 `OPENAI_API_KEY`

#### `gemini-web` 同意检查

使用 `gemini-web` 前必须先说明：

- 这是参考 `baoyu-danger-gemini-web` 的非官方方式。
- 可能因网页或接口变化失效。
- 只有用户明确接受后才可继续。

同意后写入本地同意文件：

```bash
python {SKILL_DIR}/scripts/studio.py consent --accept
```

如用户拒绝，停止 `gemini-web` 路径，改用官方后端或暂停图片生成。

图片系统说明见 `references/image-system.md`。

### 6. 汇总图文与公众号排版

将图片插回 Markdown：

```bash
python {SKILL_DIR}/scripts/studio.py assemble --workspace <job-dir>
```

再渲染公众号 HTML：

```bash
python {SKILL_DIR}/scripts/studio.py render --workspace <job-dir>
```

- 输出 `assembled.md` 和 `article.html`。
- HTML 仅使用公众号兼容标签与内联样式。
- 发布前先给用户预览排版结果。

### 7. 发布到公众号草稿箱

只有在用户明确确认发布时才执行：

```bash
python {SKILL_DIR}/scripts/studio.py publish --workspace <job-dir>
```

默认读取环境变量：

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`

发布时自动：

- 上传封面图并生成 `thumb_media_id`
- 上传正文内本地图片到微信
- 将 HTML 发送到草稿箱接口
- 产出 `publish-result.json`

发布细节见 `references/wechat-draft-api.md`。

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
- `publish-result.json`（发布后）

## 推荐子命令顺序

```bash
python {SKILL_DIR}/scripts/studio.py ideate --workspace <job-dir> ...
python {SKILL_DIR}/scripts/studio.py draft --workspace <job-dir> --input <article.md>
python {SKILL_DIR}/scripts/studio.py score --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py plan-images --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py generate-images --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py assemble --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py render --workspace <job-dir>
python {SKILL_DIR}/scripts/studio.py publish --workspace <job-dir>
```

## 参考资料

- `references/workflow.md`
- `references/scoring-rubric.md`
- `references/image-system.md`
- `references/wechat-draft-api.md`
- `references/attribution.md`
## ??????

- ???????? `source_urls` ? `score` ?????????????????????????? `evidence-report.json`???????? `article-rewrite.md`?
- ???????????????????????????????????????????
## ???????????

- ???????????? `thumb_media_id`??????????
- ????????????? + ???????????????????????????
- ? `source_urls` ? `evidence-report.json` ????????????????????????????????
- ???????? `article.wechat.html`??????????????????????
