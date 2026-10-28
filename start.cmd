@echo off
rem LawLens launcher (bypasses PowerShell execution policy)
rem   start.cmd -Init     create .env on first run
rem   start.cmd           start the server
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
