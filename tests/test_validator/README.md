# Validator Service Test Suite

This directory contains comprehensive test specifications for the validation service that sits between the LLM worker and reconciler in the data pipeline.

## Test Files

### `conftest.py`
Shared fixtures and test configuration for all validator tests.

### `test_base.py`
Tests for the `ValidationService` base class:
- Initialization and context manager support
- Passthrough method (data unchanged)
- Logging configuration
- Metadata preservation
- Database session handling

### `test_queue_setup.py`
Tests for validator queue setup and configuration:
- Queue creation and Redis connection
- Queue configuration (TTL, timeout, etc.)
- Worker configuration
- Enable/disable functionality
- Metrics setup

### `test_job_routing.py`
Tests for job routing through the validator:
- LLM → Validator → Reconciler pipeline
- Conditional routing based on configuration
- Data preservation through pipeline
- Error handling in routing

### `test_job_processor.py`
Tests for the `ValidationProcessor` class:
- Job processing entry point
- Database transaction handling
- Metrics updates
- Error handling and rollback
- Validation field updates

### `test_configuration.py`
Tests for validator configuration:
- Default configuration values
- Environment variable overrides
- Feature flags
- Queue and worker configuration
- Pipeline configuration with/without validator

### `test_backward_compatibility.py`
Tests ensuring backward compatibility when validator is disabled:
- Direct LLM → Reconciler routing
- Database fields are optional
- Existing code unchanged
- API endpoints unaffected
- Smooth enable/disable transitions

### `test_integration.py`
Integration tests for the validator service:
- Full pipeline testing
- Database integration
- Redis queue integration
- Worker processing
- Performance testing
- Error recovery

### `test_validator_main.py`
Tests for the main validator module:
- Module imports and exports
- Service initialization
- Worker setup and teardown
- CLI argument parsing
- Signal handling
- Health checks

## Running the Tests

Run all validator tests:
```bash
./bouy test --pytest tests/test_validator/
```

Run specific test file:
```bash
./bouy test --pytest tests/test_validator/test_base.py
```

Run with verbose output:
```bash
./bouy test --pytest tests/test_validator/ -- -v
```

## Expected Test Results

All tests are designed to **FAIL** initially since the validator service implementation doesn't exist yet. This follows TDD principles where tests are written before implementation.

### What These Tests Verify

1. **Structure**: The validator service follows the same patterns as existing services (reconciler, LLM worker)
2. **Data Flow**: Data passes through unchanged (no validation logic yet)
3. **Configuration**: Service can be enabled/disabled via settings
4. **Compatibility**: System works normally when validator is disabled
5. **Integration**: Validator integrates properly with existing queues and services

## Implementation Requirements

Based on these tests, the implementation needs:

1. **Directory Structure**:
   - `app/validator/` directory
   - `__init__.py`, `base.py`, `config.py`, `job_processor.py`, etc.

2. **Core Classes**:
   - `ValidationService`: Base class similar to `BaseReconciler`
   - `ValidationProcessor`: Processes jobs from queue
   - `ValidatorWorker`: RQ worker for processing jobs

3. **Queue Integration**:
   - `validator_queue` in Redis
   - Routing from LLM to validator
   - Forwarding from validator to reconciler

4. **Configuration**:
   - `VALIDATOR_ENABLED` setting (default: True)
   - `VALIDATOR_LOG_DATA_FLOW` setting
   - Other validator-specific settings

5. **Backward Compatibility**:
   - System must work with validator disabled
   - Direct LLM → Reconciler routing when disabled

## Next Steps

After these tests are reviewed and approved by @agent-tdd-implementation-planner:

1. @agent-tdd-implementation will implement minimal code to make tests pass
2. @agent-code-refactoring-executor will improve code quality
3. @agent-test-coverage-enhancer may add additional test coverage
4. @agent-integration-test-creator will verify component interactions