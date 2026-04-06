# WeChat Article Studio

这个目录是 `wechat-article-studio` skill 的仓库工作区。

日常使用时，优先看 [SKILL.md](/D:/vibe-coding/codex/my-skill/wechat-article-studio/SKILL.md)。  
细节规则、命令矩阵、产物契约、图片系统和发布接口，优先看 `references/`。

## 维护重点

- 代码入口：`scripts/studio.py`
- 主流程：`scripts/core/workflow.py`
- 图片链路：`scripts/legacy_studio.py`
- Skill 说明：`SKILL.md`
- UI 元数据：`agents/openai.yaml`

## 验证

```powershell
python -m pytest -q
```

## 本地安装位置

```text
C:\Users\dsl\.codex\skills\wechat-article-studio
```
