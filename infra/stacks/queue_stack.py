"""Queue Stack for Pantry Pirate Radio.

Creates SQS queues for the data processing pipeline:
- LLM queue: Raw content to HSDS alignment
- Validator queue: Data enrichment and confidence scoring
- Reconciler queue: Canonical record creation
- Recorder queue: Job result archiving
"""

from aws_cdk import Duration, Stack
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class QueueStack(Stack):
    """Queue infrastructure for Pantry Pirate Radio pipeline.

    Creates SQS FIFO queues for each pipeline stage:
    - LLM queue: Content → HSDS alignment (600s visibility)
    - Validator queue: Enrichment & scoring (600s visibility)
    - Reconciler queue: DB writes (300s visibility)
    - Recorder queue: Archiving (120s visibility)

    Each queue has its own DLQ for failed message handling.

    Attributes:
        llm_queue: SQS FIFO queue for LLM jobs
        llm_dlq: Dead-letter queue for LLM failures
        validator_queue: SQS FIFO queue for validation jobs
        validator_dlq: Dead-letter queue for validator failures
        reconciler_queue: SQS FIFO queue for reconciliation jobs
        reconciler_dlq: Dead-letter queue for reconciler failures
        recorder_queue: SQS FIFO queue for recording jobs
        recorder_dlq: Dead-letter queue for recorder failures
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        max_receive_count: int = 3,
        **kwargs,
    ) -> None:
        """Initialize QueueStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            max_receive_count: Number of receives before moving to DLQ
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name
        self.max_receive_count = max_receive_count

        # Create LLM queue (600s visibility for long-running LLM jobs)
        self.llm_dlq = self._create_dlq("llm")
        self.llm_queue = self._create_queue(
            name="llm",
            visibility_timeout_seconds=600,
            dlq=self.llm_dlq,
        )

        # Create Validator queue (600s visibility for enrichment)
        self.validator_dlq = self._create_dlq("validator")
        self.validator_queue = self._create_queue(
            name="validator",
            visibility_timeout_seconds=600,
            dlq=self.validator_dlq,
        )

        # Create Reconciler queue (300s visibility)
        self.reconciler_dlq = self._create_dlq("reconciler")
        self.reconciler_queue = self._create_queue(
            name="reconciler",
            visibility_timeout_seconds=300,
            dlq=self.reconciler_dlq,
        )

        # Create Recorder queue (120s visibility)
        self.recorder_dlq = self._create_dlq("recorder")
        self.recorder_queue = self._create_queue(
            name="recorder",
            visibility_timeout_seconds=120,
            dlq=self.recorder_dlq,
        )

        # Backwards compatibility alias
        self.dlq = self.llm_dlq

    def _create_dlq(self, name: str) -> sqs.Queue:
        """Create dead-letter queue for failed messages.

        Messages that fail processing multiple times are moved here
        for investigation and potential reprocessing.

        Args:
            name: Queue name (llm, validator, reconciler, recorder)

        Returns:
            SQS FIFO dead-letter queue
        """
        dlq = sqs.Queue(
            self,
            f"{name.title()}DLQ",
            queue_name=f"pantry-pirate-radio-{name}-dlq-{self.environment_name}.fifo",
            fifo=True,
            content_based_deduplication=True,
            retention_period=Duration.days(14),
        )

        return dlq

    def _create_queue(
        self,
        name: str,
        visibility_timeout_seconds: int,
        dlq: sqs.Queue,
    ) -> sqs.Queue:
        """Create SQS FIFO queue for pipeline stage.

        Features:
        - FIFO queue for exactly-once processing
        - Content-based deduplication
        - Configurable visibility timeout
        - Dead-letter queue for failed messages

        Args:
            name: Queue name (llm, validator, reconciler, recorder)
            visibility_timeout_seconds: Seconds before message becomes visible again
            dlq: Dead-letter queue for failures

        Returns:
            SQS FIFO queue
        """
        queue = sqs.Queue(
            self,
            f"{name.title()}Queue",
            queue_name=f"pantry-pirate-radio-{name}-{self.environment_name}.fifo",
            fifo=True,
            content_based_deduplication=True,
            visibility_timeout=Duration.seconds(visibility_timeout_seconds),
            retention_period=Duration.days(7),
            dead_letter_queue=sqs.DeadLetterQueue(
                queue=dlq,
                max_receive_count=self.max_receive_count,
            ),
        )

        return queue

    @property
    def queue_urls(self) -> dict[str, str]:
        """Return dict of queue URLs by stage name.

        Useful for passing queue URLs to services as environment variables.

        Returns:
            Dict mapping stage name (llm, validator, etc.) to queue URL
        """
        return {
            "llm": self.llm_queue.queue_url,
            "validator": self.validator_queue.queue_url,
            "reconciler": self.reconciler_queue.queue_url,
            "recorder": self.recorder_queue.queue_url,
        }
