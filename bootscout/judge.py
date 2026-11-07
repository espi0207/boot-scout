"""Qué es cada cosa y qué hacer con ella.

Primero se busca en la lista de conocidos (known.py). Si no está, se decide con lo que se
sabe del archivo: si existe, quién lo firma, qué dice de sí mismo, dónde está y, en Linux,
de qué paquete viene.
"""

from __future__ import annotations

import re

from . import known
from .entry import (
    BROKEN,
    CHECK,
    KEEP,
    KIND_BROWSER,
    KIND_CHAT,
    KIND_CLOUD,
    KIND_DEV,
    KIND_GAMES,
    KIND_HARDWARE,
    KIND_MEDIA,
    KIND_OFFICE,
    KIND_OTHER,
    KIND_REMOTE,
    KIND_SECURITY,
    KIND_SYSTEM,
    KIND_TOOLS,
    KIND_UPDATER,
    KIND_VPN,
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
    (re.compile(r"\b(vpn|wireguard|openvpn|tailscale|zerotier|nordvpn|protonvpn|mullvad|expressvpn|"
                r"forticlient|globalprotect|anyconnect)", re.I), KIND_VPN),
    (re.compile(r"\b(anydesk|teamviewer|rustdesk|parsec|splashtop|vnc|remote ?desktop|escritorio remoto|"
                r"remote ?utilities|supremo)", re.I), KIND_REMOTE),
    (re.compile(r"\b(discord|whatsapp|telegram|signal|slack|teams|zoom|skype|webex|element|messenger|"
                r"thunderbird|outlook|mail)", re.I), KIND_CHAT),
    (re.compile(r"\b(onedrive|dropbox|google ?drive|pcloud|nextcloud|owncloud|mega(sync)?|icloud|box|"
                r"sync|backup|copia|backblaze|acronis|veeam|syncthing)\b", re.I), KIND_CLOUD),
    (re.compile(r"\b(steam|epic games|battle\.net|riot|ubisoft|uplay|origin|ea app|gog|xbox|playnite|"
                r"overwolf|game|juego)", re.I), KIND_GAMES),
    (re.compile(r"\b(chrome|chromium|firefox|edge|brave|opera|vivaldi|browser|navegador)\b", re.I), KIND_BROWSER),
    (re.compile(r"\b(spotify|itunes|vlc|plex|kodi|jellyfin|music|música|deezer|tidal)\b", re.I), KIND_MEDIA),
]  # fmt: skip

# Trucos de los virus para arrancar solos sin que se note. Un programa normal no los
# necesita, así que pesan más que la firma o que estar en la lista de conocidos.
RED_FLAGS = [
    (
        re.compile(
            r"\b(iwr|invoke-webrequest|irm|invoke-restmethod|wget|curl|downloadstring|downloadfile|net\.webclient|"
            r"start-bitstransfer)\b.*https?://|bitsadmin(\.exe)?\s+/transfer|certutil(\.exe)?\s.*-urlcache",
            re.I,
        ),
        "Descarga algo de internet cada vez que arranca. Un programa instalado no lo necesita: así es como "
        "muchos virus traen el resto de su código.",
    ),
    (
        # solo si lo que llega a la shell viene de internet: cloud-init hace «… | nc -U socket | sh»
        re.compile(r"(curl|wget|https?://)[^\n]*\|\s*(ba|z|da)?sh\b|\biex\b|invoke-expression", re.I),
        "Ejecuta directamente lo que descarga o lo que lleva escrito, sin guardarlo en un archivo.",
    ),
    (
        re.compile(r"-w(indowstyle)?\s+(h|hidden|1)\b|-(ep|exec|executionpolicy)\s+bypass", re.I),
        "Abre PowerShell oculta o saltándose sus protecciones (-WindowStyle Hidden, -ExecutionPolicy Bypass).",
    ),
    (
        re.compile(
            r"\bmshta(\.exe)?\s+[\"']?(https?:|javascript:|vbscript:)|regsvr32(\.exe)?\s.*?/i:\s*https?:|"
            r"rundll32(\.exe)?\s+[\"']?(javascript|vbscript):",
            re.I,
        ),
        "Usa un programa de Windows (mshta, regsvr32 o rundll32) para ejecutar código de internet o escrito en "
        "la propia orden. Es un truco conocido de los virus.",
    ),
    (
        re.compile(r"base64\s+(-d|--decode)|frombase64string", re.I),
        "Descodifica algo escondido en Base64 para ejecutarlo.",
    ),
    (
        re.compile(r"/dev/tcp/|\b(nc|ncat|netcat)\b.*\s-[ec]\s|\bsocat\b.*exec|bash\s+-i\s*>&", re.I),
        "Abre una conexión que da el control de este equipo a otro (una «shell inversa»).",
    ),
]
SCRIPT_IN_APPDATA = re.compile(r"\\appdata\\.*\.(vbs|vbe|js|jse|wsf|hta|ps1|bat|cmd)$", re.I)
ANYONE_CAN_WRITE = re.compile(
    r"^[a-z]:\\users\\public\\|\\\$recycle\.bin\\|^[a-z]:\\programdata\\[^\\]+$|^[a-z]:\\perflogs\\", re.I
)


def red_flags(entry: Entry) -> list[str]:
    """Por qué la orden o el archivo tienen pinta de virus, aunque el programa sea conocido."""
    text = f"{entry.command} {entry.inline}"
    found = [reason for pattern, reason in RED_FLAGS if pattern.search(text)]
    if entry.encoded:
        found.insert(
            0, "La orden iba escondida en Base64 (powershell -EncodedCommand): los programas normales no hacen eso."
        )
    if entry.path and SCRIPT_IN_APPDATA.search(entry.path):
        found.append("Es un script guardado en AppData: los programas de verdad no arrancan así.")
    if entry.path and ANYONE_CAN_WRITE.search(entry.path):
        found.append(
            "Está en una carpeta donde puede escribir cualquiera (Acceso público, la Papelera, la raíz de "
            "ProgramData): ahí no se instala ningún programa."
        )
    return found


HARDWARE_MAKERS = re.compile(
    r"realtek|nvidia|intel|advanced micro devices|amd\b|synaptics|elan|dolby|waves|"
    r"conexant|qualcomm|broadcom|logitech|razer|corsair|steelseries|asus|lenovo|hp inc|"
    r"hewlett|dell|acer|msi|micro-star|samsung|canon|epson|brother",
    re.I,
)

# Linux: la sección del paquete (Debian/Ubuntu) ya dice de qué va.
SECTION_KINDS = {
    "net": KIND_VPN,
    "comm": KIND_VPN,
    "games": KIND_GAMES,
    "sound": KIND_MEDIA,
    "video": KIND_MEDIA,
    "graphics": KIND_TOOLS,
    "otherosfs": KIND_TOOLS,
    "editors": KIND_OFFICE,
    "text": KIND_OFFICE,
    "tex": KIND_OFFICE,
    "devel": KIND_DEV,
    "vcs": KIND_DEV,
    "database": KIND_DEV,
    "httpd": KIND_DEV,
    "interpreters": KIND_DEV,
    "python": KIND_DEV,
    "perl": KIND_DEV,
    "ruby": KIND_DEV,
    "rust": KIND_DEV,
    "golang": KIND_DEV,
    "javascript": KIND_DEV,
    "java": KIND_DEV,
    "php": KIND_DEV,
}


def judge(entry: Entry) -> Entry:
    texts = [entry.command, entry.path, entry.name, entry.location if "\\" not in entry.location else ""]
    found = known.match(*texts)
    reasons: list[str] = []

    if entry.exists is False and entry.path:
        entry.verdict, entry.kind = BROKEN, entry.kind or (found.kind if found else _kind(entry))
        entry.reasons = [
            "El archivo que tendría que abrir ya no existe: seguramente desinstalaste el programa y se quedó apuntado."
        ]
        entry.tip = (
            "No hace nada: puedes desactivarlo sin miedo."
            if entry.enabled
            else "Ya está desactivado, así que no molesta."
        )
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
        if entry.package:
            reasons.append(_comes_from(entry))
        if entry.extra.get("unusual"):
            # Un nombre conocido no tapa que esté enganchado donde no toca (IFEO, Winlogon…).
            entry.verdict = CHECK
            reasons.append(entry.extra["unusual"])
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
            # Si no lo ha puesto a arrancar el sistema, lo ha puesto alguien en tu usuario (tú,
            # al marcar «abrir al iniciar», o el propio programa), o es una app snap o flatpak.
            entry.verdict = KEEP if _from_system(entry) else OPTIONAL
            if entry.extra.get("package_of") == "definición" and not _store_app(entry):
                reasons.append(f"Lo instala {_package_label(entry)}.")
            else:
                reasons.append(f"Abre un programa de {_package_label(entry)}.")
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
    if flags := red_flags(entry):
        entry.verdict = CHECK
        # Delante: es lo que hace que salga en «Revísalo», y el resumen enseña el primer motivo.
        # «Lleva la firma de Microsoft» primero tranquilizaría justo en el caso que no debe.
        reasons[:0] = flags
    entry.reasons = reasons
    return entry


def _store_app(entry: Entry) -> bool:
    return entry.package.endswith((" (snap)", " (flatpak)"))


def _package_label(entry: Entry) -> str:
    if _store_app(entry):
        name, _, store = entry.package.rpartition(" (")
        return f"«{name}», instalado como {store.rstrip(')')}"
    return f"el paquete «{entry.package}» del sistema"


def _comes_from(entry: Entry) -> str:
    if _store_app(entry):
        return f"Viene de {_package_label(entry)}."
    return f"Viene del paquete «{entry.package}» del sistema."


def _from_system(entry: Entry) -> bool:
    """Lo puso a arrancar el sistema: es del sistema entero, o el propio paquete trae el
    archivo que lo hace arrancar (el .service, el .desktop de autostart…). Las apps snap y
    flatpak no: esas las instala uno."""
    if _store_app(entry):
        return False
    return entry.scope == "sistema" or entry.extra.get("package_of") == "definición"


def _kind(entry: Entry) -> str:
    section = entry.extra.get("section", "")
    if section in SECTION_KINDS:
        return SECTION_KINDS[section]
    text = " ".join([entry.name, entry.description, entry.product, entry.path])
    for pattern, kind in KIND_WORDS:
        if pattern.search(text):
            return kind
    if entry.company and HARDWARE_MAKERS.search(entry.company):
        return KIND_HARDWARE
    if entry.package:  # del sistema, o un programa instalado con el gestor de paquetes
        return KIND_SYSTEM if _from_system(entry) else KIND_TOOLS
    return KIND_OTHER
