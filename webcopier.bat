@echo off
REM ============================================================
REM  WebCopier v5.5 - Command Prompt launcher
REM
REM  Usage examples:
REM    webcopier fetch https://example.com/article -o out -f md
REM    webcopier batch urls.txt --delay 2
REM    webcopier crawl https://example.com --depth 2
REM    webcopier forum 150 177 171 176 -o output	row
REM    webcopier config --show
REM ============================================================
setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -m webcopier %*
exit /b %ERRORLEVEL%
