; NSIS installer script for Quant Platform

!include "MUI2.nsh"

Name "Quant Platform"
OutFile "QuantPlatformSetup.exe"
InstallDir "$PROGRAMFILES64\QuantPlatform"
RequestExecutionLevel admin

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "Main Application" SecMain
    SetOutPath "$INSTDIR"
    File "..\build\Release\quant_platform.exe"

    SetOutPath "$INSTDIR\config"
    File /r "..\config\*.*"

    SetOutPath "$INSTDIR\data"
    File /r "..\data\*.*"

    ; Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Start menu shortcuts
    CreateDirectory "$SMPROGRAMS\Quant Platform"
    CreateShortcut "$SMPROGRAMS\Quant Platform\Quant Platform.lnk" "$INSTDIR\quant_platform.exe"
    CreateShortcut "$SMPROGRAMS\Quant Platform\Quant Platform (Console).lnk" "$INSTDIR\quant_platform.exe" "--console"
    CreateShortcut "$SMPROGRAMS\Quant Platform\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    ; Desktop shortcut
    CreateShortcut "$DESKTOP\Quant Platform.lnk" "$INSTDIR\quant_platform.exe"
SectionEnd

Section "Uninstall"
    Delete "$INSTDIR\quant_platform.exe"
    Delete "$INSTDIR\Uninstall.exe"
    RMDir /r "$INSTDIR\config"
    RMDir /r "$INSTDIR\data"
    RMDir "$INSTDIR"

    Delete "$SMPROGRAMS\Quant Platform\*.lnk"
    RMDir "$SMPROGRAMS\Quant Platform"
    Delete "$DESKTOP\Quant Platform.lnk"
SectionEnd
