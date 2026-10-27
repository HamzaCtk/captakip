@echo off
chcp 65001 >nul
title CAP/YDP Takip - Testler
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
echo  Tum otomatik testler calisiyor (3-5 dakika)...
python manage.py test
pause
