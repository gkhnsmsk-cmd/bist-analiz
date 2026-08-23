@echo off
rem ============================================================
rem  Masaustune Kisayol Olustur
rem  Bu dosyaya BIR KEZ cift tiklayin. Masaustunuze "BIST Analiz
rem  Platformu" adinda bir kisayol eklenir. O andan sonra
rem  yaziliami acmak icin sadece o kisayola cift tiklamaniz yeterli.
rem ============================================================
setlocal
set "HEDEF=%~dp0BASLAT.bat"
set "KISAYOL=%USERPROFILE%\Desktop\BIST Analiz Platformu.lnk"

powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%KISAYOL%');" ^
  "$s.TargetPath = '%HEDEF%';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.IconLocation = 'shell32.dll,220';" ^
  "$s.Description = 'BIST Analiz Platformunu baslatir';" ^
  "$s.Save()"

if exist "%KISAYOL%" (
  echo.
  echo  Basarili! Masaustunuzde "BIST Analiz Platformu" kisayolu olustu.
  echo  Bundan sonra yazilimi acmak icin o kisayola cift tiklamaniz yeterli.
) else (
  echo.
  echo  Kisayol olusturulamadi. Bunun yerine bu klasordeki BASLAT.bat
  echo  dosyasini surukleyip masaustune birakabilirsiniz.
)
echo.
pause
