#!/bin/bash
# Local Development Server Launcher for Hyperplexity
# Usage:
#   ./start-local.sh          # Launch with -dev.html (development mode)
#   ./start-local.sh prod     # Launch with .html (production mode)
#   ./start-local.sh --port 3000  # Use custom port

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
DEFAULT_PORT=8000
PORT=$DEFAULT_PORT
MODE="dev"
HTML_FILE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        prod|production)
            MODE="prod"
            shift
            ;;
        --port|-p)
            PORT="$2"
            shift 2
            ;;
        --help|-h)
            echo "Hyperplexity Local Development Server"
            echo ""
            echo "Usage:"
            echo "  ./start-local.sh              Launch with dev build"
            echo "  ./start-local.sh prod         Launch with production build"
            echo "  ./start-local.sh --port 3000  Use custom port"
            echo ""
            echo "Options:"
            echo "  prod, production    Use production HTML file (Hyperplexity_FullScript_Temp.html)"
            echo "  --port, -p PORT     Specify port number (default: 8000)"
            echo "  --help, -h          Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown argument: $1${NC}"
            echo "Run './start-local.sh --help' for usage information"
            exit 1
            ;;
    esac
done

# Determine HTML file based on mode
if [ "$MODE" = "prod" ]; then
    HTML_FILE="Hyperplexity_FullScript_Temp.html"
else
    HTML_FILE="Hyperplexity_FullScript_Temp-dev.html"
fi

# Get script directory (project root)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
HTML_PATH="$FRONTEND_DIR/$HTML_FILE"

# Check if HTML file exists
if [ ! -f "$HTML_PATH" ]; then
    echo -e "${RED}Error: $HTML_FILE not found!${NC}"
    echo -e "${YELLOW}Run 'python3 frontend/build.py' to build the frontend first.${NC}"
    exit 1
fi

# Print banner
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║${NC}  🚀 Hyperplexity Local Development Server          ${BLUE}║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Mode:${NC}      $([ "$MODE" = "prod" ] && echo "Production" || echo "Development")"
echo -e "${GREEN}File:${NC}      $HTML_FILE"
echo -e "${GREEN}Port:${NC}      $PORT"
echo -e "${GREEN}URL:${NC}       http://localhost:$PORT/$HTML_FILE"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop the server${NC}"
echo ""

# Change to frontend directory
cd "$FRONTEND_DIR"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down server...${NC}"
    # Kill the Python server if it's still running
    if [ ! -z "$SERVER_PID" ]; then
        kill $SERVER_PID 2>/dev/null || true
    fi
    echo -e "${GREEN}Server stopped.${NC}"
    exit 0
}

# Trap Ctrl+C and other termination signals
trap cleanup SIGINT SIGTERM

# Start Python HTTP server in background
echo -e "${BLUE}Starting HTTP server...${NC}"
python3 -m http.server $PORT &
SERVER_PID=$!

# Wait for server to start
sleep 2

# Check if server started successfully
if ! ps -p $SERVER_PID > /dev/null; then
    echo -e "${RED}Failed to start server. Port $PORT may already be in use.${NC}"
    echo -e "${YELLOW}Try a different port with: ./start-local.sh --port 3000${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Server started successfully!${NC}"
echo ""

# Open browser based on OS
URL="http://localhost:$PORT/$HTML_FILE"

if command -v xdg-open > /dev/null; then
    # Linux
    echo -e "${BLUE}Opening browser (Linux)...${NC}"
    xdg-open "$URL" 2>/dev/null &
elif command -v open > /dev/null; then
    # macOS
    echo -e "${BLUE}Opening browser (macOS)...${NC}"
    open "$URL"
elif command -v start > /dev/null; then
    # Windows Git Bash
    echo -e "${BLUE}Opening browser (Windows)...${NC}"
    start "$URL"
else
    echo -e "${YELLOW}Could not automatically open browser.${NC}"
    echo -e "${GREEN}Manually open: ${URL}${NC}"
fi

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Server is running! View logs below:${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════════${NC}"
echo ""

# Wait for server process (will show access logs)
wait $SERVER_PID
