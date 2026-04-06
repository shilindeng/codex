# WeChat Article Studio

这个目录是 `wechat-article-studio` skill 的仓库工作区。

日常使用时，优先看 [SKILL.md](/D:/vibe-coding/codex/my-skill/wechat-article-studio/SKILL.md)。  
细节规则、命令矩阵、产物契约、图片系统和发布接口，优先看 `references/`。

## 维护重点

- 代码入口：`scripts/studio.py`
- 主流程：`scripts/core/workflow.py`
- 图片链路：`scripts/legacy_studio.py`
- 排版皮肤：`scripts/core/layout_skin.py`
- Skill 说明：`SKILL.md`
- UI 元数据：`agents/openai.yaml`

## 验证

```powershell
python -m pytest -q
```

## 排版控制

- 默认会根据文章类型、结构和正文信号自动选择排版框架与视觉皮肤。
- 需要固定皮肤时，可在 `run`、`hosted-run`、`render`、`all` 上显式传入 `--layout-skin <auto|elegant|business|warm|sunrise|tech|chinese|magazine|forest|aurora|morandi|mint|neon>`。
- 只想固定结构、不固定皮肤时，继续使用 `--layout-style`，皮肤仍会按当前文章自动重选。

## 本地安装位置

```text
C:\Users\dsl\.codex\skills\wechat-article-studio
```
