# wechat-article-studio

一个面向 Codex / 本地技能体系的微信公众号图文工作流技能。

它覆盖这条完整链路：

- 选题与方向确认
- 正文撰写与评分
- 证据抓取与引用整理
- 封面图、信息图、正文插图生成
- Markdown 汇总与公众号排版
- 发布到微信公众号草稿箱

## 当前版本特点

- 微信发布走 UTF-8 直发，避免 `\uXXXX` 乱码
- 微信发布使用 `article.wechat.html` 专用片段，不再直接发送整页 HTML
- 封面图只用于公众号封面，不进入正文
- 信息图默认放在文末总结区
- 正文插图采用“章节结构 + 字数密度”的混合策略
- 文末引用采用“脚注编号 + 简洁来源列表”

## 目录结构

- `wechat-article-studio/`：技能本体
- `runs/`：本地实战运行产物，不建议提交到 Git

## 本地开发

核心脚本：

- `wechat-article-studio/scripts/studio.py`

常用命令：

```powershell
python wechat-article-studio/scripts/studio.py ideate --help
python wechat-article-studio/scripts/studio.py score --help
python wechat-article-studio/scripts/studio.py plan-images --help
python wechat-article-studio/scripts/studio.py render --help
python wechat-article-studio/scripts/studio.py publish --help
```

语法校验：

```powershell
python -m py_compile wechat-article-studio/scripts/studio.py
```

## 安装到本机技能目录

目标目录：

- `C:\Users\dsl\.codex\skills\wechat-article-studio`

安装后可以在 Codex 环境里直接使用这个 skill。

## 发布前建议

- 先用一篇真实稿件完整跑通：评分、配图、排版、草稿发布
- 确认草稿箱里的最新稿中文、排版、图片和引用区都正常
- 再推送到 GitHub 作为可复用版本
