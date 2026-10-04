"""Leer accesos directos de Windows (.lnk) sin Windows: a qué programa apuntan.

La carpeta Inicio está llena de accesos directos. Su formato es público (MS-SHLLINK) y
dentro va la ruta del programa, sus argumentos y la carpeta de trabajo. Aquí se lee lo
justo, sin fiarse de nada: un .lnk puede venir roto o hecho a mala idea.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER_SIZE = 0x4C
CLSID = bytes.fromhex("0114020000000000c000000000000046")

HAS_ID_LIST, HAS_LINK_INFO, HAS_NAME, HAS_RELATIVE_PATH = 0x1, 0x2, 0x4, 0x8
HAS_WORKING_DIR, HAS_ARGUMENTS, HAS_ICON, IS_UNICODE = 0x10, 0x20, 0x40, 0x80
ENVIRONMENT_BLOCK = 0xA0000001


class BadLink(ValueError):
    pass


@dataclass
class Link:
    target: str = ""  # la ruta del programa
    arguments: str = ""
    working_dir: str = ""
    description: str = ""
    relative_path: str = ""
    show: str = ""  # «minimizada», «maximizada» o vacío (normal)


def _cstring(data: bytes, offset: int, wide: bool = False) -> str:
    if wide:
        end = offset
        while end + 1 < len(data) and data[end : end + 2] != b"\x00\x00":
            end += 2
        return data[offset:end].decode("utf-16-le", errors="replace")
    end = data.find(b"\x00", offset)
    return data[offset : end if end >= 0 else len(data)].decode("cp1252", errors="replace")


def parse(data: bytes) -> Link:
    if len(data) < HEADER_SIZE or struct.unpack("<I", data[:4])[0] != HEADER_SIZE or data[4:20] != CLSID:
        raise BadLink("no es un acceso directo de Windows")
    flags = struct.unpack("<I", data[20:24])[0]
    show_command = struct.unpack("<I", data[60:64])[0]
    link = Link(show={3: "maximizada", 7: "minimizada"}.get(show_command, ""))
    pos = HEADER_SIZE
    try:
        if flags & HAS_ID_LIST:
            pos += 2 + struct.unpack("<H", data[pos : pos + 2])[0]
        if flags & HAS_LINK_INFO:
            info_size, header_size, info_flags = struct.unpack("<III", data[pos : pos + 12])
            base_offset, _net_offset, suffix_offset = struct.unpack("<III", data[pos + 16 : pos + 28])
            info = data[pos : pos + info_size]
            if info_flags & 1:  # tiene ruta local
                if header_size >= 0x24:
                    wide_base, wide_suffix = struct.unpack("<II", data[pos + 28 : pos + 36])
                    path = _cstring(info, wide_base, wide=True) + _cstring(info, wide_suffix, wide=True)
                else:
                    path = _cstring(info, base_offset) + _cstring(info, suffix_offset)
                link.target = path
            pos += info_size
        wide = bool(flags & IS_UNICODE)
        for flag, name in (
            (HAS_NAME, "description"),
            (HAS_RELATIVE_PATH, "relative_path"),
            (HAS_WORKING_DIR, "working_dir"),
            (HAS_ARGUMENTS, "arguments"),
            (HAS_ICON, None),
        ):
            if not flags & flag:
                continue
            count = struct.unpack("<H", data[pos : pos + 2])[0]
            size = count * 2 if wide else count
            raw = data[pos + 2 : pos + 2 + size]
            if len(raw) < size:
                raise BadLink("texto cortado")
            pos += 2 + size
            if name:
                setattr(link, name, raw.decode("utf-16-le" if wide else "cp1252", errors="replace"))
        # Bloques extra: el de variables de entorno lleva la ruta con %VARIABLES% sin expandir,
        # que es la buena cuando el programa está en el perfil del usuario.
        for _ in range(64):
            if pos + 8 > len(data):
                break
            size, signature = struct.unpack("<II", data[pos : pos + 8])
            if size < 4:
                break
            if signature == ENVIRONMENT_BLOCK and size >= 0x314:
                unicode_target = _cstring(data[pos + 8 + 260 : pos + size], 0, wide=True)
                ansi_target = _cstring(data[pos + 8 : pos + 8 + 260], 0)
                link.target = link.target or unicode_target or ansi_target
            pos += size
    except struct.error as exc:
        raise BadLink("acceso directo cortado") from exc
    return link


def build(target: str, arguments: str = "", working_dir: str = "", description: str = "") -> bytes:
    """Un acceso directo mínimo (para las pruebas): ruta local, textos en UTF-16."""
    flags = HAS_LINK_INFO | IS_UNICODE
    strings = b""
    for flag, text in ((HAS_NAME, description), (HAS_WORKING_DIR, working_dir), (HAS_ARGUMENTS, arguments)):
        if text:
            flags |= flag
            strings += struct.pack("<H", len(text)) + text.encode("utf-16-le")
    header = struct.pack("<I", HEADER_SIZE) + CLSID + struct.pack("<II", flags, 0x20) + b"\x00" * 24
    header += struct.pack("<IiIH", 0, 0, 1, 0) + b"\x00" * 10
    ansi = target.encode("cp1252", errors="replace") + b"\x00"
    wide_path = target.encode("utf-16-le") + b"\x00\x00"
    header_size = 0x24  # con las rutas también en UTF-16
    base_offset = header_size
    suffix_offset = base_offset + len(ansi)
    wide_base = suffix_offset + 1
    wide_suffix = wide_base + len(wide_path)
    body = ansi + b"\x00" + wide_path + b"\x00\x00"
    info_size = header_size + len(body)
    info = (
        struct.pack("<IIIIIIIII", info_size, header_size, 1, 0, base_offset, 0, suffix_offset, wide_base, wide_suffix)
        + body
    )
    return header + info + strings + struct.pack("<I", 0)
