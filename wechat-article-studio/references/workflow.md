# 工作流总览

## 阶段顺序

0. `discover-topics`：用户无主题（或只说“开始 / 开启公众号创作”）时，先发现最近 12/24 小时热点选题（默认 RSS 优先，必要时 Tavily 回退）
0. `hosted-run`：宿主 agent 生成 research / 标题 / 大纲 / 正文后，继续自动跑后链路
1. `research`：收集主题、来源、信息缺口
   - 默认同时读取 `account-strategy.json`，确认当前账号定位、目标读者、首要目标和最小证据要求
2. `titles`：默认生成 10 个左右标题候选，并做打开率导向的标题决策；必要时自动触发一轮标题回炉
3. `outline`：生成文章大纲与证据需求，并产出爆款策略蓝图 `viral_blueprint`
4. `enhance`：在写作前补角度、细节、证据、边界与写作人格，产出 `content-enhancement.*`
5. `write`：写出 `article.md`（必须消费 `viral_blueprint`、`writing_persona`、`content_enhancement`）
6. `review`：生成结构化编辑拆解（爆款拆解 + 句式提炼 + AI 味问题 + 改稿优先级）
7. `score`：运行启发式评分 + `quality_gates`（硬门槛）+ `humanness_signals`
8. `revise`：低分时按“先补角度/事实/细节/边界，再处理模板腔”的顺序生成候选稿
9. `plan-images` / `generate-images`
10. `assemble` / `render`
11. `publish` / `verify-draft`

## 可移植性约定

- 工作目录和历史语料目录不允许依赖某一台机器的固定盘符。
- 近期语料根目录优先级：
  1. 显式参数
  2. `WECHAT_JOBS_ROOT` / `CODEX_WECHAT_JOBS_ROOT`
  3. 当前工作目录向上查找 `.wechat-jobs` / `wechat-jobs`
- 浏览器用户目录优先级：
  1. `CHROME_USER_DATA_ROOT` / `EDGE_USER_DATA_ROOT`
  2. 系统 `LOCALAPPDATA` 下的通用默认目录
- `.wechat-jobs` 只作为开发期可选回归输入，不作为运行前提。

## 必须停下来确认的节点

- `discover-topics` 产出的候选方向未经用户确认前，不进入正式正文生成
- 标题与方向未确认前，不进入正式发布
- `score` 未达阈值时，不进入正式发布；最多只允许 `--dry-run-publish` 做链路检查
- 评论/案例类稿件未满足最小证据要求时，不进入正式 `render` 或正式发布
- 标题在 `manifest.json`、`ideation.json`、标题报告和成稿之间不一致时，不进入正式发布
- 未通过 `quality_gates`（含“情绪价值/刺痛/金句/去 AI 味/可信度”等硬门槛）时，不进入正式发布
- “可信度与检索支撑”过低，或工作目录里仍存在 placeholder 回退结果时，不进入正式发布
- 宿主导入的 `--article-file` 也必须先过 `enhance + generation-preflight + review + score`
- 启用 `gemini-web` 前，必须先有用户同意
- 图片 provider 未指定时默认 `gemini-web`；用户指定 `codex` 时，必须由当前 Codex agent 使用内置生图工具生成并保存图片，再运行 `generate-images --provider codex` 登记
- 进入 `publish` 前，必须确认用户已明确要求发布到草稿箱
- 未显式传入 `--confirmed-publish` 前，不写入 `publish_intent=true`

## 默认推荐入口

```bash
python {SKILL_DIR}/scripts/studio.py hosted-run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --to render
```

如果宿主已经生成好正文，也可额外传入 `--article-file <agent-generated-markdown>`。

如需控制回炉轮次或注入风格样本：

- `--max-revision-rounds 3`（默认）
- `--style-sample path/to/sample.md`（可重复）

如果已经配置文本 provider，也可继续使用：

```bash
python {SKILL_DIR}/scripts/studio.py run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --to render
```

正式发布追加：

```bash
python {SKILL_DIR}/scripts/studio.py hosted-run \
  --workspace <job-dir> \
  --topic "<主题>" \
  --article-file <agent-generated-markdown> \
  --to publish \
  --confirmed-publish
```
