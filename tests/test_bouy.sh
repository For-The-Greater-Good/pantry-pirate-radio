#!/bin/bash
# Test runner for bouy script
# This script tests bouy functionality using mocked docker compose commands

set -e

echo "=== Bouy Test Suite ==="
echo "Testing bouy script functionality..."

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Test function
run_test() {
    local test_name="$1"
    local expected_exit_code="${2:-0}"
    shift 2

    TESTS_RUN=$((TESTS_RUN + 1))
    echo -n "Testing: $test_name ... "

    # Set up test environment
    export BOUY_TEST_MODE=1
    export BOUY_TEST_COMPOSE_CMD="$(pwd)/tests/shell/fixtures/mock_compose.sh"

    # Run the command
    set +e
    output=$("$@" 2>&1)
    exit_code=$?
    set -e

    # Check result
    if [ $exit_code -eq $expected_exit_code ]; then
        echo -e "${GREEN}PASS${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
    else
        echo -e "${RED}FAIL${NC}"
        echo "  Expected exit code: $expected_exit_code, got: $exit_code"
        echo "  Output: $output"
        TESTS_FAILED=$((TESTS_FAILED + 1))
    fi
}

# Test bouy exists and is executable
if [ ! -x "./bouy" ]; then
    echo -e "${RED}ERROR: bouy script not found or not executable${NC}"
    exit 1
fi

# Basic command tests
echo -e "\n${YELLOW}Basic Commands:${NC}"
run_test "Help command" 0 ./bouy --help
run_test "Version command" 0 ./bouy --version
run_test "Invalid command" 1 ./bouy --programmatic invalid-command

# Service management tests
echo -e "\n${YELLOW}Service Management:${NC}"
run_test "Status command" 0 ./bouy --programmatic status
run_test "Up command" 0 ./bouy --programmatic up
run_test "Down command" 0 ./bouy --programmatic down

# Service-specific tests
echo -e "\n${YELLOW}Service Commands:${NC}"
run_test "Logs without service" 1 ./bouy --programmatic logs
run_test "Shell without service" 1 ./bouy --programmatic shell
run_test "Exec without service" 1 ./bouy --programmatic exec

# Scraper tests
echo -e "\n${YELLOW}Scraper Commands:${NC}"
run_test "Scraper list" 0 ./bouy --programmatic scraper list
run_test "Invalid scraper name" 1 ./bouy --programmatic scraper "../etc/passwd"

# JSON output tests
echo -e "\n${YELLOW}JSON Output Mode:${NC}"
run_test "JSON status" 0 ./bouy --json status
run_test "JSON up" 0 ./bouy --json up

# Mode tests
echo -e "\n${YELLOW}Environment Modes:${NC}"
run_test "Dev mode config" 0 ./bouy --dev config
run_test "Test mode config" 0 ./bouy --test config

# Print summary
echo -e "\n=== Test Summary ==="
echo "Tests run: $TESTS_RUN"
echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "\n${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "\n${RED}Some tests failed!${NC}"
    exit 1
fi