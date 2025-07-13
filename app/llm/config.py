"""LLM configuration."""

from typing import Any

from app.llm.base import BaseModelConfig


class LLMConfig(BaseModelConfig):
    """Configuration for LLM providers"""

    def __init__(
        self,
        model_name: str = "mistral-small",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        timeout: int = 30,
        system_prompt: str | None = None,
        stop_sequences: list[str] | None = None,
        retries: int = 3,
        supports_structured: bool = False,
        **kwargs: Any,
    ) -> None:
        """Initialize LLM config.

        Args:
            model_name: Name of the model to use
            temperature: Temperature for sampling (0-1)
            max_tokens: Maximum tokens to generate (>0)
            timeout: Request timeout in seconds (>0)
            system_prompt: System prompt to use
            stop_sequences: Stop sequences
            retries: Number of retries for failed requests (>=0)
            supports_structured: Whether the model supports structured output
            **kwargs: Additional configuration parameters

        Raises:
            ValueError: If any parameters are invalid
        """
        # Validate parameters
        if temperature < 0:
            raise ValueError("Input should be greater than or equal to 0")
        if temperature > 1:
            raise ValueError("Input should be less than or equal to 1")
        if max_tokens is not None and max_tokens <= 0:
            raise ValueError("Input should be greater than 0")
        if timeout <= 0:
            raise ValueError("Input should be greater than 0")
        if retries < 0:
            raise ValueError("Input should be greater than or equal to 0")

        super().__init__(
            context_length=64768,  # Large enough for most models
            max_tokens=max_tokens,
            default_temp=temperature,
            supports_json=True,
        )
        self.model_name = model_name
        self.temperature = temperature
        self.timeout = timeout
        self.system_prompt = system_prompt
        self.stop_sequences = stop_sequences
        self.retries = retries
        self.supports_structured = supports_structured
