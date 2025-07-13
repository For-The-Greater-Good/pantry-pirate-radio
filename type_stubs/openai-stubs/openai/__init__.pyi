"""Type stubs for OpenAI package."""

from collections.abc import AsyncGenerator
from typing import Any

from openai.types.chat import ChatCompletion, ChatCompletionChunk

class ChatCompletions:
    async def create(
        self,
        **kwargs: Any,
    ) -> ChatCompletion | AsyncGenerator[ChatCompletionChunk, None]: ...

class Chat:
    @property
    def completions(self) -> ChatCompletions: ...

class AsyncOpenAI:
    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None: ...
    @property
    def chat(self) -> Chat: ...
