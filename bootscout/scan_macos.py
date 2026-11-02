"""Todo lo que arranca solo en macOS, de todos los sitios donde se puede programar.

- **launchd**, que es quien arranca casi todo en el Mac: los *agentes* (arrancan al
  iniciar sesión) y los *daemons* (arrancan con el Mac), tuyos, de otras apps y de Apple.
  Son archivos `.plist` en `~/Library/LaunchAgents`, `/Library/Launch{Agents,Daemons}` y
  `/System/Library/Launch{Agents,Daemons}` (estos últimos, de Apple).
- **Elementos de inicio de sesión**: las apps que se abren al entrar, las que salen en
  Ajustes del Sistema > General > Elementos de inicio. Hoy las guarda `sfltool dumpbtm`.
- **cron** (`crontab -l`), que todavía existe aunque Apple empuje a launchd.
- **Scripts de arranque antiguos**: `/Library/StartupItems`.
- **Perfiles de shell** (`~/.zprofile`, `~/.zshrc`, `~/.bash_profile`…), por si lanzan algo.

Lee archivos `.plist` con `plistlib`; no arranca ni para nada.
"""

from __future__ import annotations

import os
import plistlib
import re
import subprocess
from pathlib import Path

from . import cmdline
from .entry import AT_BOOT, AT_LOGON, ON_DEMAND, SCHEDULED, Entry

# (carpeta, cuándo arranca, de quién es, ámbito)
AGENT_DIRS = [
    ("~/Library/LaunchAgents", AT_LOGON, "tú", "usuario"),
    ("/Library/LaunchAgents", AT_LOGON, "una app que instalaste", "sistema"),
    ("/Library/LaunchDaemons", AT_BOOT, "una app que instalaste", "sistema"),
    ("/System/Library/LaunchAgents", AT_LOGON, "Apple (parte de macOS)", "sistema"),
    ("/System/Library/LaunchDaemons", AT_BOOT, "Apple (parte de macOS)", "sistema"),
]


def _run(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=15).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _target(command_or_argv):
    isfile = os.path.exists

    def which(name):
        from shutil import which as _w

        return _w(name)

    if isinstance(command_or_argv, list):
        return cmdline.posix_target_argv(command_or_argv, isfile, which)
    return cmdline.posix_target(command_or_argv, isfile, which)


def _when_for(plist: dict, default: str) -> tuple[str, str]:
    """Cuándo arranca de verdad, según las llaves del plist, y el detalle para el disparador."""
    if plist.get("RunAtLoad"):
        return default, ""
    if "StartInterval" in plist:
        secs = plist["StartInterval"]
        return SCHEDULED, _interval(secs)
    if "StartCalendarInterval" in plist:
        return SCHEDULED, _calendar(plist["StartCalendarInterval"])
    if plist.get("KeepAlive"):
        return default, "se mantiene siempre en marcha"
    if "WatchPaths" in plist:
        paths = plist["WatchPaths"]
        changed = isinstance(paths, list) and paths
        detail = ("cuando cambian: " + ", ".join(paths[:2])) if changed else "cuando algo cambia"
        return ON_DEMAND, detail
    if "QueueDirectories" in plist:
        return ON_DEMAND, "cuando aparecen archivos en una carpeta"
    if plist.get("OnDemand") is False:
        return default, ""
    return ON_DEMAND, "cuando algo lo pide"


def _interval(secs) -> str:
    try:
        secs = int(secs)
    except (TypeError, ValueError):
        return ""
    if secs % 3600 == 0:
        return f"cada {secs // 3600} h" if secs > 3600 else "cada hora"
    if secs % 60 == 0:
        return f"cada {secs // 60} min"
    return f"cada {secs} s"


def _calendar(spec) -> str:
    items = spec if isinstance(spec, list) else [spec]
    parts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "Hour" in item and "Minute" in item:
            parts.append(f"cada día a las {int(item['Hour']):02d}:{int(item['Minute']):02d}")
        elif "Minute" in item:
            parts.append(f"cada hora (en el minuto {item['Minute']})")
        elif "Weekday" in item:
            parts.append("una vez por semana")
    return "; ".join(parts) or "a una hora fija"


def parse_plist(data: bytes) -> dict | None:
    try:
        plist = plistlib.loads(data)
    except (plistlib.InvalidFileException, ValueError, EOFError, Exception):  # noqa: BLE001
        return None
    return plist if isinstance(plist, dict) else None


def agent_entry(
    plist: dict, path: str, when_default: str, owner: str, scope: str, disabled_labels: set[str] | None = None
) -> Entry:
    label = plist.get("Label") or Path(path).stem
    program = plist.get("Program", "")
    argv = plist.get("ProgramArguments")
    if argv and isinstance(argv, list):
        # Con Program, ese es el ejecutable y argv[0] solo el nombre con el que se ve.
        parts = [str(program), *map(str, argv[1:])] if program else [str(a) for a in argv]
        target = _target(parts)
        command = " ".join(parts)
    elif program:
        target = _target([str(program)])
        command = str(program)
    else:
        target, command = cmdline.Target("", "", ""), ""
    when, trigger = _when_for(plist, when_default)
    # ¿Está apagado? La llave Disabled del plist, o la base de datos de launchd (que manda).
    disabled = bool(plist.get("Disabled", False))
    if disabled_labels and label in disabled_labels:
        disabled = True
    is_apple = "/System/Library" in path
    return Entry(
        id=f"macos:launchd:{scope}:{label}",
        name=label,
        when=when,
        where=_where(path, scope),
        location=path,
        command=command,
        path=target.file or program,
        args=target.args,
        inline=target.inline,
        enabled=not disabled,
        scope=scope,
        trigger=trigger,
        extra={"owner": owner, "apple": is_apple, "keepalive": bool(plist.get("KeepAlive"))},
        toggle={"kind": "launchctl", "label": label, "scope": scope} if scope == "usuario" else {},
        hint=""
        if scope == "usuario"
        else f"Para desactivarlo: «sudo launchctl disable system/{label}» (hace falta administrador).",
    )


def _where(path: str, scope: str) -> str:
    if "LaunchDaemons" in path:
        return "launchd (daemon del sistema)"
    if "/System/Library" in path:
        return "launchd (agente de Apple)"
    if scope == "usuario":
        return "launchd (agente tuyo)"
    return "launchd (agente del sistema)"


def launchd_entries(
    files: dict[str, bytes], when_default: str, owner: str, scope: str, disabled_labels: set[str] | None = None
) -> list[Entry]:
    """files: {ruta del .plist: contenido}. Se saltan los que no se entienden."""
    entries = []
    for path in sorted(files):
        plist = parse_plist(files[path])
        if plist is None:
            continue
        entry = agent_entry(plist, path, when_default, owner, scope, disabled_labels)
        if entry.path or entry.command:
            entries.append(entry)
    return entries


# Elementos de inicio de sesión (Ajustes > General > Elementos de inicio)

_BTM_PATH = re.compile(r"(?:executable path|url)\s*(?:=|:)\s*(.+)", re.I)
_BTM_ITEM = re.compile(r"(?:^|\n)\s*(?:#?\d+\s+)?(?:UUID|Item)\b", re.I)


def parse_login_items(output: str) -> list[Entry]:
    """`sfltool dumpbtm`: el volcado de la base de datos de elementos de inicio. El formato
    no está documentado y cambia entre versiones, así que se leen las rutas de ejecutable y
    poco más, con cuidado."""
    entries = []
    seen = set()
    for m in re.finditer(r"(?:executable path|url|path)\s*[:=]\s*(?:file://)?(\S[^\n]*?\.app)(?:/|\b)", output, re.I):
        app = m.group(1).strip().rstrip("/")
        if app in seen:
            continue
        seen.add(app)
        name = Path(app).stem
        entries.append(
            Entry(
                id=f"macos:loginitem:{name}",
                name=name,
                when=AT_LOGON,
                where="Elemento de inicio de sesión",
                location=app,
                path=app,
                scope="usuario",
                hint="Para quitarlo: Ajustes del Sistema > General > Elementos de inicio.",
            )
        )
    return entries


# cron y perfiles de shell (como en Linux)

_CRON_SPECIAL = {
    "@reboot": AT_BOOT,
    "@daily": SCHEDULED,
    "@hourly": SCHEDULED,
    "@weekly": SCHEDULED,
    "@monthly": SCHEDULED,
    "@yearly": SCHEDULED,
    "@midnight": SCHEDULED,
    "@annually": SCHEDULED,
}
_SHELL_FILES = ["~/.zprofile", "~/.zshrc", "~/.bash_profile", "~/.bashrc", "~/.profile"]


def scan() -> list[Entry]:  # pragma: no cover - usa el sistema de verdad
    from . import scan_linux  # reutiliza cron y perfiles de shell, idénticos

    entries: list[Entry] = []
    disabled = _disabled_labels()
    for rel, when_default, owner, scope in AGENT_DIRS:
        folder = Path(rel.replace("~", str(Path.home())))
        if not folder.is_dir():
            continue
        files = {str(p): _read_bytes(p) for p in sorted(folder.glob("*.plist"))}
        entries += launchd_entries(files, when_default, owner, scope, disabled)

    entries += parse_login_items(_run(["sfltool", "dumpbtm"]))

    entries += scan_linux.parse_crontab(_run(["crontab", "-l"]), "tu usuario", "usuario")
    shell = {}
    for rel in _SHELL_FILES:
        path = Path(rel.replace("~", str(Path.home())))
        if path.is_file():
            shell[str(path)] = scan_linux._read(path)
    entries += scan_linux.shell_entries(shell)
    return entries


def _disabled_labels() -> set[str]:  # pragma: no cover
    labels = set()
    for domain in ("system", f"gui/{os.getuid()}" if hasattr(os, "getuid") else "gui/501"):
        out = _run(["launchctl", "print-disabled", domain])
        for m in re.finditer(r'"([^"]+)"\s*=>\s*(?:true|disabled)', out):
            labels.add(m.group(1))
    return labels


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        return b""
