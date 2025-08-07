# Individual Scraper Documentation

This directory contains detailed documentation for each data source scraper in the Pantry Pirate Radio system.

## Documentation Resources

- **[TEMPLATE.md](TEMPLATE.md)** - Standard template for scraper documentation
- **[SCRAPER_DOCUMENTATION_STATUS.md](SCRAPER_DOCUMENTATION_STATUS.md)** - Current documentation status for all scrapers

## Available Scrapers

### Regional Food Banks - East Coast

#### Washington DC Metro Area
- **[Capital Area Food Bank DC](capital_area_food_bank_dc_scraper.md)** - Washington DC metropolitan area ✅

#### New York
- **[Food Bank for New York City](food_bank_for_new_york_city_ny_scraper.md)** - NYC metro area 📝
- **[NYC EFAP Programs](nyc_efap_programs_scraper.md)** - NYC Emergency Food Assistance Program

#### Pennsylvania
- **[Philabundance](philabundance_pa_scraper.md)** - Philadelphia region ✅
- **[Central Pennsylvania Food Bank](central_pennsylvania_food_bank_pa_scraper.md)** - Central PA 📝
- **[Chester County Food Bank](chester_county_food_bank_pa_scraper.md)** - Chester County 📝

#### Maryland
- **[Maryland Food Bank](maryland_food_bank_md_scraper.md)** - Maryland statewide ✅

#### Massachusetts
- **[Food Bank of Western Massachusetts](food_bank_of_western_massachusetts_ma_scraper.md)** - Western MA 📝

#### North Carolina
- **[Second Harvest Northwest NC](second_harvest_food_bank_of_northwest_north_carolina_nc_scraper.md)** - Northwest NC 📝

### Regional Food Banks - West Coast

#### California
- **[SF-Marin Food Bank](sfmarin_food_bank_ca_scraper.md)** - San Francisco Bay Area 📝
- **[Second Harvest of Silicon Valley](second_harvest_of_silicon_valley_ca_scraper.md)** - Silicon Valley 📝
- **[Food Bank of Contra Costa and Solano](food_bank_of_contra_costa_and_solano_ca_scraper.md)** - Contra Costa/Solano counties 📝
- **[Community Action of Napa Valley](community_action_of_napa_valley_food_bank_ca_scraper.md)** - Napa Valley 📝
- **[Find Food Bank CA](find_food_bank_ca_scraper.md)** - California statewide 📝

#### Washington
- **[Food Lifeline WA](food_lifeline_wa_scraper.md)** - Western Washington 📝

#### Hawaii
- **[The Food Basket Inc HI](the_food_basket_inc_hi_scraper.md)** - Hawaii Island 📝

### Regional Food Banks - Central/South

#### Ohio
- **[Toledo Northwestern Ohio Food Bank](toledo_northwestern_ohio_food_bank_oh_scraper.md)** - Northwest Ohio 📝
- **[FreshTrak](freshtrak_scraper.md)** - Ohio statewide (Mid-Ohio Food Collective) ✅

#### Texas
- **[Tarrant Area Food Bank](tarrant_area_food_bank_tx_scraper.md)** - Fort Worth area 📝

#### Alabama
- **[Feeding the Gulf Coast](feeding_the_gulf_coast_al_scraper.md)** - Gulf Coast region 📝

#### Colorado
- **[Care and Share Food Locator](care_and_share_food_locator_scraper.md)** - Southern Colorado

### Technology Platforms & APIs
- **[GetFull.app API](getfull_app_api_scraper.md)** - National real-time food bank inventory ✅
- **[Vivery API](vivery_api_scraper.md)** - National food assistance API platform
- **[Plentiful](plentiful_scraper.md)** - Food pantry reservation system

### Community & Specialized Resources
- **[Food Helpline](food_helpline_org_scraper.md)** - National food assistance hotline
- **[Rutgers Against Hunger](rutgers_against_hunger_scraper.md)** - New Jersey university program
- **[The Food Pantries](the_food_pantries_org_scraper.md)** - National food pantry directory
- **[HCCC Food Pantry](hccc_food_pantry_scraper.md)** - Hudson County Community College
- **[Mercer Food Finder](mercer_food_finder_scraper.md)** - Mercer County, NJ

### Development
- **[Sample Scraper](sample_scraper.md)** - Template for creating new scrapers

## Legend
- ✅ Fully documented with new template
- 📝 Documentation needs updating or creation
- All scrapers without marks have existing documentation that needs template updates

## Quick Reference

### Running Scrapers

```bash
# List all available scrapers
./bouy scraper --list

# Run a specific scraper
./bouy scraper [scraper_name]

# Test mode (limited data)
./bouy scraper-test [scraper_name]

# Run all scrapers
./bouy scraper --all

# Run scrapers in parallel
./bouy scraper scouting-party
```

### Documentation Standards

Each scraper documentation follows the standard template and includes:
- **Overview**: Purpose and data source description
- **Data Source**: Organization, API details, endpoints
- **Coverage Area**: Geographic regions and search methods
- **Technical Implementation**: Class details, configuration, dependencies
- **Data Structure**: Input/output formats, key fields
- **Usage**: Running and testing commands
- **Error Handling**: Common errors and recovery
- **Performance**: Runtime, data volume, optimizations
- **Troubleshooting**: Common issues and debug commands
- **Maintenance Notes**: Update frequency and known limitations

## See Also

- [Scraper Implementation Guide](../scrapers.md) - How to create new scrapers
- [Architecture Overview](../architecture.md) - System design context
- [LLM System](../llm.md) - How scraped data is processed
- [Testing Guide](../testing.md) - How to test scrapers
- [Bouy Commands](../../CLAUDE.md) - Complete command reference