@echo off
echo Running cache verification test on Lambda function...
echo This will invoke the function twice to verify caching works
echo.

python create_package.py --test-only --function-name perplexity-validator --region us-east-1 --test-cache

echo.
echo Cache test completed. Press any key to exit.
pause 