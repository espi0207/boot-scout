"""Activar y desactivar lo que arranca, de forma reversible, y solo lo que es tuyo.

boot-scout nunca borra nada: desactivar es siempre algo que se puede deshacer, y solo toca
cosas de tu usuario (lo del sistema pide administrador y boot-scout dice cómo, pero no lo
hace). Cada cambio se apunta en un registro para poder deshacerlo.

- **Linux, autostart**: añade o quita «Hidden=true» en el `.desktop` (en tu carpeta;
  si el archivo era del sistema, se copia a la tuya, que es como se desactiva uno del
  sistema sin tocar el original).
- **Linux, systemd de usuario**: `systemctl --user disable/enable`.
- **Windows, Run y carpeta de Inicio**: escribe en `StartupApproved`, igual que el
  Administrador de tareas (02 = activado, 03 = desactivado).
- **macOS, agentes tuyos**: `launchctl disable/enable gui/<uid>/<label>`.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from .entry import Entry
from .history import data_dir

LOG = "cambios.json"


class CantDo(Exception):
    """No se puede hacer desde boot-scout (hace falta administrador, o es a mano)."""


def set_enabled(entry: Entry, enabled: bool) -> str:
    """Activa (enabled=True) o desactiva (False) la entrada. Devuelve un mensaje de qué pasó.
    Lanza CantDo si no se puede desde aquí."""
    toggle = entry.toggle
    if not toggle:
        raise CantDo(entry.hint or "Esto hay que cambiarlo a mano; mira «Cómo tocarlo».")
    kind = toggle.get("kind")
    if kind == "desktop":
        _desktop(Path(toggle["file"]), enabled)
    elif kind == "systemd":
        _systemd(toggle["unit"], toggle.get("user", True), enabled)
    elif kind == "launchctl":
        _launchctl(toggle["label"], enabled)
    elif kind in ("run", "startup-file"):
        _windows(toggle, enabled)
    else:
        raise CantDo("No sé cambiar esto desde aquí.")
    entry.enabled = enabled
    return f"{entry.display_name()}: {'activado' if enabled else 'desactivado'}."


# Linux


def _desktop(path: Path, enabled: bool) -> None:
    home_autostart = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "autostart"
    if str(path).startswith("/etc/"):
        # Es del sistema: para desactivarlo sin tocar el original se crea una copia en la
        # carpeta del usuario con «Hidden=true».
        home_autostart.mkdir(parents=True, exist_ok=True)
        target = home_autostart / path.name
        if enabled:
            target.unlink(missing_ok=True)  # quitar la copia reactiva el del sistema
            return
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else "[Desktop Entry]\n"
        path = target
    else:
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else "[Desktop Entry]\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_set_desktop_hidden(text, hidden=not enabled), encoding="utf-8")


def _set_desktop_hidden(text: str, hidden: bool) -> str:
    """Pone, cambia o quita las líneas Hidden y X-GNOME-Autostart-enabled en [Desktop Entry]."""
    lines = text.splitlines()
    out, in_entry, done = [], False, False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_entry and hidden and not done:
                out.append("Hidden=true")
                done = True
            in_entry = stripped == "[Desktop Entry]"
        if in_entry and stripped.lower().startswith(("hidden=", "x-gnome-autostart-enabled=")):
            continue  # se quitan las que haya; se vuelve a poner la buena si hace falta
        out.append(line)
    if hidden and not done:
        if not in_entry and "[Desktop Entry]" not in text:
            out.insert(0, "[Desktop Entry]")
        out.append("Hidden=true")
    return "\n".join(out) + "\n"


def _systemd(unit: str, user: bool, enabled: bool) -> None:  # pragma: no cover - usa systemctl
    cmd = ["systemctl"] + (["--user"] if user else []) + [("enable" if enabled else "disable"), "--now", unit]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CantDo(result.stderr.strip() or "systemctl no pudo con ello (¿hace falta administrador?).")


# macOS


def _launchctl(label: str, enabled: bool) -> None:  # pragma: no cover - usa launchctl
    uid = os.getuid() if hasattr(os, "getuid") else 501
    action = "enable" if enabled else "disable"
    result = subprocess.run(["launchctl", action, f"gui/{uid}/{label}"], capture_output=True, text=True)
    if result.returncode != 0:
        raise CantDo(result.stderr.strip() or "launchctl no pudo con ello.")


# Windows


def _windows(toggle: dict, enabled: bool) -> None:  # pragma: no cover - usa winreg
    import winreg

    if toggle["kind"] == "run":
        key_path = toggle["key"]  # ...\StartupApproved\Run
        name = toggle["name"]
        hive = getattr(winreg, {"HKCU": "HKEY_CURRENT_USER", "HKLM": "HKEY_LOCAL_MACHINE"}[toggle["hive"]])
        value = b"\x02" + b"\x00" * 11 if enabled else b"\x03" + b"\x00" * 11
        sub = key_path.split("\\", 1)[1]
        with winreg.CreateKey(hive, sub) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_BINARY, value)
    elif toggle["kind"] == "startup-file":
        # Mover el acceso directo a una subcarpeta «Desactivados» (y traerlo de vuelta).
        src = Path(toggle["file"])
        disabled_dir = src.parent / "Desactivados por boot-scout"
        if enabled:
            back = src.parent / src.name
            moved = disabled_dir / src.name
            if moved.exists():
                moved.replace(back)
        else:
            disabled_dir.mkdir(exist_ok=True)
            src.replace(disabled_dir / src.name)


# Registro de cambios (para deshacer)


class ChangeLog:
    def __init__(self, path: Path | None = None):
        self.path = path or data_dir() / LOG
        self.changes: list[dict] = []
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, list):
                self.changes = loaded
        except (OSError, ValueError):
            pass

    def add(self, entry: Entry, was_enabled: bool, now_enabled: bool) -> None:
        self.changes.append(
            {
                "when": datetime.now().isoformat(timespec="seconds"),
                "id": entry.id,
                "name": entry.display_name(),
                "toggle": entry.toggle,
                "from": was_enabled,
                "to": now_enabled,
                "hint": entry.hint,
            }
        )

    def last(self) -> dict | None:
        return self.changes[-1] if self.changes else None

    def pop(self) -> dict | None:
        return self.changes.pop() if self.changes else None

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".cambios-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.changes[-200:], f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def undo_last(log: ChangeLog) -> str:
    """Deshace el último cambio: vuelve a dejar la entrada como estaba."""
    change = log.last()
    if not change:
        raise CantDo("No hay ningún cambio que deshacer.")
    fake = Entry(
        id=change["id"],
        name=change["name"],
        when="",
        where="",
        toggle=change.get("toggle", {}),
        hint=change.get("hint", ""),
    )
    set_enabled(fake, change["from"])
    log.pop()
    log.save()
    return f"Deshecho: {change['name']} vuelve a estar {'activado' if change['from'] else 'desactivado'}."
