"""Provider factory with dict-based registry."""

from typing import Any, cast

from app.llm.providers.base import BaseLLMProvider

_PROVIDER_REGISTRY: dict[str, tuple[type, type]] = {}


def register_provider(name: str, config_class: type, provider_class: type) -> None:
    """Register a provider in the factory.

    Args:
        name: Provider name (e.g. "openai", "claude", "bedrock")
        config_class: The config class to instantiate
        provider_class: The provider class to instantiate
    """
    _PROVIDER_REGISTRY[name] = (config_class, provider_class)


def create_provider(
    provider_name: str,
    model_name: str,
    temperature: float,
    max_tokens: int | None,
) -> BaseLLMProvider[Any, Any]:
    """Create a provider instance from the registry.

    Args:
        provider_name: Registered provider name
        model_name: Model identifier
        temperature: Sampling temperature
        max_tokens: Max tokens to generate

    Returns:
        Configured provider instance

    Raises:
        ValueError: If provider_name is not registered
    """
    entry = _PROVIDER_REGISTRY.get(provider_name)
    if entry is None:
        registered = ", ".join(sorted(_PROVIDER_REGISTRY.keys()))
        raise ValueError(
            f"Unsupported LLM provider: {provider_name}. "
            f"Supported providers: {registered}"
        )
    config_class, provider_class = entry
    config = config_class(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return cast(BaseLLMProvider[Any, Any], provider_class(config))


def _register_defaults() -> None:
    """Register built-in providers."""
    from app.llm.providers.openai import OpenAIConfig, OpenAIProvider
    from app.llm.providers.claude import ClaudeConfig, ClaudeProvider
    from app.llm.providers.bedrock import BedrockConfig, BedrockProvider

    register_provider("openai", OpenAIConfig, OpenAIProvider)
    register_provider("claude", ClaudeConfig, ClaudeProvider)
    register_provider("bedrock", BedrockConfig, BedrockProvider)


_register_defaults()
