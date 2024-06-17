@echo off
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python is not installed. Please install Python and add it to your PATH.
    pause
    exit /b 1
)

echo Installing required packages...
pip install --upgrade pip
pip install -r requirements.txt

echo Starting AutoBanana...
python AutoBanana.py

echo Press any key to exit...
pause >nul
