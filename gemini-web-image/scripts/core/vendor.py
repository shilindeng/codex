from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .common import IMAGE_PROVIDER_FILES, SCRIPTS_DIR


def resolve_bun_command() -> list[str]:
    candidates = [["bun"], ["npx", "-y", "bun"]]
    for candidate in candidates:
        if shutil.which(candidate[0]) is None:
            continue
        try:
            subprocess.run(candidate + ["--version"], capture_output=True, text=True, check=True)
            return candidate
        except Exception:
            continue
    raise SystemExit("gemini-web 需要 bun 或 npx。请先安装 bun，或确保 npx 可用。")


def vendor_root() -> Path:
    return SCRIPTS_DIR / "_vendor" / "baoyu-danger-gemini-web"


def missing_vendor_files() -> list[str]:
    root = vendor_root()
    return [relative for relative in IMAGE_PROVIDER_FILES if not (root / relative).exists()]


def ensure_vendor() -> Path:
    root = vendor_root()
    missing = missing_vendor_files()
    if missing:
        preview = ", ".join(missing[:5])
        if len(missing) > 5:
            preview += ", ..."
        raise SystemExit(f"gemini-web vendor 文件不完整：缺少 {len(missing)} 个文件（{preview}）。")
    return root


def vendor_status() -> dict[str, Any]:
    missing = missing_vendor_files()
    bun_available = shutil.which("bun") is not None
    npx_available = shutil.which("npx") is not None
    return {
        "root": str(vendor_root()),
        "ok": not missing and (bun_available or npx_available),
        "bun_available": bun_available,
        "npx_available": npx_available,
        "missing_count": len(missing),
        "missing_files": missing,
    }
