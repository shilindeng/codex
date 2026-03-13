# Codex 适配约定

- 触发方式：用户明确提到“公众号文章 / 公众号图文 / 草稿箱发布 / 发布验收”，或要求用 `$wechat-article-studio`。
- 推荐入口：优先由当前 Codex 会话直接生成标题、大纲、正文，再执行 `python {SKILL_DIR}/scripts/studio.py hosted-run --workspace <job-dir> --topic "<主题>" --article-file <markdown-path> --to render`。
- 爆款蓝图：建议宿主在写正文前先生成 `viral_blueprint`（核心观点/副观点/说服策略/情绪触发点/金句/情感曲线/论证方式/视角/语言风格等），并写入 `<job-dir>/ideation.json` 的 `outline_meta.viral_blueprint`；否则工作流会回退到启发式蓝图，质量门槛更难通过。
- 正式发布：只有在用户明确确认后，才执行 `--to publish --confirmed-publish`。
- 多轮回炉：`hosted-run/run` 默认最多回炉 3 轮，可用 `--max-revision-rounds` 调整；可选注入样本 `--style-sample sample.md`（可重复）。
- 上下文映射：
  - 用户主题 -> `--topic`
  - 用户方向/切角 -> `--angle`
  - 目标读者 -> `--audience`
  - 用户提供来源 -> `--source-url`
- 输出读取：优先向用户展示 `review-report.md`、`score-report.md`、`article.wechat.html`。
