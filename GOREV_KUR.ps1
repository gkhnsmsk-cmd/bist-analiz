# ============================================================================
#  Borsa Yazilimi - Windows Gorev Zamanlayici Kurulumu
# ============================================================================
#  Bu script, iki arka plan gorevini Windows Gorev Zamanlayici'ya kaydeder:
#    1) Arka Plan Tarama       - hafta ici 18:30
#    2) Sanal Portfoy Motoru   - hafta ici 18:40
#
#  NEDEN $PSScriptRoot: Klasor yolunda Turkce karakter var ("yazilimi1").
#  Yolu script icine elle yazmak kodlama (encoding) sorunu cikariyor.
#  $PSScriptRoot, scriptin BULUNDUGU klasoru otomatik verir - bu yuzden
#  script .bat dosyalariyla AYNI klasorde durmalidir.
#
#  CALISTIRMA: PowerShell'i ac, su iki satiri sirayla calistir:
#     cd "$env:USERPROFILE\YandexDisk\Yandex genel\lispler\YAZILIMLAR\Borsa yazılımı1"
#     powershell -ExecutionPolicy Bypass -File .\GOREV_KUR.ps1
#
#  Yonetici yetkisi GEREKMEZ (gorevler sadece bu kullanici icin kurulur).
# ============================================================================

$ErrorActionPreference = "Stop"
$klasor = $PSScriptRoot

Write-Host ""
Write-Host "Klasor: $klasor" -ForegroundColor Cyan
Write-Host ""

# --- Gerekli .bat dosyalari gercekten var mi? -------------------------------
$gorevler = @(
    @{ Ad = "Borsa - Arka Plan Tarama"
       Bat = "ARKA_PLAN_TARAMA.bat"
       Saat = "18:30"
       Aciklama = "BIST taramasi - sonuc tarama_onbellek.json dosyasina yazilir" },

    @{ Ad = "Borsa - Sanal Portfoy"
       Bat = "GUNLUK_SANAL_YATIRIM.bat"
       Saat = "18:40"
       Aciklama = "Sanal portfoy izleme; alim-satim sadece Cuma gunleri" }
)

foreach ($g in $gorevler) {
    $tamYol = Join-Path $klasor $g.Bat
    if (-not (Test-Path $tamYol)) {
        Write-Host "HATA: $($g.Bat) bulunamadi!" -ForegroundColor Red
        Write-Host "Bu scripti .bat dosyalariyla ayni klasore koyun." -ForegroundColor Red
        exit 1
    }
}

# --- Gorevleri kur ----------------------------------------------------------
foreach ($g in $gorevler) {

    $tamYol = Join-Path $klasor $g.Bat

    # Ayni isimde eski bir gorev varsa once sil (tekrar calistirilabilir olsun)
    $eski = Get-ScheduledTask -TaskName $g.Ad -ErrorAction SilentlyContinue
    if ($eski) {
        Unregister-ScheduledTask -TaskName $g.Ad -Confirm:$false
        Write-Host "Eski gorev silindi: $($g.Ad)" -ForegroundColor DarkGray
    }

    # Eylem: .bat dosyasini KENDI klasorunde calistir (-WorkingDirectory sart,
    # yoksa script yanindaki .py ve .json dosyalarini bulamaz)
    $eylem = New-ScheduledTaskAction `
        -Execute $tamYol `
        -WorkingDirectory $klasor

    # Tetikleyici: hafta ici, borsa kapanisindan sonra
    $tetik = New-ScheduledTaskTrigger `
        -Weekly `
        -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday `
        -At $g.Saat

    # Ayarlar:
    #  StartWhenAvailable : PC o saatte kapaliysa, acilinca ilk firsatta calisir
    #  DontStopIfGoingOnBatteries / AllowStartIfOnBatteries : dizustunde de calissin
    #  ExecutionTimeLimit : takilirsa 2 saat sonra kendini sonlandirsin
    $ayar = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -DontStopIfGoingOnBatteries `
        -AllowStartIfOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2)

    Register-ScheduledTask `
        -TaskName $g.Ad `
        -Action $eylem `
        -Trigger $tetik `
        -Settings $ayar `
        -Description $g.Aciklama `
        -Force | Out-Null

    Write-Host "KURULDU: $($g.Ad)  ->  hafta ici $($g.Saat)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Kurulan gorevler:" -ForegroundColor Cyan
Get-ScheduledTask -TaskName "Borsa - *" |
    Select-Object TaskName, State |
    Format-Table -AutoSize

Write-Host "TEST: Gorevleri hemen calistirmak icin:" -ForegroundColor Yellow
Write-Host '  Start-ScheduledTask -TaskName "Borsa - Arka Plan Tarama"'
Write-Host '  Start-ScheduledTask -TaskName "Borsa - Sanal Portfoy"'
Write-Host ""
Write-Host "Sonucu kontrol etmek icin (birkac dakika sonra):" -ForegroundColor Yellow
Write-Host '  Get-Content .\arka_plan_tarama_log.txt -Tail 20'
Write-Host ""
