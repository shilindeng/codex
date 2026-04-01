# WeChat Article Studio

这是一个面向微信公众号图文生产的技能目录，重点不是“把文章写出来”，而是把整条链路做稳：

- 先找题，再判断值不值得写
- 先学作者风格，再决定怎么写
- 写完先预检，再进入评分和改稿
- 最后再配图、排版、发草稿箱

## 这次重构后的重点

### 1. 作者记忆

现在支持把风格样本和人工改稿沉淀成长期记忆，而不是每次临时模仿：

- `build-playbook`
  - 从样本文章里提取标题习惯、文风指纹、常见套路、容易重复的句式
  - 产出 `style-playbook.json` 和 `style-playbook.md`
- `learn-edits`
  - 对比 AI 初稿和人工终稿
  - 把人工高频修改偏好写进 `author-lessons.json`

这些信息会被标题、大纲、正文、评审、改写共同读取。

### 2. 选题去重

热点发现不再只看热度，还会结合近期语料做降重：

- 最近写过的关键词会降权
- 最近高频的标题套路会降权
- 更优先保留有讨论价值、能展开、有证据托底的方向

### 3. 生成阶段收紧

现在不是等评分时才发现文章写歪了。

正文生成时会先带着这些硬约束：

- 开头必须尽量有具体场景、动作或瞬间
- 中段必须有案例、数据或事实托底
- 全文必须有反方、误判或适用边界
- 至少保留一段真正展开的分析段
- 不允许段落起手和小标题老是一个样
- 不允许反复掉回作者明确不用的句式

正文落盘后会立刻生成：

- `generation-preflight.json`
- `generation-preflight.md`

如果预检命中明显模板风险，会先自动预修一轮，再进入正式评分。

### 4. 评分更狠

评分层现在会更明确地打掉这些问题：

- 重复段落起手
- 重复句子起手
- 小标题句法过于单一
- 模板连接词和固定收尾
- 作者记忆里明确禁用的句式

也就是说，现在不只是“分低”，而是会更清楚地告诉你，到底是哪里假、哪里重复、哪里像模板。

## 常用命令

### 生成风格作战卡

```bash
python scripts/studio.py build-playbook \
  --workspace <job-dir> \
  --style-sample path/to/sample-a.md \
  --style-sample path/to/sample-b.md
```

### 学习人工改稿

```bash
python scripts/studio.py learn-edits \
  --workspace <job-dir> \
  --draft <ai-draft.md> \
  --final <human-final.md>
```

### 联网找题

```bash
python scripts/studio.py discover-topics \
  --workspace <job-dir> \
  --window-hours 24 \
  --limit 8 \
  --provider auto \
  --focus ai-tech
```

### 宿主写正文，系统继续后半流程

```bash
python scripts/studio.py hosted-run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --to render
```

### 写前增强

```bash
python scripts/studio.py enhance \
  --workspace <job-dir>
```

这一步会自动补：

- 本篇推荐的写法策略
- 每一节必须落下的细节/证据/边界
- 默认写作人格
- 后续评审时也会自动给出“最后补哪一句最值钱”的锚点建议

### 正式发布到草稿箱

```bash
python scripts/studio.py hosted-run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --to publish \
  --confirmed-publish
```

## 目录说明

- `SKILL.md`
  - 技能主说明
- `agents/openai.yaml`
  - 默认触发提示
- `scripts/core/author_memory.py`
  - 作者记忆、风格作战卡、改稿学习
- `scripts/core/workflow.py`
  - 主流程、生成预检、命令入口
- `scripts/core/viral.py`
  - 评分、模板识别、质量门槛
- `scripts/providers/text/openai_compatible.py`
  - 文本生成提示约束
- `references/`
  - 评分、引用、流程等参考说明
- `tests/`
  - 自动化测试

## 当前建议

如果你最在意“AI 味太重、结构太像、固定句式太多”，推荐默认这样用：

1. 先准备 2 到 5 篇你认可的历史文章，跑 `build-playbook`
2. 如果你手头有人工改过的终稿，再跑 `learn-edits`
3. 再开始 `discover-topics` 或 `hosted-run`

这样出来的结果会比单纯靠一段写作提示稳定很多。
