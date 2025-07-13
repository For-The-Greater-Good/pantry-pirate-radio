"""Type stubs for OpenAI chat types."""

from typing import TypedDict

class Message(TypedDict):
    role: str
    content: str | None

class Delta(TypedDict):
    role: str | None
    content: str | None

class Choice(TypedDict):
    index: int
    message: Message
    finish_reason: str | None

class ChunkChoice(TypedDict):
    index: int
    delta: Delta
    finish_reason: str | None

class Usage(TypedDict):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model_dump: dict[str, int]

class ChatCompletion(TypedDict):
    id: str
    object: str
    created: int
    model: str
    choices: list[Choice]
    usage: Usage | None

class ChatCompletionChunk(TypedDict):
    id: str
    object: str
    created: int
    model: str
    choices: list[ChunkChoice]
