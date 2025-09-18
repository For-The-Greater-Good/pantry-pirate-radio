# Constitution Update Checklist

When amending the constitution (`.specify/memory/constitution.md`), ensure all dependent documents are updated to maintain consistency.

## Templates to Update

### When adding/modifying ANY principle:
- [ ] `.specify/templates/plan-template.md` - Update Constitution Check section
- [ ] `.specify/templates/spec-template.md` - Update if requirements/scope affected
- [ ] `.specify/templates/tasks-template.md` - Update if new task types needed
- [ ] `.claude/commands/plan.md` - Update if planning process changes
- [ ] `.claude/commands/tasks.md` - Update if task generation affected
- [ ] `CLAUDE.md` - Update runtime development guidelines
- [ ] `BOUY.md` - Update bouy command documentation if needed

### Principle-specific updates:

#### Principle I (Test-Driven Development):
- [ ] Ensure all templates emphasize TDD workflow
- [ ] Update test command examples to use `./bouy test`
- [ ] Add @agent-test-suite-monitor references
- [ ] Verify 90% coverage requirement mentioned
- [ ] Update Red-Green-Refactor cycle documentation

#### Principle II (Food Security First):
- [ ] Update geographic boundary references
- [ ] Ensure HSDS v3.1.1 compliance notes
- [ ] Add privacy/no personal data reminders
- [ ] Update mission alignment checks

#### Principle III (Container-Native Development):
- [ ] Update all commands to use `./bouy` exclusively
- [ ] Remove any direct docker/poetry commands
- [ ] Add Docker requirement notes
- [ ] Update environment setup instructions

#### Principle IV (Data Quality & Validation):
- [ ] Update validation pipeline references
- [ ] Add confidence scoring thresholds
- [ ] Include geocoding provider fallback notes
- [ ] Update deduplication requirements

#### Principle V (Privacy & Transparency):
- [ ] Add data collection restrictions
- [ ] Update attribution requirements
- [ ] Include open source/public domain notes
- [ ] Add provenance tracking requirements

#### Principle VI (Type Safety & Code Quality):
- [ ] Update mypy strict mode requirements
- [ ] Add formatting/linting command examples
- [ ] Include security scanning notes
- [ ] Update quality gate references

#### Principle VII (Distributed Architecture):
- [ ] Update service boundary documentation
- [ ] Add Redis queue references
- [ ] Include PostGIS requirements
- [ ] Update HAARRRvest publisher notes

## Validation Steps

1. **Before committing constitution changes:**
   - [ ] All templates reference new requirements
   - [ ] Examples updated to match new principles
   - [ ] No contradictions between documents
   - [ ] CLAUDE.md aligns with constitution
   - [ ] BOUY.md commands support requirements

2. **After updating templates:**
   - [ ] Run through a sample TDD workflow
   - [ ] Verify all constitution requirements addressed
   - [ ] Check that templates are self-contained
   - [ ] Test with `./bouy test` to verify compliance
   - [ ] Ensure CI/CD pipeline validates changes

3. **Version tracking:**
   - [ ] Update constitution version number
   - [ ] Note version in template footers
   - [ ] Add amendment to constitution history
   - [ ] Create git commit with conventional format
   - [ ] Update pull request template if needed

## Common Misses

Watch for these often-forgotten updates:
- Command documentation (`.claude/commands/*.md`)
- Bouy command examples in all docs
- Test coverage requirements (90% minimum)
- HSDS v3.1.1 compliance notes
- Docker-only development reminders
- `./bouy test` instead of direct pytest
- @agent references for test execution
- Geographic boundary specifications
- Data validation thresholds
- Cross-references between CLAUDE.md and constitution

## Template Sync Status

Last sync check: 2025-09-16
- Constitution version: 1.0.0
- Templates aligned: ⏳ (pending review)
- CLAUDE.md aligned: ✅
- BOUY.md aligned: ✅

## Quick Reference

### Core Commands
- Test execution: `./bouy test`
- Specific tests: `./bouy test --pytest`
- Coverage check: `./bouy test --coverage`
- Type checking: `./bouy test --mypy`
- Code formatting: `./bouy test --black`
- Linting: `./bouy test --ruff`
- Security: `./bouy test --bandit`

### Key Thresholds
- Test coverage: 90% minimum
- Validation confidence: 30 (rejection threshold)
- API response: < 200ms p95
- Scraper timeout: 30 seconds
- LLM timeout: 2 minutes

### Geographic Boundaries
- Latitude: 25°N to 49°N
- Longitude: -125°W to -67°W
- Focus: Continental United States

---

*This checklist ensures the Pantry Pirate Radio constitution's principles are consistently applied across all project documentation and development practices.*