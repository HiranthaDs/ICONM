@echo off
cd /d "%~dp0"
if not exist logs mkdir logs
py -3 diagnose.py 1>logs\diagnose.log 2>&1
type logs\diagnose.log
pause
