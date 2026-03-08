"""Queue system for LLM jobs.

Imports are lazy so lightweight environments (batch Lambdas) that only need
a single submodule don't pull in redis, rq, etc.
"""

__version__ = "0.1.0"

__all__ = [
    "JobResult",
    "JobStatus",
    "LLMJob",
    "QueueBackend",
    "QueueResult",
    "RedisQueue",
    "RedisQueueBackend",
    "SQSQueueBackend",
    "get_queue_backend",
    "reset_queue_backend",
]

_LAZY_IMPORTS = {
    "QueueBackend": "app.llm.queue.backend",
    "RedisQueueBackend": "app.llm.queue.backend",
    "get_queue_backend": "app.llm.queue.backend",
    "reset_queue_backend": "app.llm.queue.backend",
    "SQSQueueBackend": "app.llm.queue.backend_sqs",
    "JobResult": "app.llm.queue.models",
    "JobStatus": "app.llm.queue.models",
    "LLMJob": "app.llm.queue.models",
    "QueueResult": "app.llm.queue.models",
    "RedisQueue": "app.llm.queue.models",
}


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        module = importlib.import_module(_LAZY_IMPORTS[name])
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
