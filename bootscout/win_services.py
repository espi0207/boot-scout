"""Los servicios y controladores de Windows que arrancan solos.

Los servicios viven en `HKLM\\SYSTEM\\CurrentControlSet\\Services`. Cada uno dice cuándo
arranca (`Start`: 0-1 el sistema muy pronto, 2 automático, 3 a mano, 4 desactivado), qué
es (`Type`: servicio o controlador) y qué ejecuta (`ImagePath`). boot-scout enseña los de
arranque automático (2), que son los que se ponen en marcha solos con el equipo.
"""

from __future__ import annotations

from . import cmdline
from .entry import AT_BOOT, Entry
from .winreg_source import Source

SERVICES = r"HKLM\System\CurrentControlSet\Services"
_SEARCH = [r"C:\Windows\System32", r"C:\Windows"]

START = {0: "arranque (muy pronto)", 1: "arranque del sistema", 2: "automático", 3: "manual", 4: "desactivado"}
# Type: 1/2/8 = controlador (driver); 16/32 = servicio normal.
DRIVER_TYPES = {1, 2, 8}


def service_entries(source: Source, include_drivers: bool = False) -> list[Entry]:
    entries = []
    for name in source.subkeys(SERVICES):
        key = f"{SERVICES}\\{name}"
        start = _as_int(source.value(key, "Start"))
        if start not in (0, 1, 2):  # solo lo que arranca solo
            continue
        service_type = _as_int(source.value(key, "Type")) or 0
        is_driver = service_type in DRIVER_TYPES
        if is_driver and not include_drivers:
            continue
        image = source.value(key, "ImagePath")
        display = source.value(key, "DisplayName") or name
        description = source.value(key, "Description") or ""
        delayed = _as_int(source.value(key, "DelayedAutostart")) == 1
        account = source.value(key, "ObjectName") or ""
        command = _clean_image(str(image)) if image else ""
        target = cmdline.Target("", "", "")
        if command:
            target = cmdline.windows_target(command, source.env, source.is_file, _SEARCH)
        when_detail = START.get(start, "automático")
        if start == 2 and delayed:
            when_detail = "automático (con retraso)"
        display = str(display)
        if display.startswith("@"):  # «@%SystemRoot%\...,-100»: nombre en un recurso, no se resuelve
            display = name
        entry = Entry(
            id=f"win:service:{name}",
            name=display,
            when=AT_BOOT,
            where="Servicio de Windows" + (" (controlador)" if is_driver else ""),
            location=key,
            command=command,
            path=target.file,
            args=target.args,
            scope="sistema",
            enabled=start != 4,
            trigger=when_detail,
            description=str(description) if not str(description).startswith("@") else "",
            extra={"service": name, "account": str(account), "driver": is_driver, "service_name": name},
            toggle={},  # cambiar servicios pide administrador: se dice cómo, no se hace desde aquí
            hint=f'Para pararlo o cambiar su arranque: Servicios (services.msc) o «sc config "{name}" '
            "start= demand» como administrador. No toques los que no conozcas.",
        )
        _facts(entry, source)
        entries.append(entry)
    return entries


def _facts(entry: Entry, source: Source) -> None:
    if not entry.path:
        return
    entry.exists = source.is_file(entry.path)
    if not entry.exists:
        return
    info = source.version_info(entry.path)
    entry.company = entry.company or info.get("company", "")
    entry.product = info.get("product", "")
    if not entry.description:
        entry.description = info.get("description", "")
    entry.version = info.get("version", "") or info.get("file_version", "")
    entry.signature, entry.signer = source.signature(entry.path)


def _clean_image(image: str) -> str:
    """ImagePath puede traer «\\??\\C:\\...», «system32\\svchost.exe -k netsvcs» o una ruta
    relativa a System32 (los controladores)."""
    image = image.strip()
    for prefix in ("\\??\\", "\\\\?\\"):
        if image.startswith(prefix):
            image = image[len(prefix) :]
    if image and not image[1:3] == ":\\" and not image.startswith(("\\", '"')):
        # Ruta relativa: los controladores van en System32\drivers.
        if image.lower().startswith("system32") or image.lower().startswith("syswow64"):
            image = f"C:\\Windows\\{image}"
        elif "\\" in image:
            image = f"C:\\Windows\\System32\\{image}"
    return image


def _as_int(value) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return None
