@echo off
setlocal enabledelayedexpansion
rem ============================================================
rem  BIST Analiz Platformu - Tek Tik Baslatici
rem  Bu dosyaya cift tiklamaniz yeterli. Baska islem gerekmez.
rem ============================================================
title BIST Analiz Platformu - Sunucu (bu pencereyi kapatmayin)
cd /d "%~dp0"

rem --- Python'u bul: once STANDART (deneysel "free-threaded / t" OLMAYAN)
rem     bir surumu tercih et. 3.13t gibi deneysel surumlerde numpy/pandas
rem     gibi paketlerin hazir kurulum dosyasi (wheel) olmadigindan kurulum
rem     C derleyicisi gerektirip basarisiz olabiliyor. ---
set "PY="

if not defined PY ( py -3.12 -c "print(1)" >nul 2>nul && set "PY=py -3.12" )
if not defined PY ( py -3.11 -c "print(1)" >nul 2>nul && set "PY=py -3.11" )
if not defined PY ( py -3.13 -c "print(1)" >nul 2>nul && set "PY=py -3.13" )
if not defined PY ( py -3.10 -c "print(1)" >nul 2>nul && set "PY=py -3.10" )
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY goto nopython

rem --- Secilen Python deneysel "free-threaded" (t) surum mu, kontrol et ---
!PY! -c "import sys; exit(0 if 'experimental free-threading' in sys.version else 1)" >nul 2>nul
if not errorlevel 1 goto serbestiplik

rem --- Ilk calistirmada paketleri kur ---
if exist ".kurulum_tamam" goto calistir
echo.
echo  Ilk kurulum yapiliyor, internet hizina gore 2-5 dakika surebilir...
echo  Bu islem sadece ilk acilista yapilir.
echo.
!PY! -m pip install --upgrade pip --quiet
!PY! -m pip install -r requirements.txt
if errorlevel 1 goto kurulumhata
echo tamam > ".kurulum_tamam"

:calistir
rem --- EKSIK PAKET KONTROLU (her aciliste, hizli) ---
rem  NEDEN VAR: Kurulum eskiden SADECE ilk aciliste (.kurulum_tamam yoksa)
rem  yapiliyordu. Yazilima sonradan yeni bir paket eklendiginde (orn. telethon,
rem  pytesseract) mevcut kullanicilarda o paket HIC kurulmuyor ve uygulama
rem  icinde "... kurulu degil" hatasi cikiyordu. Artik her aciliste paketlerin
rem  yuklenebildigi kontrol edilir; eksik varsa requirements.txt yeniden kurulur.
!PY! -c "import streamlit,pandas,numpy,plotly,yfinance,requests,lxml,matplotlib,telethon,pytesseract,PIL,xgboost,sklearn,joblib" >nul 2>nul
if errorlevel 1 (
  echo.
  echo  Yeni/eksik paketler kuruluyor, lutfen bekleyin...
  !PY! -m pip install -r requirements.txt
)

rem --- TESSERACT-OCR KONTROLU (AKD tablo gorselini sayiya cevirmek icin) ---
rem  pytesseract SADECE bir sarmalayicidir; asil isi yapan Tesseract-OCR
rem  PROGRAMI ayrica kurulmalidir. Kurulu degilse AKD gorseli indirilir ama
rem  kurum isimleri/oranlar otomatik okunamaz. Burada winget ile sessizce
rem  kurmayi deniyoruz; basarisiz olursa uygulama yine calisir (sadece AKD
rem  tablosu gorsel olarak gosterilir), bu yuzden hata durumunda DURMUYORUZ.
rem  ONEMLI DUZELTME: Eskiden ".tesseract_denendi" isaret dosyasi kurulum
rem  BASARISIZ olsa bile yaziliyordu, bu yuzden kurulum bir kez basarisiz
rem  olursa BIR DAHA ASLA denenmiyordu. Artik isaret dosyasi YOK; her
rem  aciliste sadece "kurulu mu" diye HIZLI bir kontrol yapilir (birkac
rem  dosya/PATH kontrolu, milisaniyeler surer) ve sadece KURULU DEGILSE
rem  tekrar kurulum denenir — kurulunca bu blok bir daha calismaz.
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" goto tesseract_tamam
if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" goto tesseract_tamam
if exist "%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe" goto tesseract_tamam
if exist "%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe" goto tesseract_tamam
where tesseract >nul 2>nul
if not errorlevel 1 goto tesseract_tamam
where winget >nul 2>nul
if errorlevel 1 (
  echo.
  echo  UYARI: Tesseract-OCR kurulu degil ve winget bulunamadi, otomatik
  echo  kurulamiyor. AKD kurum isimleri/oranlari okunamayacak ama program
  echo  yine calisacak. Elle kurmak icin: https://github.com/UB-Mannheim/tesseract/wiki
  goto tesseract_tamam
)
echo.
echo  AKD tablolarini otomatik okuyabilmek icin Tesseract-OCR kuruluyor...
winget install -e --id UB-Mannheim.TesseractOCR --accept-source-agreements --accept-package-agreements --silent
if errorlevel 1 (
  echo  UYARI: Tesseract-OCR otomatik kurulumu basarisiz oldu. Program yine
  echo  calisacak ^(sadece AKD kurum isimleri okunamayacak^). Elle kurmak icin:
  echo  https://github.com/UB-Mannheim/tesseract/wiki  ^(kurduktan sonra
  echo  BASLAT.bat'i tekrar calistirin.^)
) else (
  echo  Tesseract-OCR kuruldu. Degisikligin etkili olmasi icin bu pencereyi
  echo  kapatip BASLAT.bat'i BIR KEZ DAHA calistirmaniz gerekebilir ^(PATH
  echo  guncellemesi icin^).
)
:tesseract_tamam

echo.
echo  Yazilim baslatiliyor... Tarayici otomatik acilacak.
echo  KAPATMAK ICIN: bu pencereyi kapatin.
echo.
!PY! -m streamlit run app.py --server.port 8765 --browser.gatherUsageStats false
pause
exit /b

:kurulumhata
echo.
echo  HATA: Paket kurulumu basarisiz oldu.
echo.
echo  En sik neden: bilgisayarinizda Python'un DENEYSEL "free-threaded (3.13t)"
echo  surumu kurulu olmasi. Bu surumde numpy/pandas gibi paketlerin hazir
echo  kurulum dosyasi olmadigindan derleme gerekiyor ve bu genelde basarisiz olur.
echo.
echo  COZUM: Standart Python 3.12 kurun (deneysel "t" surumunu DEGIL):
echo    https://www.python.org/downloads/release/python-3123/
echo  Kurulumda "Add Python to PATH" kutusunu isaretleyin. Kurulum bittikten
echo  sonra BASLAT.bat dosyasina tekrar cift tiklayin.
echo.
echo  Baska bir neden internet baglantisi olabilir; onu da kontrol edin.
pause
exit /b

:serbestiplik
echo.
echo  UYARI: Bilgisayarinizda Python'un DENEYSEL "free-threaded (3.13t)"
echo  surumu bulundu. Bu surum bu yazilimla uyumlu DEGIL (numpy/pandas gibi
echo  paketler icin hazir kurulum dosyasi yok, derleme basarisiz oluyor).
echo.
echo  COZUM: Standart Python 3.12 kurun (deneysel "t" surumunu DEGIL):
echo    https://www.python.org/downloads/release/python-3123/
echo  Kurulumda "Add Python to PATH" kutusunu isaretleyin. Kurulum bittikten
echo  sonra BASLAT.bat dosyasina tekrar cift tiklayin.
echo.
start https://www.python.org/downloads/release/python-3123/
pause
exit /b

:nopython
echo.
echo  Python bulunamadi. Otomatik kurulum deneniyor (winget)...
where winget >nul 2>nul
if errorlevel 1 goto elleindir
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
echo.
echo  Kurulum bittiyse lutfen BASLAT.bat dosyasina TEKRAR cift tiklayin.
pause
exit /b

:elleindir
echo.
echo  Lutfen once Python kurun: https://www.python.org/downloads/release/python-3123/
echo  ONEMLI: Kurulumda "Add Python to PATH" kutusunu isaretleyin!
start https://www.python.org/downloads/release/python-3123/
pause
exit /b
