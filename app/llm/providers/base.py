"""Base classes and types for LLM providers."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, Generic, TypeVar

from app.llm.base import BaseModelConfig
from app.llm.providers.types import GenerateConfig, LLMInput, LLMResponse

ModelType = TypeVar("ModelType")
ConfigType = TypeVar("ConfigType", bound=BaseModelConfig)
ProviderType = TypeVar("ProviderType", bound="BaseLLMProvider[Any, Any]")


class BaseLLMProvider(ABC, Generic[ModelType, ConfigType]):
    """Base class for LLM providers.

    All LLM providers should inherit from this class and implement
    its abstract methods.
    """

    def __init__(
        self,
        model_name: str,
        api_key: str | None = None,
        base_url: str | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the LLM provider.

        Args:
            model_name: The name/identifier of the model to use
            api_key: Optional API key for authentication
            base_url: Optional base URL for the API endpoint
            headers: Optional additional HTTP headers
            **kwargs: Additional provider-specific configuration
        """
        self.model_name = model_name
        self._api_key = api_key
        self._base_url = base_url
        self._headers = headers or {}
        self._config = self._init_config(**kwargs)

    @abstractmethod
    def _init_config(self, **kwargs: Any) -> ConfigType:
        """Initialize provider-specific configuration.

        Args:
            **kwargs: Configuration parameters

        Returns:
            Configuration object
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def environment_key(self) -> str:
        """The environment variable name for the API key."""
        raise NotImplementedError

    @property
    def api_key(self) -> str | None:
        """Get the API key, checking environment if not explicitly set."""
        if self._api_key is None:
            import os

            self._api_key = os.environ.get(self.environment_key)
        return self._api_key

    @property
    def base_url(self) -> str | None:
        """Get the base URL for API requests."""
        return self._base_url

    @property
    def headers(self) -> dict[str, str]:
        """Get HTTP headers for API requests."""
        return self._headers

    @property
    @abstractmethod
    def model(self) -> ModelType:
        """Get the underlying model instance."""
        raise NotImplementedError

    @abstractmethod
    async def generate(
        self,
        prompt: LLMInput,
        config: GenerateConfig | None = None,
        format: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> LLMResponse | AsyncGenerator[LLMResponse, None]:
        """Generate a response from the model.

        Args:
            prompt: The input prompt or chat messages
            config: Optional generation configuration
            format: Optional JSON schema for structured output
            **kwargs: Additional provider-specific parameters

        Returns:
            Generated response or async generator for streaming
        """
        raise NotImplementedError

    def supports_structured_output(self) -> bool:
        """Check if provider supports structured output.

        Returns:
            True if provider supports structured output, False otherwise
        """
        return bool(self._config.supports_structured)

    @classmethod
    def from_name(cls: type[ProviderType], name: str) -> ProviderType:
        """Create a provider instance from a model name.

        Args:
            name: The model name/identifier

        Returns:
            A configured provider instance
        """
        return cls(model_name=name)

    def __repr__(self) -> str:
        """String representation of the provider."""
        return f"{self.__class__.__name__}(model_name='{self.model_name}')"
