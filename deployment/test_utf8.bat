@echo off
chcp 65001 > nul
echo Running cache test with UTF-8 encoding...
echo.

python create_package.py --test-only --function-name perplexity-validator --test-cache

echo.
echo Test completed. Press any key to exit.
pause 