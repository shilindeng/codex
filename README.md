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
- 图片生成：提供 Gemini API Key 或 Gemini Web Cookie，或显式改用 OpenAI 图片接口
- 微信发布：提供 `WECHAT_APP_ID` 和 `WECHAT_APP_SECRET`
- 只有脱离宿主、单独运行 CLI 的场景，才推荐配置 `OPENAI_API_KEY` 和 `ARTICLE_STUDIO_TEXT_MODEL`

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
