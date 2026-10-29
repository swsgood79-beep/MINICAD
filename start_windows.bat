@echo off
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (echo Python 3.12+ must be installed and added to PATH. & pause & exit /b 1)
where npm >nul 2>nul
if errorlevel 1 (echo Node.js 22.12+ must be installed and added to PATH. & pause & exit /b 1)
if not exist .venv\Scripts\python.exe python -m venv .venv
if errorlevel 1 goto :failed
.venv\Scripts\python.exe -m pip install -r requirements.lock
if errorlevel 1 goto :failed
pushd frontend
call npm ci
if errorlevel 1 (popd & goto :failed)
call npm run build
if errorlevel 1 (popd & goto :failed)
popd
echo Open http://127.0.0.1:8000 in Chrome or Edge. Ctrl+C to stop.
.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000
exit /b %errorlevel%
:failed
echo Setup failed. Review the error above.
pause
exit /b 1
