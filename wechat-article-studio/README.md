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

## Viral Pipeline

- 新增爆款采集链路：`discover-viral -> select-viral -> collect-viral -> analyze-viral -> viral-run -> adapt-platforms`
- `adapt-platforms` 现在只输出公众号版本，不再生成小红书、微博、B 站版本。
- 当你用新 query 重新跑 `discover-viral` 或 `viral-run` 时，系统会自动清掉旧样本、旧拆解、旧正文、旧评分和 `versions/`，避免串稿。
- 详细说明见 [references/viral-pipeline.md](references/viral-pipeline.md)

## Publication Pipeline

- 新增发布前整理层：`prepare-publication`
- 工作流现在会先把 `article.md` 整理成 `publication.md`，再继续公众号渲染
- 这一步会统一整理技术词、对比块、数据块、引用和正文图片密度
- 公众号成品会优先走更轻的默认风格，并自动挂载文末参考资料卡片
- 最终公众号排版仍然支持多个主题风格；显式传入 `--layout-style / --layout-skin` 时会保留你选的方向
