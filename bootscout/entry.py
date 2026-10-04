"""Una cosa que se pone en marcha sola, con todo lo que se sabe de ella.

Cada sistema la encuentra en sitios distintos (el registro de Windows, un .plist de macOS,
un .desktop de Linux…), pero al final todas son lo mismo: algo que arranca sin que lo
abras tú, en algún momento, desde algún sitio.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Cuándo arranca. El orden es el de la lista.
AT_BOOT = "Al encender"
AT_LOGON = "Al iniciar sesión"
SCHEDULED = "Programado"
ON_DEMAND = "Cuando lo pide algo"
INSIDE = "Dentro de otros programas"
SYSTEM = "Configuración del sistema"
WHEN = [AT_LOGON, AT_BOOT, SCHEDULED, ON_DEMAND, INSIDE, SYSTEM]

# Qué hacer con ello.
KEEP = "Déjalo"
OPTIONAL = "Como quieras"
REMOVABLE = "Puedes quitarlo"
CHECK = "Revísalo"
BROKEN = "Roto"
UNKNOWN = "Sin datos"
VERDICTS = [CHECK, BROKEN, REMOVABLE, OPTIONAL, UNKNOWN, KEEP]

# Qué es.
KIND_UPDATER = "Actualizador"
KIND_HARDWARE = "Hardware y controladores"
KIND_SECURITY = "Antivirus y seguridad"
KIND_CLOUD = "Nube y copias"
KIND_CHAT = "Mensajería y reuniones"
KIND_MEDIA = "Música y vídeo"
KIND_GAMES = "Juegos"
KIND_REMOTE = "Control remoto"
KIND_TOOLS = "Utilidades"
KIND_SYSTEM = "Parte del sistema"
KIND_DEV = "Programación"
KIND_BROWSER = "Navegador"
KIND_OFFICE = "Ofimática"
KIND_VPN = "VPN y red"
KIND_OTHER = "Otros"


@dataclass
class Entry:
    id: str  # estable de una vez a otra: «win:run:HKCU:Spotify»
    name: str  # con el que está apuntado
    when: str  # cuándo arranca (AT_LOGON, AT_BOOT…)
    where: str  # el mecanismo, en cristiano: «Registro: Run (tu usuario)»
    location: str = ""  # dónde exactamente: la clave del registro, la ruta del archivo
    command: str = ""  # la orden entera, tal cual
    path: str = ""  # el archivo que se ejecuta de verdad (el .exe, el script, la DLL)
    args: str = ""
    inline: str = ""  # el código, si va dentro de la orden (powershell -Command, mshta javascript:…)
    encoded: bool = False  # y si además iba escondido (powershell -EncodedCommand en Base64)
    enabled: bool = True
    scope: str = "usuario"  # «usuario» (solo el tuyo) o «sistema» (todos)
    toggle: dict = field(default_factory=dict)  # cómo activarlo y desactivarlo desde aquí
    hint: str = ""  # si no se puede desde aquí, dónde se hace
    trigger: str = ""  # tareas y temporizadores: cuándo exactamente («cada día a las 10:00»)
    # Del propio archivo
    exists: bool | None = None
    company: str = ""
    product: str = ""
    description: str = ""
    version: str = ""
    signer: str = ""
    signature: str = ""  # «válida», «sin firma», «no válida» o vacío si no se ha podido mirar
    package: str = ""  # Linux: el paquete al que pertenece
    # Lo que decide boot-scout
    known: str = ""  # el nombre de lo que es, si está en la lista
    what: str = ""  # qué es, en cristiano
    kind: str = ""  # tipo (KIND_*)
    verdict: str = UNKNOWN
    reasons: list[str] = field(default_factory=list)
    tip: str = ""
    is_new: bool = False
    first_seen: str = ""
    extra: dict = field(default_factory=dict)  # lo propio de cada sitio (autor de la tarea, estado del servicio…)

    def display_name(self) -> str:
        return self.known or self.product or self.name

    def to_dict(self) -> dict:
        return asdict(self)
