@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
rem ============================================================
rem  TUM GOREVLERI TEK TIKLA KUR
rem  Yonetici yetkisi GEREKMEZ. PowerShell komutu elle
rem  yazmaya gerek yok - bu dosya hepsini kendisi yapar.
rem
rem  Kurulan gorevler:
rem    Borsa-Tarama          hafta ici 18:30
rem    Borsa-Portfoy         hafta ici 18:40
rem    Borsa-HaftalikKontrol Cumartesi 10:00
rem ============================================================
title Borsa Yazilimi - Gorev Kurulumu
echo.
echo  ============================================================
echo   GOREV ZAMANLAYICI KURULUMU
echo  ============================================================
echo.
echo   Klasor: %CD%
echo.

rem --- Gerekli dosyalar var mi? ---
set "EKSIK="
for %%F in (ARKA_PLAN_TARAMA.bat GUNLUK_SANAL_YATIRIM.bat HAFTALIK_KONTROL.bat) do (
  if not exist "%%F" set "EKSIK=!EKSIK! %%F"
)
if defined EKSIK (
  echo   HATA: Su dosyalar bulunamadi:!EKSIK!
  echo   Bu dosyayi yazilim klasorune koyun.
  echo.
  pause
  exit /b 1
)

rem --- PowerShell ile kaydet (kullanici komut yazmaz) ---
rem  schtasks.exe yerine PowerShell kullaniliyor cunku
rem  "StartWhenAvailable" (PC kapaliysa acilinca telafi et)
rem  ayari schtasks'in basit sozdiziminde yok.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$k = '%CD%';" ^
  "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 3);" ^
  "$hafta = @('Monday','Tuesday','Wednesday','Thursday','Friday');" ^
  "$gorevler = @(" ^
  "  @{Ad='Borsa-Tarama';        Bat='ARKA_PLAN_TARAMA.bat';    Saat='18:30'; Gun=$hafta}," ^
  "  @{Ad='Borsa-Portfoy';       Bat='GUNLUK_SANAL_YATIRIM.bat';Saat='18:40'; Gun=$hafta}," ^
  "  @{Ad='Borsa-HaftalikKontrol';Bat='HAFTALIK_KONTROL.bat';   Saat='10:00'; Gun=@('Saturday')}" ^
  ");" ^
  "foreach ($g in $gorevler) {" ^
  "  try {" ^
  "    $a = New-ScheduledTaskAction -Execute (Join-Path $k $g.Bat) -WorkingDirectory $k;" ^
  "    $t = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $g.Gun -At $g.Saat;" ^
  "    Register-ScheduledTask -TaskName $g.Ad -Action $a -Trigger $t -Settings $s -Force | Out-Null;" ^
  "    Write-Host ('   [OK] ' + $g.Ad + '  ->  ' + $g.Saat) -ForegroundColor Green;" ^
  "  } catch {" ^
  "    Write-Host ('   [HATA] ' + $g.Ad + ': ' + $_.Exception.Message) -ForegroundColor Red;" ^
  "  }" ^
  "}" ^
  "Write-Host '';" ^
  "Write-Host '   Kurulu gorevler:' -ForegroundColor Cyan;" ^
  "Get-ScheduledTask -TaskName 'Borsa-*' | ForEach-Object { $i = $_ | Get-ScheduledTaskInfo; Write-Host ('     ' + $_.TaskName.PadRight(24) + $_.State.ToString().PadRight(10) + 'sonraki: ' + $i.NextRunTime) }"

echo.
echo  ============================================================
echo   Kurulum bitti.
echo.
echo   Gorevler artik kendiliginden calisacak. PC o saatte
echo   kapaliysa, actiginizda ilk firsatta telafi edilir.
echo.
echo   Haftalik rapor: haftalik_rapor.txt  (Cumartesi 10:00)
echo  ============================================================
echo.
echo   Gorevler bir kez test icin simdi calistiriliyor...
echo.
schtasks /Run /TN "Borsa-Tarama" >nul 2>nul && echo    [BASLADI] Borsa-Tarama
schtasks /Run /TN "Borsa-Portfoy" >nul 2>nul && echo    [BASLADI] Borsa-Portfoy
schtasks /Run /TN "Borsa-HaftalikKontrol" >nul 2>nul && echo    [BASLADI] Borsa-HaftalikKontrol
echo.
echo   Arka planda calisiyorlar. Birkac dakika sonra su dosyalara bakin:
echo     arka_plan_tarama_log.txt
echo     sanal_yatirim_log.txt
echo     haftalik_rapor.txt
echo.
echo   Bu pencere 20 saniye sonra kapanacak.
timeout /t 20 >nul
exit /b 0
