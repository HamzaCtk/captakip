@echo off
chcp 65001 >nul
title CAP/YDP Takip
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
rem Asil (gelistirme) veritabani: db.sqlite3
python manage.py migrate --verbosity 0 || goto hata
echo  Site aciliyor: http://127.0.0.1:8000   (kapatmak icin Ctrl+C)
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"
python manage.py runserver
goto :eof
:hata
echo  HATA olustu. Bu pencerenin ekran goruntusunu alin.
pause
