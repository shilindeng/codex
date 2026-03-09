from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProviderResult:
    payload: Any
    provider: str
    model: str
    placeholder: bool = False


class TextProvider:
    provider_name = "base"

    def configured(self) -> bool:
        raise NotImplementedError

    def generate_research_pack(self, context: dict[str, Any]) -> ProviderResult:
        raise NotImplementedError

    def generate_titles(self, context: dict[str, Any]) -> ProviderResult:
        raise NotImplementedError

    def generate_outline(self, context: dict[str, Any]) -> ProviderResult:
        raise NotImplementedError

    def generate_article(self, context: dict[str, Any]) -> ProviderResult:
        raise NotImplementedError

    def review_article(self, context: dict[str, Any]) -> ProviderResult:
        raise NotImplementedError

    def revise_article(self, context: dict[str, Any]) -> ProviderResult:
        raise NotImplementedError
