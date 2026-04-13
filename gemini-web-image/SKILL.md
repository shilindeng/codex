---
name: gemini-web-image
description: Gemini Web 图片生成与登录态排查技能。用于通过 Gemini Web 做提示词生图、参考图辅助生图、登录态刷新、cookie/profile 诊断与会话查看。Use when Codex needs to generate images with Gemini Web from a text prompt or reference images, refresh Gemini Web login state, inspect cookie or Chrome profile issues, or list Gemini Web sessions.
---

# Gemini Web Image

用这个 skill 处理独立的 `Gemini Web` 生图任务，不要借用公众号文章工作流。

## 默认流程

1. 先判断用户是要真实生图，还是先验证流程。
2. 如果环境不明，先运行：

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py doctor
```

3. 如果是第一次真实调用，先取得用户明确同意，再运行：

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py consent --accept
python {SKILL_DIR}/scripts/gemini_web_image.py login
```

4. 然后再执行真实生图或 `--dry-run`。

## 何时用哪个命令

- 环境、cookie、profile、vendor、是否要重新登录不明确：用 `doctor`
- 需要记录或撤销显式同意状态：用 `consent`
- 需要刷新 Gemini Web 登录态：用 `login`
- 需要直接出图：用 `generate`
- 需要继续复用某个历史会话：先看 `list-sessions`

## 生成规则

- 普通提示词原样发送，不要套公众号文章专用 prompt 模板。
- 用户给了参考图时，直接透传给底层 `--reference`。
- `--dry-run` 只验证流程和落盘，不调用真实 Gemini Web。
- 真实调用只走 `Gemini Web`，不要静默切换到别的图片后端。
- 每次生成都要检查图片文件和同名 `.json` 侧车文件是否都已写出。
- 如果 Gemini Web 返回文本但没返回图，直接报错并说明原因，不要伪装成成功。

## 常用命令

```powershell
python {SKILL_DIR}/scripts/gemini_web_image.py doctor
python {SKILL_DIR}/scripts/gemini_web_image.py login --json
python {SKILL_DIR}/scripts/gemini_web_image.py generate --prompt "A minimalist poster of a paper crane" --output output/crane.png --json
python {SKILL_DIR}/scripts/gemini_web_image.py generate --prompt "Turn this into a warm editorial illustration" --reference assets/ref.png --workspace runs/demo --json
python {SKILL_DIR}/scripts/gemini_web_image.py generate --prompt "test" --dry-run --workspace runs/demo --json
python {SKILL_DIR}/scripts/gemini_web_image.py list-sessions --json
```

## 使用约束

- `gemini-web` 是非官方路径；做真实调用前，先确认用户已经明确同意。
- 如果 `doctor` 显示未就绪，先修登录态或运行环境，再做真实生图。
- 如果用户只想验证流程、文件落盘或参数拼装，优先用 `--dry-run`。
- 如果用户要求复用旧会话风格或上下文，优先传 `--session-id`。

## 何时读 references

- 命令和参数矩阵：读 [references/commands.md](references/commands.md)
- 首次使用、登录、cookie/profile 和常见报错：读 [references/setup.md](references/setup.md)
