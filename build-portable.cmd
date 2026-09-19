@echo off
setlocal
set "build_root=%~dp0"
set "candidate_flag="
set "build_pause=1"

:arguments
if "%~1"=="" goto build
if /i "%~1"=="--candidate" (
    set "candidate_flag=--candidate"
    shift
    goto arguments
)
if /i "%~1"=="--no-pause" (
    set "build_pause=0"
    shift
    goto arguments
)
if /i "%~1"=="--help" goto help
echo Unknown option. Use build-portable.cmd --help.
exit /b 2

:build
pushd "%build_root%"
if errorlevel 1 exit /b 1
where uv >nul 2>&1
if errorlevel 1 goto missing_uv
echo Preparing the locked build environment...
call uv sync --frozen
if errorlevel 1 goto failed
echo Building the portable application and download ZIP...
call uv run --frozen --no-sync python tools/build_portable.py %candidate_flag%
if errorlevel 1 goto failed
echo.
echo Build complete. The exact ZIP path is printed above.
echo Open the matching folder in "%build_root%dist" and start ModemController.exe.
echo Keep _internal and _console beside the executable files.
echo Use the ZIP and its .sha256 file for the future release download.
echo Files below build\pyinstaller are intermediate build files, not the application.
set "build_exit=0"
goto finish

:missing_uv
echo uv was not found. Install uv and see docs\development.md, then retry.
set "build_exit=1"
goto finish

:failed
set "build_exit=%errorlevel%"
echo.
echo Build failed. No new portable package is confirmed; review the error above.

:finish
popd
if "%build_pause%"=="1" pause
endlocal & exit /b %build_exit%

:help
echo Usage: build-portable.cmd [--candidate] [--no-pause]
echo Default: build the current checkout; uncommitted edits are marked dirty.
echo --candidate: require a clean committed source tree for release preparation.
echo --no-pause: return immediately for terminal or automated use.
exit /b 0
