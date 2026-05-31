@echo off
title TVPass Playlist Updater & Uploader
echo ====================================
echo   TVPass Playlist Auto-Updater
echo ====================================
echo.

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not added to your system PATH.
    echo Please install Python from https://www.python.org first.
    echo.
    pause
    exit /b
)

:: Install required python libraries
echo [1/4] Verifying Python packages...
pip install playwright --quiet
pip install yt-dlp --quiet

:: Ensure the chromium browser binary is installed
echo [2/4] Verifying browser binaries...
playwright install chromium

:: Run the script to generate exclusive.m3u using your home IP
echo [3/4] Starting stream link extractor...
echo.
python tvpass_generator.py

:: Automatically commit and push the updated file to GitHub
echo.
echo [4/4] Uploading updated playlist to GitHub...
git add exclusive.m3u
git commit -m "Automated local update of stream links" >nul 2>&1
git push

echo.
echo ====================================
echo   Update and GitHub upload completed!
echo ====================================
pause