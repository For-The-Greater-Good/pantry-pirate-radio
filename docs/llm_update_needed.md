# Documentation Update Needed

The following documentation files contain references to removed components and need updating:

## docs/llm.md
- Lines 119-125: Remove FieldValidator example
- Lines 189-191: Remove ValidationProvider example  
- Lines 273-304: Remove HSDSAligner usage example
- Replace with production pipeline examples using direct provider.generate()

## docs/hsds_index.md
- Line 24: Remove reference to type_defs.py
- Line 27: Remove reference to field_validator.py
- Line 168: Remove reference to type_defs.py

## docs/worker.md
- Line 434: Remove ValidationProvider reference

## Components Removed
- HSDSAligner class (aligner.py)
- FieldValidator class (field_validator.py)
- ValidationProvider class (validator.py)
- Type definition files (type_defs.py, hsds_types.py, types.py)

## Components Still In Use
- SchemaConverter - Used by scrapers to generate LLM schemas
- ValidationConfig - Used by scrapers for validation configuration

## Production Pipeline
The production pipeline (app/reconciler/job_processor.py) uses:
1. Direct provider.generate() calls with structured outputs
2. Post-processing transformation from organization-centric to HSDS structure
3. No HSDSAligner or validation components