from __future__ import annotations

import base64
import ctypes
import json
import shutil
import sqlite3
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import legacy_studio as legacy


GOOGLE_COOKIE_NAMES = {
    "__Secure-1PSID",
    "__Secure-1PSIDTS",
    "__Secure-1PSIDCC",
    "__Secure-1PSIDRTS",
    "__Secure-3PSID",
    "__Secure-3PSIDTS",
    "__Secure-3PSIDCC",
    "__Secure-3PSIDRTS",
    "__Secure-1PAPISID",
    "__Secure-3PAPISID",
    "SAPISID",
    "APISID",
    "SID",
    "HSID",
    "SSID",
    "LSID",
    "NID",
    "__Host-GAPS",
    "ACCOUNT_CHOOSER",
    "OTZ",
}


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_decrypt(payload: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(payload, len(payload))
    blob_in = DATA_BLOB(len(payload), buffer)
    blob_out = DATA_BLOB()
    if not crypt32.CryptUnprotectData(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        if blob_out.pbData:
            kernel32.LocalFree(blob_out.pbData)


def _load_master_key(local_state_path: Path) -> bytes:
    payload = json.loads(local_state_path.read_text(encoding="utf-8"))
    encoded = ((payload.get("os_crypt") or {}).get("encrypted_key") or "").strip()
    raw = base64.b64decode(encoded)
    if raw.startswith(b"DPAPI"):
        raw = raw[5:]
    return _dpapi_decrypt(raw)


def _decrypt_cookie(encrypted_value: bytes, master_key: bytes) -> str:
    if not encrypted_value:
        return ""
    if encrypted_value.startswith(b"v10") or encrypted_value.startswith(b"v11"):
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:]
        value = AESGCM(master_key).decrypt(nonce, ciphertext, None)
        return value.decode("utf-8", errors="replace")
    return _dpapi_decrypt(encrypted_value).decode("utf-8", errors="replace")


def _browser_sources() -> list[tuple[str, Path, Path]]:
    sources: list[tuple[str, Path, Path]] = []

    def candidate_roots() -> list[tuple[str, Path]]:
        roots: list[tuple[str, Path]] = []
        local_app_data = legacy.os.getenv("LOCALAPPDATA")
        browser_envs = {
            "chrome": [
                legacy.os.getenv("CHROME_USER_DATA_ROOT") or "",
                str(Path(local_app_data) / "Google" / "Chrome" / "User Data") if local_app_data else "",
            ],
            "edge": [
                legacy.os.getenv("EDGE_USER_DATA_ROOT") or "",
                str(Path(local_app_data) / "Microsoft" / "Edge" / "User Data") if local_app_data else "",
            ],
        }
        for browser, values in browser_envs.items():
            seen: set[str] = set()
            for raw in values:
                item = str(raw or "").strip()
                if not item:
                    continue
                path = Path(item).expanduser()
                key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                roots.append((browser, path))
        return roots

    for browser, root in candidate_roots():
        if not root.exists():
            continue
        local_state = root / "Local State"
        if not local_state.exists():
            continue
        profile_dirs = [item for item in root.iterdir() if item.is_dir() and (item.name == "Default" or item.name.startswith("Profile "))]
        for profile_dir in sorted(profile_dirs, key=lambda item: item.name):
            cookies = profile_dir / "Network" / "Cookies"
            if cookies.exists():
                sources.append((f"{browser}:{profile_dir.name}", local_state, cookies))
    return sources


def _copy_cookie_db(path: Path) -> Path:
    handle = tempfile.NamedTemporaryFile(prefix="wechat-gemini-cookie-", suffix=".sqlite", delete=False)
    handle.close()
    target = Path(handle.name)
    if legacy.os.name == "nt":
        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        FILE_SHARE_DELETE = 0x00000004
        OPEN_EXISTING = 3
        FILE_ATTRIBUTE_NORMAL = 0x80
        kernel32 = ctypes.windll.kernel32
        source = kernel32.CreateFileW(
            str(path),
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,
            None,
        )
        if source == wintypes.HANDLE(-1).value:
            raise ctypes.WinError()
        try:
            with target.open("wb") as writer:
                buffer = ctypes.create_string_buffer(1024 * 1024)
                bytes_read = wintypes.DWORD()
                while kernel32.ReadFile(source, buffer, len(buffer), ctypes.byref(bytes_read), None):
                    if bytes_read.value == 0:
                        break
                    writer.write(buffer.raw[: bytes_read.value])
        finally:
            kernel32.CloseHandle(source)
    else:
        shutil.copy2(path, target)
    return target


def _read_cookie_map(local_state: Path, cookie_db: Path) -> dict[str, str]:
    master_key = _load_master_key(local_state)
    copied = _copy_cookie_db(cookie_db)
    rows: list[tuple[str, str, bytes, str, int]] = []
    try:
        conn = sqlite3.connect(str(copied))
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT host_key, name, encrypted_value, value, COALESCE(last_access_utc, creation_utc, 0)
                FROM cookies
                WHERE (host_key LIKE '%google.com%' OR host_key LIKE '%googleusercontent.com%')
                """
            )
            rows = cursor.fetchall()
        finally:
            conn.close()
    finally:
        copied.unlink(missing_ok=True)

    best: dict[str, tuple[int, str]] = {}
    for host_key, name, encrypted_value, value, stamp in rows:
        if name not in GOOGLE_COOKIE_NAMES:
            continue
        decoded = value or _decrypt_cookie(encrypted_value or b"", master_key)
        if not decoded:
            continue
        previous = best.get(name)
        if previous is None or int(stamp or 0) >= previous[0]:
            best[name] = (int(stamp or 0), decoded)
    return {key: value for key, (_, value) in best.items()}


def import_google_cookies(target_path: Path) -> dict[str, Any]:
    best_payload: dict[str, str] = {}
    best_source = ""
    best_score = -1
    for source_name, local_state, cookie_db in _browser_sources():
        try:
            payload = _read_cookie_map(local_state, cookie_db)
        except Exception:
            continue
        score = len(payload)
        if "__Secure-1PSID" in payload:
            score += 20
        if "__Secure-1PSIDTS" in payload:
            score += 20
        if score > best_score:
            best_score = score
            best_payload = payload
            best_source = source_name
    if not best_payload or "__Secure-1PSID" not in best_payload or "__Secure-1PSIDTS" not in best_payload:
        return {"ok": False, "source": "", "cookie_count": len(best_payload), "target_path": str(target_path)}
    legacy.ensure_dir(target_path.parent)
    legacy.write_cookie_payload(target_path, best_payload)
    return {
        "ok": True,
        "source": best_source,
        "cookie_count": len(best_payload),
        "target_path": str(target_path),
        "cookie_names": sorted(best_payload.keys()),
    }
