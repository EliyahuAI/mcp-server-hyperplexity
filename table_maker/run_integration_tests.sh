#!/bin/bash
#
# Script to run integration tests for the table generation system
#
# Usage:
#   ./run_integration_tests.sh              # Run all integration tests
#   ./run_integration_tests.sh TEST_NAME    # Run specific test
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Table Maker Integration Tests${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}[ERROR]${NC} ANTHROPIC_API_KEY environment variable not set"
    echo ""
    echo "Please set your API key:"
    echo "  export ANTHROPIC_API_KEY='your-api-key-here'"
    echo ""
    exit 1
fi

echo -e "${GREEN}[SUCCESS]${NC} ANTHROPIC_API_KEY is set"
echo ""

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} pytest not found"
    echo ""
    echo "Please install dependencies:"
    echo "  pip install -r requirements.txt"
    echo ""
    exit 1
fi

echo -e "${GREEN}[SUCCESS]${NC} pytest is installed"
echo ""

# Determine which tests to run
if [ -z "$1" ]; then
    # Run all integration tests
    echo -e "${YELLOW}[INFO]${NC} Running ALL integration tests..."
    echo -e "${YELLOW}[INFO]${NC} This will make REAL API calls and may take 10-15 minutes"
    echo ""

    # Ask for confirmation
    read -p "Continue? (y/n) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi

    echo ""
    pytest -m integration tests/test_integration.py -v --tb=short
else
    # Run specific test
    TEST_NAME="$1"
    echo -e "${YELLOW}[INFO]${NC} Running specific test: ${TEST_NAME}"
    echo -e "${YELLOW}[INFO]${NC} This will make REAL API calls"
    echo ""

    pytest -m integration "tests/test_integration.py::${TEST_NAME}" -v -s --tb=short
fi

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}All tests PASSED${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}Some tests FAILED${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
