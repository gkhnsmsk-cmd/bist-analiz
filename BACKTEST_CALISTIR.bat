@echo off
rem ============================================================
rem  Backtest Motoru - Cok Yilli Dogrulama Calistirmasi
rem  Uygulamayi acmaya GEREK YOKTUR. Bu dosyaya cift tiklayin,
rem  birkac dakika surebilir (yuzlerce hisse x binlerce gun islenir).
rem  Sonuclar "backtest_sonuc.txt" (okunabilir rapor) ve
rem  "backtest_sonuc.csv" (ham veri) dosyalarina yazilir.
rem ============================================================
cd /d "%~dp0"

rem --- Python secimi: BASLAT.bat ile AYNI mantik (pandas kurulu olan surum) ---
set "PY="
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PY (
    py -%%V -c "import pandas" >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY ( py -3 -c "import pandas" >nul 2>nul && set "PY=py -3" )
if not defined PY ( python -c "import pandas" >nul 2>nul && set "PY=python" )
if not defined PY (
  echo.
  echo  HATA: Gerekli paketlerin kurulu oldugu bir Python bulunamadi.
  echo  Once BASLAT.bat ile ana uygulamayi bir kez calistirin.
  echo.
  pause
  exit /b 1
)

%PY% backtest_calistir.py
echo.
echo Tamamlandi. backtest_sonuc.txt dosyasini acabilirsiniz.
pause
