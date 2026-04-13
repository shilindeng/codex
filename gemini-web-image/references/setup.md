# Gemini Web Image Setup

## 导航

- 首次使用
- 状态目录
- cookie 与 profile
- 常见排查顺序
- 常见报错

## 首次使用

推荐顺序：

1. 检查环境

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py doctor
```

2. 如果要真实调用，先取得用户明确同意

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py consent --accept
```

3. 刷新登录态

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py login --json
```

4. 先跑一次 `--dry-run`

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py generate --prompt "test" --dry-run --workspace runs/demo --json
```

5. 再跑真实生图

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py generate --prompt "A minimalist poster of a paper crane" --workspace runs/demo --json
```

## 状态目录

默认状态目录在：

- Windows：`%APPDATA%\gemini-web-image`

里面会存这些内容：

- `consent.json`
- `cookies.json`
- `session-state.json`
- `chrome-profile/`

兼容读取这些旧来源：

- `%APPDATA%\wechat-article-studio\gemini-web`
- `%APPDATA%\baoyu-skills\gemini-web`

如果旧登录态可用，skill 会优先读它，再同步到自己的状态目录。

## cookie 与 profile

优先级大致是：

1. 当前命令显式传入的 `GEMINI_WEB_COOKIE` / `GEMINI_WEB_COOKIE_PATH`
2. 当前 skill 自己保存的 cookie
3. 旧 skill 遗留的 cookie
4. 系统浏览器中可导入的 Google cookie
5. 共享 profile 登录恢复

显式指定时可用：

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py login --cookie-path C:\path\cookies.json
python {SKILL_DIR}/scripts/gemini_web_image.py login --profile-dir C:\path\ChromeProfile
```

## 常见排查顺序

1. 跑 `doctor`
2. 看 `consent.accepted` 是否为 `true`
3. 看 `vendor.ok` 是否为 `true`
4. 看 `session.needs_browser_login` 是否为 `false`
5. 如果需要，先跑 `login`
6. 先用 `generate --dry-run` 验证落盘
7. 再做真实调用

## 常见报错

### `gemini-web 为非官方方式，必须先取得用户明确同意`

说明：

- 还没写入 consent 状态

处理：

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py consent --accept
```

### `gemini-web 需要 bun 或 npx`

说明：

- 本机没有可用的 `bun`，也没有可用的 `npx`

处理：

- 安装 `bun`，或确保 `npx -y bun` 可运行

### `vendor 文件不完整`

说明：

- `scripts/_vendor/baoyu-danger-gemini-web` 缺文件

处理：

- 重新同步完整的 vendor 目录

### `未返回图片文件` / 只回文本不回图

说明：

- 上游当前只返回了文本，没有成功返回图片

处理：

1. 先重新 `login`
2. 再做一次真实调用
3. 如果仍然只回文本，视为 Gemini Web 当前兼容性变化，不要把这次调用算成功

### `找不到参考图`

说明：

- `--reference` 指向的文件不存在

处理：

- 先确认文件路径，再重跑
