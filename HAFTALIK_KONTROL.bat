@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
rem ============================================================
rem  Haftalik Kontrol Raporu
rem  Tum olcumleri otomatik yapar, TEK rapor yazar.
rem  Gorev Zamanlayici: Cumartesi 10:00
rem  Sonuc: haftalik_rapor.txt
rem ============================================================
set "PYTHONIOENCODING=utf-8"
set "PY="
if not defined PY ( py -3.12 -c "import pandas" >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( py -3.11 -c "import pandas" >nul 2>nul && set "PY=py -3.11" )
if not defined PY ( py -3.13 -c "import pandas" >nul 2>nul && set "PY=py -3.13" )
if not defined PY ( py -3.10 -c "import pandas" >nul 2>nul && set "PY=py -3.10" )
if not defined PY ( py -3 -c "import pandas" >nul 2>nul && set "PY=py -3" )
if not defined PY ( python -c "import pandas" >nul 2>nul && set "PY=python" )
if not defined PY (
  echo. >> haftalik_calisma.txt
  echo [%date% %time%] HATA: pandas kurulu Python bulunamadi. >> haftalik_calisma.txt
  exit /b 1
)
echo. >> haftalik_calisma.txt
echo [%date% %time%] BASLIYOR - Python: !PY! >> haftalik_calisma.txt
!PY! haftalik_kontrol.py >> haftalik_calisma.txt 2>&1
echo [%date% %time%] BITTI - cikis kodu: %errorlevel% >> haftalik_calisma.txt
exit /b %errorlevel%
