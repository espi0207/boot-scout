"""Todo lo que arranca solo en Windows, de todos los sitios donde se puede programar.

Es donde más rincones hay. boot-scout mira:
- **Claves Run** del registro: `Run`, `RunOnce`, `RunOnceEx` y la de políticas, en tu
  usuario (HKCU) y en todo el equipo (HKLM), incluidas las vistas de 32 bits (Wow6432Node).
  El estado activado/desactivado sale de `StartupApproved`, igual que en el Administrador
  de tareas.
- **Carpetas de Inicio**: la tuya y la común (accesos directos .lnk, .exe, .bat, .vbs…).
- **Tareas programadas** (los XML de `C:\\Windows\\System32\\Tasks`): al arrancar, al
  iniciar sesión, a una hora…
- **Servicios y controladores** (`...\\Services`): los de arranque automático.
- **Winlogon** (`Shell`, `Userinit`), **Active Setup**, depuradores de **IFEO** y
  **AppInit_DLLs**, que son por donde se cuela el malware.

Todo esto se lee a través de `winreg_source`, que en Windows lee el registro y el disco de
verdad, y en las pruebas, unos de mentira. No arranca ni cambia nada al mirar.
"""

from __future__ import annotations

import ntpath

from . import cmdline, lnk
from .entry import AT_LOGON, ON_DEMAND, Entry
from .winreg_source import Source

SYSTEM_SEARCH = [r"C:\Windows\System32", r"C:\Windows", r"C:\Windows\System32\WindowsPowerShell\v1.0"]

# Claves tipo «Run»: (clave, hive, ámbito, cuándo, una sola vez).
RUN_KEYS = [
    (r"Software\Microsoft\Windows\CurrentVersion\Run", "HKCU", "usuario", AT_LOGON, False),
    (r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "HKCU", "usuario", AT_LOGON, True),
    (r"Software\Microsoft\Windows\CurrentVersion\Run", "HKLM", "sistema", AT_LOGON, False),
    (r"Software\Microsoft\Windows\CurrentVersion\RunOnce", "HKLM", "sistema", AT_LOGON, True),
    (r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Run", "HKLM", "sistema", AT_LOGON, False),
    (r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\RunOnce", "HKLM", "sistema", AT_LOGON, True),
    (r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run", "HKCU", "usuario", AT_LOGON, False),
    (r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer\Run", "HKLM", "sistema", AT_LOGON, False),
]
# Para saber si una entrada de Run está desactivada (lo guarda el Administrador de tareas).
APPROVED_KEYS = {
    ("HKCU", False): r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
    ("HKCU", True): r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder",
    ("HKLM", False): r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
    ("HKLM", True): r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder",
}


def _resolve(command: str, source: Source) -> cmdline.Target:
    return cmdline.windows_target(command, source.env, source.is_file, SYSTEM_SEARCH)


def _file_facts(entry: Entry, source: Source) -> None:
    """Rellena si el archivo existe, su info de versión y su firma."""
    if not entry.path:
        return
    entry.exists = source.is_file(entry.path)
    if not entry.exists:
        return
    info = source.version_info(entry.path)
    entry.company = info.get("company", "")
    entry.product = info.get("product", "")
    entry.description = info.get("description", "")
    entry.version = info.get("version", "") or info.get("file_version", "")
    status, signer = source.signature(entry.path)
    entry.signature = status
    entry.signer = signer


def _approved_disabled(data) -> bool:
    """El valor de StartupApproved (12 bytes). El primer byte: 02 o 06 = activada, 03 = la
    desactivaste tú en el Administrador de tareas. Lo impar marca desactivada."""
    if isinstance(data, bytes) and data:
        return bool(data[0] & 0x01)
    return False


def run_key_entries(source: Source) -> list[Entry]:
    entries = []
    for subkey, hive, scope, when, once in RUN_KEYS:
        path = f"{hive}\\{subkey}"
        approved_path = f"{hive}\\{APPROVED_KEYS[(hive, False)]}"
        approved = {name.lower(): data for name, data in source.values(approved_path)}
        for name, data in source.values(path):
            command = data if isinstance(data, str) else str(data)
            if not command.strip():
                continue
            target = _resolve(command, source)
            view = " (32 bits)" if "Wow6432Node" in subkey else ""
            where = (
                "Registro: "
                + ("RunOnce" if once else "Run")
                + (" (tu usuario)" if hive == "HKCU" else " (todo el equipo)")
                + view
            )
            if "Policies" in subkey:
                where = f"Registro: política de inicio ({'tu usuario' if hive == 'HKCU' else 'equipo'})"
            entry = Entry(
                id=f"win:run:{hive}:{subkey}:{name}",
                name=name,
                when=when,
                where=where,
                location=f"{path}\\{name}",
                command=command,
                path=target.file,
                args=target.args,
                inline=target.inline,
                encoded=target.encoded,
                scope=scope,
                enabled=not _approved_disabled(approved.get(name.lower())),
                trigger="solo la próxima vez que enciendas" if once else "",
                # Solo lo de tu usuario (HKCU): lo de todo el equipo se explica, pero no se toca.
                toggle={"kind": "run", "hive": hive, "key": approved_path, "name": name}
                if not once and hive == "HKCU"
                else {},
                hint=""
                if hive == "HKCU" or once
                else "Es de todo el equipo: desactívalo en el Administrador de tareas > Inicio (pide administrador).",
            )
            _file_facts(entry, source)
            entries.append(entry)
    return entries


# Carpetas de Inicio

STARTUP_FOLDERS = [
    (r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup", "usuario", "tu carpeta de Inicio"),
    (r"%PROGRAMDATA%\Microsoft\Windows\Start Menu\Programs\Startup", "sistema", "la carpeta de Inicio común"),
]
_STARTUP_EXT = (".lnk", ".exe", ".bat", ".cmd", ".vbs", ".vbe", ".js", ".jse", ".ps1", ".wsf", ".com", ".url")


def startup_folder_entries(source: Source) -> list[Entry]:
    entries = []
    for raw, scope, label in STARTUP_FOLDERS:
        folder = cmdline.expand(raw, source.env)
        for name in source.list_dir(folder):
            if name.lower() == "desktop.ini" or not name.lower().endswith(_STARTUP_EXT):
                continue
            full = ntpath.join(folder, name)
            if name.lower().endswith(".lnk"):
                target = _lnk_target(source.read(full), source)
                command = target.program + (f" {target.args}" if target.args else "")
            else:
                target = _resolve(f'"{full}"', source)
                command, target = full, cmdline.Target(full, "", full)
            entry = Entry(
                id=f"win:startup:{scope}:{name}",
                name=ntpath.splitext(name)[0],
                when=AT_LOGON,
                where=f"Carpeta de Inicio ({label})",
                location=full,
                command=command,
                path=target.file,
                args=target.args,
                inline=target.inline,
                scope=scope,
                toggle={"kind": "startup-file", "file": full} if scope == "usuario" else {},
                hint=""
                if scope == "usuario"
                else "Para quitarlo del todo, borra este acceso directo (hace falta administrador).",
            )
            _file_facts(entry, source)
            entries.append(entry)
    return entries


def _lnk_target(data: bytes, source: Source) -> cmdline.Target:
    try:
        link = lnk.parse(data)
    except lnk.BadLink:
        return cmdline.Target("", "", "")
    command = f'"{link.target}"' + (f" {link.arguments}" if link.arguments else "")
    return _resolve(command, source)


# Winlogon, Active Setup, IFEO, AppInit_DLLs

WINLOGON = r"HKLM\Software\Microsoft\Windows NT\CurrentVersion\Winlogon"
IFEO = r"HKLM\Software\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"
APPINIT = r"HKLM\Software\Microsoft\Windows NT\CurrentVersion\Windows"
ACTIVE_SETUP = r"HKLM\Software\Microsoft\Active Setup\Installed Components"


def special_entries(source: Source) -> list[Entry]:
    entries = []
    # Winlogon: Shell (normal: explorer.exe) y Userinit (normal: userinit.exe).
    for value_name, normal, home, label in (
        ("Shell", "explorer.exe", r"%SystemRoot%", "el shell de Windows"),
        ("Userinit", "userinit.exe", r"%SystemRoot%\System32", "el arranque de la sesión"),
    ):
        canonical = cmdline.expand(rf"{home}\{normal}", source.env).lower()
        data = source.value(WINLOGON, value_name)
        if not data:
            continue
        for command in [c for c in str(data).split(",") if c.strip()]:
            expanded = cmdline.expand(command.strip().strip('"'), source.env).lower()
            base = ntpath.basename(expanded)
            # Lo de siempre: el nombre solo (Windows lo busca en su carpeta) o la ruta de Windows.
            # Un explorer.exe en otra carpeta no lo es, aunque se llame igual.
            if expanded in (normal, normal.replace(".exe", ""), canonical):
                continue
            target = _resolve(command.strip(), source)
            entry = Entry(
                id=f"win:winlogon:{value_name}:{base}",
                name=command.strip(),
                when=AT_LOGON,
                where=f"Winlogon · {value_name}",
                location=f"{WINLOGON}\\{value_name}",
                command=command.strip(),
                path=target.file,
                args=target.args,
                scope="sistema",
                extra={
                    "unusual": f"Está enganchado a {label} (Winlogon {value_name}), que normalmente solo "
                    f"lleva {normal}. Eso es raro y es un sitio típico de los virus."
                },
            )
            _file_facts(entry, source)
            entries.append(entry)
    # AppInit_DLLs: DLLs que se cargan en casi todos los programas (casi nadie las usa ya).
    appinit = source.value(APPINIT, "AppInit_DLLs")
    if appinit and str(appinit).strip():
        for dll in str(appinit).replace(",", " ").split():
            target = cmdline.expand(dll.strip('"'), source.env)
            entry = Entry(
                id=f"win:appinit:{ntpath.basename(target).lower()}",
                name=ntpath.basename(target),
                when=ON_DEMAND,
                where="AppInit_DLLs",
                location=f"{APPINIT}\\AppInit_DLLs",
                command=dll,
                path=target,
                scope="sistema",
                extra={
                    "unusual": "Es una DLL que Windows mete dentro de casi todos los programas al abrirse "
                    "(AppInit_DLLs). Casi nada legítimo usa esto hoy; míralo."
                },
            )
            _file_facts(entry, source)
            entries.append(entry)
    # IFEO: un «Debugger» en un programa hace que Windows abra otra cosa en su lugar.
    for program in source.subkeys(IFEO):
        debugger = source.value(f"{IFEO}\\{program}", "Debugger")
        if not debugger or not str(debugger).strip():
            continue
        target = _resolve(str(debugger), source)
        entry = Entry(
            id=f"win:ifeo:{program.lower()}",
            name=f"{program} → {ntpath.basename(target.file or str(debugger))}",
            when=ON_DEMAND,
            where="Image File Execution Options (Debugger)",
            location=f"{IFEO}\\{program}\\Debugger",
            command=str(debugger),
            path=target.file,
            scope="sistema",
            extra={
                "unusual": f"Cuando se abre «{program}», Windows abre esto en su lugar (un «depurador» de "
                "IFEO). A veces es una herramienta de desarrollo, pero también es un truco de los virus "
                "para secuestrar un programa."
            },
        )
        _file_facts(entry, source)
        entries.append(entry)
    return entries


def scan(source: Source | None = None) -> list[Entry]:
    """Todas las entradas de Windows. Sin `source`, usa el registro y el disco de verdad."""
    if source is None:  # pragma: no cover - solo en Windows
        from .winreg_source import RealSource

        source = RealSource()
    entries = run_key_entries(source)
    entries += startup_folder_entries(source)
    entries += special_entries(source)
    from . import win_services, win_tasks

    entries += win_services.service_entries(source)
    entries += win_tasks.task_entries(source)
    return entries
