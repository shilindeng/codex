# ClaudeCode 适配约定

- 触发方式：当任务是“从选题到公众号成稿”的端到端链路时，直接使用本 skill 的 CLI。
- 推荐命令序列：
  - 宿主会话直接生成标题 / 大纲 / 正文
  - `hosted-run --to render`
- 用户上下文映射：
  - conversation goal -> `topic`
  - intended angle -> `angle`
  - target readers -> `audience`
  - supplied links -> `source_urls`
- 交付标准：把工作目录作为状态容器，不依赖 ClaudeCode 专有记忆；默认不要求用户额外填写文本模型配置。
