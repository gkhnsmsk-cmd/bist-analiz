@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
rem ============================================================
rem  Arka Plan Taramasi - One Cikan + Yukselebilecek Hisseler
rem  Windows Gorev Zamanlayici tarafindan calistirilir.
rem  Sonuc ve HATALAR "arka_plan_tarama_log.txt" dosyasina yazilir.
rem ============================================================
rem  HATA GECMISI (18.08.2026):
rem  Burada eskiden FOR dongusu ile Python araniyordu ve calismiyordu:
rem  gorev "sonuc 255" ile sessizce cikiyor, log dosyasina HICBIR SEY
rem  yazilmiyordu. Cunku hata mesajlari konsola gidiyordu, gorev
rem  zamanlayicida konsol yok. Artik:
rem    1) BASLAT.bat ile AYNI (calistigi kanitlanmis) tespit yapisi
rem    2) HATALAR DA loga yaziliyor - sessiz cokme yok
rem    3) Secilen Python surumu loga yaziliyor - teshis kolay
rem ============================================================

rem  Windows konsolu varsayilan olarak cp1254 kullanir; Python emoji/
rem  Unicode yazdirmaya calisinca UnicodeEncodeError ile COKER. Gercek is
rem  bitmis olsa bile gorev "hata" olarak kapanir. Bu satir onu engeller.
set "PYTHONIOENCODING=utf-8"

set "PY="
if not defined PY ( py -3.12 -c "import pandas" >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( py -3.11 -c "import pandas" >nul 2>nul && set "PY=py -3.11" )
if not defined PY ( py -3.13 -c "import pandas" >nul 2>nul && set "PY=py -3.13" )
if not defined PY ( py -3.10 -c "import pandas" >nul 2>nul && set "PY=py -3.10" )
if not defined PY ( py -3 -c "import pandas" >nul 2>nul && set "PY=py -3" )
if not defined PY ( python -c "import pandas" >nul 2>nul && set "PY=python" )

if not defined PY (
  echo. >> arka_plan_tarama_log.txt
  echo [%date% %time%] HATA: pandas kurulu bir Python bulunamadi. >> arka_plan_tarama_log.txt
  echo   Cozum: BASLAT.bat ile ana uygulamayi bir kez calistirin. >> arka_plan_tarama_log.txt
  exit /b 1
)

echo. >> arka_plan_tarama_log.txt
echo [%date% %time%] BASLIYOR - Python: !PY! >> arka_plan_tarama_log.txt
!PY! arka_plan_tarama.py >> arka_plan_tarama_log.txt 2>&1
echo [%date% %time%] BITTI - cikis kodu: %errorlevel% >> arka_plan_tarama_log.txt
exit /b %errorlevel%
