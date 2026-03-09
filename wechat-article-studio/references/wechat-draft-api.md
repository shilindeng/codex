# 微信公众号草稿发布

## 默认环境变量

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`

## 发布顺序

1. 获取 `access_token`
2. 上传封面图，得到 `thumb_media_id`
3. 上传正文内图片并替换 HTML 中的本地路径
4. 落盘上传后的 `article.wechat.uploaded.html`
5. 调用草稿箱接口新增草稿
6. 回读草稿箱做验收
7. 保存 `publish-result.json`

## 约束

- 没有封面图时，不执行正式发布
- 未经用户明确确认，不执行正式发布
- 正式发布必须显式传入 `--confirmed-publish`
- 工作目录必须已记录 `publish_intent=true`
- 发布失败时保留本地 HTML、Markdown、素材和错误响应，方便排查

## 草稿接口

- `GET /cgi-bin/token?grant_type=client_credential`
- `POST /cgi-bin/material/add_material?type=image`
- `POST /cgi-bin/media/uploadimg`
- `POST /cgi-bin/draft/add`
- `POST /cgi-bin/draft/batchget`

## 验收重点

- 草稿内容里的图片数量是否达到预期
- 草稿内容里是否仍残留本地路径
- 草稿内容是否带有 `thumb_media_id`
- `publish-result.json` 是否记录 `draft_media_id`、`uploaded_html_path`、`verify_status`
