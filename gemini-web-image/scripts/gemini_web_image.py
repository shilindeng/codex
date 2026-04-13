from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from core.common import (
    DEFAULT_IMAGE_MODEL,
    GEMINI_WEB_IMAGE_TIMEOUT,
    GEMINI_WEB_LOGIN_TIMEOUT,
    GEMINI_WEB_IMAGE_MODEL_CANDIDATES,
    SCRIPTS_DIR,
    ensure_dir,
    ensure_png_path,
    make_placeholder_png,
    read_text,
    safe_print,
    safe_print_json,
    sidecar_path,
    summarize_text,
    write_json,
)
from core.session import (
    consent_path,
    describe_session_source,
    ensure_consent,
    read_consent,
    run_gemini_web_command,
    session_diagnostics,
    set_consent,
    shared_cookie_path,
    shared_data_dir,
)
from core.vendor import ensure_vendor, resolve_bun_command, vendor_status


def _normalize_optional_path(raw: str | None) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    return str(Path(value).expanduser().resolve())


def _base_env_from_args(args: argparse.Namespace) -> dict[str, str]:
    env = os.environ.copy()
    cookie_path = _normalize_optional_path(getattr(args, "cookie_path", None))
    profile_dir = _normalize_optional_path(getattr(args, "profile_dir", None))
    if cookie_path:
        env["GEMINI_WEB_COOKIE_PATH"] = cookie_path
    if profile_dir:
        env["GEMINI_WEB_CHROME_PROFILE_DIR"] = profile_dir
    return env


def _read_prompt_files(paths: list[Path]) -> str:
    return "\n\n".join(read_text(path) for path in paths)


def _read_stdin_prompt() -> str:
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read().strip()


def _resolve_prompt(args: argparse.Namespace) -> tuple[str, str, list[Path]]:
    prompt_files = [Path(item).expanduser().resolve() for item in (args.prompt_file or [])]
    for path in prompt_files:
        if not path.exists():
            raise SystemExit(f"找不到 prompt 文件：{path}")

    positional_prompt = " ".join(args.prompt_parts or []).strip()
    if args.prompt:
        return args.prompt.strip(), "flag", prompt_files
    if positional_prompt and not prompt_files:
        return positional_prompt, "positional", prompt_files
    if prompt_files:
        return _read_prompt_files(prompt_files).strip(), "file", prompt_files
    stdin_prompt = _read_stdin_prompt()
    if stdin_prompt:
        return stdin_prompt, "stdin", prompt_files
    if positional_prompt:
        return positional_prompt, "positional", prompt_files
    raise SystemExit("缺少 prompt。请使用 --prompt、位置参数、--prompt-file 或 stdin。")


def _resolve_reference_paths(items: list[str] | None) -> list[Path]:
    references = [Path(item).expanduser().resolve() for item in (items or [])]
    missing = [str(path) for path in references if not path.exists()]
    if missing:
        raise SystemExit(f"找不到参考图：{', '.join(missing)}")
    return references


def _resolve_output_path(args: argparse.Namespace) -> tuple[Path, Path | None]:
    workspace = Path(args.workspace).expanduser().resolve() if getattr(args, "workspace", None) else None
    if workspace:
        ensure_dir(workspace)
    if args.output:
        output_path = ensure_png_path(Path(args.output).expanduser().resolve())
    elif workspace:
        output_path = ensure_png_path(workspace / "outputs" / "images" / "generated.png")
    else:
        output_path = ensure_png_path(Path.cwd() / "generated.png")
    ensure_dir(output_path.parent)
    return output_path, workspace


def _parse_json_output(raw: str) -> dict[str, Any]:
    value = (raw or "").strip()
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {"text": value}
    if isinstance(payload, dict):
        return payload
    return {"payload": payload}


def _response_summary(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates")
    return {
        "text": summarize_text(str(payload.get("text") or "")),
        "model": payload.get("model"),
        "session_id": payload.get("sessionId"),
        "saved_image": payload.get("savedImage"),
        "candidate_count": len(candidates) if isinstance(candidates, list) else 0,
    }


def _candidate_models(requested: str) -> list[str]:
    ordered: list[str] = []
    value = (requested or "").strip()
    for item in [value] + GEMINI_WEB_IMAGE_MODEL_CANDIDATES:
        name = str(item or "").strip()
        if not name or name in ordered:
            continue
        ordered.append(name)
    return ordered


def _sidecar_payload(
    *,
    output_path: Path,
    workspace: Path | None,
    prompt: str,
    prompt_source: str,
    prompt_files: list[Path],
    references: list[Path],
    model: str,
    session_id: str,
    session_source: str,
    dry_run: bool,
    raw_summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ok": True,
        "provider": "gemini-web",
        "output_path": str(output_path),
        "sidecar_path": str(sidecar_path(output_path)),
        "workspace": str(workspace) if workspace else "",
        "prompt": prompt,
        "prompt_source": prompt_source,
        "prompt_files": [str(path) for path in prompt_files],
        "reference_images": [str(path) for path in references],
        "model": model,
        "session_id": session_id,
        "session_source": session_source,
        "dry_run": dry_run,
        "output_exists": output_path.exists(),
        "file_size": output_path.stat().st_size if output_path.exists() else 0,
        "raw_response_summary": raw_summary,
    }


def _print_result(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        safe_print_json(payload)
    else:
        safe_print(payload.get("output_path") or "")


def cmd_doctor(args: argparse.Namespace) -> int:
    env = _base_env_from_args(args)
    consent = read_consent()
    vendor = vendor_status()
    diagnostics = session_diagnostics(env)
    report = {
        "python": {
            "version": sys.version.split()[0],
            "ok": sys.version_info >= (3, 10),
        },
        "platform": {
            "os_name": os.name,
            "sys_platform": sys.platform,
        },
        "paths": {
            "skill_dir": str(SCRIPTS_DIR.parent),
            "scripts_dir": str(SCRIPTS_DIR),
            "state_dir": str(shared_data_dir()),
            "consent_path": str(consent_path()),
        },
        "consent": {
            "accepted": bool(consent.get("accepted")),
            "disclaimer_version": consent.get("disclaimerVersion") or "",
            "expected_disclaimer_version": "1.0",
        },
        "vendor": vendor,
        "session": diagnostics,
        "ready_for_live_generation": bool(
            consent.get("accepted") and vendor.get("ok") and not diagnostics.get("needs_browser_login")
        ),
    }
    safe_print_json(report)
    return 0


def cmd_consent(args: argparse.Namespace) -> int:
    if args.accept:
        path = set_consent(True)
        safe_print(str(path))
        return 0
    if args.revoke:
        path = set_consent(False)
        safe_print(str(path))
        return 0
    safe_print_json(read_consent())
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    ensure_consent()
    root = ensure_vendor()
    bun = resolve_bun_command()
    env = _base_env_from_args(args)

    command = bun + [str(root / "main.ts"), "--login", "--json"]
    cookie_path = _normalize_optional_path(getattr(args, "cookie_path", None))
    profile_dir = _normalize_optional_path(getattr(args, "profile_dir", None))
    if cookie_path:
        command += ["--cookie-path", cookie_path]
    if profile_dir:
        command += ["--profile-dir", profile_dir]

    completed, session_info = run_gemini_web_command(
        command,
        cwd=str(root),
        label="gemini-web 登录刷新",
        timeout=GEMINI_WEB_LOGIN_TIMEOUT,
        base_env=env,
    )
    payload = _parse_json_output(completed.stdout)
    result = {
        "ok": True,
        "cookie_path": str(payload.get("cookiePath") or session_info.get("active_cookie_path") or shared_cookie_path()),
        "session_source": session_info.get("active_source") or "",
    }
    if args.json:
        safe_print_json(result)
    else:
        safe_print(result["cookie_path"])
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    prompt, prompt_source, prompt_files = _resolve_prompt(args)
    references = _resolve_reference_paths(args.reference)
    output_path, workspace = _resolve_output_path(args)
    model = (args.model or DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    env = _base_env_from_args(args)

    if args.dry_run:
        make_placeholder_png(output_path)
        diagnostics = session_diagnostics(env)
        result = _sidecar_payload(
            output_path=output_path,
            workspace=workspace,
            prompt=prompt,
            prompt_source=prompt_source,
            prompt_files=prompt_files,
            references=references,
            model=model,
            session_id=str(args.session_id or ""),
            session_source=str(diagnostics.get("effective_source") or ""),
            dry_run=True,
            raw_summary={"text": "dry-run placeholder image", "model": model, "session_id": args.session_id or ""},
        )
        write_json(sidecar_path(output_path), result)
        _print_result(result, as_json=args.json)
        return 0

    ensure_consent()
    root = ensure_vendor()
    bun = resolve_bun_command()
    cookie_path = _normalize_optional_path(getattr(args, "cookie_path", None))
    profile_dir = _normalize_optional_path(getattr(args, "profile_dir", None))
    payload: dict[str, Any] = {}
    session_info: dict[str, Any] = {}
    actual_output = output_path
    tried_models: list[str] = []
    last_error = ""
    for candidate_model in _candidate_models(model):
        tried_models.append(candidate_model)
        output_path.unlink(missing_ok=True)
        command = bun + [str(root / "main.ts"), "--model", candidate_model, "--prompt", prompt, "--image", str(output_path), "--json"]
        if args.session_id:
            command += ["--sessionId", args.session_id]
        if cookie_path:
            command += ["--cookie-path", cookie_path]
        if profile_dir:
            command += ["--profile-dir", profile_dir]
        if references:
            command += ["--reference", *[str(path) for path in references]]
        try:
            completed, session_info = run_gemini_web_command(
                command,
                cwd=str(root),
                label="gemini-web 图片生成",
                timeout=GEMINI_WEB_IMAGE_TIMEOUT,
                base_env=env,
            )
            payload = _parse_json_output(completed.stdout)
            actual_output = Path(str(payload.get("savedImage") or output_path)).expanduser().resolve()
            if actual_output.exists():
                break
            last_error = "gemini-web 未返回图片文件。"
        except SystemExit as exc:
            message = str(exc)
            last_error = message
            if "超时" in message or "No image returned in response." in message or "Unknown model name" in message:
                continue
            raise
    else:
        tried = ", ".join(tried_models)
        raise SystemExit(f"gemini-web 未成功返回图片。已尝试模型：{tried}。最后错误：{last_error}")

    session_id = str(payload.get("sessionId") or args.session_id or "")
    result = _sidecar_payload(
        output_path=actual_output,
        workspace=workspace,
        prompt=prompt,
        prompt_source=prompt_source,
        prompt_files=prompt_files,
        references=references,
        model=str(payload.get("model") or tried_models[-1]),
        session_id=session_id,
        session_source=describe_session_source(session_info),
        dry_run=False,
        raw_summary={**_response_summary(payload), "tried_models": tried_models},
    )
    write_json(sidecar_path(actual_output), result)
    _print_result(result, as_json=args.json)
    return 0


def _parse_session_lines(raw: str) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for line in (raw or "").splitlines():
        value = line.strip()
        if not value:
            continue
        parts = value.split("\t", 3)
        while len(parts) < 4:
            parts.append("")
        session_id, updated_at, message_count, preview = parts
        try:
            count = int(message_count)
        except ValueError:
            count = 0
        sessions.append(
            {
                "session_id": session_id,
                "updated_at": updated_at,
                "message_count": count,
                "preview": preview,
            }
        )
    return sessions


def cmd_list_sessions(args: argparse.Namespace) -> int:
    root = ensure_vendor()
    bun = resolve_bun_command()
    env = _base_env_from_args(args)
    command = bun + [str(root / "main.ts"), "--list-sessions"]
    completed, _session_info = run_gemini_web_command(
        command,
        cwd=str(root),
        label="gemini-web 会话列表",
        timeout=60,
        base_env=env,
    )
    if args.json:
        safe_print_json(_parse_session_lines(completed.stdout))
    else:
        safe_print((completed.stdout or "").rstrip())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gemini_web_image.py", description="Gemini Web 生图与登录态管理 CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="检查环境、vendor、登录态和 consent 状态")
    doctor.add_argument("--cookie-path")
    doctor.add_argument("--profile-dir")
    doctor.set_defaults(func=cmd_doctor)

    consent = subparsers.add_parser("consent", help="管理 Gemini Web 的显式同意状态")
    consent.add_argument("--accept", action="store_true")
    consent.add_argument("--revoke", action="store_true")
    consent.set_defaults(func=cmd_consent)

    login = subparsers.add_parser("login", help="刷新 Gemini Web 登录态")
    login.add_argument("--cookie-path")
    login.add_argument("--profile-dir")
    login.add_argument("--json", action="store_true")
    login.set_defaults(func=cmd_login)

    generate = subparsers.add_parser("generate", help="用 Gemini Web 生成图片")
    generate.add_argument("--prompt")
    generate.add_argument("--prompt-file", action="append", default=[])
    generate.add_argument("--reference", action="append", default=[])
    generate.add_argument("--output")
    generate.add_argument("--workspace")
    generate.add_argument("--model", default=DEFAULT_IMAGE_MODEL)
    generate.add_argument("--session-id")
    generate.add_argument("--cookie-path")
    generate.add_argument("--profile-dir")
    generate.add_argument("--json", action="store_true")
    generate.add_argument("--dry-run", action="store_true")
    generate.add_argument("prompt_parts", nargs="*")
    generate.set_defaults(func=cmd_generate)

    list_sessions = subparsers.add_parser("list-sessions", help="列出最近的 Gemini Web 会话")
    list_sessions.add_argument("--cookie-path")
    list_sessions.add_argument("--profile-dir")
    list_sessions.add_argument("--json", action="store_true")
    list_sessions.set_defaults(func=cmd_list_sessions)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
