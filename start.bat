@echo off
setlocal enabledelayedexpansion

REM Kill any existing process listening on port before starting.
REM Set MAARS_START_KILL_OLD=0 to disable.
if "%MAARS_START_KILL_OLD%"=="" set MAARS_START_KILL_OLD=1
if "%MAARS_PORT%"=="" set MAARS_PORT=3001

if "%MAARS_START_KILL_OLD%"=="1" (
	for /f "tokens=5" %%a in ('netstat -ano ^| findstr /R /C:":%MAARS_PORT% .*LISTENING"') do (
		if not "%%a"=="0" (
			echo INFO: Killing existing listener PID %%a on port %MAARS_PORT%
			taskkill /F /PID %%a >NUL 2>&1
		)
	)
)

cd /d "%~dp0backend"
python -m uvicorn main:asgi_app --host 0.0.0.0 --port %MAARS_PORT% --loop asyncio --http h11

endlocal
