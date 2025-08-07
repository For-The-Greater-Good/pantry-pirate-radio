# Scraper Documentation Status

This document tracks the documentation status of all scrapers in the Pantry Pirate Radio system.

**Last Updated**: 2025-08-07

## Documentation Template

All scraper documentation should follow the template in [TEMPLATE.md](./TEMPLATE.md)

## Scraper Documentation Status

### ✅ Fully Documented (Updated to Template)

| Scraper | Module Name | Documentation File | Status |
|---------|------------|-------------------|---------|
| Capital Area Food Bank DC | `capital_area_food_bank_dc_scraper` | [capital_area_food_bank_dc_scraper.md](./capital_area_food_bank_dc_scraper.md) | ✅ Complete |
| GetFull.app API | `getfull_app_api_scraper` | [getfull_app_api_scraper.md](./getfull_app_api_scraper.md) | ✅ Complete |
| Maryland Food Bank | `maryland_food_bank_md_scraper` | [maryland_food_bank_md_scraper.md](./maryland_food_bank_md_scraper.md) | ✅ Complete |

### 📝 Documentation Exists (Needs Update to Template)

| Scraper | Module Name | Documentation File | Issues |
|---------|------------|-------------------|---------|
| Care and Share Food Locator | `care_and_share_food_locator_scraper` | [care_and_share_food_locator_scraper.md](./care_and_share_food_locator_scraper.md) | Needs template format |
| Food Helpline Org | `food_helpline_org_scraper` | [food_helpline_org_scraper.md](./food_helpline_org_scraper.md) | Needs template format |
| FreshTrak | `freshtrak_scraper` | [freshtrak_scraper.md](./freshtrak_scraper.md) | Needs template format |
| HCCC Food Pantry | `hccc_food_pantry_scraper` | [hccc_food_pantry_scraper.md](./hccc_food_pantry_scraper.md) | Needs template format |
| Mercer Food Finder | `mercer_food_finder_scraper` | [mercer_food_finder_scraper.md](./mercer_food_finder_scraper.md) | Needs template format |
| NYC EFAP Programs | `nyc_efap_programs_scraper` | [nyc_efap_programs_scraper.md](./nyc_efap_programs_scraper.md) | Needs template format |
| Plentiful | `plentiful_scraper` | [plentiful_scraper.md](./plentiful_scraper.md) | Needs template format |
| Rutgers Against Hunger | `rutgers_against_hunger_scraper` | [rutgers_against_hunger_scraper.md](./rutgers_against_hunger_scraper.md) | Needs template format |
| Sample Scraper | `sample_scraper` | [sample_scraper.md](./sample_scraper.md) | Example/test scraper |
| The Food Pantries Org | `the_food_pantries_org_scraper` | [the_food_pantries_org_scraper.md](./the_food_pantries_org_scraper.md) | Needs template format |
| Vivery API | `vivery_api_scraper` | [vivery_api_scraper.md](./vivery_api_scraper.md) | Needs template format |

### ❌ Missing Documentation

| Scraper | Module Name | Class Name | Region |
|---------|------------|------------|--------|
| Central Pennsylvania Food Bank | `central_pennsylvania_food_bank_pa_scraper` | `CentralPennsylvaniaFoodBankPAScraper` | PA |
| Chester County Food Bank | `chester_county_food_bank_pa_scraper` | `ChesterCountyFoodBankPaScraper` | PA |
| Community Action of Napa Valley | `community_action_of_napa_valley_food_bank_ca_scraper` | `CommunityActionOfNapaValleyFoodBankCaScraper` | CA |
| Feeding the Gulf Coast | `feeding_the_gulf_coast_al_scraper` | `FeedingTheGulfCoastALScraper` | AL |
| Find Food Bank CA | `find_food_bank_ca_scraper` | `FindFoodBankCaScraper` | CA |
| Food Bank for New York City | `food_bank_for_new_york_city_ny_scraper` | `FoodBankForNewYorkCityNyScraper` | NY |
| Food Bank of Contra Costa and Solano | `food_bank_of_contra_costa_and_solano_ca_scraper` | `FoodBankOfContraCostaAndSolanoCAScraper` | CA |
| Food Bank of Western Massachusetts | `food_bank_of_western_massachusetts_ma_scraper` | `FoodBankOfWesternMassachusettsMaScraper` | MA |
| Food Lifeline WA | `food_lifeline_wa_scraper` | `FoodLifelineWAScraper` | WA |
| Philabundance | `philabundance_pa_scraper` | `PhilabundancePaScraper` | PA |
| Second Harvest Northwest NC | `second_harvest_food_bank_of_northwest_north_carolina_nc_scraper` | `SecondHarvestFoodBankOfNorthwestNorthCarolinaNCScraper` | NC |
| Second Harvest of Silicon Valley | `second_harvest_of_silicon_valley_ca_scraper` | `SecondHarvestOfSiliconValleyCaScraper` | CA |
| SF-Marin Food Bank | `sfmarin_food_bank_ca_scraper` | `SfmarinFoodBankCAScraper` | CA |
| Tarrant Area Food Bank | `tarrant_area_food_bank_tx_scraper` | `TarrantAreaFoodBankTXScraper` | TX |
| The Food Basket Inc HI | `the_food_basket_inc_hi_scraper` | `The_Food_Basket_Inc_HiScraper` | HI |
| Toledo Northwestern Ohio Food Bank | `toledo_northwestern_ohio_food_bank_oh_scraper` | `ToledoNorthwesternOhioFoodBankOHScraper` | OH |

## Action Items

### High Priority
1. ✅ Create documentation template - **COMPLETE**
2. ✅ Update existing documentation to match template format - **IN PROGRESS**
3. Create documentation for all undocumented scrapers

### Medium Priority
1. Add testing instructions specific to each scraper
2. Document common error patterns and solutions
3. Add performance benchmarks and optimization notes

### Low Priority
1. Create scraper development guide
2. Add examples of data transformations
3. Document integration with reconciler and publisher

## Notes

- All scrapers inherit from `ScraperJob` base class
- Most scrapers use either:
  - Direct API calls (REST/GraphQL)
  - ArcGIS Feature Services
  - HTML scraping with BeautifulSoup
  - JavaScript rendering with Playwright
- Common patterns include grid-based searches, pagination, and geocoding
- All scrapers should be testable with `./bouy scraper-test [name]`

## How to Update Documentation

1. Use the [TEMPLATE.md](./TEMPLATE.md) as a guide
2. Analyze the scraper implementation in `app/scraper/[scraper_name].py`
3. Run the scraper in test mode to understand its behavior
4. Document all configuration parameters and data structures
5. Include troubleshooting steps and common issues
6. Update this status document when complete