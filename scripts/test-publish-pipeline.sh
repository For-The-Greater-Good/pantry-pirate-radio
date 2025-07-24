#!/bin/bash
# Test script for the data publishing pipeline
# This runs a minimal test to verify all components work

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}Testing Data Publishing Pipeline${NC}"
echo "=================================="

# Test 1: Check dependencies
echo -e "\n${GREEN}Test 1: Checking dependencies${NC}"
if "$SCRIPT_DIR/publish-data.sh" --help > /dev/null 2>&1; then
    echo "✓ Script is executable and shows help"
else
    echo -e "${RED}✗ Script failed to run${NC}"
    exit 1
fi

# Test 2: Verify file structure
echo -e "\n${GREEN}Test 2: Verifying file structure${NC}"
if [ -d "$PROJECT_ROOT/outputs" ]; then
    echo "✓ Outputs directory exists"
    
    # Create test structure if needed
    TEST_DATE=$(date +%Y-%m-%d)
    TEST_DIR="$PROJECT_ROOT/outputs/daily/$TEST_DATE/scrapers/test_scraper"
    mkdir -p "$TEST_DIR"
    
    # Create a test JSON file
    cat > "$TEST_DIR/test-job-123.json" << EOF
{
  "job_id": "test-job-123",
  "job": {
    "id": "test-job-123",
    "metadata": {"scraper_id": "test_scraper"},
    "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  },
  "status": "completed",
  "result": {
    "text": "{\\"organization\\": [{\\"name\\": \\"Test Org\\"}]}"
  }
}
EOF
    echo "✓ Created test data file"
else
    echo -e "${RED}✗ Outputs directory not found${NC}"
    exit 1
fi

# Test 3: Test sync without push
echo -e "\n${GREEN}Test 3: Testing sync (no push)${NC}"
TEST_REPO_PATH="$PROJECT_ROOT/test-HAARRRvest"
rm -rf "$TEST_REPO_PATH"

# Initialize test repository
git init "$TEST_REPO_PATH"
cd "$TEST_REPO_PATH"
git config user.email "test@example.com"
git config user.name "Test User"
echo "# Test Data Repo" > README.md
git add README.md
git commit -m "Initial commit"
cd "$PROJECT_ROOT"

# Run pipeline with test settings
export DATA_REPO_PATH="$TEST_REPO_PATH"
export DAYS_TO_SYNC=1
export PUSH_TO_REMOTE=false
export REBUILD_DATABASE=false  # Skip DB operations for test
export EXPORT_DATASETTE=false

if "$SCRIPT_DIR/publish-data.sh" > /tmp/publish-test.log 2>&1; then
    echo "✓ Pipeline ran successfully"
    
    # Verify files were synced
    if [ -f "$TEST_REPO_PATH/daily/$TEST_DATE/scrapers/test_scraper/test-job-123.json" ]; then
        echo "✓ Test file was synced correctly"
    else
        echo -e "${RED}✗ Test file was not synced${NC}"
        cat /tmp/publish-test.log
        exit 1
    fi
    
    # Check for stats file
    if [ -f "$TEST_REPO_PATH/STATS.md" ]; then
        echo "✓ Statistics file was created"
    else
        echo -e "${RED}✗ Statistics file was not created${NC}"
    fi
else
    echo -e "${RED}✗ Pipeline failed${NC}"
    cat /tmp/publish-test.log
    exit 1
fi

# Test 4: Verify Git operations
echo -e "\n${GREEN}Test 4: Verifying Git operations${NC}"
cd "$TEST_REPO_PATH"
if git log --oneline | grep -q "Data update"; then
    echo "✓ Git commit was created"
else
    echo -e "${RED}✗ Git commit was not created${NC}"
    exit 1
fi
cd "$PROJECT_ROOT"

# Cleanup
echo -e "\n${GREEN}Cleaning up test artifacts${NC}"
rm -rf "$TEST_REPO_PATH"
rm -f "$PROJECT_ROOT/outputs/daily/$TEST_DATE/scrapers/test_scraper/test-job-123.json"
rmdir "$PROJECT_ROOT/outputs/daily/$TEST_DATE/scrapers/test_scraper" 2>/dev/null || true
rm -f /tmp/publish-test.log

echo -e "\n${GREEN}All tests passed! ✓${NC}"
echo "The data publishing pipeline is working correctly."
echo
echo "Next steps:"
echo "1. Set up DATABASE_URL for full testing with database operations"
echo "2. Configure DATA_REPO_TOKEN in GitHub secrets"
echo "3. Run the GitHub Action manually to test automation"