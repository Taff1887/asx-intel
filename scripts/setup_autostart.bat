@echo off
REM ============================================================
REM ASX Intel — Windows Auto-Start Setup
REM
REM Run this file ONCE as Administrator.
REM It registers two Windows Task Scheduler tasks:
REM
REM   1. asx_intel_backend  — starts the FastAPI server at login
REM   2. asx_intel_scheduler — starts the daily scheduler at login
REM
REM After running this, both will start automatically every time
REM you log in to Windows. No cmd windows to open manually.
REM ============================================================

SET APP_DIR=C:\Users\Taffy Jackson\quantlab\applications\asx_intel
SET PYTHON=python

echo === ASX Intel Auto-Start Setup ===
echo.

REM -- Backend server task --
echo Registering: asx_intel_backend (FastAPI on port 8000)
schtasks /create /tn "asx_intel_backend" /tr "cmd /c cd /d \"%APP_DIR%\" && %PYTHON% -m uvicorn backend.main:app --port 8000 >> \"%APP_DIR%\data\backend.log\" 2>&1" /sc ONLOGON /delay 0000:30 /ru "%USERNAME%" /f
if %errorlevel%==0 (echo   OK) else (echo   FAILED - try running as Administrator)

REM -- Frontend server task --
echo Registering: asx_intel_frontend (Next.js on port 3001)
schtasks /create /tn "asx_intel_frontend" /tr "cmd /c cd /d \"%APP_DIR%\frontend\" && npm run dev >> \"%APP_DIR%\data\frontend.log\" 2>&1" /sc ONLOGON /delay 0001:00 /ru "%USERNAME%" /f
if %errorlevel%==0 (echo   OK) else (echo   FAILED - try running as Administrator)

REM -- Scheduler task --
echo Registering: asx_intel_scheduler (daily announcement pipeline)
schtasks /create /tn "asx_intel_scheduler" /tr "cmd /c cd /d \"%APP_DIR%\" && %PYTHON% scripts/scheduler.py >> \"%APP_DIR%\data\scheduler.log\" 2>&1" /sc ONLOGON /delay 0001:30 /ru "%USERNAME%" /f
if %errorlevel%==0 (echo   OK) else (echo   FAILED - try running as Administrator)

echo.
echo === Done! ===
echo All three tasks will start automatically at next login.
echo.
echo To manage tasks: open Task Scheduler (taskschd.msc)
echo To remove:       schtasks /delete /tn "asx_intel_backend" /f
echo                  schtasks /delete /tn "asx_intel_frontend" /f
echo                  schtasks /delete /tn "asx_intel_scheduler" /f
echo.
pause
