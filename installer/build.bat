if "%1" == "" (
set /P "vno=Version Number (10.1.2 etc) :"
) else (
echo set to %1
set vno=%1
)
echo Build %vno%
"\Program Files (x86)\Inno Setup 6\iscc.exe" /DMyAppVersion=%vno% innoscript.iss
certutil -hashfile installers\EDD-EDMC-%vno%.exe SHA256 >installers\checksums.%vno%.txt
