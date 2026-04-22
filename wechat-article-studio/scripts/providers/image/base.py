from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ImageProviderDescriptor:
    name: str
    env_keys: tuple[str, ...]
    stable: bool = True


IMAGE_PROVIDER_DESCRIPTORS = [
    ImageProviderDescriptor(
        "gemini-web",
        ("GEMINI_WEB_COOKIE", "GEMINI_WEB_COOKIE_PATH", "GEMINI_WEB_CHROME_PROFILE_DIR"),
        stable=False,
    ),
    ImageProviderDescriptor("codex", ()),
    ImageProviderDescriptor("gemini-api", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
    ImageProviderDescriptor("openai-image", ("OPENAI_API_KEY",)),
]
