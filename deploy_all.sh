#!/bin/bash
# This script deploys all lambda functions sequentially.
# Usage: ./deploy_all.sh [--environment ENV] [--force-rebuild]
# Examples:
#   ./deploy_all.sh                              # Deploy to prod (default)
#   ./deploy_all.sh --environment dev            # Deploy to dev environment
#   ./deploy_all.sh --environment test --force-rebuild  # Deploy to test with force rebuild

set -e # Exit immediately if a command exits with a non-zero status.

# Default values
ENVIRONMENT="prod"
FORCE_REBUILD=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --environment|-e)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --force-rebuild)
            FORCE_REBUILD="--force-rebuild"
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [--environment ENV] [--force-rebuild]"
            echo "  --environment, -e  : Environment to deploy to (dev, test, staging, prod). Default: prod"
            echo "  --force-rebuild    : Force rebuild packages even if they exist"
            echo "  --help, -h         : Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate environment
if [[ ! "$ENVIRONMENT" =~ ^(dev|test|staging|prod)$ ]]; then
    echo "[ERROR] Invalid environment: $ENVIRONMENT"
    echo "[ERROR] Valid environments: dev, test, staging, prod"
    exit 1
fi

echo "=== Deploying All Lambda Functions ==="
echo "[INFO] Environment: $ENVIRONMENT"
echo "[INFO] Force rebuild: ${FORCE_REBUILD:-no}"
echo "======================================"

echo "--- Deploying Interface Lambda ---"
python.exe deployment/create_interface_package.py --deploy --environment "$ENVIRONMENT" $FORCE_REBUILD

echo "--- Deploying Validation Lambda ---"
python.exe deployment/create_package.py --deploy --environment "$ENVIRONMENT" $FORCE_REBUILD

echo "--- Deploying Config Lambda ---"
python.exe deployment/deploy_config_lambda.py --deploy --environment "$ENVIRONMENT" $FORCE_REBUILD

echo "--- All lambdas deployed successfully to $ENVIRONMENT! ---" 