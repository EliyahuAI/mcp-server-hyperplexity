@echo off
echo Running improved cache verification test...
echo This will invoke the function twice to verify caching works
echo With improved detection logic to avoid false positives
echo.

python create_package.py --test-only --function-name perplexity-validator --region us-east-1 --test-cache

echo.
echo Cache test completed. Press any key to exit.
pause 