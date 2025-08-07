# Custom Type Stubs

This directory contains custom type stubs for third-party packages that don't provide their own type hints. Type stubs help maintain type safety across the codebase and enable better IDE support and static analysis.

## Purpose

Type stubs (`.pyi` files) provide type information for packages written without type annotations. They enable:
- Static type checking with mypy
- Better IDE autocomplete and IntelliSense
- Early detection of type-related bugs
- Improved code documentation through types

## Current Type Stubs

### prometheus_client-stubs
Type stubs for the prometheus-client package, providing type hints for:
- Metrics classes (Counter, Gauge, Histogram, Summary)
- Core functionality (generate_latest, push_to_gateway)
- Registry operations (REGISTRY, set_to_current_time)
- Common operations and configurations

### fastapi-stubs
Partial type stubs for FastAPI framework components that need additional type information.

### openai-stubs
Type stubs for the OpenAI Python client, including:
- Client initialization and configuration
- Chat completion types and responses
- API interaction types

### pytest-stubs
Type stubs for pytest testing framework, providing better type hints for test fixtures and assertions.

## Type Checking with Bouy

### Running Type Checks

```bash
# Run mypy type checking on all code
./bouy test --mypy

# Check specific files or directories
./bouy test --mypy app/api/
./bouy test --mypy app/api/ app/llm/

# Run all CI checks including type checking
./bouy test
```

### Type Checking Output

The type checker will report:
- Type mismatches and incompatible assignments
- Missing type annotations (if configured)
- Undefined attributes and methods
- Import errors for missing stubs

## Project Type Checking Standards

### Configuration

Type checking is configured in `pyproject.toml` under `[tool.mypy]`:
- Python version: 3.11
- Strict mode: Disabled (gradual typing approach)
- Missing imports: Ignored (allows untyped third-party packages)
- Custom stub paths: Configured via `mypy_path`

### Gradual Typing Approach

This project follows a gradual typing strategy:
1. **Core modules**: Should have comprehensive type hints
2. **API interfaces**: Must have complete type annotations
3. **Data models**: Fully typed using Pydantic
4. **Utilities**: Type hints added incrementally
5. **Scrapers**: Basic type hints, not strictly enforced

### Type Annotation Guidelines

```python
# Good: Clear type annotations
from typing import Optional, List, Dict, Any

def process_data(
    items: List[Dict[str, Any]], 
    filter_empty: bool = True
) -> Optional[Dict[str, Any]]:
    """Process data items with optional filtering."""
    ...

# Bad: Missing or vague types
def process_data(items, filter_empty=True):
    """Process data items."""
    ...
```

## Creating Custom Type Stubs

### When to Create Stubs

Create custom type stubs when:
- A package has no type hints and no official stubs
- Official stubs are incomplete or incorrect
- You need to override type definitions for specific use cases

### How to Create Stubs

1. **Create stub directory structure**:
   ```bash
   mkdir type_stubs/{package-name}-stubs
   touch type_stubs/{package-name}-stubs/py.typed
   ```

2. **Generate initial stubs** (if possible):
   ```bash
   ./bouy exec app stubgen -p {package-name} -o type_stubs/{package-name}-stubs/
   ```

3. **Create manual stubs** for specific modules:
   ```python
   # type_stubs/{package-name}-stubs/__init__.pyi
   from typing import Any, Optional, List
   
   class SomeClass:
       def __init__(self, config: dict[str, Any]) -> None: ...
       def method(self, param: str) -> Optional[str]: ...
   ```

4. **Add to mypy path** in `pyproject.toml`:
   ```toml
   [tool.mypy]
   mypy_path = "type_stubs/{package-name}-stubs:..."
   ```

5. **Test the stubs**:
   ```bash
   ./bouy test --mypy
   ```

### Stub File Structure

```
type_stubs/
├── {package-name}-stubs/
│   ├── py.typed                    # Marks as stub package
│   ├── __init__.pyi                # Main module stubs
│   └── submodule/
│       └── __init__.pyi            # Submodule stubs
```

## Installing Third-Party Stubs

### Check for Official Stubs

Before creating custom stubs, check if official type stubs exist:

```bash
# Search for types-* packages
./bouy exec app pip search types-{package-name}

# Common stub packages
types-requests      # For requests library
types-redis         # For redis library
types-pyyaml       # For PyYAML library
```

### Install Type Stubs

Add to `pyproject.toml` under `[tool.poetry.group.dev.dependencies]`:

```toml
[tool.poetry.group.dev.dependencies]
types-requests = "^2.32.0"
types-redis = "^4.6.0"
```

Then update dependencies:
```bash
./bouy build app
```

## Best Practices for Type Safety

### 1. Use Type Hints Consistently

- Add type hints to all function signatures in core modules
- Use descriptive type aliases for complex types
- Document generic types clearly

### 2. Leverage Pydantic Models

```python
from pydantic import BaseModel, Field

class Organization(BaseModel):
    """Type-safe organization model."""
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., min_length=1)
    location: Optional[Location] = None
```

### 3. Handle Optional Types Properly

```python
from typing import Optional

def get_value(key: str) -> Optional[str]:
    """Returns value or None if not found."""
    value = cache.get(key)
    if value is not None:  # Explicit None check
        return str(value)
    return None
```

### 4. Use Type Guards

```python
from typing import TypeGuard, Any

def is_valid_response(obj: Any) -> TypeGuard[dict[str, str]]:
    """Type guard for response validation."""
    return (
        isinstance(obj, dict) and
        all(isinstance(k, str) and isinstance(v, str) 
            for k, v in obj.items())
    )
```

## Troubleshooting

### Common Issues

1. **Import errors**: Package needs type stubs
   - Solution: Create custom stubs or install types-* package

2. **Attribute errors**: Incomplete stubs
   - Solution: Add missing attributes to stub files

3. **Type incompatibilities**: Incorrect stub definitions
   - Solution: Update stub signatures to match runtime behavior

4. **Mypy configuration issues**: Path or exclusion problems
   - Solution: Check `mypy_path` and `exclude` patterns in pyproject.toml

### Debugging Type Issues

```bash
# Show detailed mypy errors
./bouy exec app mypy --show-error-codes app/module.py

# Reveal internal types
./bouy exec app mypy --reveal-type app/module.py

# Check specific file ignoring config
./bouy exec app mypy --no-config-file app/module.py
```

## Maintenance

### Regular Tasks

1. **Update stubs** when package APIs change
2. **Review MISSING_STUBS.md** for packages needing stubs
3. **Check for new official stubs** for packages we maintain custom stubs for
4. **Run type checking** as part of CI/CD pipeline
5. **Document stub changes** in commit messages

### Stub Quality Checklist

- [ ] All public APIs have type annotations
- [ ] Return types are explicitly defined
- [ ] Optional parameters use `Optional[]` or `| None`
- [ ] Complex types use clear type aliases
- [ ] Stubs are tested with actual usage
- [ ] Documentation explains any non-obvious types
