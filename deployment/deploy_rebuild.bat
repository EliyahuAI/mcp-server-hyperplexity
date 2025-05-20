@echo off
echo Setting up for full rebuild of Lambda package...
echo.

echo Building and deploying Lambda Function...
python create_package.py --deploy --region us-east-1 --s3-bucket perplexity-cache --verify --use-layer --force-rebuild --run-test

echo.
echo Deployment with rebuild completed. Press any key to exit.
pause 