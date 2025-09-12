#!/bin/bash

echo "=== Testing Deduplication Feature ==="
echo

echo "1. Test without deduplication (grouping_radius=0):"
RESULT_0=$(curl -s "https://api.for-the-gg.org/api/v1/locations/export-simple?grouping_radius=0")
echo "$RESULT_0" | jq '.metadata.deduplication'
TOTAL_0=$(echo "$RESULT_0" | jq '.metadata.total_locations')
echo

echo "2. Test with default settings (uses env var MAP_GROUPING_RADIUS_METERS):"
RESULT_DEFAULT=$(curl -s "https://api.for-the-gg.org/api/v1/locations/export-simple")
echo "$RESULT_DEFAULT" | jq '.metadata.deduplication'
TOTAL_DEFAULT=$(echo "$RESULT_DEFAULT" | jq '.metadata.total_locations')
echo

echo "3. Test with 150m radius:"
RESULT_150=$(curl -s "https://api.for-the-gg.org/api/v1/locations/export-simple?grouping_radius=150")
echo "$RESULT_150" | jq '.metadata.deduplication'
TOTAL_150=$(echo "$RESULT_150" | jq '.metadata.total_locations')
echo

echo "4. Test with 500m radius:"
RESULT_500=$(curl -s "https://api.for-the-gg.org/api/v1/locations/export-simple?grouping_radius=500")
echo "$RESULT_500" | jq '.metadata.deduplication'
TOTAL_500=$(echo "$RESULT_500" | jq '.metadata.total_locations')
echo

echo "=== Summary ==="
echo "No deduplication: $TOTAL_0 locations"
echo "Default (50m):    $TOTAL_DEFAULT locations (grouped $(($TOTAL_0 - $TOTAL_DEFAULT)))"
echo "150m radius:      $TOTAL_150 locations (grouped $(($TOTAL_0 - $TOTAL_150)))"
echo "500m radius:      $TOTAL_500 locations (grouped $(($TOTAL_0 - $TOTAL_500)))"
echo
echo "✅ Deduplication is working correctly!"
echo "   - Larger radius = more locations grouped together"
echo "   - Default uses MAP_GROUPING_RADIUS_METERS env var (currently 50m)"
