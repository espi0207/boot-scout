"""Una pasada entera: encontrar todo lo que arranca, clasificarlo y marcar lo nuevo.

Elige el rastreador según el sistema (Windows, macOS o Linux), pasa cada hallazgo por el
«juez» (qué es y qué hacer con ello) y, con el historial, marca lo que ha aparecido desde
la última vez.
"""

from __future__ import annotations

import sys
import time
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime

from . import judge
from .entry import VERDICTS, WHEN, Entry


@dataclass
class Result:
    system: str  # «Windows», «macOS» o «Linux»
    started: str = ""
    seconds: float = 0.0
    first_scan: bool = False
    entries: list[Entry] = field(default_factory=list)
    gone: list[dict] = field(default_factory=list)  # lo que estaba y ya no

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> Result:
        entries = [_entry_from(e) for e in data.get("entries", [])]
        names = {f.name for f in fields(cls)}
        return cls(**{k: (entries if k == "entries" else v) for k, v in data.items() if k in names})


def _entry_from(data: dict) -> Entry:
    names = {f.name for f in fields(Entry)}
    return Entry(**{k: v for k, v in data.items() if k in names})


def current_system() -> str:
    return {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")


def _raw_scan(system: str) -> list[Entry]:  # pragma: no cover - usa el sistema de verdad
    if system == "Windows":
        from . import scan_windows

        return scan_windows.scan()
    if system == "macOS":
        from . import scan_macos

        return scan_macos.scan()
    from . import scan_linux

    return scan_linux.scan()


def classify(entries: list[Entry]) -> list[Entry]:
    """Pasa cada entrada por el juez y las ordena: primero lo que hay que revisar, y dentro
    de cada grupo por cuándo arranca."""
    seen_ids: dict[str, int] = {}
    unique = []
    for entry in entries:
        if not (entry.path or entry.command or entry.inline):
            continue
        if entry.id in seen_ids:  # el mismo sitio dos veces (p. ej. 64 y 32 bits): una sola
            continue
        seen_ids[entry.id] = 1
        unique.append(judge.judge(entry))
    verdict_order = {v: i for i, v in enumerate(VERDICTS)}
    when_order = {w: i for i, w in enumerate(WHEN)}
    unique.sort(key=lambda e: (verdict_order.get(e.verdict, 99), when_order.get(e.when, 99), e.display_name().lower()))
    return unique


def scan(system: str | None = None, history=None, raw: list[Entry] | None = None) -> Result:
    """Una pasada. Con `raw` se le pasan las entradas ya recogidas (para la demo y las
    pruebas); si no, las recoge del sistema de verdad."""
    system = system or current_system()
    started, clock = datetime.now(), time.monotonic()
    entries = classify(raw if raw is not None else _raw_scan(system))
    result = Result(system=system, started=started.isoformat(timespec="seconds"), entries=entries)
    if history is not None:
        result.gone = history.record(entries, started)
        result.first_scan = history.is_first_scan()
        history.save()
    result.seconds = round(time.monotonic() - clock, 1)
    return result


def counts_by(entries: list[Entry], attr: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for entry in entries:
        out[getattr(entry, attr)] = out.get(getattr(entry, attr), 0) + 1
    return out
