# Gemini Web Image Commands

## 导航

- 命令概览
- `doctor`
- `consent`
- `login`
- `generate`
- `list-sessions`
- 输出约定

## 命令概览

主入口：

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py <command> ...
```

可用命令：

- `doctor`：检查环境和登录态
- `consent`：管理显式同意状态
- `login`：刷新 Gemini Web 登录态
- `generate`：执行生图
- `list-sessions`：列出最近会话

## `doctor`

用途：

- 检查 Python 版本
- 检查 `bun` / `npx`
- 检查 vendor 文件是否完整
- 检查 consent、cookie、profile、是否需要重新登录

示例：

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py doctor
python {SKILL_DIR}/scripts/gemini_web_image.py doctor --cookie-path C:\path\cookies.json
python {SKILL_DIR}/scripts/gemini_web_image.py doctor --profile-dir C:\path\ChromeProfile
```

输出：固定为 JSON。

## `consent`

用途：

- 写入显式同意状态
- 撤销显式同意状态
- 查看当前同意状态

示例：

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py consent --accept
python {SKILL_DIR}/scripts/gemini_web_image.py consent --revoke
python {SKILL_DIR}/scripts/gemini_web_image.py consent
```

规则：

- 只有在用户明确同意使用 `gemini-web` 这条非官方路径时，才执行 `--accept`

## `login`

用途：

- 只刷新登录态，不出图

参数：

- `--cookie-path`：显式指定 cookie 文件
- `--profile-dir`：显式指定浏览器 profile
- `--json`：以 JSON 输出

示例：

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py login
python {SKILL_DIR}/scripts/gemini_web_image.py login --json
python {SKILL_DIR}/scripts/gemini_web_image.py login --profile-dir C:\Users\me\AppData\Local\Google\Chrome\User Data\Default
```

## `generate`

用途：

- 用文本提示词和可选参考图生成图片

输入来源：

- `--prompt`
- 位置参数 prompt
- `--prompt-file` 可重复
- stdin

参数：

- `--output`：显式输出路径
- `--workspace`：未给 `--output` 时，默认落到 `<workspace>/outputs/images/generated.png`
- `--model`：图片模型，默认 `gemini-3.1-flash-image`
- `--reference`：可重复，传参考图
- `--session-id`：复用已有会话
- `--cookie-path`
- `--profile-dir`
- `--json`
- `--dry-run`

示例：

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py generate --prompt "A blue paper crane on a white desk"
python {SKILL_DIR}/scripts/gemini_web_image.py generate "A cinematic night street in Shanghai" --output output\street.png --json
python {SKILL_DIR}/scripts/gemini_web_image.py generate --prompt-file prompt.md --reference ref-1.png --reference ref-2.png --workspace runs\demo --json
Get-Content prompt.txt | python {SKILL_DIR}/scripts/gemini_web_image.py generate --workspace runs\pipe --dry-run --json
```

规则：

- 普通提示词原样发送
- 参考图直接透传到底层
- `--dry-run` 只生成占位图和侧车文件
- 不做其他图片后端回退

## `list-sessions`

用途：

- 查看最近保存的 Gemini Web 会话

参数：

- `--json`
- `--cookie-path`
- `--profile-dir`

示例：

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py list-sessions
python {SKILL_DIR}/scripts/gemini_web_image.py list-sessions --json
```

## 输出约定

`generate` 每次都会落两个文件：

- 图片文件
- 同名侧车 JSON，例如 `generated.png.json`

侧车 JSON 至少包含：

- 是否成功
- 图片路径
- prompt 和 prompt 来源
- prompt 文件列表
- 参考图列表
- model
- session id
- 当前登录态来源
- dry-run 标记
- 原始返回摘要
