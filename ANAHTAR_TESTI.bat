@echo off
rem ============================================================
rem  API Anahtar Testi - sohbet asistaninin anahtarlarini dener
rem  Bu dosyaya cift tiklayin. Anahtarlar ekrana YAZILMAZ.
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo Python bulunamadi. Once BASLAT.bat ile ana uygulamayi bir kez calistirin.
  pause
  exit /b 1
)

%PY% anahtar_testi.py
