#!/bin/bash
# This script deploys all lambda functions sequentially.
# Usage: ./deploy_all.sh [--environment ENV] [--force-rebuild|--no-rebuild] [--deploy-mode MODE]
# Examples:
#   ./deploy_all.sh                              # Deploy to prod (default, unified mode)
#   ./deploy_all.sh --environment dev            # Deploy to dev environment
#   ./deploy_all.sh --deploy-mode dual           # Deploy both lightweight and background lambdas
#   ./deploy_all.sh --environment test --force-rebuild --deploy-mode dual  # Deploy to test with dual mode
#   ./deploy_all.sh --no-rebuild                 # Deploy without rebuilding packages

set -e # Exit immediately if a command exits with a non-zero status.

# Default values
ENVIRONMENT="prod"
REBUILD_OPTION=""
DEPLOY_MODE="unified"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --environment|-e)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --force-rebuild)
            REBUILD_OPTION="--force-rebuild"
            shift
            ;;
        --no-rebuild)
            REBUILD_OPTION="--no-rebuild"
            shift
            ;;
        --deploy-mode|-m)
            DEPLOY_MODE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--environment ENV] [--force-rebuild|--no-rebuild] [--deploy-mode MODE]"
            echo "  --environment, -e  : Environment to deploy to (dev, test, staging, prod). Default: prod"
            echo "  --force-rebuild    : Force rebuild packages even if they exist"
            echo "  --no-rebuild       : Skip rebuilding packages if they exist"
            echo "  --deploy-mode, -m  : Deployment mode (unified, dual). Default: unified"
            echo "                       unified - Single Lambda with all operations (legacy)"
            echo "                       dual    - Deploy both lightweight (API) and background (SQS) Lambdas"
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

# Validate deployment mode
if [[ ! "$DEPLOY_MODE" =~ ^(unified|dual)$ ]]; then
    echo "[ERROR] Invalid deployment mode: $DEPLOY_MODE"
    echo "[ERROR] Valid modes: unified, dual"
    exit 1
fi

echo "=== Deploying All Lambda Functions ==="
echo "[INFO] Environment: $ENVIRONMENT"
echo "[INFO] Deployment Mode: $DEPLOY_MODE"
echo "[INFO] Rebuild option: ${REBUILD_OPTION:-default (prompt if needed)}"
echo "======================================"

# Deploy Interface Lambda based on mode
if [[ "$DEPLOY_MODE" == "dual" ]]; then
    echo "--- Deploying Lightweight Interface Lambda (with infrastructure setup) ---"
    python.exe deployment/create_interface_package.py --deploy --environment "$ENVIRONMENT" --mode lightweight $REBUILD_OPTION

    echo "--- Deploying Background Processor Lambda (skip infrastructure setup) ---"
    python.exe deployment/create_interface_package.py --deploy --environment "$ENVIRONMENT" --mode background $REBUILD_OPTION --skip-db-setup --skip-s3-setup --skip-ws-test
else
    echo "--- Deploying Unified Interface Lambda (legacy) ---"
    python.exe deployment/create_interface_package.py --deploy --environment "$ENVIRONMENT" --mode unified $REBUILD_OPTION
fi

echo "--- Deploying Validation Lambda ---"
python.exe deployment/create_package.py --deploy --environment "$ENVIRONMENT" $REBUILD_OPTION

# Config Lambda merged into Interface Lambda - no separate deployment needed
# echo "--- Deploying Config Lambda ---"
# python.exe deployment/deploy_config_lambda.py --deploy --environment "$ENVIRONMENT" $REBUILD_OPTION

echo "--- All lambdas deployed successfully to $ENVIRONMENT! ---"
echo "[INFO] Deployment mode: $DEPLOY_MODE"
echo "[INFO] Config generation now runs within Interface Lambda (merged)" 