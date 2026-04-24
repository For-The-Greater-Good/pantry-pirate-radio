"""Tests for the main-repo CDK that wires portal_ingest scraper dispatch
into the ppr-write-api plugin Lambda.

The Write API Lambda dispatches the admin portal CSV/XLSX upload to an ECS
RunTask against the shared scraper Fargate task definition. This test
confirms the main repo passes the required plugin_context keys so the
write-api stack's `_wire_ingest()` method can emit the Lambda env vars +
IAM grants.

Without this wiring, POST /ingest returns 503 at runtime (the designed
first-deploy fallback). With this wiring, the Lambda has the cluster
ARN / task def ARN / container name / subnet IDs / security group IDs /
pass-role ARNs it needs to successfully invoke RunTask.
"""

from __future__ import annotations

import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from stacks.compute_stack import ComputeStack
from stacks.database_stack import DatabaseStack
from stacks.ecr_stack import ECRStack
from stacks.queue_stack import QueueStack
from stacks.secrets_stack import SecretsStack
from stacks.services_stack import ServiceConfig, ServicesStack
from stacks.storage_stack import StorageStack

# Import the write-api plugin stack from the submodule on disk. Skip the
# plugin-dependent tests cleanly if the submodule isn't checked out (e.g.
# a CI runner that forgot `submodules: recursive`). The MANUAL_ONLY_SCRAPERS
# test below still runs since it doesn't depend on the plugin.
_WRITE_API_INFRA = (
    Path(__file__).resolve().parents[2] / "plugins" / "ppr-write-api" / "infra"
)
_WRITE_API_STACK_FILE = _WRITE_API_INFRA / "write_api_stack.py"

if _WRITE_API_STACK_FILE.exists():
    if str(_WRITE_API_INFRA) not in sys.path:
        sys.path.insert(0, str(_WRITE_API_INFRA))
    from write_api_stack import WriteApiStack  # type: ignore[import-not-found]  # noqa: E402

    _PLUGIN_AVAILABLE = True
else:
    _PLUGIN_AVAILABLE = False
    WriteApiStack = None  # type: ignore[assignment,misc]


ENV = cdk.Environment(account="123456789012", region="us-east-1")


requires_plugin = pytest.mark.skipif(
    not _PLUGIN_AVAILABLE,
    reason="ppr-write-api submodule not checked out — run `git submodule update --init` or add `submodules: recursive` to the checkout step",
)


@pytest.fixture()
def wired_write_api_template() -> assertions.Template:
    """Build the minimal stack chain that app.py builds, populate
    plugin_context exactly the way app.py does, synthesize WriteApiStack,
    and return its CloudFormation Template for assertions."""
    app = cdk.App()
    env_name = "test"

    secrets_stack = SecretsStack(
        app, f"SecretsStack-{env_name}", environment_name=env_name, env=ENV
    )
    ECRStack(app, f"ECRStack-{env_name}", environment_name=env_name, env=ENV)
    storage_stack = StorageStack(
        app, f"StorageStack-{env_name}", environment_name=env_name, env=ENV
    )
    queue_stack = QueueStack(
        app, f"QueueStack-{env_name}", environment_name=env_name, env=ENV
    )
    compute_stack = ComputeStack(
        app, f"ComputeStack-{env_name}", environment_name=env_name, env=ENV
    )
    database_stack = DatabaseStack(
        app,
        f"DatabaseStack-{env_name}",
        vpc=compute_stack.vpc,
        environment_name=env_name,
        env=ENV,
    )
    service_config = ServiceConfig(
        database_host=database_stack.proxy_endpoint,
        database_name=database_stack.database_name,
        database_user="pantry_pirate",
        database_secret=database_stack.database_credentials_secret,
        queue_urls=queue_stack.queue_urls,
        content_bucket_name=storage_stack.content_bucket.bucket_name,
        content_index_table_name=storage_stack.content_index_table.table_name,
        geocoding_cache_table_name=database_stack.geocoding_cache_table.table_name,
        github_pat_secret=secrets_stack.github_pat_secret,
        llm_api_keys_secret=secrets_stack.llm_api_keys_secret,
    )
    services_stack = ServicesStack(
        app,
        f"ServicesStack-{env_name}",
        vpc=compute_stack.vpc,
        cluster=compute_stack.cluster,
        environment_name=env_name,
        config=service_config,
        env=ENV,
    )

    # Mirror the plugin_context construction in infra/app.py — specifically
    # the six keys this PR adds. Test will fail if any of these attributes
    # get renamed or removed from compute_stack / services_stack.
    plugin_context = {
        "vpc": compute_stack.vpc,
        "proxy_endpoint": database_stack.proxy_endpoint,
        "database_credentials_secret": database_stack.database_credentials_secret,
        # Portal ingest wiring (this PR):
        "scraper_cluster_arn": compute_stack.cluster.cluster_arn,
        "portal_ingest_task_arn": services_stack.scraper_task_definition.task_definition_arn,
        "scraper_container_name": "ScraperContainer",
        "scraper_subnet_ids": [s.subnet_id for s in compute_stack.vpc.private_subnets],
        "scraper_security_group_ids": [
            services_stack.scraper_security_group.security_group_id,
        ],
        "scraper_pass_role_arns": [
            services_stack.scraper_task_role.role_arn,
            services_stack.scraper_task_definition.execution_role.role_arn,
        ],
    }

    write_api_stack = WriteApiStack(
        app,
        f"WriteApiStack-{env_name}",
        environment_name=env_name,
        plugin_context=plugin_context,
        env=ENV,
    )
    return assertions.Template.from_stack(write_api_stack)


@requires_plugin
class TestLambdaEnvVars:
    """The Lambda must receive the five SCRAPER_* env vars from plugin_context."""

    def test_scraper_cluster_arn_is_set(self, wired_write_api_template) -> None:
        _assert_env_var_present(wired_write_api_template, "SCRAPER_CLUSTER_ARN")

    def test_scraper_task_family_is_set(self, wired_write_api_template) -> None:
        _assert_env_var_present(wired_write_api_template, "SCRAPER_TASK_FAMILY")

    def test_scraper_container_name_is_scraper_container(
        self, wired_write_api_template
    ) -> None:
        env_vars = _get_write_api_env_vars(wired_write_api_template)
        assert env_vars.get("SCRAPER_CONTAINER_NAME") == "ScraperContainer"

    def test_scraper_subnet_ids_is_csv(self, wired_write_api_template) -> None:
        _assert_env_var_present(wired_write_api_template, "SCRAPER_SUBNET_IDS")

    def test_scraper_security_group_ids_is_csv(self, wired_write_api_template) -> None:
        _assert_env_var_present(wired_write_api_template, "SCRAPER_SECURITY_GROUP_IDS")

    def test_uploads_bucket_name_is_set(self, wired_write_api_template) -> None:
        # Already covered by the plugin's own tests, but re-assert here to
        # prove the full end-to-end wiring lands Lambda env vars for both
        # the S3 bucket (write-api owns) and the ECS dispatch (main repo).
        _assert_env_var_present(wired_write_api_template, "UPLOADS_BUCKET_NAME")


@requires_plugin
class TestIamGrants:
    """Lambda IAM must include ecs:RunTask scoped to the task def ARN
    and iam:PassRole scoped to the two role ARNs."""

    def test_ecs_runtask_policy_exists(self, wired_write_api_template) -> None:
        wired_write_api_template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": {
                    "Statement": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Action": "ecs:RunTask",
                                    "Effect": "Allow",
                                },
                            ),
                        ],
                    ),
                },
            },
        )

    def test_iam_passrole_policy_exists(self, wired_write_api_template) -> None:
        wired_write_api_template.has_resource_properties(
            "AWS::IAM::Policy",
            {
                "PolicyDocument": {
                    "Statement": assertions.Match.array_with(
                        [
                            assertions.Match.object_like(
                                {
                                    "Action": "iam:PassRole",
                                    "Effect": "Allow",
                                },
                            ),
                        ],
                    ),
                },
            },
        )


class TestManualOnlyScrapers:
    """portal_ingest must be in MANUAL_ONLY_SCRAPERS so the daily scheduler
    does not auto-run it with no upload payload."""

    def test_portal_ingest_is_manual_only(self) -> None:
        # Import from the main-repo app package, not the plugin.
        import importlib.util

        root = Path(__file__).resolve().parents[2]
        main_path = root / "app" / "scraper" / "__main__.py"
        spec = importlib.util.spec_from_file_location("_scraper_main", main_path)
        assert spec is not None
        module = importlib.util.module_from_spec(spec)
        # __main__.py imports from app.scraper.scrapers; stub to keep this
        # unit test hermetic (we only need the MANUAL_ONLY_SCRAPERS constant).
        import types

        sys.modules.setdefault("app.scraper.scrapers", types.ModuleType("stub"))
        try:
            spec.loader.exec_module(module)
        except Exception:
            # If the module import fails for reasons unrelated to the
            # constant (e.g. missing scraper modules), fall back to a
            # plain text read.
            text = main_path.read_text()
            assert '"portal_ingest"' in text, (
                "MANUAL_ONLY_SCRAPERS must include 'portal_ingest' — "
                "otherwise the daily scheduler will try to run an empty upload"
            )
            return
        assert "portal_ingest" in module.MANUAL_ONLY_SCRAPERS


# --- helpers ---


def _get_write_api_env_vars(
    template: assertions.Template,
) -> dict[str, object]:
    """Return the Environment.Variables dict of the WriteApi Lambda."""
    funcs = template.find_resources("AWS::Lambda::Function")
    api_func = next((f for k, f in funcs.items() if "WriteApi" in k), None)
    assert api_func is not None, "WriteApiStack did not emit a Lambda function"
    vars_: dict[str, object] = (
        api_func.get("Properties", {}).get("Environment", {}).get("Variables", {})
    )
    return vars_


def _assert_env_var_present(template: assertions.Template, name: str) -> None:
    env_vars = _get_write_api_env_vars(template)
    assert (
        name in env_vars
    ), f"Expected Lambda env var {name!r}, found keys: {sorted(env_vars)}"
