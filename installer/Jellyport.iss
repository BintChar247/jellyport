; Inno Setup script for Jellyport - build with installer\build.ps1
#define AppName "Jellyport"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{B3F1A2D4-7C6E-4E1B-9A35-5D2C8F0E7A41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Jellyport contributors
AppPublisherURL=https://github.com/BintChar247/jellyport
AppSupportURL=https://github.com/BintChar247/jellyport/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist
OutputBaseFilename=Jellyport-Setup-{#AppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\Jellyport.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\build\dist\Jellyport\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Jellyport"; Filename: "{app}\Jellyport.exe"
Name: "{group}\Uninstall Jellyport"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Jellyport"; Filename: "{app}\Jellyport.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Jellyport.exe"; Description: "Launch Jellyport"; Flags: nowait postinstall skipifsilent

; Settings in %APPDATA%\Jellyport are kept on uninstall so a reinstall remembers them.
