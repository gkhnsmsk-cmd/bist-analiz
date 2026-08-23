@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
rem ============================================================
rem  Takas Vekil Gostergeleri Testi
rem  Birikim/dagitim BIST'te ongoruyor mu? 30-60 dakika.
rem  Sonuc: takas_vekil_sonuc.txt
rem ============================================================
set "PYTHONIOENCODING=utf-8"
set "PY="
if not defined PY ( py -3.12 -c "import pandas,scipy" >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( py -3.11 -c "import pandas,scipy" >nul 2>nul && set "PY=py -3.11" )
if not defined PY ( py -3.13 -c "import pandas,scipy" >nul 2>nul && set "PY=py -3.13" )
if not defined PY ( py -3.10 -c "import pandas,scipy" >nul 2>nul && set "PY=py -3.10" )
if not defined PY ( py -3.12 -c "import pandas" >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( py -3.11 -c "import pandas" >nul 2>nul && set "PY=py -3.11" )
if not defined PY ( py -3 -c "import pandas" >nul 2>nul && set "PY=py -3" )
if not defined PY ( python -c "import pandas" >nul 2>nul && set "PY=python" )
if not defined PY (
  echo  HATA: pandas kurulu bir Python bulunamadi. Once BASLAT.bat calistirin.
  pause
  exit /b 1
)
echo.
echo  Takas vekil testi basliyor - 30-60 dakika surebilir.
echo  Bu pencereyi kapatmayin.
echo.
!PY! takas_vekil_testi.py
echo.
pause
