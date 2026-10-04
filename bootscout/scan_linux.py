"""Todo lo que arranca solo en Linux, de todos los sitios donde se puede programar.

- **Autostart del escritorio** (`~/.config/autostart` y `/etc/xdg/autostart`): los
  programas que abre el escritorio al iniciar sesión, en archivos `.desktop`.
- **systemd**, el que arranca casi todo hoy: servicios y temporizadores, tuyos
  (`--user`) y del sistema, habilitados (`enabled`).
- **Al abrir la terminal / la sesión**: `~/.bashrc`, `~/.profile`, `~/.zshrc`,
  `/etc/profile.d`… (solo se mira si lanzan algo, no se interpretan).
- **cron**: las tareas programadas, las tuyas y las del sistema, incluidas las de
  `@reboot` (al arrancar), y las carpetas `/etc/cron.{hourly,daily,weekly,monthly}`.
- **Lo antiguo**: `/etc/rc.local` (órdenes al final del arranque).

Lee archivos y pregunta a `systemctl`; no arranca ni para nada.
"""

from __future__ import annotations

import configparser
import os
import re
import subprocess
from pathlib import Path

from . import cmdline
from .entry import AT_BOOT, AT_LOGON, INSIDE, SCHEDULED, Entry


def _run(args: list[str]) -> str:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def _target(command: str) -> cmdline.Target:
    return cmdline.posix_target(command, lambda p: os.path.exists(p), _which)


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


def parse_desktop(text: str) -> dict:
    """Un archivo .desktop, solo la sección [Desktop Entry]."""
    parser = configparser.RawConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read_string(text)
    except configparser.Error:
        return {}
    if not parser.has_section("Desktop Entry"):
        return {}
    return dict(parser["Desktop Entry"])


def autostart_entries(dirs: dict[str, list[Path]]) -> list[Entry]:
    """dirs: {"usuario": [~/.config/autostart], "sistema": [/etc/xdg/autostart]}. Un mismo
    nombre de archivo en el de usuario tapa al del sistema (así se desactiva uno del sistema)."""
    entries: dict[str, Entry] = {}
    for scope, folders in dirs.items():
        for folder in folders:
            if not folder.is_dir():
                continue
            for path in sorted(folder.glob("*.desktop")):
                data = parse_desktop(_read(path))
                if not data:
                    continue
                enabled = data.get("Hidden", "false").strip().lower() != "true"
                command = data.get("Exec", "")
                target = _target(command)
                name = data.get("Name", path.stem)
                entry = Entry(
                    id=f"linux:autostart:{path.name}",
                    name=name,
                    when=AT_LOGON,
                    where="Autostart del escritorio",
                    location=str(path),
                    command=command,
                    path=target.file,
                    args=target.args,
                    enabled=enabled,
                    scope=scope,
                    description=data.get("Comment", ""),
                    toggle={"file": str(path), "kind": "desktop"} if scope == "usuario" else {},
                    hint=""
                    if scope == "usuario"
                    else "Para quitarlo solo para ti: copia este archivo a "
                    "~/.config/autostart y añádele la línea «Hidden=true».",
                )
                if data.get("X-GNOME-Autostart-enabled", "").strip().lower() == "false":
                    entry.enabled = False
                entries[path.name] = entry  # el de usuario, al ir después, tapa al del sistema
    return list(entries.values())


def systemd_entries(scope: str, list_output: str, enabled_output: str) -> list[Entry]:
    """De `systemctl list-unit-files --state=enabled` (qué va a arrancar) y
    `systemctl list-units` (qué está puesto en marcha). Solo lo habilitado: lo demás no
    arranca solo."""
    enabled = _systemd_enabled(enabled_output)
    entries = []
    for unit, kind in enabled:
        if unit.endswith("@") or "@." in unit:  # plantillas: no son una instancia concreta
            continue
        when = SCHEDULED if kind == "timer" else (AT_BOOT if scope == "sistema" else AT_LOGON)
        entries.append(
            Entry(
                id=f"linux:systemd:{scope}:{unit}",
                name=unit,
                when=when,
                where=f"systemd ({'tu usuario' if scope == 'usuario' else 'sistema'})",
                location=unit,
                enabled=True,
                scope=scope,
                toggle={"kind": "systemd", "unit": unit, "user": scope == "usuario"},
            )
        )
    return entries


def _systemd_enabled(output: str) -> list[tuple[str, str]]:
    found = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] in ("enabled", "static-enabled") and "." in parts[0]:
            unit = parts[0]
            kind = unit.rsplit(".", 1)[1]
            if kind in ("service", "timer"):
                found.append((unit, kind))
    return found


def describe_units(entries: list[Entry], user: bool) -> None:
    """Rellena la descripción y la orden de cada servicio con `systemctl show`."""
    for entry in entries:
        if not entry.id.startswith("linux:systemd"):
            continue
        base = [
            "systemctl",
            "show",
            entry.location,
            "--no-pager",
            "--property=Description,ExecStart,FragmentPath,Names",
        ]
        if user:
            base.insert(1, "--user")
        info = _show(_run(base))
        entry.description = info.get("Description", "")
        exec_start = info.get("ExecStart", "")
        m = re.search(r"argv\[\]=([^;]+)", exec_start) or re.search(r"path=(\S+)", exec_start)
        if m:
            entry.command = m.group(1).strip()
            target = _target(entry.command)
            entry.path, entry.args = target.file, target.args
        entry.extra["fragment"] = info.get("FragmentPath", "")


def _show(output: str) -> dict:
    info = {}
    for line in output.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            info[key] = value
    return info


# cron

_CRON_SPECIAL = {
    "@reboot": AT_BOOT,
    "@yearly": SCHEDULED,
    "@annually": SCHEDULED,
    "@monthly": SCHEDULED,
    "@weekly": SCHEDULED,
    "@daily": SCHEDULED,
    "@midnight": SCHEDULED,
    "@hourly": SCHEDULED,
}


def parse_crontab(text: str, source: str, scope: str, with_user: bool = False) -> list[Entry]:
    """Un crontab. Con `with_user` (los de /etc/crontab y /etc/cron.d) hay un campo más: el
    usuario con el que corre."""
    entries = []
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()
        first = line.split()[0] if line.split() else ""
        if not line or line.startswith("#") or "=" in first:  # vacía, comentario o «VAR=valor»
            continue
        when = SCHEDULED
        if line.startswith("@"):
            parts = line.split(None, 1)
            when = _CRON_SPECIAL.get(parts[0].lower(), SCHEDULED)
            schedule, rest = parts[0], (parts[1] if len(parts) > 1 else "")
        else:
            fields = line.split(None, 5)
            if len(fields) < 6:
                continue
            schedule, rest = " ".join(fields[:5]), fields[5]
        if with_user:
            bits = rest.split(None, 1)
            rest = bits[1] if len(bits) > 1 else ""
        if not rest:
            continue
        target = _target(rest)
        entries.append(
            Entry(
                id=f"linux:cron:{source}:{i}",
                name=Path(target.file).name or rest[:40],
                when=when,
                where=f"Tarea programada (cron, {source})",
                location=source,
                command=rest,
                path=target.file,
                args=target.args,
                scope=scope,
                trigger="al arrancar" if when == AT_BOOT else _cron_human(schedule),
            )
        )
    return entries


def _cron_human(schedule: str) -> str:
    specials = {
        "@daily": "cada día",
        "@midnight": "cada día a medianoche",
        "@hourly": "cada hora",
        "@weekly": "cada semana",
        "@monthly": "cada mes",
        "@yearly": "cada año",
        "@annually": "cada año",
    }
    if schedule.lower() in specials:
        return specials[schedule.lower()]
    fields = schedule.split()
    if len(fields) == 5:
        minute, hour, dom, month, dow = fields
        if minute.isdigit() and hour.isdigit() and dom == month == dow == "*":
            return f"cada día a las {int(hour):02d}:{int(minute):02d}"
        if dom == month == dow == "*" and hour == "*" and minute.isdigit():
            return f"cada hora (en el minuto {minute})"
    return schedule


# carpetas de scripts que ejecuta run-parts: /etc/cron.{hourly,daily,weekly,monthly} (vía
# anacron/cron) y los scripts de arranque del sistema.

_PERIODIC = {
    "cron.hourly": "cada hora",
    "cron.daily": "cada día",
    "cron.weekly": "cada semana",
    "cron.monthly": "cada mes",
}


def run_parts_entries(folder: Path, trigger: str, where: str, when: str = SCHEDULED) -> list[Entry]:
    """Cada script ejecutable de una carpeta que corre run-parts."""
    entries = []
    if not folder.is_dir():
        return entries
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.name.startswith(".") or "." in path.name:  # run-parts salta los que llevan punto
            continue
        if not os.access(path, os.X_OK):
            continue
        entries.append(
            Entry(
                id=f"linux:runparts:{folder.name}:{path.name}",
                name=path.name,
                when=when,
                where=where,
                location=str(path),
                command=str(path),
                path=str(path),
                scope="sistema",
                trigger=trigger,
                hint=f"Es un script del sistema en {path}. Suele venir de un paquete; míralo antes de tocarlo.",
            )
        )
    return entries


# Órdenes de preparación del arranque que no son "un programa que arranca": tocar archivos,
# cargar módulos, ajustar permisos o el sistema.
_RC_NOISE = re.compile(
    r"^(exit|set|export|touch|mkdir|rm|chmod|chown|chgrp|ln|mount|umount|modprobe|insmod|"
    r"rmmod|sysctl|echo|printf|hwclock|ip|ifconfig|route|iptables|ethtool|setterm|"
    r"dmesg|logger|stty|loadkeys|swapon|hdparm|blockdev)\b"
)


def rc_local_entries(text: str, source: str = "/etc/rc.local") -> list[Entry]:
    """/etc/rc.local: las órdenes que el sistema ejecuta al final del arranque (lo antiguo)."""
    entries = []
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line or line.startswith("#") or line in ("exit 0", "#!/bin/sh", "#!/bin/bash"):
            continue
        if _RC_NOISE.match(line):
            continue
        target = _target(line)
        if not target.file or _RC_NOISE.match(Path(target.file).name):
            continue
        entries.append(
            Entry(
                id=f"linux:rc-local:{i}",
                name=Path(target.file).name,
                when=AT_BOOT,
                where="Al arrancar (rc.local)",
                location=source,
                command=line,
                path=target.file,
                args=target.args,
                scope="sistema",
                hint=f"Está escrito a mano en {source}: ábrelo como administrador y borra o comenta esa línea.",
            )
        )
    return entries


# shell

_SHELL_FILES = [
    ("~/.bashrc", INSIDE),
    ("~/.bash_profile", AT_LOGON),
    ("~/.profile", AT_LOGON),
    ("~/.zshrc", INSIDE),
    ("~/.zprofile", AT_LOGON),
    ("~/.config/fish/config.fish", INSIDE),
    ("~/.xprofile", AT_LOGON),
    ("~/.xinitrc", AT_LOGON),
]


def shell_entries(read: dict[str, str]) -> list[Entry]:
    """read: {ruta: contenido}. Solo se marcan las líneas que lanzan algo en segundo plano
    (acaban en `&`, o usan nohup/setsid), no se interpreta el script."""
    entries = []
    for path, text in read.items():
        for i, raw in enumerate(text.splitlines()):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.rstrip().endswith("&") and not line.rstrip().endswith("&&"):
                command = line.rstrip().rstrip("&").strip()
            elif re.match(r"(nohup|setsid)\s+\S", line):
                command = re.sub(r"^(nohup|setsid)\s+", "", line).rstrip("& ")
            else:
                continue
            target = _target(command)
            if not target.file or target.file in ("[", "test", "true", "false"):
                continue
            system = path.startswith("/etc/")
            entries.append(
                Entry(
                    id=f"linux:shell:{Path(path).name}:{i}",
                    name=Path(target.file).name,
                    when=AT_LOGON if ("profile" in path or system) else INSIDE,
                    where=f"Al iniciar sesión ({Path(path).name})"
                    if system
                    else f"Al abrir la terminal ({Path(path).name})",
                    location=path,
                    command=command,
                    path=target.file,
                    args=target.args,
                    scope="sistema" if system else "usuario",
                    hint=f"Está escrito a mano en {path}: ábrelo"
                    + (" como administrador" if system else "")
                    + " con un editor y borra o comenta esa línea.",
                )
            )
    return entries


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def scan() -> list[Entry]:  # pragma: no cover - usa el sistema de verdad
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    entries: list[Entry] = []

    entries += autostart_entries(
        {
            "sistema": [Path("/etc/xdg/autostart")],
            "usuario": [config / "autostart"],
        }
    )

    for scope, user in (("usuario", True), ("sistema", False)):
        base = ["systemctl", "list-unit-files", "--state=enabled", "--no-legend", "--no-pager", "--all"]
        if user:
            base.insert(1, "--user")
        units = systemd_entries(scope, _run(base), _run(base))
        describe_units(units, user)
        entries += units

    entries += parse_crontab(_run(["crontab", "-l"]), "tu usuario", "usuario")
    for name in ("/etc/crontab",):
        if Path(name).is_file():
            entries += parse_crontab(_read(Path(name)), name, "sistema", with_user=True)
    cron_d = Path("/etc/cron.d")
    if cron_d.is_dir():
        for path in sorted(cron_d.iterdir()):
            if path.is_file():
                entries += parse_crontab(_read(path), str(path), "sistema", with_user=True)
    for folder, trigger in _PERIODIC.items():
        entries += run_parts_entries(Path("/etc") / folder, trigger, f"Tarea programada ({folder})")

    for name in ("/etc/rc.local",):
        if Path(name).is_file():
            entries += rc_local_entries(_read(Path(name)), name)

    shell = {}
    for rel, _when in _SHELL_FILES:
        path = Path(rel.replace("~", str(home)))
        if path.is_file():
            shell[str(path)] = _read(path)
    for path in sorted(Path("/etc/profile.d").glob("*.sh")) if Path("/etc/profile.d").is_dir() else []:
        shell[str(path)] = _read(path)
    entries += shell_entries(shell)
    return entries
