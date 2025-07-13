# ruff: noqa
# Whitelist for vulture dead code detection - not meant to be linted

# Redis protocol type annotations (required for type checking)
ConnectionPool  # Used in type annotations for Redis protocol
section  # Required parameter in Redis protocol interface

# Context manager protocol parameters (required by Python)
exc_type  # Required __aexit__ parameter
exc_val  # Required __aexit__ parameter
exc_tb  # Required __aexit__ parameter

# Pytest fixtures (used indirectly through fixture system)
mock_redis_url  # Sets up environment for Redis tests
