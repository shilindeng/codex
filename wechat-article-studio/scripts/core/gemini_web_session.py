from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import legacy_studio as legacy
from core.browser_cookie_sync import import_google_cookies


SESSION_STATE_FILE = "session-state.json"
INLINE_COOKIE_FILE = "inline-cookie.json"
COOKIE_FILE = "cookies.json"

AUTH_MARKERS = (
    "autherror",
    "unauthorized",
    "login",
    "sign in",
    "signin",
    "__secure-1psid",
    "__secure-1psidts",
    "refresh cookies",
    "failed to refresh cookies",
)


def shared_data_dir() -> Path:
    path = legacy.consent_dir()
    legacy.ensure_dir(path)
    return path


def shared_cookie_path() -> Path:
    return shared_data_dir() / COOKIE_FILE


def shared_profile_dir() -> Path:
    return shared_data_dir() / "chrome-profile"


def session_state_path() -> Path:
    return shared_data_dir() / SESSION_STATE_FILE


def load_session_state() -> dict[str, Any]:
    path = session_state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_session_state(payload: dict[str, Any]) -> None:
    state = {"version": 1, **payload, "updated_at": legacy.now_iso()}
    session_state_path().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _path_if_exists(raw: str) -> Path | None:
    value = str(raw or "").strip()
    if not value:
        return None
    path = Path(value).expanduser().resolve()
    return path if path.exists() else None


def _inline_cookie_path(cookie_string: str) -> Path | None:
    cookie_map = legacy.parse_cookie_string(cookie_string)
    if not cookie_map:
        return None
    path = shared_data_dir() / INLINE_COOKIE_FILE
    legacy.write_cookie_payload(path, cookie_map)
    return path


def explicit_cookie_path(env: dict[str, str] | None = None) -> Path | None:
    env = env or os.environ
    return _path_if_exists(env.get("GEMINI_WEB_COOKIE_PATH") or "")


def explicit_profile_path(env: dict[str, str] | None = None) -> Path | None:
    env = env or os.environ
    return _path_if_exists(env.get("GEMINI_WEB_CHROME_PROFILE_DIR") or "")


def _cookie_has_required_pair(path: Path | None) -> bool:
    if not path or not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    cookie_map = payload.get("cookieMap") if isinstance(payload, dict) else {}
    if not isinstance(cookie_map, dict):
        return False
    return bool(cookie_map.get("__Secure-1PSID") and cookie_map.get("__Secure-1PSIDTS"))


def sync_system_browser_cookies() -> dict[str, Any]:
    result = import_google_cookies(shared_cookie_path())
    if result.get("ok"):
        save_session_state(
            {
                "active_cookie_path": str(shared_cookie_path()),
                "shared_cookie_path": str(shared_cookie_path()),
                "profile_dir": str(shared_profile_dir()),
                "last_source": "system-browser-sync",
                "sync_error": "",
            }
        )
    return result


def _profile_has_state(path: Path | None) -> bool:
    if not path or not path.exists() or not path.is_dir():
        return False
    try:
        return any(path.iterdir())
    except OSError:
        return False


def has_session_material(env: dict[str, str] | None = None) -> bool:
    env = env or os.environ
    if str(env.get("GEMINI_WEB_COOKIE") or "").strip():
        return True
    if _cookie_has_required_pair(explicit_cookie_path(env)):
        return True
    if _profile_has_state(explicit_profile_path(env)):
        return True
    state = load_session_state()
    if _cookie_has_required_pair(_path_if_exists(str(state.get("active_cookie_path") or ""))):
        return True
    if _cookie_has_required_pair(shared_cookie_path()):
        return True
    return _profile_has_state(shared_profile_dir())


def prepare_session_env(base_env: dict[str, str] | None = None) -> tuple[dict[str, str], dict[str, Any]]:
    original_env = dict(base_env or os.environ.copy())
    env = dict(original_env)
    env["GEMINI_WEB_DATA_DIR"] = str(shared_data_dir())
    env.setdefault("GEMINI_WEB_CHROME_PROFILE_DIR", str(shared_profile_dir()))

    state = load_session_state()
    explicit_cookie = explicit_cookie_path(original_env)
    inline_cookie = _inline_cookie_path(str(original_env.get("GEMINI_WEB_COOKIE") or "").strip()) if str(original_env.get("GEMINI_WEB_COOKIE") or "").strip() else None
    cached_cookie = shared_cookie_path() if shared_cookie_path().exists() else None
    recovery_cookie = _path_if_exists(str(state.get("active_cookie_path") or ""))
    candidates: list[tuple[str, Path]] = []
    if recovery_cookie and _cookie_has_required_pair(recovery_cookie):
        candidates.append(("shared-recovery", recovery_cookie))
    if explicit_cookie and _cookie_has_required_pair(explicit_cookie):
        candidates.append(("explicit-cookie", explicit_cookie))
    if inline_cookie:
        candidates.append(("inline-cookie", inline_cookie))
    if cached_cookie and _cookie_has_required_pair(cached_cookie):
        candidates.append(("shared-cache", cached_cookie))

    if not candidates:
        sync_result = sync_system_browser_cookies()
        if sync_result.get("ok") and _cookie_has_required_pair(shared_cookie_path()):
            candidates.append(("system-browser-sync", shared_cookie_path()))

    active_source = "profile-only"
    active_cookie = None
    if candidates:
        active_source, active_cookie = candidates[0]
        env["GEMINI_WEB_COOKIE_PATH"] = str(active_cookie)
    else:
        env.pop("GEMINI_WEB_COOKIE_PATH", None)

    info = {
        "shared_data_dir": str(shared_data_dir()),
        "shared_cookie_path": str(shared_cookie_path()),
        "shared_profile_dir": str(shared_profile_dir()),
        "session_state_path": str(session_state_path()),
        "active_source": active_source,
        "active_cookie_path": str(active_cookie) if active_cookie else "",
        "explicit_cookie_path": str(explicit_cookie) if explicit_cookie else "",
        "explicit_profile_path": str(explicit_profile_path(original_env) or ""),
    }
    return env, info


def describe_session_source(info: dict[str, Any]) -> str:
    source = str(info.get("active_source") or "profile-only")
    path = str(info.get("active_cookie_path") or "").strip()
    if path:
        return f"{source}（{path}）"
    return source


def _sync_cookie(src: Path, dst: Path) -> str:
    legacy.ensure_dir(dst.parent)
    shutil.copy2(src, dst)
    return str(dst)


def finalize_session_run(env: dict[str, str], info: dict[str, Any], *, browser_refresh_attempted: bool) -> dict[str, Any]:
    shared_cookie = shared_cookie_path()
    current_cookie = _path_if_exists(env.get("GEMINI_WEB_COOKIE_PATH") or "") or (shared_cookie if shared_cookie.exists() else None)
    explicit_cookie = _path_if_exists(info.get("explicit_cookie_path") or "")
    sync_error = ""
    if current_cookie and current_cookie.exists() and current_cookie.resolve() != shared_cookie.resolve():
        try:
            _sync_cookie(current_cookie, shared_cookie)
            current_cookie = shared_cookie
        except OSError as exc:
            sync_error = str(exc)
    if current_cookie and explicit_cookie and explicit_cookie.resolve() != current_cookie.resolve():
        try:
            _sync_cookie(current_cookie, explicit_cookie)
        except OSError as exc:
            sync_error = str(exc)
    if current_cookie and current_cookie.exists():
        save_session_state(
            {
                "active_cookie_path": str(current_cookie),
                "shared_cookie_path": str(shared_cookie),
                "profile_dir": str(env.get("GEMINI_WEB_CHROME_PROFILE_DIR") or shared_profile_dir()),
                "last_source": "browser-refresh" if browser_refresh_attempted else info.get("active_source") or "shared-cache",
                "sync_error": sync_error,
            }
        )
    info["active_source"] = "browser-refresh" if browser_refresh_attempted else info.get("active_source") or "shared-cache"
    info["active_cookie_path"] = str(current_cookie) if current_cookie else ""
    info["sync_error"] = sync_error
    return info


def run_gemini_web_command(
    command: list[str],
    *,
    cwd: str,
    label: str,
    timeout: int | None = None,
    base_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    env, info = prepare_session_env(base_env)
    browser_refresh_attempted = False
    browser_cookie_sync_attempted = False
    for _ in range(2):
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            cwd=cwd,
            check=False,
            timeout=timeout,
        )
        if completed.returncode == 0:
            return completed, finalize_session_run(env, info, browser_refresh_attempted=browser_refresh_attempted)
        combined = "\n".join(part for part in [completed.stdout or "", completed.stderr or ""] if part).lower()
        if not browser_refresh_attempted and any(marker in combined for marker in AUTH_MARKERS):
            if not browser_cookie_sync_attempted and not str(info.get("explicit_cookie_path") or "").strip():
                sync_result = sync_system_browser_cookies()
                browser_cookie_sync_attempted = True
                if sync_result.get("ok") and _cookie_has_required_pair(shared_cookie_path()):
                    env["GEMINI_WEB_COOKIE_PATH"] = str(shared_cookie_path())
                    info["active_source"] = "system-browser-sync"
                    info["active_cookie_path"] = str(shared_cookie_path())
                    continue
            env.pop("GEMINI_WEB_COOKIE_PATH", None)
            env["GEMINI_WEB_LOGIN"] = "1"
            env["GEMINI_WEB_CHROME_PROFILE_DIR"] = str(shared_profile_dir())
            info["active_source"] = "browser-refresh"
            browser_refresh_attempted = True
            continue
        detail = "\n".join(part for part in [completed.stdout or "", completed.stderr or ""] if part).strip()
        raise SystemExit(f"{label}失败：{detail}\n当前登录态来源：{describe_session_source(info)}")
    raise SystemExit(f"{label}失败：登录态恢复未成功。\n当前登录态来源：{describe_session_source(info)}")


def session_diagnostics(env: dict[str, str] | None = None) -> dict[str, Any]:
    env = env or os.environ.copy()
    _, info = prepare_session_env(env)
    state = load_session_state()
    shared_cookie = shared_cookie_path()
    explicit_cookie = explicit_cookie_path(env)
    return {
        "shared_data_dir": str(shared_data_dir()),
        "shared_cookie_path": str(shared_cookie),
        "shared_cookie_exists": shared_cookie.exists(),
        "shared_profile_dir": str(shared_profile_dir()),
        "shared_profile_exists": _profile_has_state(shared_profile_dir()),
        "explicit_cookie_path": str(explicit_cookie) if explicit_cookie else "",
        "explicit_cookie_exists": bool(explicit_cookie and explicit_cookie.exists()),
        "session_state_path": str(session_state_path()),
        "last_source": str(state.get("last_source") or ""),
        "active_cookie_path": str(state.get("active_cookie_path") or ""),
        "effective_source": str(info.get("active_source") or ""),
        "effective_cookie_path": str(info.get("active_cookie_path") or ""),
        "needs_browser_login": not has_session_material(env),
        "sync_error": str(state.get("sync_error") or ""),
    }
