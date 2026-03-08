"""Secrets Stack for Pantry Pirate Radio.

Creates AWS Secrets Manager secrets for centralized secrets management:
- GitHub PAT for HAARRRvest publishing
- LLM API keys (Anthropic/OpenRouter)

Note: Database credentials are managed by DatabaseStack to avoid cross-stack
dependency issues with Aurora cluster credentials.
"""

from aws_cdk import RemovalPolicy, Stack
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class SecretsStack(Stack):
    """Secrets infrastructure for Pantry Pirate Radio.

    Creates Secrets Manager secrets for:
    - GitHub Personal Access Token for HAARRRvest repository
    - LLM API keys (Anthropic Claude, OpenRouter)

    Note: Database credentials are managed by DatabaseStack.

    Attributes:
        github_pat_secret: Secret for GitHub PAT
        llm_api_keys_secret: Secret for LLM provider API keys
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        environment_name: str = "dev",
        **kwargs,
    ) -> None:
        """Initialize SecretsStack.

        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            environment_name: Environment name (dev, staging, prod)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        self.environment_name = environment_name

        # Determine removal policy based on environment
        removal_policy = (
            RemovalPolicy.RETAIN
            if environment_name == "prod"
            else RemovalPolicy.DESTROY
        )

        # Create secrets
        self.github_pat_secret = self._create_github_pat_secret(removal_policy)
        self.llm_api_keys_secret = self._create_llm_api_keys_secret(removal_policy)

    def _create_github_pat_secret(
        self, removal_policy: RemovalPolicy
    ) -> secretsmanager.Secret:
        """Create secret for GitHub Personal Access Token.

        This secret is for HAARRRvest repository access.
        The actual PAT value must be provided externally after stack creation.

        Returns:
            Secrets Manager secret for GitHub PAT
        """
        secret = secretsmanager.Secret(
            self,
            "GitHubPATSecret",
            secret_name=f"pantry-pirate-radio/github-pat-{self.environment_name}",
            description=f"GitHub PAT for HAARRRvest repository access - {self.environment_name}",
            # No auto-generation - must be set manually via AWS Console/CLI
            secret_string_value=None,
            removal_policy=removal_policy,
        )

        return secret

    def _create_llm_api_keys_secret(
        self, removal_policy: RemovalPolicy
    ) -> secretsmanager.Secret:
        """Create secret for LLM provider API keys.

        Stores API keys for:
        - Anthropic Claude (ANTHROPIC_API_KEY)
        - OpenRouter (OPENROUTER_API_KEY)

        The actual values must be provided externally after stack creation.

        Returns:
            Secrets Manager secret for LLM API keys
        """
        secret = secretsmanager.Secret(
            self,
            "LLMApiKeysSecret",
            secret_name=f"pantry-pirate-radio/llm-api-keys-{self.environment_name}",
            description=f"LLM API keys (Anthropic/OpenRouter) - {self.environment_name}",
            # No auto-generation - must be set manually via AWS Console/CLI
            secret_string_value=None,
            removal_policy=removal_policy,
        )

        return secret
