@echo off
chcp 65001 >nul
title CAP/YDP Takip - DEMO
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

rem --- Demo ayri bir veritabani ve dosya klasoru kullanir; asil veriler (db.sqlite3) etkilenmez
set CAPTAKIP_SQLITE=demo.sqlite3
set CAPTAKIP_DOSYA_KLASORU=korunan_dosyalar_demo
set CAPTAKIP_DEBUG=0
set CAPTAKIP_SECRET_KEY=demo-yerel-%RANDOM%-%RANDOM%-%RANDOM%-%RANDOM%-%RANDOM%

echo.
echo  Demo veritabani sifirdan kuruluyor (10-20 saniye)...
if exist demo.sqlite3 del /q demo.sqlite3
if exist demo.sqlite3-wal del /q demo.sqlite3-wal
if exist demo.sqlite3-shm del /q demo.sqlite3-shm
if exist korunan_dosyalar_demo rmdir /s /q korunan_dosyalar_demo
python manage.py migrate --verbosity 0 || goto hata
python manage.py demo_verisi || goto hata

echo.
echo  Site aciliyor: http://127.0.0.1:8000   (kapatmak icin bu pencerede Ctrl+C)
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"
python manage.py runserver --insecure
goto :eof

:hata
echo.
echo  HATA olustu. Bu pencerenin ekran goruntusunu alin.
pause
