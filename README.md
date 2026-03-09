# wechat-article-studio

一个面向 Codex / ClaudeCode / OpenClaw 等 agent 场景的微信公众号图文工作流 skill。

## 当前版本能力

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
python wechat-article-studio/scripts/studio.py run --workspace runs/demo --topic "AI 时代的个人品牌写作" --to render --image-provider openai-image --dry-run-images
python wechat-article-studio/scripts/studio.py publish --workspace runs/demo --confirmed-publish
python wechat-article-studio/scripts/studio.py verify-draft --workspace runs/demo
```

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
