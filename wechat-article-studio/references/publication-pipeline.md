# 发布前整理链路

## 目标

- 在 `article.md` 和 `article.wechat.html` 之间增加一层成品整理
- 先把正文整理成更适合公众号排版的 `publication.md`
- 再用它继续插图、组装和渲染

## 命令

- `prepare-publication`
  - 输入：`--workspace [--input]`
  - 输出：
    - `publication.md`
    - `publication-report.json`

## 自动接入点

- `render`
- `run`
- `hosted-run`
- `viral-run`

这些命令在进入公众号渲染前都会自动生成或刷新 `publication.md`。

## publication.md 会做什么

- 去掉重复 H1、空洞导语、模板化前置提示
- 清理 AI 标签词和手写参考资料块
- 保留轻引用编号，并在渲染时转成更轻的上标引用
- 控制正文已有图片数量
- 自动把适合结构化的正文整理成：
  - 对比表
  - 数据列表
  - 真代码块

## publication-report.json 关键字段

- `article_archetype`
- `inline_image_limit`
- `kept_existing_image_blocks`
- `removed_existing_image_blocks`
- `technical_terms`
- `reference_count`
- `citation_count`
- `suggested_wechat_style`
- `compare_block_count`
- `stats_block_count`
- `code_block_count`

## 当前默认规则

- 评论 / 分析 / 案例 / 叙事稿：
  - 正文已有图片最多保留 2 张
- 教程稿：
  - 正文已有图片最多保留 3 张
- 最终公众号排版仍然支持多个主题风格
  - 显式传入 `--layout-style / --layout-skin` 时，会保留你选的主题方向
  - 自动模式下，会按正文结构建议更适合的默认风格
- 当前默认建议方向主要包括：
  - `clean`
  - `magazine`
  - `business`
  - `warm`
  - `tech`
  - `blueprint`

## 主题个性化

- `magazine`
  - 更像杂志长文，标题与小标题更有纸感，引用和参考资料更像编辑部版式
- `business`
  - 更像商业简报，标题更利落，引用和来源卡片更像备忘录块
- `warm`
  - 更柔和，标题和引用更有人味，来源区更像延伸阅读
- `tech`
  - 更像技术手册，代码区、引用区、来源按钮都会更偏技术稿气质
