"""Qué es cada cosa y qué hacer con ella.

Primero se busca en la lista de conocidos (known.py). Si no está, se decide con lo que se
sabe del archivo: si existe, quién lo firma, qué dice de sí mismo y dónde está.
"""

from __future__ import annotations

import re

from . import known
from .entry import (
    BROKEN,
    CHECK,
    KEEP,
    KIND_HARDWARE,
    KIND_OTHER,
    KIND_SECURITY,
    KIND_SYSTEM,
    KIND_UPDATER,
    OPTIONAL,
    UNKNOWN,
    Entry,
)

# Carpetas donde no se instalan los programas normales.
TEMP_DIRS = re.compile(r"\\(temp|tmp)\\|\\appdata\\local\\temp\\|^/tmp/|^/var/tmp/|^/dev/shm/", re.I)

KIND_WORDS = [
    (re.compile(r"updat|upgrad|actualiz", re.I), KIND_UPDATER),
    (
        re.compile(
            r"driver|controlador|audio|sound|graphics|touchpad|bluetooth|printer|nvidia|intel|amd|realtek|"
            r"synaptics|logitech",
            re.I,
        ),
        KIND_HARDWARE,
    ),
    (re.compile(r"antivirus|security|defender|firewall|protect", re.I), KIND_SECURITY),
]
HARDWARE_MAKERS = re.compile(
    r"realtek|nvidia|intel|advanced micro devices|amd\b|synaptics|elan|dolby|waves|"
    r"conexant|qualcomm|broadcom|logitech|razer|corsair|steelseries|asus|lenovo|hp inc|"
    r"hewlett|dell|acer|msi|micro-star|samsung|canon|epson|brother",
    re.I,
)


def judge(entry: Entry) -> Entry:
    texts = [entry.command, entry.path, entry.name, entry.location if "\\" not in entry.location else ""]
    found = known.match(*texts)
    reasons: list[str] = []

    if entry.exists is False and entry.path:
        entry.verdict, entry.kind = BROKEN, entry.kind or KIND_OTHER
        entry.reasons = [
            "El archivo que tendría que abrir ya no existe: seguramente desinstalaste el programa y se quedó apuntado."
        ]
        entry.tip = "No hace nada: puedes desactivarlo sin miedo."
        if found:
            entry.known, entry.what = found.name, found.what
        return entry

    if found:
        entry.known, entry.what, entry.kind, entry.verdict, entry.tip = (
            found.name,
            found.what,
            found.kind,
            found.verdict,
            found.tip,
        )
        reasons.append(f"Es {found.name}.")
    elif entry.extra.get("unusual"):
        # Un ajuste del sistema que no tiene su valor de siempre (lo decide quien lo encuentra).
        entry.verdict, entry.kind = CHECK, KIND_SYSTEM
        reasons.append(entry.extra["unusual"])
    elif entry.extra.get("default"):
        entry.verdict, entry.kind = KEEP, KIND_SYSTEM
        entry.what = entry.what or "Un ajuste de siempre del sistema."
    else:
        entry.kind = entry.kind or _kind(entry)
        if entry.signature == "válida" and entry.signer:
            entry.verdict = OPTIONAL
            reasons.append(f"No lo conozco, pero lleva la firma digital de {entry.signer}.")
        elif entry.package:
            entry.verdict = OPTIONAL if entry.scope == "usuario" else KEEP
            reasons.append(f"Viene del paquete «{entry.package}» del sistema.")
        elif entry.signature == "sin firma":
            entry.verdict = CHECK
            reasons.append("No lo conozco y no lleva firma digital, así que no se sabe de quién es.")
        else:
            entry.verdict = UNKNOWN
            reasons.append("No lo conozco.")
        if entry.company:
            reasons.append(
                f"El archivo dice que es de {entry.company}"
                + (f" («{entry.description}»)." if entry.description else ".")
            )

    # Lo que pesa más que la lista: una firma rota o una carpeta temporal.
    if entry.signature == "no válida":
        entry.verdict = CHECK
        reasons.append(
            "Su firma digital no es válida: el archivo se ha modificado después de firmarlo, o la firma es de otro."
        )
    if entry.path and TEMP_DIRS.search(entry.path):
        entry.verdict = CHECK
        reasons.append("Está en una carpeta temporal, y ahí no se instalan los programas.")
    entry.reasons = reasons
    return entry


def _kind(entry: Entry) -> str:
    text = " ".join([entry.name, entry.description, entry.product, entry.path])
    for pattern, kind in KIND_WORDS:
        if pattern.search(text):
            return kind
    if entry.company and HARDWARE_MAKERS.search(entry.company):
        return KIND_HARDWARE
    return KIND_OTHER
