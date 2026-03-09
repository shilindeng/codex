# wechat-article-studio

一个面向 Codex / 本地技能体系的微信公众号图文工作流技能。

它覆盖这条完整链路：

- 选题与方向确认
- 正文撰写与评分
- 证据抓取与引用整理
- 封面图、信息图、正文插图生成
- Markdown 汇总与公众号排版
- 发布到微信公众号草稿箱
- 发布后草稿回读验收

## 当前版本特点

- 微信发布走 UTF-8 直发，避免 `\uXXXX` 乱码
- 微信发布使用 `article.wechat.html` 专用片段，不再直接发送整页 HTML
- 发布时会落盘 `article.wechat.uploaded.html`，方便追查“上传后到底发了什么”
- 发布后支持 `verify-draft` 回读草稿，校验图片数量、本地路径残留和 `thumb_media_id`
- 封面图默认只用于公众号封面，不进入正文
- 图片默认只自动选择官方接口：`gemini-api` 优先，其次 `openai-image`
- `gemini-web` 改为显式 opt-in 的 best-effort 路径

## 支持矩阵

- `Windows / macOS / Linux`：稳定支持 `ideate`、`draft`、`score`、`plan-images`、`assemble`、`render`、`doctor`
- `gemini-api`：稳定路径，推荐优先使用
- `openai-image`：稳定路径，推荐备选
- `gemini-web`：非官方路径，仅显式启用

## 目录结构

- `wechat-article-studio/`：技能本体
- `runs/`：本地实战运行产物，不建议提交到 Git

## 本地开发

核心脚本：

- `wechat-article-studio/scripts/studio.py`

常用命令：

```powershell
python wechat-article-studio/scripts/studio.py doctor
python wechat-article-studio/scripts/studio.py ideate --help
python wechat-article-studio/scripts/studio.py score --help
python wechat-article-studio/scripts/studio.py plan-images --help
python wechat-article-studio/scripts/studio.py render --help
python wechat-article-studio/scripts/studio.py publish --help
python wechat-article-studio/scripts/studio.py verify-draft --help
```

语法校验：

```powershell
python -m py_compile wechat-article-studio/scripts/studio.py
```

## 发布契约

- 评分未达阈值时，`all` 会直接停止，不再继续配图和发布
- 正式发布必须显式带 `--confirmed-publish`
- 正式发布前，工作目录必须已写入 `publish_intent=true`
- 发布后必须检查 `publish-result.json` 和 `verify-draft` 结果

## 安装到本机技能目录

目标目录：

- `C:\Users\dsl\.codex\skills\wechat-article-studio`

安装后可以在 Codex 环境里直接使用这个 skill。
