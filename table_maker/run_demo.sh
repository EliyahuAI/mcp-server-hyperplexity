#!/bin/bash
# Quick-start script for Table Generation CLI Demo

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}================================${NC}"
echo -e "${CYAN}Table Generation System Demo${NC}"
echo -e "${CYAN}================================${NC}"
echo ""

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo -e "${RED}[ERROR]${NC} ANTHROPIC_API_KEY not set"
    echo ""
    echo "Please set your API key:"
    echo -e "  ${YELLOW}export ANTHROPIC_API_KEY='your-api-key-here'${NC}"
    echo ""
    echo "For permanent setup, add to ~/.bashrc:"
    echo -e "  ${YELLOW}echo \"export ANTHROPIC_API_KEY='your-key'\" >> ~/.bashrc${NC}"
    echo -e "  ${YELLOW}source ~/.bashrc${NC}"
    exit 1
fi

echo -e "${GREEN}[SUCCESS]${NC} API key found"
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if cli_demo.py exists
if [ ! -f "cli_demo.py" ]; then
    echo -e "${RED}[ERROR]${NC} cli_demo.py not found"
    exit 1
fi

# Check for Python
if command -v python3.exe &> /dev/null; then
    PYTHON_CMD="python3.exe"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}[ERROR]${NC} Python not found"
    exit 1
fi

echo -e "${GREEN}[INFO]${NC} Using Python: $PYTHON_CMD"
echo -e "${GREEN}[INFO]${NC} Starting CLI demo..."
echo ""

# Run the demo
exec "$PYTHON_CMD" cli_demo.py
