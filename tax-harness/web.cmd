@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -X utf8 -m tax_harness init
if errorlevel 1 goto end
echo Open http://127.0.0.1:8765 in your browser.
python -X utf8 -m tax_harness web
:end
pause
