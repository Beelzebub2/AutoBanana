@echo off

:: Check if Python is installed using default installation path
set PYTHON_PATH=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python312
if not exist "%PYTHON_PATH%\python.exe" (
    echo Python is not installed in the default path. Please install Python and add it to your PATH.
    pause
    exit /b 1
)

:: Prompt for the version number
set /p version="Enter the version number (e.g., v1.8): "

:: Update badge in README.md using Python script
echo Updating badge in README.md...
"%PYTHON_PATH%\python.exe" update_badge.py %version%
if %errorlevel% neq 0 (
    echo Error updating badge.
    exit /b 1
)
:: Update the logo
echo Updating badge in README.md...
"%PYTHON_PATH%\python.exe" update_logo.py "autobanana %version%"
if %errorlevel% neq 0 (
    echo Error updating logo.
    exit /b 1
)

:: Check if the tag exists locally
git tag -l %version% >nul 2>&1
if %errorlevel% equ 0 (
    :: Delete the local tag
    echo Deleting existing local tag %version%...
    git tag -d %version%
    if %errorlevel% neq 0 (
        echo Error deleting local tag %version%
        exit /b 1
    )
)

:: Check if the tag exists remotely
git ls-remote --tags origin | findstr /r /c:"refs/tags/%version%" >nul 2>&1
if %errorlevel% equ 0 (
    :: Delete the remote tag
    echo Deleting existing remote tag %version%...
    git push origin :refs/tags/%version%
    if %errorlevel% neq 0 (
        echo Error deleting remote tag %version%
        exit /b 1
    )
)

:: Create the tag locally
echo Creating tag %version% locally...
git tag %version%
if %errorlevel% neq 0 (
    echo Error creating local tag %version%
    exit /b 1
)

:: Push the tag to remote
echo Pushing tag %version% to remote...
git push origin %version%
if %errorlevel% neq 0 (
    echo Error pushing tag %version% to remote
    exit /b 1
)

echo Tag %version% has been successfully managed.
echo Press any key to exit...
pause >nul
