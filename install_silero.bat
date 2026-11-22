@echo off
chcp 65001 >nul
rem Ставим голоса в папку установленной программы (туда, откуда она запускается)
if exist "%USERPROFILE%\AAC Translator\install_silero.py" (
    cd /d "%USERPROFILE%\AAC Translator"
) else (
    cd /d "%~dp0"
)
py install_silero.py
if errorlevel 9009 (
    echo Не найден Python.
    pause
)
