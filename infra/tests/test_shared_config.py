"""Tests for shared pipeline configuration in CDK context."""

import json

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from shared_config import SHARED, SECRETS
from stacks.batch_stack import BatchInferenceStack
from stacks.compute_stack import ComputeStack
from stacks.ecr_stack import ECRStack
from stacks.queue_stack import QueueStack
from stacks.services_stack import ServicesStack, ServiceConfig
from stacks.storage_stack import StorageStack


class TestSharedConfig:
    """Tests for the SHARED config dict."""

    def test_shared_contains_all_expected_keys(self):
        """SHARED dict must have all Category 1 variables."""
        expected_keys = {
            "LLM_TEMPERATURE",
            "LLM_MAX_TOKENS",
            "LLM_TIMEOUT",
            "LLM_RETRIES",
            "VALIDATOR_ENABLED",
            "VALIDATION_REJECTION_THRESHOLD",
            "VALIDATOR_ENRICHMENT_ENABLED",
            "ENRICHMENT_CACHE_TTL",
            "ENRICHMENT_TIMEOUT",
            "ENRICHMENT_GEOCODING_PROVIDERS",
            "GEOCODING_PROVIDER",
            "GEOCODING_ENABLE_FALLBACK",
            "GEOCODING_MAX_RETRIES",
            "GEOCODING_TIMEOUT",
            "CONTENT_STORE_ENABLED",
            "RECONCILER_LOCATION_TOLERANCE",
        }
        assert set(SHARED.keys()) == expected_keys

    def test_shared_values_are_strings(self):
        """All SHARED values must be strings for CDK env dicts."""
        for key, value in SHARED.items():
            assert isinstance(
                value, str
            ), f"SHARED[{key!r}] = {value!r} is not a string"

    def test_shared_llm_max_tokens(self):
        """LLM_MAX_TOKENS must be '64768' (not '8192' or 'None')."""
        assert SHARED["LLM_MAX_TOKENS"] == "64768"

    def test_shared_boolean_values_are_lowercase(self):
        """Boolean values must be lowercase 'true'/'false'."""
        bool_keys = [
            "VALIDATOR_ENABLED",
            "VALIDATOR_ENRICHMENT_ENABLED",
            "GEOCODING_ENABLE_FALLBACK",
            "CONTENT_STORE_ENABLED",
        ]
        for key in bool_keys:
            assert SHARED[key] in (
                "true",
                "false",
            ), f"SHARED[{key!r}] = {SHARED[key]!r}, expected 'true' or 'false'"

    def test_shared_geocoding_providers_is_json_list(self):
        """ENRICHMENT_GEOCODING_PROVIDERS must be a JSON-encoded list."""
        providers = json.loads(SHARED["ENRICHMENT_GEOCODING_PROVIDERS"])
        assert isinstance(providers, list)
        assert "arcgis" in providers


class TestSecretsConfig:
    """Tests for the SECRETS config dict."""

    def test_secrets_only_contains_allowed_keys(self):
        """SECRETS must only contain known secret keys."""
        allowed = {
            "ARCGIS_API_KEY",
            "OPENROUTER_API_KEY",
            "ANTHROPIC_API_KEY",
            "DATA_REPO_TOKEN",
        }
        for key in SECRETS:
            assert key in allowed, f"Unexpected secret key: {key!r}"


class TestBatchStackUsesSharedConfig:
    """Tests that BatchInferenceStack uses shared config values."""

    @pytest.fixture
    def template(self):
        """Create BatchInferenceStack and return CloudFormation template."""
        app = cdk.App()
        storage = StorageStack(app, "StorageStack", environment_name="dev")
        queues = QueueStack(app, "QueueStack", environment_name="dev")
        compute = ComputeStack(app, "ComputeStack", environment_name="dev")
        ecr = ECRStack(app, "ECRStack", environment_name="dev")
        BatchInferenceStack(
            app,
            "BatchStack",
            environment_name="dev",
            content_bucket=storage.content_bucket,
            jobs_table=storage.jobs_table,
            llm_queue=queues.llm_queue,
            validator_queue=queues.validator_queue,
            reconciler_queue=queues.reconciler_queue,
            recorder_queue=queues.recorder_queue,
            vpc=compute.vpc,
            ecr_repository=ecr.repositories.get("batch-lambda"),
        )
        return assertions.Template.from_stack(app.node.find_child("BatchStack"))

    def test_batcher_lambda_has_shared_llm_max_tokens(self, template):
        """Batcher Lambda must use shared LLM_MAX_TOKENS (64768)."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            assertions.Match.object_like(
                {
                    "Environment": {
                        "Variables": assertions.Match.object_like(
                            {
                                "LLM_MAX_TOKENS": SHARED["LLM_MAX_TOKENS"],
                            }
                        ),
                    },
                }
            ),
        )

    def test_batcher_lambda_has_shared_llm_temperature(self, template):
        """Batcher Lambda must use shared LLM_TEMPERATURE."""
        template.has_resource_properties(
            "AWS::Lambda::Function",
            assertions.Match.object_like(
                {
                    "Environment": {
                        "Variables": assertions.Match.object_like(
                            {
                                "LLM_TEMPERATURE": SHARED["LLM_TEMPERATURE"],
                            }
                        ),
                    },
                }
            ),
        )


class TestServicesStackUsesSharedConfig:
    """Tests that ServicesStack passes shared config to services."""

    @pytest.fixture
    def template(self):
        """Create ServicesStack and return CloudFormation template."""
        app = cdk.App()
        compute = ComputeStack(app, "ComputeStack", environment_name="dev")
        import aws_cdk.aws_ecs as ecs

        cluster = ecs.Cluster(compute, "TestCluster", vpc=compute.vpc)
        config = ServiceConfig(
            queue_urls={"validator": "https://sqs.example.com/validator"},
        )
        ServicesStack(
            app,
            "ServicesStack",
            environment_name="dev",
            vpc=compute.vpc,
            cluster=cluster,
            config=config,
        )
        return assertions.Template.from_stack(app.node.find_child("ServicesStack"))

    def test_validator_has_geocoding_provider(self, template):
        """Validator task def must include GEOCODING_PROVIDER."""
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            assertions.Match.object_like(
                {
                    "ContainerDefinitions": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Environment": assertions.Match.array_with(
                                        [
                                            assertions.Match.object_like(
                                                {
                                                    "Name": "GEOCODING_PROVIDER",
                                                    "Value": SHARED[
                                                        "GEOCODING_PROVIDER"
                                                    ],
                                                }
                                            ),
                                        ]
                                    ),
                                }
                            ),
                        ]
                    ),
                }
            ),
        )

    def test_validator_has_geocoding_enable_fallback(self, template):
        """Validator task def must include GEOCODING_ENABLE_FALLBACK."""
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            assertions.Match.object_like(
                {
                    "ContainerDefinitions": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Environment": assertions.Match.array_with(
                                        [
                                            assertions.Match.object_like(
                                                {
                                                    "Name": "GEOCODING_ENABLE_FALLBACK",
                                                    "Value": SHARED[
                                                        "GEOCODING_ENABLE_FALLBACK"
                                                    ],
                                                }
                                            ),
                                        ]
                                    ),
                                }
                            ),
                        ]
                    ),
                }
            ),
        )

    def test_validator_has_enrichment_geocoding_providers(self, template):
        """Validator task def must include ENRICHMENT_GEOCODING_PROVIDERS."""
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            assertions.Match.object_like(
                {
                    "ContainerDefinitions": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Environment": assertions.Match.array_with(
                                        [
                                            assertions.Match.object_like(
                                                {
                                                    "Name": "ENRICHMENT_GEOCODING_PROVIDERS",
                                                    "Value": SHARED[
                                                        "ENRICHMENT_GEOCODING_PROVIDERS"
                                                    ],
                                                }
                                            ),
                                        ]
                                    ),
                                }
                            ),
                        ]
                    ),
                }
            ),
        )

    def test_validator_has_validator_enabled(self, template):
        """Validator task def must include VALIDATOR_ENABLED."""
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            assertions.Match.object_like(
                {
                    "ContainerDefinitions": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Environment": assertions.Match.array_with(
                                        [
                                            assertions.Match.object_like(
                                                {
                                                    "Name": "VALIDATOR_ENABLED",
                                                    "Value": SHARED[
                                                        "VALIDATOR_ENABLED"
                                                    ],
                                                }
                                            ),
                                        ]
                                    ),
                                }
                            ),
                        ]
                    ),
                }
            ),
        )

    def test_validator_has_validation_rejection_threshold(self, template):
        """Validator task def must include VALIDATION_REJECTION_THRESHOLD."""
        template.has_resource_properties(
            "AWS::ECS::TaskDefinition",
            assertions.Match.object_like(
                {
                    "ContainerDefinitions": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Environment": assertions.Match.array_with(
                                        [
                                            assertions.Match.object_like(
                                                {
                                                    "Name": "VALIDATION_REJECTION_THRESHOLD",
                                                    "Value": SHARED[
                                                        "VALIDATION_REJECTION_THRESHOLD"
                                                    ],
                                                }
                                            ),
                                        ]
                                    ),
                                }
                            ),
                        ]
                    ),
                }
            ),
        )
