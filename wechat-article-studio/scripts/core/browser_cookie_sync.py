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
    chrome_root = legacy.local_chrome_user_data_root()
    if chrome_root:
        local_state = chrome_root / "Local State"
        for profile_name in ["Default", "Profile 1", "Profile 2", "Profile 3"]:
            cookies = chrome_root / profile_name / "Network" / "Cookies"
            if local_state.exists() and cookies.exists():
                sources.append((f"chrome:{profile_name}", local_state, cookies))
    edge_root = Path(r"C:\Users\dsl\AppData\Local\Microsoft\Edge\User Data")
    if edge_root.exists():
        local_state = edge_root / "Local State"
        for profile_name in ["Default", "Profile 1", "Profile 2", "Profile 3"]:
            cookies = edge_root / profile_name / "Network" / "Cookies"
            if local_state.exists() and cookies.exists():
                sources.append((f"edge:{profile_name}", local_state, cookies))
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
