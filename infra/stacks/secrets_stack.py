"""Secrets Stack for Pantry Pirate Radio.

Creates AWS Secrets Manager secrets for centralized secrets management:
- GitHub PAT for HAARRRvest publishing
- LLM API keys (Anthropic/OpenRouter/ArcGIS)
- Tightbeam API keys (deprecated — retained for CloudFormation export compatibility)

Secret values are seeded from .env at deploy time. CloudFormation only updates
the value if it changes in the template (i.e., if .env changes between deploys).

Note: Database credentials are managed by DatabaseStack to avoid cross-stack
dependency issues with Aurora cluster credentials.
"""

import json

from aws_cdk import RemovalPolicy, SecretValue, Stack
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct
from shared_config import SECRETS

# Keys expected in the LLM API keys secret JSON object
_LLM_SECRET_KEYS = ("ANTHROPIC_API_KEY", "OPENROUTER_API_KEY", "ARCGIS_API_KEY")


class SecretsStack(Stack):
    """Secrets infrastructure for Pantry Pirate Radio.

    Creates Secrets Manager secrets for:
    - GitHub Personal Access Token for HAARRRvest repository
    - LLM API keys (Anthropic Claude, OpenRouter, ArcGIS)

    Values are seeded from the project .env file at CDK synth time.

    Note: Database credentials are managed by DatabaseStack.

    Attributes:
        github_pat_secret: Secret for GitHub PAT
        llm_api_keys_secret: Secret for LLM provider API keys
        tightbeam_api_keys_secret: (Deprecated) Retained for CloudFormation export stability
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
        self.tightbeam_api_keys_secret = self._create_tightbeam_api_keys_secret(
            removal_policy
        )

    def _create_github_pat_secret(
        self, removal_policy: RemovalPolicy
    ) -> secretsmanager.Secret:
        """Create secret for GitHub Personal Access Token.

        Seeds the value from DATA_REPO_TOKEN in .env if available.

        Returns:
            Secrets Manager secret for GitHub PAT
        """
        pat_value = SECRETS.get("DATA_REPO_TOKEN", "")

        secret = secretsmanager.Secret(
            self,
            "GitHubPATSecret",
            secret_name=f"pantry-pirate-radio/github-pat-{self.environment_name}",
            description=f"GitHub PAT for HAARRRvest repository access - {self.environment_name}",
            secret_string_value=(
                SecretValue.unsafe_plain_text(pat_value) if pat_value else None
            ),
            removal_policy=removal_policy,
        )

        return secret

    def _create_llm_api_keys_secret(
        self, removal_policy: RemovalPolicy
    ) -> secretsmanager.Secret:
        """Create secret for LLM provider API keys.

        Stores API keys as a JSON object with keys:
        - ANTHROPIC_API_KEY
        - OPENROUTER_API_KEY
        - ARCGIS_API_KEY

        Seeds values from .env if available.

        Returns:
            Secrets Manager secret for LLM API keys
        """
        api_keys = {k: SECRETS.get(k, "") for k in _LLM_SECRET_KEYS}
        has_any_key = any(api_keys.values())

        secret = secretsmanager.Secret(
            self,
            "LLMApiKeysSecret",
            secret_name=f"pantry-pirate-radio/llm-api-keys-{self.environment_name}",
            description=f"LLM API keys (Anthropic/OpenRouter/ArcGIS) - {self.environment_name}",
            secret_string_value=(
                SecretValue.unsafe_plain_text(json.dumps(api_keys))
                if has_any_key
                else None
            ),
            removal_policy=removal_policy,
        )

        return secret

    def _create_tightbeam_api_keys_secret(
        self, removal_policy: RemovalPolicy
    ) -> secretsmanager.Secret:
        """Create secret for Tightbeam API keys.

        DEPRECATED: Tightbeam has been migrated to ppr-write-api plugin.
        This secret is retained because LambdaApiStack references it as a
        CloudFormation cross-stack export. Deleting it would fail the deploy.
        Remove in a future PR after staged CF cleanup.
        """
        value = SECRETS.get("TIGHTBEAM_API_KEYS", "")

        secret = secretsmanager.Secret(
            self,
            "TightbeamApiKeysSecret",
            secret_name=f"pantry-pirate-radio/tightbeam-api-keys-{self.environment_name}",
            description=f"Tightbeam API keys for location management - {self.environment_name}",
            secret_string_value=(
                SecretValue.unsafe_plain_text(value) if value else None
            ),
            removal_policy=removal_policy,
        )

        return secret
