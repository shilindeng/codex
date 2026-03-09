# OpenClaw 适配约定

- 触发方式：当用户要求自动产出公众号图文、生成配图、排版预览或发布草稿箱时调用。
- 推荐入口：`python {SKILL_DIR}/scripts/studio.py run --workspace <job-dir> --topic "<主题>" --to render`
- 若用户已有正文，可走兼容入口：`draft -> score -> plan-images -> generate-images -> assemble -> render`
- 平台接入要求：
  - 能执行 Python CLI
  - 能读取和写入标准工作目录产物
  - 能透传环境变量给文本 provider、图片 provider、微信发布器
- 工作目录中的标准产物是唯一状态来源，不依赖 OpenClaw 专有会话格式。
