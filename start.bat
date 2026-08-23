@echo off
setlocal
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
title x-download - Mxioc
color 0B

where py >nul 2>nul
if errorlevel 1 goto use_python

py -3 -X utf8 scripts\bootstrap.py --windows-menu %*
set "START_EXIT_CODE=%errorlevel%"
goto finish

:use_python
python -X utf8 scripts\bootstrap.py --windows-menu %*
set "START_EXIT_CODE=%errorlevel%"

:finish
if not "%START_EXIT_CODE%"=="0" (
  echo.
  echo x-download failed to start. Exit code: %START_EXIT_CODE%
  echo Review the error above, then press any key to close this window.
  pause >nul
)
exit /b %START_EXIT_CODE%
