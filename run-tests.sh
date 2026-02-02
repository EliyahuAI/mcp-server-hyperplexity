#!/bin/bash
# Hyperplexity Test Runner
# Comprehensive test execution script for all test types

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

# Configuration
PROJECT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TEST_EMAIL="${TEST_EMAIL:-eliyahu@eliyahu.ai}"
TEST_SESSION="${TEST_SESSION:-session_20260202_144646_02c0f05c}"

# Print banner
print_banner() {
    echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  🧪 Hyperplexity Test Suite Runner                   ${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Print section header
print_section() {
    echo ""
    echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Parse arguments
TEST_TYPE="all"
HEADED=false
UI_MODE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --playwright|-p)
            TEST_TYPE="playwright"
            shift
            ;;
        --python|-py)
            TEST_TYPE="python"
            shift
            ;;
        --security|-s)
            TEST_TYPE="security"
            shift
            ;;
        --headed|-h)
            HEADED=true
            shift
            ;;
        --ui|-u)
            UI_MODE=true
            shift
            ;;
        --email)
            TEST_EMAIL="$2"
            shift 2
            ;;
        --session)
            TEST_SESSION="$2"
            shift 2
            ;;
        --help)
            echo "Hyperplexity Test Runner"
            echo ""
            echo "Usage:"
            echo "  ./run-tests.sh [options]"
            echo ""
            echo "Options:"
            echo "  --playwright, -p    Run only Playwright tests"
            echo "  --python, -py       Run only Python tests"
            echo "  --security, -s      Run only security tests"
            echo "  --headed, -h        Run Playwright in headed mode (show browser)"
            echo "  --ui, -u            Run Playwright in UI mode (interactive)"
            echo "  --email EMAIL       Test email (default: eliyahu@eliyahu.ai)"
            echo "  --session ID        Test session ID"
            echo "  --help              Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run-tests.sh                    # Run all tests"
            echo "  ./run-tests.sh --playwright       # Only Playwright tests"
            echo "  ./run-tests.sh --python           # Only Python tests"
            echo "  ./run-tests.sh --security         # Only security tests"
            echo "  ./run-tests.sh --headed           # Show browser while testing"
            echo "  ./run-tests.sh --ui               # Interactive test mode"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Run './run-tests.sh --help' for usage information"
            exit 1
            ;;
    esac
done

# Print configuration
print_banner
echo -e "${GREEN}Test Configuration:${NC}"
echo -e "  Test Type:    ${TEST_TYPE}"
echo -e "  Email:        ${TEST_EMAIL}"
echo -e "  Session:      ${TEST_SESSION}"
echo -e "  Headed Mode:  ${HEADED}"
echo -e "  UI Mode:      ${UI_MODE}"
echo ""

cd "$PROJECT_DIR"

# Track results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# ==========================================
# PLAYWRIGHT TESTS
# ==========================================

run_playwright_tests() {
    print_section "🎭 Playwright E2E Tests"

    if ! command_exists npx; then
        echo -e "${RED}✗ npm/npx not found. Install Node.js first.${NC}"
        echo -e "${YELLOW}  Install from: https://nodejs.org/${NC}"
        return 1
    fi

    # Check if node_modules exists
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}Installing dependencies...${NC}"
        npm install
    fi

    # Check if browsers are installed
    if [ ! -d "node_modules/.playwright" ]; then
        echo -e "${YELLOW}Installing Playwright browsers...${NC}"
        npx playwright install
    fi

    # Build frontend first
    echo -e "${BLUE}Building frontend...${NC}"
    python3 frontend/build.py

    # Run tests
    echo -e "${BLUE}Running Playwright tests...${NC}"

    PLAYWRIGHT_ARGS=""
    if [ "$HEADED" = true ]; then
        PLAYWRIGHT_ARGS="--headed"
    fi
    if [ "$UI_MODE" = true ]; then
        PLAYWRIGHT_ARGS="--ui"
    fi

    if [ "$TEST_TYPE" = "security" ]; then
        npx playwright test security-flow.spec.js $PLAYWRIGHT_ARGS
    else
        npx playwright test $PLAYWRIGHT_ARGS
    fi

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Playwright tests passed${NC}"
        ((PASSED_TESTS++))
    else
        echo -e "${RED}✗ Playwright tests failed${NC}"
        ((FAILED_TESTS++))
    fi
    ((TOTAL_TESTS++))
}

# ==========================================
# PYTHON API TESTS
# ==========================================

run_python_tests() {
    print_section "🐍 Python API Tests"

    if ! command_exists python3; then
        echo -e "${RED}✗ python3 not found${NC}"
        return 1
    fi

    # Test viewer session
    echo -e "${BLUE}Testing viewer session with JWT authentication...${NC}"
    python3 tests/test_viewer_session.py \
        --email "$TEST_EMAIL" \
        --session "$TEST_SESSION"

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Python tests passed${NC}"
        ((PASSED_TESTS++))
    else
        echo -e "${RED}✗ Python tests failed${NC}"
        ((FAILED_TESTS++))
    fi
    ((TOTAL_TESTS++))
}

# ==========================================
# SECURITY TESTS
# ==========================================

run_security_tests() {
    print_section "🔐 Security Tests"

    echo -e "${BLUE}Running security-specific tests...${NC}"

    # Playwright security tests
    if command_exists npx && [ -d "node_modules" ]; then
        echo -e "\n${BOLD}1. JWT Authentication Tests${NC}"
        npx playwright test security-flow.spec.js -g "JWT Authentication" $PLAYWRIGHT_ARGS

        echo -e "\n${BOLD}2. Token Revocation Tests${NC}"
        npx playwright test security-flow.spec.js -g "Security Violations" $PLAYWRIGHT_ARGS

        echo -e "\n${BOLD}3. Demo Mode Security${NC}"
        npx playwright test security-flow.spec.js -g "Demo Mode" $PLAYWRIGHT_ARGS
    fi

    # Python security tests (viewer with auth)
    if command_exists python3; then
        echo -e "\n${BOLD}4. API Security Tests${NC}"
        python3 tests/test_viewer_session.py \
            --email "$TEST_EMAIL" \
            --session "$TEST_SESSION"
    fi

    echo -e "${GREEN}✓ Security tests completed${NC}"
    ((PASSED_TESTS++))
    ((TOTAL_TESTS++))
}

# ==========================================
# MAIN EXECUTION
# ==========================================

# Run requested tests
case $TEST_TYPE in
    playwright)
        run_playwright_tests
        ;;
    python)
        run_python_tests
        ;;
    security)
        run_security_tests
        ;;
    all)
        run_playwright_tests
        run_python_tests
        ;;
    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        exit 1
        ;;
esac

# Print summary
print_section "📊 Test Summary"
echo -e "${BOLD}Total Test Suites:${NC} $TOTAL_TESTS"
echo -e "${GREEN}Passed:${NC} $PASSED_TESTS"
echo -e "${RED}Failed:${NC} $FAILED_TESTS"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✓ All tests passed!${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}${BOLD}✗ Some tests failed${NC}"
    echo -e "${YELLOW}View detailed report: npx playwright show-report${NC}"
    echo ""
    exit 1
fi
