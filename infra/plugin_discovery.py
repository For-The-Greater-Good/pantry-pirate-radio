"""Plugin CDK stack discovery for Pantry Pirate Radio.

Scans ``../plugins/*/plugin.yml`` manifests, dynamically loads declared CDK
stack classes, wires dependencies and RDS Proxy ingress, and resolves
inter-plugin dependencies.

Extracted from ``app.py`` to keep the entry point under 600 lines.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import warnings

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2


def discover_and_load_plugins(
    app: cdk.App,
    environment_name: str,
    env: cdk.Environment,
    *,
    plugin_context: dict,
    compute_stack: cdk.Stack,
    secrets_stack: cdk.Stack,
    database_stack: object,
    services_stack: cdk.Stack,
) -> dict[str, list]:
    """Discover and instantiate plugin CDK stacks.

    Args:
        app: The CDK app.
        environment_name: Target environment (dev/staging/prod).
        env: CDK ``Environment`` with account/region.
        plugin_context: Shared platform resources for plugin stacks.
        compute_stack: Stack dependency for all plugin stacks.
        secrets_stack: Stack dependency for all plugin stacks.
        database_stack: Database stack with ``proxy_security_group``.
        services_stack: Services stack — plugin stacks that reference its
            scraper task def ARN / role ARNs (e.g. ppr-write-api for portal
            ingest) need this ordering to resolve cross-stack references.

    Returns:
        A dict of ``{plugin_name: [stack_instances]}``.
    """
    import yaml

    plugins_dir = pathlib.Path(__file__).parent.parent / "plugins"
    plugin_stacks: dict[str, list] = {}
    plugin_deps: dict[str, list[str]] = {}

    for manifest in sorted(plugins_dir.glob("*/plugin.yml")):
        try:
            plugin_conf = yaml.safe_load(manifest.read_text())
        except (yaml.YAMLError, OSError) as exc:
            warnings.warn(
                f"Skipping plugin manifest {manifest}: {exc}",
                stacklevel=2,
            )
            continue
        infra_stacks = plugin_conf.get("cdk_stacks", [])
        plugin_infra_dir = manifest.parent / "infra"

        plugin_name = plugin_conf.get("name", manifest.parent.name)
        plugin_depends_on = plugin_conf.get("depends_on", [])
        plugin_deps.setdefault(plugin_name, plugin_depends_on)

        for stack_entry in infra_stacks:
            module_name = stack_entry.get("module")
            class_name = stack_entry.get("class")
            if not module_name or not class_name:
                continue
            module_path = plugin_infra_dir / f"{module_name}.py"
            if not module_path.resolve().is_relative_to(plugin_infra_dir.resolve()):
                warnings.warn(
                    f"Plugin module path escapes plugin dir: {module_path}",
                    stacklevel=2,
                )
                continue
            if not module_path.exists():
                warnings.warn(
                    f"Plugin CDK module not found: {module_path}", stacklevel=2
                )
                continue
            # Add plugin infra dir to sys.path so intra-plugin imports work
            plugin_infra_str = str(plugin_infra_dir.resolve())
            if plugin_infra_str not in sys.path:
                sys.path.insert(0, plugin_infra_str)
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            if not spec or not spec.loader:
                warnings.warn(f"Cannot load plugin module: {module_path}", stacklevel=2)
                continue
            mod = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(mod)  # type: ignore[union-attr]
            except Exception as exc:
                warnings.warn(
                    f"Failed to load plugin {module_path}: {exc}", stacklevel=2
                )
                continue
            stack_cls = getattr(mod, class_name, None)
            if not stack_cls:
                warnings.warn(
                    f"Class {class_name!r} not found in {module_path}",
                    stacklevel=2,
                )
                continue
            try:
                instance = stack_cls(
                    app,
                    f"{class_name}-{environment_name}",
                    environment_name=environment_name,
                    env=env,
                    plugin_context=plugin_context,
                    description=f"{plugin_name} plugin stack ({environment_name})",
                )
            except Exception as exc:
                warnings.warn(
                    f"Failed to instantiate {class_name}: {exc}", stacklevel=2
                )
                continue
            instance.add_dependency(compute_stack)
            instance.add_dependency(secrets_stack)
            instance.add_dependency(database_stack)
            instance.add_dependency(services_stack)

            # Per-stack tag for cost attribution
            cdk.Tags.of(instance).add("Stack", f"{class_name}-{environment_name}")

            # Track for inter-plugin dependency resolution
            plugin_stacks.setdefault(plugin_name, []).append(instance)

            # Wire RDS Proxy SG ingress for plugins with lambda_sg
            # Uses L1 CfnSecurityGroupIngress on the PLUGIN stack
            # (not database stack) to avoid cyclic cross-stack refs.
            if hasattr(instance, "lambda_sg") and instance.lambda_sg:
                ec2.CfnSecurityGroupIngress(
                    instance,
                    f"PluginLambdaToProxyIngress-{class_name}",
                    ip_protocol="tcp",
                    from_port=5432,
                    to_port=5432,
                    group_id=database_stack.proxy_security_group.security_group_id,
                    source_security_group_id=instance.lambda_sg.security_group_id,
                    description=f"{plugin_name} Lambda to RDS Proxy",
                )

    # Resolve inter-plugin dependencies (depends_on in plugin.yml)
    for dep_plugin, dep_names in plugin_deps.items():
        for dep_name in dep_names:
            dep_stacks_list = plugin_stacks.get(dep_name, [])
            if not dep_stacks_list:
                warnings.warn(
                    f"Plugin {dep_plugin!r} depends on {dep_name!r} but no stacks found",
                    stacklevel=2,
                )
                continue
            my_stacks = plugin_stacks.get(dep_plugin, [])
            for my_stack in my_stacks:
                for dep_stack in dep_stacks_list:
                    my_stack.add_dependency(dep_stack)

    return plugin_stacks
