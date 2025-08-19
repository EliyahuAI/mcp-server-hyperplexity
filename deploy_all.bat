@echo off
echo "--- Deploying Interface Lambda ---"
python deployment/create_interface_package.py --deploy --force-rebuild

echo "--- Deploying Validation Lambda ---"
python deployment/create_package.py --deploy --force-rebuild

echo "--- Deploying Config Lambda ---"
python deployment/deploy_config_lambda.py --deploy --force-rebuild

echo "--- All lambdas deployed successfully! ---" 