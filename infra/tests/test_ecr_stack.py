"""Tests for ECRStack CDK stack."""

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.ecr_stack import ECRStack


class TestECRStackResources:
    """Tests for ECRStack resource creation."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return ECRStack(app, "TestECRStack", environment_name="dev")

    @pytest.fixture
    def template(self, stack):
        """Get CloudFormation template from stack."""
        return assertions.Template.from_stack(stack)

    def test_creates_seven_ecr_repositories(self, template):
        """ECRStack should create 7 ECR repositories."""
        # worker, validator, reconciler, publisher, recorder, scraper, app
        template.resource_count_is("AWS::ECR::Repository", 7)

    def test_worker_repository_exists(self, template):
        """Worker repository should be created."""
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "RepositoryName": assertions.Match.string_like_regexp(
                    "pantry-pirate-radio-worker.*"
                ),
            },
        )

    def test_validator_repository_exists(self, template):
        """Validator repository should be created."""
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "RepositoryName": assertions.Match.string_like_regexp(
                    "pantry-pirate-radio-validator.*"
                ),
            },
        )

    def test_app_repository_exists(self, template):
        """App repository should be created (for db-init and API)."""
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "RepositoryName": assertions.Match.string_like_regexp(
                    "pantry-pirate-radio-app.*"
                ),
            },
        )

    def test_repositories_have_image_scanning(self, template):
        """Repositories should have image scanning enabled."""
        template.has_resource_properties(
            "AWS::ECR::Repository",
            {
                "ImageScanningConfiguration": {"ScanOnPush": True},
            },
        )


class TestECRStackEnvironments:
    """Tests for environment-specific ECR configuration."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    def test_dev_repositories_can_be_deleted(self, app):
        """Dev repositories should have DESTROY removal policy."""
        stack = ECRStack(app, "DevECRStack", environment_name="dev")
        template = assertions.Template.from_stack(stack)

        # In dev, EmptyOnDelete should be true (allows deletion)
        template.has_resource(
            "AWS::ECR::Repository",
            {
                "DeletionPolicy": "Delete",
            },
        )

    def test_prod_repositories_retained(self, app):
        """Prod repositories should be retained on stack deletion."""
        stack = ECRStack(app, "ProdECRStack", environment_name="prod")
        template = assertions.Template.from_stack(stack)

        template.has_resource(
            "AWS::ECR::Repository",
            {
                "DeletionPolicy": "Retain",
            },
        )


class TestECRStackAttributes:
    """Tests for ECRStack attributes."""

    @pytest.fixture
    def app(self):
        """Create CDK app for testing."""
        return cdk.App()

    @pytest.fixture
    def stack(self, app):
        """Create stack for testing."""
        return ECRStack(app, "AttrTestStack", environment_name="dev")

    def test_exposes_worker_repository(self, stack):
        """Stack should expose worker_repository attribute."""
        assert stack.worker_repository is not None
        assert hasattr(stack.worker_repository, "repository_uri")

    def test_exposes_validator_repository(self, stack):
        """Stack should expose validator_repository attribute."""
        assert stack.validator_repository is not None
        assert hasattr(stack.validator_repository, "repository_uri")

    def test_exposes_reconciler_repository(self, stack):
        """Stack should expose reconciler_repository attribute."""
        assert stack.reconciler_repository is not None
        assert hasattr(stack.reconciler_repository, "repository_uri")

    def test_exposes_publisher_repository(self, stack):
        """Stack should expose publisher_repository attribute."""
        assert stack.publisher_repository is not None
        assert hasattr(stack.publisher_repository, "repository_uri")

    def test_exposes_recorder_repository(self, stack):
        """Stack should expose recorder_repository attribute."""
        assert stack.recorder_repository is not None
        assert hasattr(stack.recorder_repository, "repository_uri")

    def test_exposes_scraper_repository(self, stack):
        """Stack should expose scraper_repository attribute."""
        assert stack.scraper_repository is not None
        assert hasattr(stack.scraper_repository, "repository_uri")

    def test_exposes_app_repository(self, stack):
        """Stack should expose app_repository attribute."""
        assert stack.app_repository is not None
        assert hasattr(stack.app_repository, "repository_uri")

    def test_environment_name_stored(self, stack):
        """Stack should store environment name."""
        assert stack.environment_name == "dev"

    def test_repositories_dict_has_all_repos(self, stack):
        """repositories property should return dict of all repos."""
        repos = stack.repositories
        assert "worker" in repos
        assert "validator" in repos
        assert "reconciler" in repos
        assert "publisher" in repos
        assert "recorder" in repos
        assert "scraper" in repos
        assert "app" in repos
        assert len(repos) == 7
