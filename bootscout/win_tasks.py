"""Las tareas programadas de Windows (el Programador de tareas).

Cada tarea es un archivo XML en `C:\\Windows\\System32\\Tasks` (en carpetas, como
`\\Microsoft\\Windows\\...`). El XML dice cuándo se dispara (al arrancar, al iniciar
sesión, a una hora, cada x tiempo…), qué ejecuta y si está activada. boot-scout enseña las
que arrancan algo solas; se saltan las de la propia Windows a no ser que estén apagadas o
apunten a algo raro, que serían demasiadas y casi todas de fábrica.
"""

from __future__ import annotations

import ntpath
import re
import xml.etree.ElementTree as ET

from . import cmdline
from .entry import AT_BOOT, AT_LOGON, ON_DEMAND, SCHEDULED, Entry
from .winreg_source import Source

TASKS_ROOT = r"C:\Windows\System32\Tasks"
_NS = "{http://schemas.microsoft.com/windows/2004/02/mit/task}"


def _text(element, tag: str, default: str = "") -> str:
    found = element.find(f"{_NS}{tag}")
    return found.text.strip() if found is not None and found.text else default


def _parse_xml(xml_bytes: bytes):
    """Los XML de tareas se guardan en UTF-16; algunos exportados, en UTF-8. Se prueban los
    dos, quitando la declaración de codificación para que no choque con los bytes."""
    try:
        return ET.fromstring(xml_bytes)
    except ET.ParseError:
        pass
    for encoding in ("utf-16", "utf-8", "utf-16-le"):
        try:
            text = xml_bytes.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
        text = re.sub(r"<\?xml[^>]*\?>", "", text, count=1).lstrip("﻿ \n\r\t")
        try:
            return ET.fromstring(text)
        except ET.ParseError:
            continue
    return None


def parse_task(xml_bytes: bytes) -> dict | None:
    """Lo que interesa de un XML de tarea: disparadores, acciones, estado, autor."""
    root = _parse_xml(xml_bytes)
    if root is None or not root.tag.endswith("Task"):
        return None
    settings = root.find(f"{_NS}Settings")
    enabled = True
    if settings is not None:
        enabled = _text(settings, "Enabled", "true").lower() != "false"
    reg = root.find(f"{_NS}RegistrationInfo")
    author = _text(reg, "Author") if reg is not None else ""
    description = _text(reg, "Description") if reg is not None else ""

    triggers = []
    trig_el = root.find(f"{_NS}Triggers")
    if trig_el is not None:
        for child in trig_el:
            tag = child.tag[len(_NS) :] if child.tag.startswith(_NS) else child.tag
            if _text(child, "Enabled", "true").lower() == "false":
                continue
            triggers.append(_trigger(tag, child))

    actions = []
    act_el = root.find(f"{_NS}Actions")
    if act_el is not None:
        for exec_el in act_el.findall(f"{_NS}Exec"):
            command = _text(exec_el, "Command")
            args = _text(exec_el, "Arguments")
            if command:
                actions.append((command, args))
    return {"enabled": enabled, "author": author, "description": description, "triggers": triggers, "actions": actions}


def _trigger(tag: str, element) -> tuple[str, str]:
    """(cuándo arranca en términos de boot-scout, detalle legible)."""
    if tag == "BootTrigger":
        return AT_BOOT, "al arrancar el equipo"
    if tag == "LogonTrigger":
        user = _text(element, "UserId")
        return AT_LOGON, "al iniciar sesión" + (f" ({user})" if user else "")
    if tag in ("TimeTrigger", "CalendarTrigger"):
        start = _text(element, "StartBoundary")
        return SCHEDULED, "a una hora" + (f" (desde {start[:16].replace('T', ' ')})" if start else "")
    if tag == "RegistrationTrigger":
        return ON_DEMAND, "al registrarse la tarea"
    if tag in ("SessionStateChangeTrigger", "EventTrigger", "IdleTrigger"):
        detail = {
            "IdleTrigger": "cuando el equipo está sin usar",
            "EventTrigger": "cuando pasa cierto evento",
            "SessionStateChangeTrigger": "al bloquear/desbloquear o conectar",
        }
        return ON_DEMAND, detail.get(tag, "cuando algo lo pide")
    return ON_DEMAND, "cuando algo lo pide"


def task_entries(source: Source) -> list[Entry]:
    entries = []
    for path in _walk(source, TASKS_ROOT):
        task = parse_task(source.read(path))
        if not task or not task["actions"]:
            continue
        name = path[len(TASKS_ROOT) :].lstrip("\\")  # «Microsoft\Windows\...\Tarea»
        when, detail = task["triggers"][0] if task["triggers"] else (ON_DEMAND, "cuando algo lo pide")
        if when == ON_DEMAND and not task["triggers"]:
            continue  # sin disparador: no arranca sola
        for command, args in task["actions"]:
            full = f'"{command}" {args}'.strip()
            target = cmdline.windows_target(full, source.env, source.is_file, [r"C:\Windows\System32", r"C:\Windows"])
            is_ms = name.lower().startswith("microsoft\\")
            entry = Entry(
                id=f"win:task:{name}",
                name=ntpath.basename(name) or name,
                when=when,
                where="Tarea programada",
                location=path,
                command=full,
                path=target.file,
                args=target.args,
                inline=target.inline,
                encoded=target.encoded,
                scope="sistema",
                enabled=task["enabled"],
                trigger=detail,
                description=task["description"],
                extra={"author": task["author"], "task_path": "\\" + name, "microsoft": is_ms},
                hint="Para verla o cambiarla: Programador de tareas (taskschd.msc).",
            )
            _facts(entry, source)
            entries.append(entry)
    return entries


def _walk(source: Source, root: str, depth: int = 0) -> list[str]:
    """Recorre el árbol de Tasks. Como los archivos no tienen extensión, se distingue
    carpeta de tarea por si tiene hijos."""
    if depth > 8:
        return []
    found = []
    for name in source.list_dir(root):
        full = ntpath.join(root, name)
        children = source.list_dir(full)
        if children:
            found += _walk(source, full, depth + 1)
        elif source.is_file(full):
            found.append(full)
    return found


def _facts(entry: Entry, source: Source) -> None:
    if not entry.path:
        return
    entry.exists = source.is_file(entry.path)
    if not entry.exists:
        return
    info = source.version_info(entry.path)
    entry.company = info.get("company", "")
    entry.product = info.get("product", "")
    if not entry.description:
        entry.description = info.get("description", "")
    entry.version = info.get("version", "") or info.get("file_version", "")
    entry.signature, entry.signer = source.signature(entry.path)
