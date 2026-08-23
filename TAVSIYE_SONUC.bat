@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
rem ============================================================
rem  Tavsiyeler gercekten kazandirdi mi?
rem  Tavsiye edilen HER hissenin bugunku fiyatini ceker.
rem  ~2-5 dakika. Sonuc: tavsiye_gercek_sonuc.txt
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
  echo  HATA: pandas kurulu bir Python bulunamadi. Once BASLAT.bat calistirin.
  pause
  exit /b 1
)
!PY! tavsiye_gercek_sonuc.py
echo.
pause
