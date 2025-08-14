# Data Validation Pipeline Implementation Handoff

## Overview
This document tracks the implementation of the data validation pipeline for improving location data quality in the Pantry Pirate Radio system. The pipeline adds validation, enrichment, and confidence scoring between the LLM worker and reconciler.

## Architecture
```
Scrapers → LLM Worker → **Validation Service** → Reconciler → HAARRRvest
```

## Implementation Workflow

For each issue, follow this TDD workflow:

1. **Read the next incomplete issue** from the list below
2. **Use @agent-tdd-test-spec** to create failing tests for the issue requirements
3. **Use @agent-tdd-implementation** to implement minimal code to pass the tests
4. **Use @agent-code-refactoring-executor** to refactor and improve code quality
5. **Use @agent-integration-test-creator** to write integration tests
6. **Use @agent-test-coverage-enhancer** to ensure 90%+ coverage
7. **Use @agent-doc-maintainer** to update/create documentation
8. **Update this document** with progress and notes

## Issues and Progress

### Issue #362: Add confidence score fields to database schema
**Status:** ⏳ Not Started  
**GitHub:** https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/362  
**Description:** Add database fields for confidence scoring and validation tracking  
**Key Requirements:**
- Add confidence_score, validation_notes, validation_status, geocoding_source columns
- Create migration script
- Update HAARRRvest views

**Implementation Notes:**
```
[To be filled during implementation]
```

**Tests Created:**
```
[List test files created]
```

**Documentation Updated:**
```
[List documentation updated]
```

---

### Issue #363: Create validation service structure
**Status:** ⏳ Not Started  
**GitHub:** https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/363  
**Description:** Create the validation service between LLM and reconciler  
**Key Requirements:**
- Create app/validator/ directory
- Create ValidationService base class
- Set up Redis queue
- Route LLM output through validator

**Implementation Notes:**
```
[To be filled during implementation]
```

**Tests Created:**
```
[List test files created]
```

**Documentation Updated:**
```
[List documentation updated]
```

---

### Issue #364: Refactor geocoding utilities
**Status:** ⏳ Not Started  
**GitHub:** https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/364  
**Description:** Move geocoding code to shared location  
**Key Requirements:**
- Move to app/core/geocoding/
- Consolidate from reconciler and LLM utils
- Maintain backward compatibility

**Implementation Notes:**
```
[To be filled during implementation]
```

**Tests Created:**
```
[List test files created]
```

**Documentation Updated:**
```
[List documentation updated]
```

---

### Issue #365: Add geocoding enrichment
**Status:** ⏳ Not Started  
**GitHub:** https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/365  
**Dependencies:** #363, #364  
**Description:** Implement data enrichment via geocoding  
**Key Requirements:**
- Geocode missing coordinates
- Reverse geocode missing addresses
- Provider fallback chain
- Track geocoding source

**Implementation Notes:**
```
[To be filled during implementation]
```

**Tests Created:**
```
[List test files created]
```

**Documentation Updated:**
```
[List documentation updated]
```

---

### Issue #366: Implement validation and scoring
**Status:** ⏳ Not Started  
**GitHub:** https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/366  
**Dependencies:** #362, #363  
**Description:** Add validation rules and confidence scoring  
**Key Requirements:**
- US bounds checking
- Test data detection
- Confidence score calculation (0-100)
- Store validation results

**Implementation Notes:**
```
[To be filled during implementation]
```

**Tests Created:**
```
[List test files created]
```

**Documentation Updated:**
```
[List documentation updated]
```

---

### Issue #367: Filter worthless data
**Status:** ⏳ Not Started  
**GitHub:** https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/367  
**Dependencies:** #366  
**Description:** Discard low-confidence data  
**Key Requirements:**
- Configurable threshold (default: 10)
- Mark as 'rejected' status
- Skip in reconciler
- Log rejections

**Implementation Notes:**
```
[To be filled during implementation]
```

**Tests Created:**
```
[List test files created]
```

**Documentation Updated:**
```
[List documentation updated]
```

---

### Issue #368: Export confidence to HAARRRvest
**Status:** ⏳ Not Started  
**GitHub:** https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/368  
**Dependencies:** #362  
**Description:** Include confidence in HAARRRvest exports  
**Key Requirements:**
- Add confidence to exports
- Update map data JSON
- Show in location details

**Implementation Notes:**
```
[To be filled during implementation]
```

**Tests Created:**
```
[List test files created]
```

**Documentation Updated:**
```
[List documentation updated]
```

---

### Issue #369: Update replay tool
**Status:** ⏳ Not Started  
**GitHub:** https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/369  
**Dependencies:** #363  
**Description:** Route replay through validator  
**Key Requirements:**
- Add --validate flag
- Route through validator service
- Update documentation

**Implementation Notes:**
```
[To be filled during implementation]
```

**Tests Created:**
```
[List test files created]
```

**Documentation Updated:**
```
[List documentation updated]
```

---

### Issue #370: Remove reconciler geocoding
**Status:** ⏳ Not Started  
**GitHub:** https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/370  
**Dependencies:** #365  
**Description:** Clean up redundant geocoding code  
**Key Requirements:**
- Remove geocoding from reconciler
- Use validator's coordinates
- Clean up imports

**Implementation Notes:**
```
[To be filled during implementation]
```

**Tests Created:**
```
[List test files created]
```

**Documentation Updated:**
```
[List documentation updated]
```

---

### Issue #371: Add test coverage
**Status:** ⏳ Not Started  
**GitHub:** https://github.com/For-The-Greater-Good/pantry-pirate-radio/issues/371  
**Dependencies:** All validator functionality  
**Description:** Comprehensive test coverage  
**Key Requirements:**
- 90%+ coverage
- Test all validation rules
- Test provider fallback
- Integration tests

**Implementation Notes:**
```
[To be filled during implementation]
```

**Tests Created:**
```
[List test files created]
```

**Documentation Updated:**
```
[List documentation updated]
```

---

## Overall Progress

**Issues Completed:** 0/10  
**Current Issue:** #362  
**Blockers:** None  

## Key Decisions and Learnings

### Design Decisions
- Validation happens AFTER LLM processing (not before) due to varied input formats
- All data gets published with confidence scores (users filter)
- Worthless data (confidence < 10) gets rejected, not deleted
- Geocoding enrichment happens before validation

### Technical Notes
- Using existing geocoding utilities from reconciler/LLM utils
- ArcGIS → Nominatim fallback chain for geocoding
- Confidence scores stored as INTEGER 0-100
- validation_notes as JSONB for flexibility

### Handoff Notes
```
[Add any special notes for the next person/session working on this]
```

## Commands for Testing

```bash
# Run tests for validator
./bouy test --pytest tests/test_validator/

# Test specific issue implementation
./bouy test --pytest tests/test_validator/test_issue_362.py

# Check coverage
./bouy test --coverage

# Run integration tests
./bouy test --pytest tests/test_integration/test_validation_pipeline.py
```

## Next Steps

1. Start with Issue #362 (database schema)
2. Follow TDD workflow for each issue
3. Update this document after each issue completion
4. Ensure each issue is atomic and can be merged independently

---

*Last Updated: [To be updated with each change]*  
*Current Session: [Session identifier/date]*