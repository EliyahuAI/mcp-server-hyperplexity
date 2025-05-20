@echo off
echo Setting up unique package directories to avoid permission errors...
set TIMESTAMP=%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%
set TMPNAME=package_%TIMESTAMP%

echo Checking if Lambda package exists...
echo.

echo Deploying Lambda Function...
python create_package.py --deploy --region us-east-1 --s3-bucket perplexity-cache --verify --use-layer --no-rebuild --run-test

echo.
echo Deployment completed. Press any key to exit.
pause 