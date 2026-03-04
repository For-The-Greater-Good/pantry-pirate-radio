"""ECR Stack for Pantry Pirate Radio.

Creates ECR repositories for all container images used by the pipeline.
"""

from aws_cdk import Duration, RemovalPolicy, Stack
from aws_cdk import aws_ecr as ecr
from constructs import Construct


class ECRStack(Stack):
    """ECR repository infrastructure for Pantry Pirate Radio.

    Creates ECR repositories for:
    - worker: LLM job processing
    - validator: Data validation and enrichment
    - reconciler: Database reconciliation
    - publisher: HAARRRvest publishing
    - recorder: Job result recording
    - scraper: Web scraping tasks
    - app: API and db-init shared image

    Attributes:
        worker_repository: ECR repository for worker image
        validator_repository: ECR repository for validator image
        reconciler_repository: ECR repository for reconciler image
        publisher_repository: ECR repository for publisher image
        recorder_repository: ECR repository for recorder image
        scraper_repository: ECR repository for scraper image
        app_repository: ECR repository for app/db-init image
        repositories: Dict of all repositories by name
    """

    # Services that need ECR repositories
    SERVICE_NAMES = [
        "worker",
        "validator",
        "reconciler",
        "publisher",
        "recorder",
        "scraper",
        "app",
    ]

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        **kwargs,
    ) -> None:
        """Initialize ECRStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Environment-specific configuration
        is_prod = environment_name == "prod"
        removal_policy = RemovalPolicy.RETAIN if is_prod else RemovalPolicy.DESTROY

        # Create repositories for each service
        self._repositories: dict[str, ecr.Repository] = {}

        for service_name in self.SERVICE_NAMES:
            repo = self._create_repository(
                name=service_name,
                removal_policy=removal_policy,
                is_prod=is_prod,
            )
            self._repositories[service_name] = repo
            # Set as instance attribute for direct access
            setattr(self, f"{service_name}_repository", repo)

    def _create_repository(
        self,
        name: str,
        removal_policy: RemovalPolicy,
        is_prod: bool,
    ) -> ecr.Repository:
        """Create an ECR repository for a service.

        Args:
            name: Service name (worker, validator, etc.)
            removal_policy: CDK removal policy
            is_prod: Whether this is a production environment

        Returns:
            ECR repository
        """
        repo = ecr.Repository(
            self,
            f"{name.title()}Repository",
            repository_name=f"pantry-pirate-radio-{name}-{self.environment_name}",
            removal_policy=removal_policy,
            # Auto-delete images in non-prod when stack is deleted
            empty_on_delete=not is_prod,
            # Security: scan images for vulnerabilities on push
            image_scan_on_push=True,
            # Lifecycle rules to manage storage costs
            # Note: Rules with TagStatus.ANY (implicit in max_image_count) must have
            # the highest rule_priority number (lowest priority runs last)
            lifecycle_rules=[
                ecr.LifecycleRule(
                    description="Delete untagged images after 1 day",
                    tag_status=ecr.TagStatus.UNTAGGED,
                    max_image_age=Duration.days(1 if not is_prod else 7),
                    rule_priority=1,
                ),
                ecr.LifecycleRule(
                    description="Keep last 10 images",
                    max_image_count=10,
                    rule_priority=2,
                ),
            ],
        )

        return repo

    @property
    def repositories(self) -> dict[str, ecr.Repository]:
        """Return dict of all repositories by service name."""
        return self._repositories
