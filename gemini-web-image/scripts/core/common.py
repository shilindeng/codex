from __future__ import annotations

import base64
import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = SKILL_DIR / "scripts"

DISCLAIMER_VERSION = "1.0"
DEFAULT_IMAGE_MODEL = (os.getenv("GEMINI_WEB_IMAGE_MODEL") or "gemini-3.1-flash-image").strip() or "gemini-3.1-flash-image"
GEMINI_WEB_IMAGE_TIMEOUT = 240
_timeout_raw = (os.getenv("GEMINI_WEB_IMAGE_TIMEOUT") or os.getenv("GEMINI_WEB_IMAGE_TIMEOUT_SEC") or "").strip()
if _timeout_raw:
    try:
        GEMINI_WEB_IMAGE_TIMEOUT = max(10, int(_timeout_raw))
    except ValueError:
        pass
GEMINI_WEB_LOGIN_TIMEOUT = max(300, GEMINI_WEB_IMAGE_TIMEOUT)
_login_timeout_raw = (os.getenv("GEMINI_WEB_LOGIN_TIMEOUT") or os.getenv("GEMINI_WEB_LOGIN_TIMEOUT_SEC") or "").strip()
if _login_timeout_raw:
    try:
        GEMINI_WEB_LOGIN_TIMEOUT = max(30, int(_login_timeout_raw))
    except ValueError:
        pass

GEMINI_WEB_NO_IMAGE_MARKER = "No image returned in response."
GEMINI_WEB_IMAGE_MODEL_CANDIDATES = [
    "gemini-3.1-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
]
IMAGE_PROVIDER_FILES = [
    "main.ts",
    "gemini-webapi/client.ts",
    "gemini-webapi/constants.ts",
    "gemini-webapi/exceptions.ts",
    "gemini-webapi/index.ts",
    "gemini-webapi/components/gem-mixin.ts",
    "gemini-webapi/components/index.ts",
    "gemini-webapi/types/candidate.ts",
    "gemini-webapi/types/gem.ts",
    "gemini-webapi/types/grpc.ts",
    "gemini-webapi/types/image.ts",
    "gemini-webapi/types/index.ts",
    "gemini-webapi/types/modeloutput.ts",
    "gemini-webapi/utils/cookie-file.ts",
    "gemini-webapi/utils/decorators.ts",
    "gemini-webapi/utils/get-access-token.ts",
    "gemini-webapi/utils/http.ts",
    "gemini-webapi/utils/index.ts",
    "gemini-webapi/utils/load-browser-cookies.ts",
    "gemini-webapi/utils/logger.ts",
    "gemini-webapi/utils/parsing.ts",
    "gemini-webapi/utils/paths.ts",
    "gemini-webapi/utils/rotate-1psidts.ts",
    "gemini-webapi/utils/upload-file.ts",
]

TRANSPARENT_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9pY8m7QAAAAASUVORK5CYII="
)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").lstrip("\ufeff")


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def read_json(path: Path, default: Any | None = None) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_print(text: str) -> None:
    value = text or ""
    if not value.endswith("\n"):
        value += "\n"
    try:
        sys.stdout.write(value)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(value.encode("utf-8", errors="replace"))
        sys.stdout.flush()


def safe_print_json(data: Any) -> None:
    safe_print(json.dumps(data, ensure_ascii=False, indent=2))


def save_binary(path: Path, payload: bytes) -> None:
    ensure_dir(path.parent)
    path.write_bytes(payload)


def make_placeholder_png(path: Path) -> tuple[int, int]:
    save_binary(path, TRANSPARENT_PNG)
    return 1, 1


def parse_cookie_string(raw: str) -> dict[str, str]:
    cookie_map: dict[str, str] = {}
    for item in raw.split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            cookie_map[key] = value
    return cookie_map


def write_cookie_payload(path: Path, cookie_map: dict[str, str], *, source: str = "gemini-web-image") -> None:
    payload = {
        "version": 1,
        "updatedAt": now_iso(),
        "cookieMap": cookie_map,
        "source": source,
    }
    write_json(path, payload)


def ensure_png_path(path: Path) -> Path:
    return path if path.suffix else path.with_suffix(".png")


def sidecar_path(image_path: Path) -> Path:
    return image_path.with_name(f"{image_path.name}.json")


def summarize_text(value: str, *, max_chars: int = 500) -> str:
    text = " ".join((value or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def app_data_root() -> Path:
    if os.name == "nt":
        return Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))


def current_state_dir() -> Path:
    return app_data_root() / "gemini-web-image"


def legacy_state_dirs() -> list[Path]:
    base = app_data_root()
    candidates = [
        base / "wechat-article-studio" / "gemini-web",
        base / "baoyu-skills" / "gemini-web",
    ]
    deduped: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
