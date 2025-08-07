# Missing Type Stubs Tracking

This document tracks third-party packages that are missing type stubs in our codebase. It serves as a reference for maintaining type safety and prioritizing stub creation efforts.

## Status Legend
- 🔴 **Missing stubs** - No type stubs available, needed for type checking
- 🟡 **Partial/incomplete stubs** - Some stubs exist but are incomplete
- 🟢 **Complete stubs** - Full type stubs available (custom or official)
- ⚪ **Not needed** - Package has built-in type hints or not used in typed code
- 🔵 **Official available** - Official types-* package exists

## Current Package Status

### Packages with Custom Stubs

Package | Status | Location | Notes
--------|--------|----------|-------
prometheus_client | 🟡 | type_stubs/prometheus_client-stubs | Basic stubs for Counter class, needs expansion for full API
fastapi | 🟡 | type_stubs/fastapi-stubs | Partial stubs to supplement official types
openai | 🟡 | type_stubs/openai-stubs | Custom stubs for chat completion types
pytest | 🟡 | type_stubs/pytest-stubs | Enhanced stubs for fixtures and assertions

### Packages with Official Stubs (Installed)

Package | Status | Package Name | Version
--------|--------|--------------|----------
redis | 🟢 | types-redis | 4.6.0.20241004
requests | 🟢 | types-requests | 2.32.4.20250611
pyyaml | 🟢 | types-pyyaml | 6.0.12.20250516
jsonschema | 🟢 | types-jsonschema | 4.24.0.20250708

### Packages Missing Type Stubs

Package | Status | Priority | Usage | Notes
--------|--------|----------|-------|-------
bs4 (BeautifulSoup) | 🔴 | High | 15+ scrapers | Used extensively for HTML parsing
geopy | 🔴 | High | Geocoding service | Critical for location services
playwright | 🔴 | Medium | 2 scrapers | Used for dynamic content scraping
demjson3 | 🔴 | Medium | Reconciler | JSON parsing with relaxed syntax
pdfplumber | 🔴 | Low | 2 scrapers | PDF content extraction
marshmallow | 🔴 | Low | Not actively used | Schema validation library
xlrd | 🔴 | Low | Not actively used | Excel file reading
db-to-sqlite | 🔴 | Low | Datasette integration | Database conversion utility

### Packages with Built-in Types

Package | Status | Notes
--------|--------|-------
pydantic | ⚪ | Full type support built-in
sqlalchemy | ⚪ | Comprehensive type annotations included
httpx | ⚪ | Native type hints throughout
structlog | ⚪ | Has type annotations (removed from missing list)

## Priority Guidelines

### High Priority
Packages that:
- Are used in core business logic
- Are imported in 5+ modules
- Affect API interfaces or data models
- Are critical for system functionality

### Medium Priority
Packages that:
- Are used in 2-4 modules
- Are important for specific features
- Have workarounds available

### Low Priority
Packages that:
- Are used in 1 module only
- Are used in non-critical code paths
- Are candidates for removal/replacement
- Have minimal type interaction

## Creating Stubs for Missing Packages

### For bs4 (BeautifulSoup)
```bash
# Most critical - used in many scrapers
./bouy exec app stubgen -p bs4 -o type_stubs/bs4-stubs/
# Then enhance with proper types for:
# - BeautifulSoup.__init__
# - Tag.find, find_all, select methods
# - NavigableString types
```

### For geopy
```bash
# Critical for geocoding services
./bouy exec app stubgen -p geopy -o type_stubs/geopy-stubs/
# Focus on:
# - Nominatim and ArcGIS geocoder classes
# - RateLimiter functionality
# - Location and Point types
# - Exception types
```

### For playwright
```bash
# Note: playwright has complex async APIs
# May need manual stub creation
# Focus on:
# - async_playwright context manager
# - Page class and methods
# - Browser and BrowserContext types
```

## Checking for Official Stubs

Before creating custom stubs, always check PyPI for official type packages:

```bash
# Check if types package exists (note: pip search is disabled on PyPI)
# Visit: https://pypi.org/search/?q=types-{package-name}

# Or try installing directly
./bouy exec app pip install types-{package-name}

# Common naming patterns:
# - types-{package-name}
# - {package-name}-stubs
# - {package-name}-types
```

## Process for Adding Type Stubs

1. **Identify missing stubs** through mypy errors:
   ```bash
   ./bouy test --mypy
   ```

2. **Check for official stubs**:
   - Search PyPI for types-* packages
   - Check package documentation for typing support
   - Look for py.typed marker in package

3. **Generate initial stubs** (if no official stubs):
   ```bash
   ./bouy exec app stubgen -p {package} -o type_stubs/{package}-stubs/
   ```

4. **Enhance generated stubs**:
   - Add proper return types
   - Fix Any types with specific types
   - Add missing methods and attributes
   - Test with actual usage

5. **Configure mypy path**:
   - Update `mypy_path` in pyproject.toml
   - Add stub directory to path

6. **Verify stubs work**:
   ```bash
   ./bouy test --mypy
   ```

7. **Update this document**:
   - Move package to appropriate section
   - Document any special considerations
   - Note version compatibility

## Maintenance Schedule

- **Weekly**: Review mypy errors for new missing stubs
- **Monthly**: Check for new official stub packages
- **Quarterly**: Audit and update custom stubs
- **Per PR**: Update when adding new dependencies

## Notes

- Mypy is configured with `ignore_missing_imports = true` to allow gradual stub adoption
- Custom stubs in type_stubs/ take precedence over installed stubs
- Some packages (like structlog) now include type hints and no longer need stubs
- The `py.typed` marker file is required in each stub package directory
- Stub packages should follow the `{package}-stubs` naming convention
