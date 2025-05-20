@echo off
echo Deploying Lambda function with debugging capabilities...
echo This will rebuild the package and update the Lambda function.
echo.

python create_package.py --deploy --function-name perplexity-validator --region us-east-1 --force-rebuild

echo.
echo Deployment completed. Running test with debug mode...
echo.

python create_package.py --test-only --function-name perplexity-validator --region us-east-1 --test-cache

echo.
echo Debug deployment and test completed. Press any key to exit.
pause 