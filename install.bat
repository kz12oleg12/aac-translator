@echo off
chcp 65001 >nul
cd /d "%~dp0"
py install.py
if errorlevel 9009 (
    echo Не найден Python. Установите его с python.org ^(галочка "Add python.exe to PATH"^).
    pause
)
