@echo off
setlocal

set "VIEWER_ROOT=%~dp0"
set "PYTHON=%VIEWER_ROOT%.venv-win7\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Creating the Python 3.8 build environment...
    python -m venv "%VIEWER_ROOT%.venv-win7"
    if errorlevel 1 exit /b 1
)

"%PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 8) else 1)"
if errorlevel 1 (
    echo This build requires Python 3.8.x. Install Python 3.8 and run build.bat again.
    exit /b 1
)

echo Installing the locked Windows 7 dependencies...
"%PYTHON%" -m pip install --disable-pip-version-check -r "%VIEWER_ROOT%requirements-win7-lock.txt"
if errorlevel 1 exit /b 1

echo Running viewer tests...
"%PYTHON%" -m unittest discover -s "%VIEWER_ROOT%tests" -v
if errorlevel 1 exit /b 1

echo Building OpenLabDataViewer.exe...
"%PYTHON%" -m PyInstaller --clean --noconfirm --distpath "%VIEWER_ROOT%dist" --workpath "%VIEWER_ROOT%build" "%VIEWER_ROOT%OpenLabDataViewer.spec"
if errorlevel 1 exit /b 1

echo Build complete: "%VIEWER_ROOT%dist\OpenLabDataViewer.exe"
