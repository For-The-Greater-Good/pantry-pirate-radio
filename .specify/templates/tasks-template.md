# Tasks: [FEATURE NAME]

**Input**: Design documents from `/specs/[###-feature-name]/`
**Prerequisites**: plan.md (required), research.md, data-model.md, contracts/

## Execution Flow (main)
```
1. Load plan.md from feature directory
   → If not found: ERROR "No implementation plan found"
   → Extract: tech stack, libraries, structure
2. Load optional design documents:
   → data-model.md: Extract entities → model tasks
   → contracts/: Each file → contract test task
   → research.md: Extract decisions → setup tasks
3. Generate tasks by category:
   → Setup: project init, dependencies, linting
   → Tests: contract tests, integration tests
   → Core: models, services, CLI commands
   → Integration: DB, middleware, logging
   → Polish: unit tests, performance, docs
4. Apply task rules:
   → Different files = mark [P] for parallel
   → Same file = sequential (no [P])
   → Tests before implementation (TDD)
5. Number tasks sequentially (T001, T002...)
6. Generate dependency graph
7. Create parallel execution examples
8. Validate task completeness:
   → All contracts have tests?
   → All entities have models?
   → All endpoints implemented?
9. Return: SUCCESS (tasks ready for execution)
```

## Format: `[ID] [P?] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- Include exact file paths in descriptions

## Path Conventions
- **PPR Structure**: `app/` for source code, `tests/` for all tests
- **Test naming**: `tests/test_[module]/test_[feature].py`
- **Service modules**: `app/[service]/` (api, scraper, llm, validator, etc.)
- All commands use `./bouy` exclusively - no direct docker or poetry

## Phase 3.1: Setup
- [ ] T001 Create feature module structure in `app/[module]/`
- [ ] T002 Update dependencies in `pyproject.toml` if needed
- [ ] T003 [P] Configure type hints and ensure mypy compliance

## Phase 3.2: Tests First (TDD) ⚠️ MUST COMPLETE BEFORE 3.3
**CRITICAL: These tests MUST be written and MUST FAIL before ANY implementation**
**Run with: `./bouy test --pytest tests/test_[module]/` to verify RED phase**
- [ ] T004 [P] API test for endpoint in tests/test_api/test_[endpoint].py
- [ ] T005 [P] Validator test in tests/test_validator/test_[feature].py
- [ ] T006 [P] Integration test in tests/test_integration/test_[flow].py
- [ ] T007 [P] HSDS compliance test in tests/test_api/test_hsds_compliance.py

## Phase 3.3: Core Implementation (ONLY after tests are failing)
**Run with: `./bouy test --pytest` after each task to verify GREEN phase**
- [ ] T008 [P] Database model in app/database/models/[model].py
- [ ] T009 [P] Repository in app/database/repositories/[repo].py
- [ ] T010 [P] Service layer in app/[module]/services/[service].py
- [ ] T011 FastAPI endpoint in app/api/endpoints/[endpoint].py
- [ ] T012 Validation service integration in app/validator/
- [ ] T013 HSDS compliance in Pydantic models
- [ ] T014 Error handling with proper logging

## Phase 3.4: Integration
- [ ] T015 Connect service to PostgreSQL with PostGIS
- [ ] T016 Redis queue integration for job processing
- [ ] T017 Content store deduplication check
- [ ] T018 HAARRRvest publisher integration

## Phase 3.5: Polish & Quality Gates
**CRITICAL: Must pass all checks before merge**
- [ ] T019 [P] Run `./bouy test --coverage` (must be 90%+)
- [ ] T020 [P] Run `./bouy test --mypy` (zero errors)
- [ ] T021 [P] Run `./bouy test --black` (formatting)
- [ ] T022 [P] Run `./bouy test --bandit` (security)
- [ ] T023 Run full test suite `./bouy test` (all must pass)

## Dependencies
- Tests (T004-T007) before implementation (T008-T014)
- T008 blocks T009, T015
- T016 blocks T018
- Implementation before polish (T019-T023)

## Parallel Example
```
# Launch T004-T007 together (TDD Red Phase):
Task: "Create API test for endpoint in tests/test_api/test_[endpoint].py"
Task: "Create validator test in tests/test_validator/test_[feature].py"
Task: "Create integration test in tests/test_integration/test_[flow].py"
Task: "Create HSDS compliance test in tests/test_api/test_hsds_compliance.py"

# Verify all tests fail:
./bouy test --pytest tests/  # Should show RED (failing tests)
```

## Notes
- [P] tasks = different files, no dependencies
- Verify tests fail before implementing (RED phase)
- Use `./bouy test --pytest` to run tests
- Use @agent-test-suite-monitor for test execution
- Commit after each task with conventional format
- All commands use `./bouy` - never direct docker/poetry
- Maintain 90% test coverage throughout

## Task Generation Rules
*Applied during main() execution*

1. **From Contracts**:
   - Each contract file → contract test task [P]
   - Each endpoint → implementation task
   
2. **From Data Model**:
   - Each entity → model creation task [P]
   - Relationships → service layer tasks
   
3. **From User Stories**:
   - Each story → integration test [P]
   - Quickstart scenarios → validation tasks

4. **Ordering**:
   - Setup → Tests → Models → Services → Endpoints → Polish
   - Dependencies block parallel execution

## Validation Checklist
*GATE: Checked by main() before returning*

- [ ] All API endpoints have corresponding tests
- [ ] All entities have database model tasks
- [ ] All tests come before implementation (TDD)
- [ ] Parallel tasks truly independent
- [ ] Each task specifies exact file path
- [ ] No task modifies same file as another [P] task
- [ ] HSDS v3.1.1 compliance verified
- [ ] All commands use `./bouy` exclusively
- [ ] Test coverage requirement (90%) mentioned
- [ ] Validation service integration included
