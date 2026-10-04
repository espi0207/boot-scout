"""Lo que boot-scout recuerda de una vez a otra: qué arrancaba ya.

Así puede decir "esto es nuevo" (apareció desde la última vez), que es lo que más interesa:
algo que empieza a arrancar solo de repente suele ser un programa que acabas de instalar…
o algo que no querías. Se guarda en un JSON en la carpeta de datos del usuario (o en
BOOTSCOUT_HOME, si existe esa variable). Cada sistema (Windows/macOS/Linux) va aparte.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from .entry import Entry

FILE = "visto.json"


def data_dir() -> Path:
    if custom := os.environ.get("BOOTSCOUT_HOME"):
        return Path(custom)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "boot-scout"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "boot-scout"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "boot-scout"


def _system_key() -> str:
    return {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")


class History:
    def __init__(self, path: Path | None = None, system: str | None = None):
        self.path = path or data_dir() / FILE
        self.system = system or _system_key()
        self.data = {"version": 1, "systems": {}}
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("systems"), dict):
                self.data = loaded
        except (OSError, ValueError):
            pass

    def _bucket(self) -> dict:
        return self.data["systems"].setdefault(self.system, {"scans": 0, "entries": {}})

    def record(self, entries: list[Entry], when: datetime | None = None) -> list[dict]:
        """Marca las entradas nuevas y devuelve las que estaban y ya no están."""
        when_text = (when or datetime.now()).isoformat(timespec="seconds")
        bucket = self._bucket()
        known = bucket["entries"]
        first_time = bucket["scans"] == 0
        seen = set()
        for entry in entries:
            seen.add(entry.id)
            stored = known.get(entry.id)
            if stored is None:
                entry.is_new = not first_time
                stored = known[entry.id] = {"first_seen": when_text}
            entry.first_seen = stored.get("first_seen", when_text)
            stored.update(
                last_seen=when_text,
                name=entry.display_name(),
                where=entry.where,
                path=entry.path,
                verdict=entry.verdict,
            )
        gone = [dict(v, id=k) for k, v in known.items() if k not in seen]
        gone.sort(key=lambda v: v.get("last_seen", ""), reverse=True)
        # Las que llevan tiempo sin verse se olvidan, para que la lista no crezca sin fin.
        for stale in gone:
            if _old(stale.get("last_seen", ""), when):
                known.pop(stale["id"], None)
        bucket["scans"] += 1
        bucket["last_scan"] = when_text
        return gone

    def is_first_scan(self) -> bool:
        return self._bucket().get("scans", 0) <= 1

    def forget(self, entry_id: str) -> bool:
        return self._bucket()["entries"].pop(entry_id, None) is not None

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".visto-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1, sort_keys=True)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def _old(iso: str, now: datetime | None, days: int = 30) -> bool:
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return False
    return ((now or datetime.now()) - then).days > days
