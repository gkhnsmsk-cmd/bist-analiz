@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
rem ============================================================
rem  Takas Verisi - Kaynak Avi
rem  Hangi kaynak GERCEKTEN calisiyor, olcer. ~1-2 dakika.
rem  Sonuc: takas_kaynak_avi_sonuc.txt
rem ============================================================
set "PYTHONIOENCODING=utf-8"
set "PY="
if not defined PY ( py -3.12 -c "import requests" >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( py -3.11 -c "import requests" >nul 2>nul && set "PY=py -3.11" )
if not defined PY ( py -3.13 -c "import requests" >nul 2>nul && set "PY=py -3.13" )
if not defined PY ( py -3.10 -c "import requests" >nul 2>nul && set "PY=py -3.10" )
if not defined PY ( py -3 -c "import requests" >nul 2>nul && set "PY=py -3" )
if not defined PY ( python -c "import requests" >nul 2>nul && set "PY=python" )
if not defined PY (
  echo  HATA: requests kurulu Python bulunamadi. Once BASLAT.bat calistirin.
  pause
  exit /b 1
)
!PY! takas_kaynak_avi.py
echo.
pause
