"""Queue system for LLM jobs."""

__version__ = "0.1.0"

from app.llm.queue.backend import (
    QueueBackend,
    RedisQueueBackend,
    get_queue_backend,
    reset_queue_backend,
)
from app.llm.queue.backend_sqs import SQSQueueBackend
from app.llm.queue.models import (
    JobResult,
    JobStatus,
    LLMJob,
    QueueResult,
    RedisQueue,
)

# NOTE: llm_queue, reconciler_queue, recorder_queue are NOT imported here
# because queues.py creates a Redis connection at module load time, which
# crashes in SQS-based environments (AWS Fargate). Import them directly
# from app.llm.queue.queues where needed.

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
