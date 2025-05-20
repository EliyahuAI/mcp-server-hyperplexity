@echo off
echo Running test against Lambda function...
python create_package.py --test-only --function-name perplexity-validator --region us-east-1

echo.
echo Test completed. Press any key to exit.
pause 