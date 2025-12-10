@echo off



:: Prompt for the version number
set /p version="Enter the version number (e.g., v1.8): "

:: Update badge in README.md using Python script
echo Updating badge in README.md...
"python" update_badge.py %version%
if %errorlevel% neq 0 (
    echo Error updating badge.
    exit /b 1
)

:: Update the logo
echo Updating logo in README.md...
"python" update_logo.py "autobanana %version%"
if %errorlevel% neq 0 (
    echo Error updating logo.
    exit /b 1
)

:: Stage the changes
echo Staging changes...
git add -A
if %errorlevel% neq 0 (
    echo Error staging changes.
    exit /b 1
)

:: Check for changes before committing
git diff-index --quiet HEAD --
if %errorlevel% equ 0 (
    echo No changes to commit.
    exit /b 0
)

:: Commit the changes with a message including the version number
echo Committing changes...
git commit -m "%version%"
if %errorlevel% neq 0 (
    echo Error committing changes.
    exit /b 1
)

:: Push the commit to the remote repository
echo Pushing commit to remote...
git push
if %errorlevel% neq 0 (
    echo Error pushing commit to remote.
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
    echo Error pushing tag %version% to remote.
    exit /b 1
)

echo Finished build process for %version%.
