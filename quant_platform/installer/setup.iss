; Inno Setup script for Quant Platform

[Setup]
AppName=Quant Platform
AppVersion=1.0.0
DefaultDirName={autopf}\QuantPlatform
DefaultGroupName=Quant Platform
OutputBaseFilename=QuantPlatformSetup
Compression=lzma
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "..\build\Release\quant_platform.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config\*"; DestDir: "{app}\config"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\data\*"; DestDir: "{app}\data"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Quant Platform"; Filename: "{app}\quant_platform.exe"
Name: "{group}\Quant Platform (Console)"; Filename: "{app}\quant_platform.exe"; Parameters: "--console"
Name: "{commondesktop}\Quant Platform"; Filename: "{app}\quant_platform.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\quant_platform.exe"; Description: "Launch Quant Platform"; Flags: nowait postinstall skipifsilent
