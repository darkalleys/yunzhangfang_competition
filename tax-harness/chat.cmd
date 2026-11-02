@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -X utf8 -m tax_harness init
if errorlevel 1 goto end
python -X utf8 -m tax_harness chat --user U001 --company C001
:end
pause
