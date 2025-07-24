"""Mock LLM provider for testing."""

from typing import Any, Dict

from app.llm.providers.base import BaseLLMProvider, BaseModelConfig
from app.llm.providers.types import GenerateConfig, LLMInput, LLMResponse


class MockConfig(BaseModelConfig):
    """Mock provider configuration."""

    pass


class MockProvider(BaseLLMProvider[Dict[str, Any], MockConfig]):
    """Mock LLM provider for testing."""

    async def generate(
        self,
        prompt: LLMInput,
        config: GenerateConfig | None = None,
        format: Dict[str, Any] | None = None,
        **kwargs: Dict[str, Any],
    ) -> LLMResponse:
        """Mock generate method."""
        return LLMResponse(
            text="Test response",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

    def _init_config(self, **kwargs: Dict[str, Any]) -> MockConfig:
        """Mock config initialization."""
        return MockConfig(
            context_length=1024,
            max_tokens=512,
            supports_structured=True,
        )

    @property
    def environment_key(self) -> str:
        """Mock environment key."""
        return "TEST_API_KEY"

    @property
    def model(self) -> Dict[str, Any]:
        """Mock model instance."""
        return {}


class ErrorProvider(MockProvider):
    """Mock provider that raises errors."""

    async def generate(
        self,
        prompt: LLMInput,
        config: GenerateConfig | None = None,
        format: Dict[str, Any] | None = None,
        **kwargs: Dict[str, Any],
    ) -> LLMResponse:
        """Mock generate method that raises an error."""
        raise ValueError("Test error")
