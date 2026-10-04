"""Cómo se cuenta lo encontrado: agrupar, resumir y la ficha de cada entrada.

Lo usan la terminal y la ventana, así que aquí no se pinta nada: solo se decide qué decir.
"""

from __future__ import annotations

from datetime import datetime

from .entry import BROKEN, CHECK, KEEP, OPTIONAL, REMOVABLE, UNKNOWN, VERDICTS, WHEN, Entry
from .scan import Result

# Un símbolo para cada veredicto (y un color, que pone quien pinta).
VERDICT_MARK = {CHECK: "!", BROKEN: "×", REMOVABLE: "·", OPTIONAL: "·", UNKNOWN: "?", KEEP: " "}
VERDICT_COLOR = {CHECK: "red", BROKEN: "yellow", REMOVABLE: "yellow", OPTIONAL: "gray", UNKNOWN: "gray", KEEP: "green"}


def plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def ago(iso: str, now: datetime | None = None) -> str:
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    seconds = ((now or datetime.now()) - then).total_seconds()
    if seconds < 3600:
        return "hace un rato"
    if seconds < 86400:
        return f"hace {plural(int(seconds // 3600), 'hora', 'horas')}"
    days = int(seconds // 86400)
    if days < 60:
        return "ayer" if days == 1 else f"hace {days} días"
    return f"el {then:%d/%m/%Y}"


def headline(result: Result) -> str:
    parts = [f"{result.system}", plural(len(result.entries), "cosa arranca sola", "cosas arrancan solas")]
    review = sum(1 for e in result.entries if e.verdict in (CHECK, BROKEN))
    if review:
        parts.append(plural(review, "para revisar", "para revisar"))
    if result.seconds:
        parts.append(f"{result.seconds:.1f} s".replace(".", ","))
    return " · ".join(parts)


def summary(result: Result) -> str:
    """«8 déjalo, 5 como quieras, 2 revísalo…»."""
    counts: dict[str, int] = {}
    for entry in result.entries:
        counts[entry.verdict] = counts.get(entry.verdict, 0) + 1
    parts = [f"{counts[v]} {v.lower()}" for v in VERDICTS if counts.get(v)]
    return ", ".join(parts)


def group_by(result: Result, axis: str) -> list[tuple[str, list[Entry]]]:
    """Agrupa las entradas por un eje: «verdict», «when» o «kind». El orden de los grupos
    es el natural de cada eje."""
    order = {"verdict": VERDICTS, "when": WHEN}.get(axis)
    groups: dict[str, list[Entry]] = {}
    for entry in result.entries:
        groups.setdefault(getattr(entry, axis), []).append(entry)
    if order:
        keys = [k for k in order if k in groups]
    else:
        keys = sorted(groups, key=lambda k: -len(groups[k]))
    return [(k, groups[k]) for k in keys]


def details(entry: Entry) -> list[tuple[str, str]]:
    """La ficha completa: (etiqueta, valor), solo de lo que se sabe."""
    rows: list[tuple[str, str]] = []

    def add(label, value):
        if value:
            rows.append((label, value))

    add("Qué es", entry.what or (entry.known if entry.known else ""))
    add("Tipo", entry.kind)
    add("Qué hacer", entry.verdict if entry.verdict != UNKNOWN else "no se sabe, míralo tú")
    add("Cuándo arranca", entry.when + (f" — {entry.trigger}" if entry.trigger else ""))
    add("Configurado en", entry.where)
    add("Sitio exacto", entry.location)
    add("Para", "todo el equipo" if entry.scope == "sistema" else "tu usuario")
    if not entry.enabled:
        add("Estado", "desactivado (no arranca)")
    add("Programa", entry.path)
    if entry.args:
        add("Con", entry.args)
    if entry.inline:
        extra = " (venía escondido en Base64)" if entry.encoded else ""
        add("Código que ejecuta", entry.inline[:300] + extra)
    if entry.exists is False:
        add("Archivo", "ya no existe")
    add("Fabricante", entry.company)
    add("Producto", entry.product + (f" {entry.version}" if entry.version else ""))
    if entry.description and entry.description != entry.product:
        add("Descripción", entry.description)
    if entry.signature:
        signer = f" ({entry.signer})" if entry.signer else ""
        add("Firma digital", entry.signature + signer)
    add("Paquete", entry.package)
    if entry.reasons:
        add("Por qué lo digo", " ".join(entry.reasons))
    if entry.tip:
        add("Consejo", entry.tip)
    if entry.hint:
        add("Cómo tocarlo", entry.hint)
    if entry.first_seen:
        add("Visto por primera vez", _date(entry.first_seen))
    return rows


def can_toggle(entry: Entry) -> bool:
    """Si boot-scout puede activarlo/desactivarlo él mismo (solo cosas de tu usuario)."""
    return bool(entry.toggle)


def _date(iso: str) -> str:
    try:
        return f"{datetime.fromisoformat(iso):%d/%m/%Y %H:%M}"
    except ValueError:
        return iso
