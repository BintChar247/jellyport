# Builds dist\Jellyport-Setup-<version>.exe
# Needs (once):  python -m pip install pyinstaller
#                winget install JRSoftware.InnoSetup
# (PyInstaller logs to stderr, so this relies on exit codes.)
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$ico = Join-Path $PSScriptRoot "icon.ico"
$version = (Select-String -Path jellyport_cli.py -Pattern '^__version__ = "(.+)"').Matches[0].Groups[1].Value

python -m PyInstaller --noconfirm --clean --onedir --windowed --name Jellyport `
    --icon $ico --add-data "$ico;." `
    --distpath build\dist --workpath build\work --specpath build jellyport.py
if ($LASTEXITCODE) { throw "PyInstaller failed" }

$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
          "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup not found - winget install JRSoftware.InnoSetup" }
& $iscc "/DAppVersion=$version" (Join-Path $PSScriptRoot "Jellyport.iss")
if ($LASTEXITCODE) { throw "Inno Setup failed" }
Get-ChildItem dist\*.exe
