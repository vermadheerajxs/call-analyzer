@echo off
REM One-command Windows setup (CMD or double-click).
REM From repo root after clone:
REM   setup.cmd
REM Then: edit .env and run
REM   venv\Scripts\python.exe src\main.py

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
exit /b %ERRORLEVEL%
