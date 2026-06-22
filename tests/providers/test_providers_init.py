"""Tests for lazy provider exports from nanobot.providers."""

from __future__ import annotations

import importlib
import sys


def test_importing_providers_package_is_lazy(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "nanobot.providers", raising=False)
    monkeypatch.delitem(sys.modules, "nanobot.providers.anthropic_provider", raising=False)
    monkeypatch.delitem(sys.modules, "nanobot.providers.openai_compat_provider", raising=False)

    providers = importlib.import_module("nanobot.providers")

    assert "nanobot.providers.anthropic_provider" not in sys.modules
    assert "nanobot.providers.openai_compat_provider" not in sys.modules
    assert providers.__all__ == [
        "LLMProvider",
        "LLMResponse",
        "AnthropicProvider",
        "OpenAICompatProvider",
    ]


def test_explicit_provider_import_still_works(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "nanobot.providers", raising=False)
    monkeypatch.delitem(sys.modules, "nanobot.providers.anthropic_provider", raising=False)

    namespace: dict[str, object] = {}
    exec("from nanobot.providers import AnthropicProvider", namespace)

    assert namespace["AnthropicProvider"].__name__ == "AnthropicProvider"
    assert "nanobot.providers.anthropic_provider" in sys.modules


def test_removed_backend_raises_attribute_error() -> None:
    import nanobot.providers as providers

    # Cloud-specific backends were removed in the meta-nanobot distillation.
    for name in ("BedrockProvider", "AzureOpenAIProvider", "GitHubCopilotProvider"):
        try:
            getattr(providers, name)
        except AttributeError:
            continue
        raise AssertionError(f"{name} should no longer be exported")
