if "%1" == "" (
set /P vno=Version Number (10.1.2 etc) :
) else (
echo set to %1
set vno=%1
)
Build %vno%
"\Program Files (x86)\Inno Setup 6\iscc.exe" /DMyAppVersion=%vno% innoscript.iss
rem copy ..\EDDiscovery\bin\Release\EDDiscovery.Portable.Zip installers\EDDiscovery.Portable.%vno%.zip
rem certutil -hashfile installers\EDDiscovery-%vno%.exe SHA256 >installers\checksums.%vno%.txt
rem certutil -hashfile installers\EDDiscovery.Portable.%vno%.zip SHA256 >>installers\checksums.%vno%.txt
