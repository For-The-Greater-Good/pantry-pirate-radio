# Custom Type Stubs

This directory contains custom type stubs for packages that don't provide their own type hints.

## Packages

### prometheus-client-stubs
Type stubs for the prometheus-client package, providing type hints for:
- Metrics classes (Counter, Gauge, Histogram, Summary)
- Core functionality (generate_latest, push_to_gateway)
- Common operations and configurations

### structlog-stubs
Type stubs for the structlog package, providing type hints for:
- Core logging functionality
- Processors for log formatting and manipulation
- Standard library integration
- Common configuration patterns

## Usage

These stubs are automatically included in the mypy path via pyproject.toml configuration.

## Development

When adding new stubs:
1. Create a new directory named `{package-name}-stubs`
2. Add an empty `py.typed` file in the stub directory
3. Create `.pyi` files matching the package's module structure
4. Add appropriate type hints based on the package's documentation and runtime behavior
5. Add tests to verify the type hints work correctly
