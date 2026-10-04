"""De dónde salen los datos de Windows, detrás de una interfaz.

En Windows de verdad es el registro (`winreg`) y el disco. En las pruebas, un registro y un
disco de mentira. Así toda la lógica de `scan_windows.py` se prueba en Linux sin Windows.
"""

from __future__ import annotations

import ntpath
from dataclasses import dataclass, field


@dataclass
class RegValue:
    name: str
    data: object
    type: int = 1  # REG_SZ


@dataclass
class RegKey:
    values: dict[str, object] = field(default_factory=dict)  # nombre → dato (strings casi siempre)
    subkeys: dict[str, RegKey] = field(default_factory=dict)


class Source:
    """Lo que scan_windows necesita del sistema: leer el registro, listar y leer archivos,
    y la info de versión y firma de un .exe. Esta es la de mentira, para pruebas."""

    def __init__(
        self,
        registry: dict[str, RegKey] | None = None,
        files: dict[str, bytes] | None = None,
        env: dict[str, str] | None = None,
        version: dict | None = None,
        signatures: dict | None = None,
    ):
        self.registry = registry or {}  # «HKLM\SOFTWARE\...\Run» → RegKey
        self.files = files or {}  # ruta → contenido (se busca sin distinguir mayúsculas)
        # Mapa de la ruta en minúsculas a la ruta tal cual, para no perder el caso del nombre.
        self._by_lower = {_norm_file(p): p for p in self.files}
        self.env = env or {}
        self._version = version or {}  # ruta → dict con company, product…
        self._signatures = signatures or {}  # ruta → (estado, firmante)

    # Registro
    def open_key(self, path: str) -> RegKey | None:
        norm = _norm_key(path)
        if norm in self.registry:
            return self.registry[norm]
        # Si no está como clave de primer nivel, se baja por las subclaves anidadas desde la
        # raíz registrada más larga que encaje (así el árbol de Services funciona).
        lower = norm.lower()
        for root in sorted(self.registry, key=len, reverse=True):
            if lower == root.lower():
                return self.registry[root]
            if lower.startswith(root.lower() + "\\"):
                key = self.registry[root]
                for part in norm[len(root) + 1 :].split("\\"):
                    found = next((k for k in key.subkeys if k.lower() == part.lower()), None)
                    if found is None:
                        return None
                    key = key.subkeys[found]
                return key
        return None

    def values(self, path: str) -> list[tuple[str, object]]:
        key = self.open_key(path)
        return list(key.values.items()) if key else []

    def subkeys(self, path: str) -> list[str]:
        key = self.open_key(path)
        return list(key.subkeys) if key else []

    def value(self, path: str, name: str):
        key = self.open_key(path)
        if not key:
            return None
        return key.values.get(name)

    # Disco
    def exists(self, path: str) -> bool:
        norm = _norm_file(path)
        return norm in self._by_lower or any(k.startswith(norm.rstrip("\\") + "\\") for k in self._by_lower)

    def is_file(self, path: str) -> bool:
        return _norm_file(path) in self._by_lower

    def list_dir(self, path: str) -> list[str]:
        prefix = _norm_file(path).rstrip("\\") + "\\"
        names = set()
        for lower, original in self._by_lower.items():
            if lower.startswith(prefix):
                depth = len(prefix.split("\\"))
                names.add(original.split("\\")[depth - 1])
        return sorted(names)

    def read(self, path: str) -> bytes:
        return self.files.get(self._by_lower.get(_norm_file(path), ""), b"")

    # Metadatos de un ejecutable
    def version_info(self, path: str) -> dict:
        return self._version.get(_norm_file(path), {})

    def signature(self, path: str) -> tuple[str, str]:
        return self._signatures.get(_norm_file(path), ("", ""))


def _norm_key(path: str) -> str:
    return path.replace("/", "\\").rstrip("\\")


def _norm_file(path: str) -> str:
    return ntpath.normpath(path).lower()


# La de verdad, en Windows. Importa winreg y ctypes solo al usarla, para que el módulo se
# pueda importar (y probar) en Linux.

HIVES = {"HKLM": "HKEY_LOCAL_MACHINE", "HKCU": "HKEY_CURRENT_USER", "HKU": "HKEY_USERS", "HKCR": "HKEY_CLASSES_ROOT"}


class RealSource:  # pragma: no cover - solo corre en Windows
    """Lee el registro de verdad (`winreg`) y el disco. `view` es "both" (mira las claves de
    64 y de 32 bits), "64" o "32"."""

    def __init__(self, view: str = "both"):
        import winreg

        self.winreg = winreg
        self.view = view
        self.env = dict(__import__("os").environ)

    def _roots(self, path: str):
        import winreg

        hive_name, _, sub = path.replace("/", "\\").partition("\\")
        hive = getattr(winreg, HIVES.get(hive_name, hive_name), None)
        if hive is None:
            return []
        flags = []
        if self.view in ("both", "64"):
            flags.append(winreg.KEY_WOW64_64KEY)
        if self.view in ("both", "32"):
            flags.append(winreg.KEY_WOW64_32KEY)
        roots = []
        for flag in flags:
            try:
                roots.append(winreg.OpenKey(hive, sub, 0, winreg.KEY_READ | flag))
            except OSError:
                pass
        return roots

    def values(self, path: str) -> list[tuple[str, object]]:
        import winreg

        out, seen = [], set()
        for key in self._roots(path):
            try:
                i = 0
                while True:
                    name, data, _type = winreg.EnumValue(key, i)
                    if name not in seen:
                        seen.add(name)
                        out.append((name, data))
                    i += 1
            except OSError:
                pass
            finally:
                winreg.CloseKey(key)
        return out

    def subkeys(self, path: str) -> list[str]:
        import winreg

        out, seen = [], set()
        for key in self._roots(path):
            try:
                i = 0
                while True:
                    name = winreg.EnumKey(key, i)
                    if name.lower() not in seen:
                        seen.add(name.lower())
                        out.append(name)
                    i += 1
            except OSError:
                pass
            finally:
                winreg.CloseKey(key)
        return out

    def value(self, path: str, name: str):
        import winreg

        for key in self._roots(path):
            try:
                return winreg.QueryValueEx(key, name)[0]
            except OSError:
                pass
            finally:
                winreg.CloseKey(key)
        return None

    def exists(self, path: str) -> bool:
        import os

        return os.path.exists(self._clean(path))

    def is_file(self, path: str) -> bool:
        import os

        return os.path.isfile(self._clean(path))

    def list_dir(self, path: str) -> list[str]:
        import os

        try:
            return os.listdir(self._clean(path))
        except OSError:
            return []

    def read(self, path: str) -> bytes:
        try:
            with open(self._clean(path), "rb") as f:
                return f.read()
        except OSError:
            return b""

    @staticmethod
    def _clean(path: str) -> str:
        path = path.strip().strip('"')
        for prefix in ("\\??\\", "\\\\?\\"):
            if path.startswith(prefix):
                path = path[len(prefix) :]
        return path

    def version_info(self, path: str) -> dict:
        from . import winver

        return winver.version_info(self._clean(path))

    def signature(self, path: str) -> tuple[str, str]:
        from . import winver

        return winver.signature(self._clean(path))
