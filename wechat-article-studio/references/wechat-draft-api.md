# 微信公众号草稿发布

## 默认环境变量

- `WECHAT_APP_ID`
- `WECHAT_APP_SECRET`

## 发布顺序

1. 获取 `access_token`
2. 上传封面图，得到 `thumb_media_id`
3. 上传正文内图片，替换 HTML 中的本地路径
4. 调用草稿箱接口新增草稿
5. 保存 `publish-result.json`

## 约束

- 没有封面图时，不执行正式发布
- 未经用户明确确认，不执行正式发布
- 发布失败时保留本地 HTML、Markdown、素材和报错响应

## 草稿接口

- `GET /cgi-bin/token?grant_type=client_credential`
- `POST /cgi-bin/material/add_material?type=image`
- `POST /cgi-bin/media/uploadimg`
- `POST /cgi-bin/draft/add`
