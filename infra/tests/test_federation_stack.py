"""Tests for FederationStack (archive tiering + retention prune, P1 PR-D).

The load-bearing property is the "never destroy" archive (§6.2g): the archive
bucket must have NO lifecycle expiry, be versioned, and block public access — so a
trimmed leaf's signed bytes survive forever and checkpoints/proofs stay valid.
"""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.compute_stack import ComputeStack
from stacks.ecr_stack import ECRStack
from stacks.federation_stack import FederationStack


class TestFederationStackResources:
    @pytest.fixture
    def app(self):
        return cdk.App()

    @pytest.fixture
    def compute(self, app):
        return ComputeStack(app, "TestComputeStack", environment_name="dev")

    @pytest.fixture
    def ecr(self, app):
        return ECRStack(app, "TestECRStack", environment_name="dev")

    @pytest.fixture
    def stack(self, app, compute, ecr):
        # Pass an ECR repo so the Lambda uses from_ecr (no image-asset bundling at synth).
        return FederationStack(
            app,
            "TestFederationStack",
            environment_name="dev",
            vpc=compute.vpc,
            ecr_repository=ecr.repositories.get("batch-lambda"),
        )

    @pytest.fixture
    def template(self, stack):
        return assertions.Template.from_stack(stack)

    def test_creates_prune_lambda_in_vpc(self, template):
        # Asserted by properties, not count: auto_delete_objects on the dev archive
        # bucket adds a custom-resource Lambda, so the count is >1.
        template.has_resource_properties(
            "AWS::Lambda::Function",
            {
                "FunctionName": "pantry-pirate-radio-federation-prune-dev",
                "VpcConfig": assertions.Match.any_value(),
            },
        )

    def test_creates_daily_eventbridge_rule_disabled_in_dev(self, template):
        template.resource_count_is("AWS::Events::Rule", 1)
        template.has_resource_properties("AWS::Events::Rule", {"State": "DISABLED"})

    def test_archive_bucket_never_expires_and_is_versioned(self, template):
        """The §6.2g 'never destroy' guard: versioned, public access blocked, and —
        critically — NO lifecycle expiry rule on the archive bucket."""
        template.has_resource_properties(
            "AWS::S3::Bucket",
            {
                "VersioningConfiguration": {"Status": "Enabled"},
                "PublicAccessBlockConfiguration": {
                    "BlockPublicAcls": True,
                    "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True,
                    "RestrictPublicBuckets": True,
                },
            },
        )
        for resource in template.find_resources("AWS::S3::Bucket").values():
            assert "LifecycleConfiguration" not in resource.get("Properties", {})


def test_eventbridge_rule_enabled_in_prod():
    app = cdk.App()
    compute = ComputeStack(app, "TestComputeStackProd", environment_name="prod")
    ecr = ECRStack(app, "TestECRStackProd", environment_name="prod")
    stack = FederationStack(
        app,
        "TestFederationStackProd",
        environment_name="prod",
        vpc=compute.vpc,
        ecr_repository=ecr.repositories.get("batch-lambda"),
    )
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::Events::Rule", {"State": "ENABLED"})
