"""LLM module for HSDS data alignment.

Provider imports are lazy to avoid pulling in optional dependencies (openai,
anthropic) when only a subset is needed — e.g. batch Lambdas only need Bedrock.
"""

from app.llm.config import LLMConfig
from app.llm.hsds_aligner.type_defs import (
    AlignmentInputDict as AlignmentInput,
)
from app.llm.hsds_aligner.type_defs import (
    AlignmentOutputDict as AlignmentOutput,
)
from app.llm.providers.base import BaseLLMProvider

__all__ = [
    "AlignmentInput",
    "AlignmentOutput",
    "BaseLLMProvider",
    "BedrockConfig",
    "BedrockProvider",
    "LLMConfig",
    "OpenAIConfig",
    "OpenAIProvider",
]

_LAZY_IMPORTS = {
    "BedrockConfig": "app.llm.providers.bedrock",
    "BedrockProvider": "app.llm.providers.bedrock",
    "OpenAIConfig": "app.llm.providers.openai",
    "OpenAIProvider": "app.llm.providers.openai",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        module = importlib.import_module(_LAZY_IMPORTS[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
