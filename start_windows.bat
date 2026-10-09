@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONUTF8=1"
chcp 65001 >nul

echo ============================================================
echo  VN Investment Research - Windows quick start
echo ============================================================
echo.

set "PY_CMD="
set "PY_ARGS="
set "PY_VERSION="

where py.exe >nul 2>&1
if not errorlevel 1 goto check_py_launcher
goto try_python

:check_py_launcher
py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" >nul 2>&1
if not errorlevel 1 goto select_py312
py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 goto select_py311

:try_python
where python.exe >nul 2>&1
if errorlevel 1 goto try_python3
python -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 12), (3, 11)) else 1)" >nul 2>&1
if not errorlevel 1 goto select_python

:try_python3
where python3.exe >nul 2>&1
if errorlevel 1 goto python_missing
python3 -c "import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 12), (3, 11)) else 1)" >nul 2>&1
if not errorlevel 1 goto select_python3
goto python_missing

:select_py312
set "PY_CMD=py"
set "PY_ARGS=-3.12"
set "PY_VERSION=3.12"
goto python_selected

:select_py311
set "PY_CMD=py"
set "PY_ARGS=-3.11"
set "PY_VERSION=3.11"
goto python_selected

:select_python
set "PY_CMD=python"
set "PY_VERSION=installed Python"
goto python_selected

:select_python3
set "PY_CMD=python3"
set "PY_VERSION=installed Python"

:python_selected
echo Using %PY_VERSION%.
if exist ".venv\Scripts\python.exe" goto check_venv

echo Creating the project's virtual environment in .venv ...
%PY_CMD% %PY_ARGS% -m venv .venv
if errorlevel 1 goto venv_failed

:check_venv
set "VENV_PY=%CD%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" goto venv_failed
"%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info[0] == 3 and sys.version_info[1] in (11, 12) else 1)" >nul 2>&1
if errorlevel 1 goto venv_version_failed

if exist ".venv\.vnresearch-dev-installed" goto start_server
echo.
echo First-run setup: installing the application and development dependencies.
echo This can take several minutes. Progress will appear below.
"%VENV_PY%" -m pip install -e ".[dev]"
if errorlevel 1 goto install_failed
> ".venv\.vnresearch-dev-installed" echo installed

:start_server
echo.
echo Starting the local web app at http://127.0.0.1:8000
echo Keep this window open while using the app. Press Ctrl+C to stop it.
echo.
"%VENV_PY%" -m vnresearch.cli serve --host 127.0.0.1 --port 8000
if errorlevel 1 goto serve_failed
echo.
echo The web app has stopped.
pause
endlocal
exit /b 0

:python_missing
echo ERROR: Python 3.11 or 3.12 was not found.
echo Install Python 3.11 or 3.12, enable the Python Launcher or add Python to PATH,
echo then double-click start_windows.bat again.
goto failed

:venv_failed
echo ERROR: Could not create or find .venv\Scripts\python.exe.
echo Check that this folder is writable and that Python 3.11 or 3.12 is installed.
goto failed

:venv_version_failed
echo ERROR: The existing .venv does not use Python 3.11 or 3.12.
echo Remove the .venv folder and run start_windows.bat again to recreate it.
goto failed

:install_failed
echo ERROR: Dependency installation failed.
echo Check your internet connection and the error shown above, then run this file again.
goto failed

:serve_failed
echo ERROR: The web app exited with an error. Review the message shown above.
goto failed

:failed
echo.
pause
endlocal
exit /b 1
