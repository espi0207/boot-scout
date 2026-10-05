import pytest

from bootscout import cmdline


def win(command, files=(), env=None):
    env = env or {"APPDATA": r"C:\Users\Ana\AppData\Roaming", "SystemRoot": r"C:\Windows", "windir": r"C:\Windows"}
    files = {f.lower() for f in files}
    search = [r"C:\Windows\System32", r"C:\Windows", r"C:\Windows\System32\WindowsPowerShell\v1.0"]
    return cmdline.windows_target(command, env, lambda p: p.lower() in files, search)


@pytest.mark.parametrize(
    ("command", "files", "file"),
    [
        (
            r'"C:\Program Files\Spotify\Spotify.exe" /minimized',
            [r"C:\Program Files\Spotify\Spotify.exe"],
            r"C:\Program Files\Spotify\Spotify.exe",
        ),
        (
            r"C:\Program Files\Foo Bar\foo.exe -silent",
            [r"C:\Program Files\Foo Bar\foo.exe"],
            r"C:\Program Files\Foo Bar\foo.exe",
        ),
        (
            r"rundll32.exe %APPDATA%\x.dll,Inicio",
            [r"C:\Windows\System32\rundll32.exe"],
            r"C:\Users\Ana\AppData\Roaming\x.dll",
        ),
        (
            r"powershell -w hidden -File C:\x.ps1",
            [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"],
            r"C:\x.ps1",
        ),
        (
            r'cmd /c start "" /min "C:\Program Files\X\x.exe"',
            [r"C:\Windows\System32\cmd.exe"],
            r"C:\Program Files\X\x.exe",
        ),
        (r"%SystemRoot%\system32\SecurityHealthSystray.exe", [], r"C:\Windows\system32\SecurityHealthSystray.exe"),
    ],
)
def test_windows_llega_al_archivo_de_verdad(command, files, file):
    assert win(command, files).file == file


def test_windows_powershell_codificado_se_descodifica():
    t = win(
        "powershell -nop -w hidden -enc ZQBjAGgAbwAgAGgAbwBsAGEA",
        [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"],
    )
    assert t.inline == "echo hola" and t.encoded is True


def test_windows_powershell_command_no_codificado():
    t = win('powershell -Command "Start-Process calc"', [r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"])
    assert "Start-Process calc" in t.inline and not t.encoded


def test_windows_sin_comillas_elige_el_ejecutable_mas_largo_que_existe():
    # «C:\Program Files\A B\run.exe» existe, así que el programa es eso, no «C:\Program».
    assert (
        win(r"C:\Program Files\A B\run.exe --x", [r"C:\Program Files\A B\run.exe"]).program
        == r"C:\Program Files\A B\run.exe"
    )


def posix(command, exists=True):
    return cmdline.posix_target(command, lambda p: exists, lambda w: "/usr/bin/" + w)


@pytest.mark.parametrize(
    ("command", "file"),
    [
        ("cd / && run-parts --report /etc/cron.hourly", "/usr/bin/run-parts"),
        ("nohup syncthing serve >/dev/null 2>&1 &", "/usr/bin/syncthing"),
        ("nice -n 10 /opt/x/job.sh --all", "/opt/x/job.sh"),
        ("timeout 30 /usr/bin/backup.sh", "/usr/bin/backup.sh"),
        ("env FOO=1 /usr/bin/python3 /opt/x/run.py", "/opt/x/run.py"),
        ('sh -c "sleep 5; nm-applet"', "/usr/bin/nm-applet"),
        ("setsid -f firefox --new-window &", "/usr/bin/firefox"),
        ("test -x /usr/sbin/anacron || ( cd / && run-parts /etc/cron.daily )", "/usr/bin/run-parts"),
        ("sudo -u nobody /opt/x/agent", "/opt/x/agent"),
    ],
)
def test_posix_llega_al_archivo_de_verdad(command, file):
    assert posix(command).file == file


def test_posix_python_module_y_c():
    assert posix("python3 -m http.server").file == "/usr/bin/python3 -m http.server"
    assert posix("python3 -c 'import x'").inline == "import x"


def test_posix_argv_ya_troceado():
    t = cmdline.posix_target_argv(["/usr/bin/env", "FOO=1", "/opt/run", "-x"], lambda p: True, lambda w: w)
    assert t.file == "/opt/run"


def test_comando_vacio_no_rompe():
    assert posix("").file == ""
    assert win("").file == ""
    assert posix('sh -c "   "').file in ("", "/usr/bin/sh")


@pytest.mark.parametrize(
    ("command", "file"),
    [
        # Lo que se abre dentro de una terminal es lo que importa, no la terminal
        (
            "bash -c \"gnome-terminal --window --title='X' -- btop; sleep 1; wmctrl -r 'X' -e 0,1400,0,500,400\"",
            "/usr/bin/btop",
        ),
        ("xterm -e htop", "/usr/bin/htop"),
        ('xfce4-terminal -e "nohup glances -w"', "/usr/bin/glances"),
        ("konsole --noclose -e /opt/tool/run --fast", "/opt/tool/run"),
        ("gnome-terminal", "/usr/bin/gnome-terminal"),  # sin nada dentro, es la terminal
    ],
)
def test_posix_terminales(command, file):
    assert posix(command).file == file
