# wechat-article-studio

一个面向 Codex / ClaudeCode / OpenClaw 等 agent 场景的微信公众号图文工作流 skill。

## 当前版本能力

- `hosted-run -> score -> revise -> images -> render -> publish`
- `research -> titles -> outline -> write -> review -> score -> revise -> render`
- 微信公众号封面图、信息图、正文插图规划与生成
- Markdown 汇总与公众号 HTML 渲染
- 微信草稿箱发布与回读验收
- 标准工作目录产物，便于跨平台接入

## 目录结构

- `wechat-article-studio/SKILL.md`：精简 skill 主说明
- `wechat-article-studio/references/`：流程、命令矩阵、产物契约、provider 契约
- `wechat-article-studio/scripts/studio.py`：统一 CLI 入口
- `wechat-article-studio/scripts/legacy_studio.py`：旧版 monolith，供兼容后链路复用
- `wechat-article-studio/scripts/core/`：workflow、manifest、score、rewrite、images、render
- `wechat-article-studio/scripts/providers/`：文本与图片 provider 抽象
- `wechat-article-studio/scripts/publishers/`：微信发布器
- `wechat-article-studio/scripts/adapters/`：Codex / ClaudeCode / OpenClaw 接入约定

## 常用命令

```powershell
python wechat-article-studio/scripts/studio.py doctor
python wechat-article-studio/scripts/studio.py hosted-run --workspace runs/demo --topic "AI 时代的个人品牌写作" --to render --image-provider openai-image --dry-run-images
python wechat-article-studio/scripts/studio.py hosted-run --workspace runs/demo --topic "AI 时代的个人品牌写作" --article-file runs/demo/source.md --to render
python wechat-article-studio/scripts/studio.py run --workspace runs/demo --topic "AI 时代的个人品牌写作" --to render
python wechat-article-studio/scripts/studio.py publish --workspace runs/demo --confirmed-publish
python wechat-article-studio/scripts/studio.py verify-draft --workspace runs/demo
```

## 默认接入方式

- Codex / ClaudeCode / OpenClaw：默认由宿主 agent 直接生成 research、标题、大纲、正文，不要求用户额外填写文本模型配置
- 只提供主题也能跑通：`hosted-run` 会优先使用现成 `article.md` / `--article-file`，缺失时再从当前 provider 能力自动补全正文
- 无主题启动也支持：当用户只说“开始”或不提供 topic 时，可先运行 `discover-topics` 联网发现最近 12/24 小时热点，再从建议里二次创作
- 图片生成：提供 Gemini API Key 或 Gemini Web Cookie，或显式改用 OpenAI 图片接口
- 统一图片风格：可选 `--image-preset`，当前内置 `cute / fresh / warm / bold / minimal / retro / pop / notion / chalkboard / editorial-grain / organic-natural / scientific-blueprint / professional-corporate / abstract-geometric / luxury-minimal / illustrated-handdrawn / photoreal-sketch`
- 图片密度模式：支持 `--image-density minimal|balanced|per-section|rich`，默认 `rich`
- 章节级配图控制：支持在正文中写 `<!-- image:force -->`、`<!-- image:skip -->`、`<!-- image:type=流程图 -->`、`<!-- image:count=2 -->`
- 微信发布：提供 `WECHAT_APP_ID` 和 `WECHAT_APP_SECRET`
- 只有脱离宿主、单独运行 CLI 的场景，才推荐配置 `OPENAI_API_KEY` 和 `ARTICLE_STUDIO_TEXT_MODEL`

## 常用参数说明

### 文本与工作流

- `--workspace`：工作目录。所有中间产物、图片、HTML、发布结果都会写到这里。
- `--topic`：文章主题。`hosted-run` 推荐传入；不传或传“开始”时会走热点发现。
- `--angle`：切入角度或文章方向。
- `--audience`：目标读者画像，影响写作语气和配图表达。
- `--source-url`：可重复传入，用于补充研究来源。
- `--title`：显式指定文章标题；不传则从正文或规划过程推断。
- 标题准入：系统会对候选标题做多维爆款评分，并优先选择通过准入阈值的标题作为最终 `selected_title`。
- `--article-file`：宿主 agent 已经写好的 Markdown 正文文件。
- `--outline-file`：可选章节大纲文件，每行一个章节。
- `--to render|publish`：只渲染，或继续走到草稿箱发布。

### 图片规划

- `--image-provider`：图片后端，可选 `gemini-web / gemini-api / openai-image`。
- `--image-preset`：统一视觉主题预设。
- `--image-density`：配图密度，支持 `minimal / balanced / per-section / rich`，默认 `rich`。
- `--image-layout-family`：布局家族偏好，支持 `editorial / process / comparison / timeline / hierarchy / dashboard / map / radial / list`。
- `--image-theme`：覆盖默认主题领域。
- `--image-style`：覆盖默认视觉风格。
- `--image-type`：覆盖图片用途基调。
- `--image-mood`：覆盖整体氛围。
- `--custom-visual-brief`：补充额外视觉要求。
- `--inline-count`：显式要求正文插图数量；系统仍会根据密度模式和章节情况做合理修正。

### 渲染与发布

- `--dry-run-images`：不调用真实图片接口，生成占位图用于验证流程。
- `--dry-run-publish`：不真实发布到微信，只验证发布前置条件并生成 `publish-result.json`。
- `--confirmed-publish`：正式发布必填，避免误发布。
- `--accent-color`：HTML 预览强调色。

## 图片系统怎么工作

图片流程分 3 步：

1. `plan-images`
   - 读取正文，识别章节、信息密度、流程/对比/清单等结构
   - 生成 `image-plan.json`
   - 生成 `image-outline.json` / `image-outline.md`
   - 生成 `prompts/images/*.md`

2. `generate-images`
   - 优先回读 `prompts/images/*.md` 中的 `## Prompt` 段落
   - 你可以先人工改 prompt 文件，再执行真实出图

3. `assemble` / `render`
   - 把图片插回 Markdown
   - 渲染 HTML 和公众号 HTML

## 典型用法

### 1. 宿主 agent 直接写正文，再自动出整套图文

```powershell
python wechat-article-studio/scripts/studio.py hosted-run `
  --workspace runs/demo `
  --topic "AI 时代的个人品牌写作" `
  --article-file runs/demo/source.md `
  --image-preset notion `
  --image-density rich `
  --to render
```

### 2. 只给主题，让系统自动补正文并继续出图

```powershell
python wechat-article-studio/scripts/studio.py hosted-run `
  --workspace runs/demo `
  --topic "如何搭建个人知识管理系统" `
  --image-preset fresh `
  --image-density rich `
  --dry-run-images `
  --to render
```

### 3. 先规划配图，人工微调 prompt，再出图

```powershell
python wechat-article-studio/scripts/studio.py plan-images `
  --workspace runs/demo `
  --provider openai-image `
  --image-preset chalkboard `
  --image-layout-family process `
  --image-density rich

python wechat-article-studio/scripts/studio.py generate-images `
  --workspace runs/demo `
  --provider openai-image
```

### 4. 先 dry-run 发布，确认没问题再正式推草稿箱

```powershell
python wechat-article-studio/scripts/studio.py hosted-run `
  --workspace runs/demo `
  --topic "一篇测试文章" `
  --to publish `
  --dry-run-publish `
  --dry-run-images
```

## 建议的生产方式

- 文本：优先用宿主 agent 产出正文，减少 placeholder 回退风险。
- 图片：先跑 `plan-images`，检查 `image-outline.md` 和 `prompts/images/*.md`，再执行真实出图。
- 发布：先 `--dry-run-publish`，确认封面图、HTML、微信凭证无误，再正式发布。

## 兼容说明

- 旧版 `ideate / draft / score / plan-images / generate-images / assemble / render / publish / verify-draft / all` 仍可用
- `all` 现在是 `run` 的兼容别名
- 根目录 `runs/` 继续作为本地运行产物目录

## 开发校验

```powershell
python -m py_compile wechat-article-studio/scripts/studio.py
python wechat-article-studio/scripts/studio.py run --help
python wechat-article-studio/scripts/studio.py doctor
```
### 5. 无主题启动，先抓热点选题

```powershell
python wechat-article-studio/scripts/studio.py discover-topics `
  --workspace runs/demo `
  --window-hours 24 `
  --limit 8
```

## 标题系统怎么工作

- `topic` 只是主题，不默认等于最终标题。
- `titles` 阶段会生成候选标题，并做多维评分：
  - 钩子强度
  - 具体度
  - 利益点
  - 人群相关性
  - 时效热度
- 只有满足准入阈值的标题，才会被优先选为 `selected_title`。
- 相关产物：
  - `title-report.json`
  - `title-report.md`
