#!/bin/bash
# Script to run map search index migration

echo "Running map search index migration..."
echo "This will create indexes to improve search performance."
echo ""

# Run the migration using bouy
./bouy exec app python app/database/migrations/add_map_search_indexes.py

echo ""
echo "Migration complete!"
echo ""
echo "You can also run the SQL directly with:"
echo "  ./bouy exec db psql -U postgres -d pantry_pirate_radio < app/database/init_scripts/04_map_search_indexes.sql"
echo ""
echo "To verify indexes were created:"
echo "  ./bouy exec db psql -U postgres -d pantry_pirate_radio -c \"SELECT indexname FROM pg_indexes WHERE schemaname='public' AND indexname LIKE 'idx_%' ORDER BY indexname;\""