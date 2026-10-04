; Instalador de Windows, con Inno Setup 6. Lo compila la CI después de PyInstaller:
;     iscc packaging\windows\boot-scout.iss
; La versión llega en la variable de entorno BOOTSCOUT_VERSION.

#define AppVersion GetEnv("BOOTSCOUT_VERSION")

[Setup]
; Este identificador no se cambia nunca: es lo que hace que una versión nueva se instale
; encima de la anterior en vez de al lado.
AppId={{F45589C7-6203-4180-AA97-D1B8481978DB}
AppName=boot-scout
AppVersion={#AppVersion}
AppVerName=boot-scout {#AppVersion}
AppPublisher=espi0207
AppPublisherURL=https://github.com/espi0207/boot-scout
AppSupportURL=https://github.com/espi0207/boot-scout/issues
DefaultDirName={autopf}\boot-scout
DisableProgramGroupPage=yes
; Sin permisos de administrador se instala solo para quien lo instala (y no sale el aviso
; de "¿Quieres permitir que esta aplicación haga cambios?").
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=boot-scout-windows
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\boot-scout.exe
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; Flags: unchecked

[Files]
Source: "..\..\dist\boot-scout\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\boot-scout"; Filename: "{app}\boot-scout.exe"
Name: "{autodesktop}\boot-scout"; Filename: "{app}\boot-scout.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\boot-scout.exe"; Description: "Abrir boot-scout"; Flags: nowait postinstall skipifsilent
