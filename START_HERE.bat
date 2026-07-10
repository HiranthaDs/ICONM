@echo off
cd /d "%~dp0"
title IM ERP PY SYS PRO
if not exist logs mkdir logs
echo Starting IM ERP PY SYS PRO...
py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
py -3 app.py 1>>logs\app_run_error.log 2>&1
pause
