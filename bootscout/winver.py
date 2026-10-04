"""Info de versión y firma digital de un ejecutable de Windows.

Todo esto solo corre en Windows (usa ctypes contra la API de Windows y, para la firma,
PowerShell). El módulo se puede importar en cualquier sitio; cada función devuelve algo
vacío si no está en Windows o si falla.
"""

from __future__ import annotations

import subprocess
import sys

# Los campos de la info de versión que interesan, con el nombre que boot-scout usa.
_FIELDS = {
    "CompanyName": "company",
    "ProductName": "product",
    "FileDescription": "description",
    "ProductVersion": "version",
    "FileVersion": "file_version",
}


def version_info(path: str) -> dict:  # pragma: no cover - solo Windows
    """Empresa, producto, descripción y versión que el .exe lleva dentro."""
    if sys.platform != "win32":
        return {}
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return {}
    try:
        version = ctypes.windll.version
        size = version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return {}
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(path, 0, size, buffer):
            return {}
        # El idioma en el que vienen los textos (puede haber varios; se coge el primero).
        lang = ctypes.c_void_p()
        length = wintypes.UINT()
        if (
            not version.VerQueryValueW(buffer, "\\VarFileInfo\\Translation", ctypes.byref(lang), ctypes.byref(length))
            or not length.value
        ):
            codepages = ["040904b0", "040904E4", "000004b0"]
        else:
            pair = ctypes.cast(lang, ctypes.POINTER(wintypes.WORD * 2)).contents
            codepages = [f"{pair[0]:04x}{pair[1]:04x}"]
        info = {}
        for codepage in codepages:
            for field, key in _FIELDS.items():
                value = ctypes.c_wchar_p()
                n = wintypes.UINT()
                query = f"\\StringFileInfo\\{codepage}\\{field}"
                if version.VerQueryValueW(buffer, query, ctypes.byref(value), ctypes.byref(n)) and value.value:
                    info.setdefault(key, value.value.strip())
            if info:
                break
        return info
    except (OSError, ctypes.ArgumentError, ValueError):
        return {}


def signature(path: str) -> tuple[str, str]:  # pragma: no cover - solo Windows
    """(estado, firmante). estado: «válida», «no válida», «sin firma» o «» si no se ha
    podido mirar. Usa PowerShell (Get-AuthenticodeSignature), que no necesita permisos."""
    if sys.platform != "win32":
        return "", ""
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        f"$s=Get-AuthenticodeSignature -LiteralPath '{path}';"
        "if($s){$n='';if($s.SignerCertificate){$n=$s.SignerCertificate.GetNameInfo(0,$false)};"
        "Write-Output ($s.Status.ToString()+'|'+$n)}"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "", ""
    if "|" not in out:
        return "", ""
    status, _, signer = out.partition("|")
    status = status.strip().lower()
    mapping = {"valid": "válida", "notsigned": "sin firma", "hashmismatch": "no válida", "notrusted": "no válida"}
    return mapping.get(status, "no válida" if status else ""), _clean_signer(signer.strip())


def _clean_signer(name: str) -> str:
    # El nombre del firmante a veces viene como «CN=Microsoft Corporation, O=…»: solo el CN.
    if name.upper().startswith("CN="):
        name = name[3:].split(",")[0]
    return name.strip().strip('"')
