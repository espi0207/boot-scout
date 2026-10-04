"""De una orden de arranque al archivo que se ejecuta de verdad.

En el registro pone cosas como «"C:\\Program Files\\Spotify\\Spotify.exe" /minimized»,
«rundll32.exe C:\\Users\\Ana\\AppData\\x.dll,Inicio» o, sin comillas,
«C:\\Program Files\\Foo\\foo.exe -silent». Y en Linux y macOS, «sh -c "sleep 5; nm-applet"»
o «nohup setsid -f programa > /dev/null 2>&1 &». Para saber qué es cada cosa hay que
encontrar el archivo que de verdad se pone en marcha: el .exe, la DLL que carga rundll32,
el script que ejecuta wscript o el programa que hay detrás de los envoltorios.

Aquí solo se lee el texto de la orden: no se ejecuta ni se interpreta nada.
"""

from __future__ import annotations

import base64
import binascii
import ntpath
import posixpath
import re
import shlex
from collections.abc import Callable
from dataclasses import dataclass

_ENV = re.compile(r"%([^%\s]+)%")

# Programas de Windows que solo cargan otra cosa: lo interesante es esa otra cosa.
LOADERS = {
    "rundll32.exe",
    "regsvr32.exe",
    "wscript.exe",
    "cscript.exe",
    "mshta.exe",
    "powershell.exe",
    "pwsh.exe",
    "cmd.exe",
    "javaw.exe",
    "java.exe",
    "python.exe",
    "pythonw.exe",
    "msiexec.exe",
    "conhost.exe",
    "explorer.exe",
}


@dataclass
class Target:
    program: str  # lo que se ejecuta («C:\Windows\System32\rundll32.exe»)
    args: str  # el resto de la orden
    file: str  # el archivo que importa («C:\Users\Ana\AppData\x.dll»); a veces es el mismo program
    inline: str = ""  # si la orden lleva el código dentro (powershell -Command, mshta javascript:…), cuál
    encoded: bool = False  # y si además va escondido (powershell -EncodedCommand)


def expand(text: str, env: dict[str, str]) -> str:
    """%APPDATA%\\x → C:\\Users\\Ana\\AppData\\Roaming\\x (las variables de Windows no
    distinguen mayúsculas)."""
    lower = {k.lower(): v for k, v in env.items()}
    return _ENV.sub(lambda m: lower.get(m.group(1).lower(), m.group(0)), text)


def split_windows(command: str) -> list[str]:
    """Trocea como Windows (CommandLineToArgvW, lo justo): las comillas agrupan; las
    barras invertidas son parte de las rutas."""
    args, current, quoted, started = [], [], False, False
    i = 0
    while i < len(command):
        c = command[i]
        if c == '"':
            if quoted and command[i + 1 : i + 2] == '"':  # "" dentro de comillas: unas comillas
                current.append('"')
                i += 2
                continue
            quoted, started = not quoted, True
        elif c in " \t" and not quoted:
            if current or started:
                args.append("".join(current))
                current, started = [], False
        else:
            current.append(c)
            started = True
        i += 1
    if current or started:
        args.append("".join(current))
    return args


def _with_exe(path: str, isfile: Callable[[str], bool]) -> str | None:
    for candidate in (path, path + ".exe"):
        if candidate and isfile(candidate):
            return candidate
    return None


def windows_target(
    command: str, env: dict[str, str], isfile: Callable[[str], bool], search: list[str] | None = None
) -> Target:
    command = expand(command.strip(), env)
    if command.startswith("\\??\\") or command.startswith("\\\\?\\"):
        command = command[4:]
    if not command:
        return Target("", "", "")
    search = search or []
    if command.startswith('"'):
        end = command.find('"', 1)
        program = command[1:end] if end > 0 else command[1:]
        rest = command[end + 1 :].strip() if end > 0 else ""
    else:
        # Sin comillas y con espacios («C:\Program Files\Foo\foo.exe -x»): el programa es el
        # trozo más largo que existe como archivo. Si ninguno existe, hasta «.exe» (lo que
        # hace Windows en la práctica) o hasta el primer espacio.
        words = command.split(" ")
        program, rest = words[0], " ".join(words[1:])
        for n in range(len(words), 0, -1):
            candidate = " ".join(words[:n])
            if _with_exe(candidate, isfile):
                program, rest = candidate, " ".join(words[n:])
                break
        else:
            m = re.match(r"(?i)^(.+?\.(exe|com|bat|cmd|scr|pif))(\s|$)", command)
            if m and " " in m.group(1):
                program, rest = m.group(1), command[m.end(1) :]
    program = program.strip()
    rest = rest.strip()
    if program and not ntpath.isabs(program) and "\\" not in program:
        for folder in search:
            found = _with_exe(ntpath.join(folder, program), isfile)
            if found:
                program = found
                break
    found = _with_exe(program, isfile)
    if found:
        program = found
    target = Target(program, rest, program)
    _loaded_file(target, env, isfile, search)
    return target


def _ps_encoded_switch(arg: str) -> bool:
    """PowerShell acepta cualquier abreviatura de -EncodedCommand: -e, -ec, -enc, -encodedc…"""
    name = arg.lower().lstrip("-/")
    return name in ("e", "ec") or (len(name) >= 2 and name.startswith("en") and "encodedcommand".startswith(name))


def decode_powershell(text: str) -> str:
    """El código de un -EncodedCommand: Base64 de UTF-16. Solo se descodifica para
    enseñarlo; nunca se ejecuta."""
    try:
        raw = base64.b64decode(text + "=" * (-len(text) % 4), validate=False)
        return raw.decode("utf-16-le", errors="replace").strip()
    except (binascii.Error, ValueError):
        return ""


def _loaded_file(target: Target, env, isfile, search) -> None:
    """Si el programa es un cargador (rundll32, wscript, powershell…), lo que carga."""
    base = ntpath.basename(target.program).lower()
    if "." not in base:
        base += ".exe"
    rest = target.args
    if base not in LOADERS or not rest:
        return
    args = split_windows(rest)
    if base == "rundll32.exe":
        if args:
            target.file = args[0].split(",")[0].strip()
            if target.file.lower().startswith(("javascript:", "vbscript:")):
                target.inline, target.file = rest, target.program
        return
    if base in ("regsvr32.exe", "wscript.exe", "cscript.exe", "mshta.exe", "python.exe", "pythonw.exe"):
        for i, arg in enumerate(args):
            low = arg.lower()
            if low.startswith(("javascript:", "vbscript:", "about:")):
                target.inline = " ".join(args[i:])
                return
            if base in ("python.exe", "pythonw.exe") and low == "-c":
                target.inline = " ".join(args[i + 1 :])
                return
            if not arg.startswith(("/", "-")):
                target.file = arg
                return
        return
    if base in ("powershell.exe", "pwsh.exe"):
        for i, arg in enumerate(args):
            low = arg.lower().lstrip("-/")
            if arg.startswith(("-", "/")) and low in ("file", "f") and i + 1 < len(args):
                target.file = args[i + 1]
                return
            if arg.startswith(("-", "/")) and _ps_encoded_switch(arg) and i + 1 < len(args):
                target.inline, target.encoded = decode_powershell(args[i + 1]) or args[i + 1], True
                return
            if arg.startswith(("-", "/")) and low in ("command", "c") and i + 1 < len(args):
                target.inline = " ".join(args[i + 1 :])
                return
            if arg.startswith(("-", "/")) and low in (
                "executionpolicy",
                "ep",
                "ex",
                "windowstyle",
                "w",
                "win",
                "version",
                "v",
                "inputformat",
                "outputformat",
                "configurationname",
                "psconsolefile",
                "workingdirectory",
                "wd",
            ):
                continue
            if (
                not arg.startswith(("-", "/"))
                and i > 0
                and args[i - 1].lower().lstrip("-/")
                in (
                    "executionpolicy",
                    "ep",
                    "ex",
                    "windowstyle",
                    "w",
                    "win",
                    "version",
                    "v",
                    "inputformat",
                    "outputformat",
                    "configurationname",
                    "psconsolefile",
                    "workingdirectory",
                    "wd",
                )
            ):
                continue
            if not arg.startswith(("-", "/")):
                if arg.lower().endswith(".ps1"):
                    target.file = arg
                else:
                    target.inline = " ".join(args[i:])
                return
        return
    if base in ("javaw.exe", "java.exe"):
        for i, arg in enumerate(args[:-1]):
            if arg.lower() == "-jar":
                target.file = args[i + 1]
                return
        return
    if base == "msiexec.exe":
        for i, arg in enumerate(args[:-1]):
            if arg.lower() in ("/i", "/x", "/fa", "/fu", "/f", "/p", "/update", "/package"):
                target.file = args[i + 1]
                return
        return
    if base == "conhost.exe":
        inner = [a for a in args if not a.startswith("-")]
        if inner:
            target.file = windows_target(" ".join(_quote(a) for a in inner), env, isfile, search).file
        return
    if base == "cmd.exe":
        for i, arg in enumerate(args):
            if arg.lower() in ("/c", "/k", "/r") and i + 1 < len(args):
                inner = args[i + 1 :]
                if inner[0].lower() == "start":  # cmd /c start "" /min "C:\…\programa.exe"
                    inner = [a for a in inner[1:] if not a.startswith("/")]
                    if len(inner) > 1 and (not inner[0] or not re.search(r"[\\/.]", inner[0])):
                        inner = inner[1:]  # el título de la ventana
                if inner:
                    inner_target = windows_target(" ".join(_quote(a) for a in inner), env, isfile, search)
                    target.file, target.inline, target.encoded = (
                        inner_target.file,
                        inner_target.inline,
                        inner_target.encoded,
                    )
                return
        return
    if base == "explorer.exe" and args and not args[0].startswith("/"):
        target.file = args[0]


def _quote(arg: str) -> str:
    return f'"{arg}"' if " " in arg or not arg else arg


# POSIX (macOS y Linux)

# Programas que solo envuelven a otro: (opciones que llevan un valor detrás, cuántos
# argumentos propios van antes de la orden de verdad).
WRAPPERS: dict[str, tuple[set[str], int]] = {
    "nohup": (set(), 0),
    "setsid": (set(), 0),
    "exec": ({"-a"}, 0),
    "nice": ({"-n", "--adjustment"}, 0),
    "ionice": ({"-c", "-n", "-p", "-P", "-u", "--class", "--classdata"}, 0),
    "time": ({"-o", "-f", "--output", "--format"}, 0),
    "stdbuf": ({"-i", "-o", "-e"}, 0),
    "chrt": (set(), 1),
    "taskset": (set(), 1),
    "flock": ({"-w", "-E", "--timeout", "--wait", "--conflict-exit-code"}, 1),
    "timeout": ({"-s", "-k", "--signal", "--kill-after"}, 1),
    "env": ({"-u", "-C", "--unset", "--chdir"}, 0),
    "sudo": ({"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U", "--user", "--group"}, 0),
    "doas": ({"-u", "-C"}, 0),
    "systemd-inhibit": ({"--what", "--who", "--why", "--mode"}, 0),
    "dbus-launch": ({"--config-file", "--autolaunch"}, 0),
    "caffeinate": ({"-t", "-w"}, 0),
    "arch": (set(), 0),
    "xvfb-run": ({"-n", "-s", "-f", "-e", "-p", "--server-num", "--server-args"}, 0),
    "torsocks": (set(), 0),
    "proxychains": ({"-f"}, 0),
    "proxychains4": ({"-f"}, 0),
}
NOISE = {
    "cd",
    "export",
    "sleep",
    "set",
    "unset",
    "umask",
    "test",
    "[",
    "[[",
    "true",
    "false",
    ":",
    "echo",
    "printf",
    "source",
    ".",
    "wait",
    "fi",
    "done",
    "esac",
    "then",
    "else",
    "do",
    "return",
    "exit",
    "shift",
    "local",
    "read",
    "eval",
    "trap",
    "ulimit",
    "alias",
    "shopt",
    "{",
    "}",
}
KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "!", "time"}
_SEPARATORS = {";", "&&", "||", "&", "|", "|&", ";;", "\n"}
_REDIRECTS = {">", ">>", "<", "<<", "<<<", ">&", "&>", "&>>", "<&", ">|", "<>"}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "fish", "csh", "tcsh"}
INTERPRETERS = re.compile(r"^(python[0-9.]*|perl[0-9.]*|ruby[0-9.]*|node|nodejs|php[0-9.]*|osascript|lua[0-9.]*)$")


def tokens(command: str) -> list[str]:
    """Trocea como la terminal, con los separadores (;, &&, |, &…) y las redirecciones
    como trozos aparte. Si las comillas no cierran, se trocea por espacios."""
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
        lex.whitespace_split = True
        lex.commenters = ""
        return list(lex)
    except ValueError:
        return command.replace(";", " ; ").replace("&&", " && ").split()


def segments(command: str) -> list[list[str]]:
    """Las órdenes sueltas de una línea, sin redirecciones ni paréntesis. Las que reciben
    la salida de otra por una tubería («… | logger») se marcan con «|» delante."""
    out: list[list[str]] = []
    current: list[str] = []
    piped = False
    words = tokens(command)
    i = 0
    while i < len(words):
        word = words[i]
        if word in _SEPARATORS:
            if current:
                out.append((["|"] if piped else []) + current)
            current, piped = [], word in ("|", "|&")
        elif word in _REDIRECTS:
            if current and current[-1].isdigit() and len(current[-1]) == 1:
                current.pop()  # el 2 de «2>&1»
            i += 1  # y el destino
        elif word in ("(", ")"):
            pass
        else:
            current.append(word)
        i += 1
    if current:
        out.append((["|"] if piped else []) + current)
    return out


def _unwrap(words: list[str]) -> list[str]:
    """Quita lo que va delante de la orden de verdad: VAR=valor, palabras como «if» o
    «then», y los envoltorios (nohup, setsid -f, timeout 30, nice -n 10…) con sus opciones."""
    words = list(words)
    for _ in range(20):
        while words and (words[0] in KEYWORDS or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", words[0])):
            words.pop(0)
        if not words:
            return words
        name = posixpath.basename(words[0])
        if name not in WRAPPERS:
            return words
        takes_value, positional = WRAPPERS[name]
        words.pop(0)
        if name == "flock" and any(w in ("-c", "--command") for w in words):
            i = next(i for i, w in enumerate(words) if w in ("-c", "--command"))
            return _pick(words[i + 1]) if i + 1 < len(words) else []
        while words:
            word = words[0]
            if word == "--":
                words.pop(0)
                break
            if name in ("env", "sudo") and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", word):
                words.pop(0)
                continue
            if not word.startswith("-") or word == "-":
                break
            words.pop(0)
            if word in takes_value and words:
                words.pop(0)
        for _ in range(positional):
            if words:
                words.pop(0)
    return words


def _pick(command: str) -> list[str]:
    """De todas las órdenes de una línea, la que importa: la última que no es de relleno
    (cd, sleep, export, echo…) ni recibe la salida de otra."""
    best: list[str] = []
    fallback: list[str] = []
    for segment in segments(command):
        if segment[0] == "|":
            continue
        words = _unwrap(segment)
        if not words:
            continue
        fallback = fallback or words
        if posixpath.basename(words[0]) not in NOISE:
            best = words
    return best or fallback


def posix_target(command: str, isfile: Callable[[str], bool], which: Callable[[str], str | None]) -> Target:
    """Lo mismo en macOS y Linux: «sh -c "sleep 5; nm-applet"» → nm-applet."""
    words = _pick(command)
    if not words:
        return Target("", "", "")
    return _resolve(words, isfile, which, depth=0)


def posix_target_argv(argv: list[str], isfile, which) -> Target:
    """Para las órdenes que ya vienen troceadas (ProgramArguments de un plist)."""
    words = _unwrap(argv)
    if not words:
        return Target("", "", "")
    return _resolve(words, isfile, which, depth=0)


def _resolve(words: list[str], isfile, which, depth: int) -> Target:
    program = words[0]
    if not program.startswith("/") and not program.startswith("~"):
        program = which(program) or program
    rest = " ".join(shlex.quote(w) for w in words[1:])
    target = Target(program, rest, program)
    base = posixpath.basename(program)
    args = words[1:]
    if base in SHELLS and args and depth < 4:
        i = 0
        while i < len(args):
            arg = args[i]
            if arg.startswith("-") and not arg.startswith("--") and "c" in arg[1:] or arg == "--command":
                if i + 1 < len(args):
                    inner = _pick(args[i + 1])
                    if inner:
                        found = _resolve(inner, isfile, which, depth + 1)
                        target.file, target.inline = found.file, found.inline
                    else:
                        target.inline = args[i + 1]
                return target
            if arg in ("-o", "+o", "-O", "+O", "--rcfile", "--init-file"):
                i += 2
                continue
            if arg.startswith(("-", "+")):
                i += 1
                continue
            target.file = arg
            return target
        return target
    if INTERPRETERS.match(base) and args:
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in ("-c", "-e", "-E", "--eval", "-r"):
                target.inline = " ".join(args[i + 1 :])
                return target
            if arg == "-m" and i + 1 < len(args):
                target.file = f"{program} -m {args[i + 1]}"
                return target
            if arg in ("-W", "-X", "-I", "-l") and base.startswith(("python", "perl", "ruby", "osascript")):
                i += 2
                continue
            if arg.startswith("-"):
                i += 1
                continue
            target.file = arg
            return target
        return target
    if base == "open" and args:  # macOS: open -a App, open -b com.x, open /Applications/X.app
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--args":
                break
            if arg in ("-a", "-b") and i + 1 < len(args):
                value = args[i + 1]
                if arg == "-a" and not value.startswith("/"):
                    value = value if value.endswith(".app") else value + ".app"
                    for folder in ("/Applications", "/System/Applications", "/Applications/Utilities"):
                        if isfile(f"{folder}/{value}"):
                            value = f"{folder}/{value}"
                            break
                target.file = value
                return target
            if arg.startswith("-"):
                i += 1
                continue
            target.file = arg
            return target
        return target
    if base in ("java",) and "-jar" in args:
        i = args.index("-jar")
        if i + 1 < len(args):
            target.file = args[i + 1]
    return target
