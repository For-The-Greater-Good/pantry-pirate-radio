"""Tests for SecretsStack CDK stack."""

import json
from unittest.mock import patch

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.secrets_stack import SecretsStack


class TestSecretsStackResources:
    """Tests for SecretsStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def dev_stack(self, app):
        """Create dev environment stack."""
        return SecretsStack(app, "TestSecretsStack", environment_name="dev")

    @pytest.fixture
    def prod_stack(self, app):
        """Create prod environment stack."""
        return SecretsStack(app, "TestSecretsStackProd", environment_name="prod")

    @pytest.fixture
    def dev_template(self, dev_stack):
        """Get CloudFormation template from dev stack."""
        return assertions.Template.from_stack(dev_stack)

    @pytest.fixture
    def prod_template(self, prod_stack):
        """Get CloudFormation template from prod stack."""
        return assertions.Template.from_stack(prod_stack)

    def test_creates_secrets(self, dev_template):
        """SecretsStack should create 2 secrets: GitHub PAT and LLM keys."""
        # DB credentials are in DatabaseStack to avoid cross-stack dependency issues
        dev_template.resource_count_is("AWS::SecretsManager::Secret", 2)

    def test_github_pat_secret_exists(self, dev_template):
        """GitHub PAT secret should exist."""
        dev_template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Description": assertions.Match.string_like_regexp(".*GitHub.*PAT.*")},
        )

    def test_llm_api_keys_secret_exists(self, dev_template):
        """LLM API keys secret should exist."""
        dev_template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {"Description": assertions.Match.string_like_regexp(".*LLM.*API.*keys.*")},
        )



class TestSecretsStackEnvironments:
    """Tests for environment-specific configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_dev_secrets_can_be_deleted(self, app):
        """Dev environment secrets should allow deletion."""
        stack = SecretsStack(app, "DevStack", environment_name="dev")
        template = assertions.Template.from_stack(stack)

        # In dev, secrets should have DeletionPolicy: Delete
        template.has_resource(
            "AWS::SecretsManager::Secret",
            {
                "DeletionPolicy": "Delete",
                "UpdateReplacePolicy": "Delete",
            },
        )

    def test_prod_secrets_retained(self, app):
        """Prod environment secrets should be retained on deletion."""
        stack = SecretsStack(app, "ProdStack", environment_name="prod")
        template = assertions.Template.from_stack(stack)

        # In prod, secrets should have DeletionPolicy: Retain
        template.has_resource(
            "AWS::SecretsManager::Secret",
            {
                "DeletionPolicy": "Retain",
                "UpdateReplacePolicy": "Retain",
            },
        )


class TestSecretsStackAttributes:
    """Tests for stack attributes and outputs."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return SecretsStack(app, "AttrTestStack", environment_name="dev")

    def test_exposes_github_pat_secret(self, stack):
        """Stack should expose github_pat_secret attribute."""
        assert stack.github_pat_secret is not None
        assert hasattr(stack.github_pat_secret, "secret_arn")

    def test_exposes_llm_api_keys_secret(self, stack):
        """Stack should expose llm_api_keys_secret attribute."""
        assert stack.llm_api_keys_secret is not None
        assert hasattr(stack.llm_api_keys_secret, "secret_arn")

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"


class TestSecretsStackSecretNames:
    """Tests for secret naming conventions."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_secrets_have_environment_suffix(self, app):
        """Secrets should include environment in their name."""
        stack = SecretsStack(app, "NameTestStack", environment_name="staging")
        template = assertions.Template.from_stack(stack)

        # Check that secrets have staging in their names
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {
                "Name": assertions.Match.string_like_regexp(
                    ".*pantry-pirate-radio.*staging.*"
                )
            },
        )


class TestSecretsPopulation:
    """Tests for secrets population from .env via shared_config.SECRETS."""

    @pytest.fixture
    def app(self):
        return cdk.App()

    @patch(
        "stacks.secrets_stack.SECRETS",
        {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENROUTER_API_KEY": "sk-or-test",
            "ARCGIS_API_KEY": "arcgis-test",
            "DATA_REPO_TOKEN": "ghp_test",
        },
    )
    def test_llm_secret_populated_from_env(self, app):
        """LLM API keys secret should contain JSON from .env values."""
        stack = SecretsStack(app, "PopulatedStack", environment_name="dev")
        template = assertions.Template.from_stack(stack)

        expected_json = json.dumps(
            {
                "ANTHROPIC_API_KEY": "sk-ant-test",
                "OPENROUTER_API_KEY": "sk-or-test",
                "ARCGIS_API_KEY": "arcgis-test",
            }
        )
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {
                "Name": "pantry-pirate-radio/llm-api-keys-dev",
                "SecretString": expected_json,
            },
        )

    @patch(
        "stacks.secrets_stack.SECRETS",
        {
            "DATA_REPO_TOKEN": "ghp_test",
        },
    )
    def test_github_pat_populated_from_env(self, app):
        """GitHub PAT secret should contain DATA_REPO_TOKEN from .env."""
        stack = SecretsStack(app, "PatStack", environment_name="dev")
        template = assertions.Template.from_stack(stack)

        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {
                "Name": "pantry-pirate-radio/github-pat-dev",
                "SecretString": "ghp_test",
            },
        )

    @patch("stacks.secrets_stack.SECRETS", {})
    def test_empty_env_creates_secrets_without_values(self, app):
        """Secrets should still be created when .env has no values."""
        stack = SecretsStack(app, "EmptyStack", environment_name="dev")
        template = assertions.Template.from_stack(stack)

        # All 3 secrets should exist
        template.resource_count_is("AWS::SecretsManager::Secret", 3)

    @patch(
        "stacks.secrets_stack.SECRETS",
        {
            "ANTHROPIC_API_KEY": "sk-ant-only",
        },
    )
    def test_partial_env_populates_available_keys(self, app):
        """LLM secret should include available keys with empty strings for missing ones."""
        stack = SecretsStack(app, "PartialStack", environment_name="dev")
        template = assertions.Template.from_stack(stack)

        expected_json = json.dumps(
            {
                "ANTHROPIC_API_KEY": "sk-ant-only",
                "OPENROUTER_API_KEY": "",
                "ARCGIS_API_KEY": "",
            }
        )
        template.has_resource_properties(
            "AWS::SecretsManager::Secret",
            {
                "Name": "pantry-pirate-radio/llm-api-keys-dev",
                "SecretString": expected_json,
            },
        )

