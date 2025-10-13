@echo off
REM Script to run integration tests for the table generation system (Windows)
REM
REM Usage:
REM   run_integration_tests.bat              - Run all integration tests
REM   run_integration_tests.bat TEST_NAME    - Run specific test
REM

setlocal enabledelayedexpansion

echo ========================================
echo Table Maker Integration Tests
echo ========================================
echo.

REM Check for API key
if not defined ANTHROPIC_API_KEY (
    echo [ERROR] ANTHROPIC_API_KEY environment variable not set
    echo.
    echo Please set your API key:
    echo   set ANTHROPIC_API_KEY=your-api-key-here
    echo.
    exit /b 1
)

echo [SUCCESS] ANTHROPIC_API_KEY is set
echo.

REM Check if pytest is installed
where pytest >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] pytest not found
    echo.
    echo Please install dependencies:
    echo   pip install -r requirements.txt
    echo.
    exit /b 1
)

echo [SUCCESS] pytest is installed
echo.

REM Determine which tests to run
if "%1"=="" (
    REM Run all integration tests
    echo [INFO] Running ALL integration tests...
    echo [INFO] This will make REAL API calls and may take 10-15 minutes
    echo.

    REM Ask for confirmation
    set /p CONFIRM="Continue? (y/n) "
    if /i not "!CONFIRM!"=="y" (
        echo Aborted.
        exit /b 0
    )

    echo.
    pytest -m integration tests/test_integration.py -v --tb=short
) else (
    REM Run specific test
    echo [INFO] Running specific test: %1
    echo [INFO] This will make REAL API calls
    echo.

    pytest -m integration "tests/test_integration.py::%1" -v -s --tb=short
)

REM Check exit code
if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo All tests PASSED
    echo ========================================
) else (
    echo.
    echo ========================================
    echo Some tests FAILED
    echo ========================================
    exit /b 1
)
