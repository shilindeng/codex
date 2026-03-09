# 工作流总览

## 阶段顺序

1. `research`：收集主题、来源、信息缺口
2. `titles`：生成 3 个左右标题候选
3. `outline`：生成文章大纲与证据需求
4. `write`：写出 `article.md`
5. `review`：生成编辑评审报告
6. `score`：运行启发式评分与低分改写候选
7. `revise`：在低分时生成 `article-rewrite.md`
8. `plan-images` / `generate-images`
9. `assemble` / `render`
10. `publish` / `verify-draft`

## 必须停下来确认的节点

- 标题与方向未确认前，不进入正式发布
- `score` 未达阈值但用户要求继续发布时，必须明确说明风险
- 启用 `gemini-web` 前，必须先有用户同意
- 进入 `publish` 前，必须确认用户已明确要求发布到草稿箱

## 默认推荐入口

```bash
python {SKILL_DIR}/scripts/studio.py run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --to render
```

正式发布追加：

```bash
python {SKILL_DIR}/scripts/studio.py run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --to publish \
  --confirmed-publish
```
