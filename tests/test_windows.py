import pytest

from bootscout import lnk
from bootscout import scan_windows as sw
from bootscout import win_services as wsvc
from bootscout import win_tasks as wt
from bootscout.winreg_source import RegKey, Source

ENV = {
    "APPDATA": r"C:\Users\Ana\AppData\Roaming",
    "PROGRAMDATA": r"C:\ProgramData",
    "SystemRoot": r"C:\Windows",
    "windir": r"C:\Windows",
}


def files(*paths):
    return {p.lower(): b"x" for p in paths}


def test_run_keys_con_estado_activado_y_desactivado():
    reg = {
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run": RegKey(
            values={"Spotify": r'"C:\Spotify.exe" /min', "Off": r"C:\off.exe"}
        ),
        r"HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run": RegKey(
            values={"Spotify": b"\x02" + b"\x00" * 11, "Off": b"\x03" + b"\x00" * 11}
        ),
    }
    src = Source(registry=reg, files=files(r"C:\Spotify.exe", r"C:\off.exe"), env=ENV)
    by_name = {e.name: e for e in sw.run_key_entries(src)}
    assert by_name["Spotify"].enabled is True
    assert by_name["Off"].enabled is False
    assert by_name["Spotify"].scope == "usuario" and by_name["Spotify"].toggle["kind"] == "run"


def test_run_32_bits_se_etiqueta():
    reg = {r"HKLM\Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Run": RegKey(values={"X": r"C:\x.exe"})}
    (entry,) = sw.run_key_entries(Source(registry=reg, files=files(r"C:\x.exe"), env=ENV))
    assert "32 bits" in entry.where and entry.scope == "sistema"


def test_runonce_es_solo_una_vez():
    reg = {r"HKCU\Software\Microsoft\Windows\CurrentVersion\RunOnce": RegKey(values={"Setup": r"C:\setup.exe"})}
    (entry,) = sw.run_key_entries(Source(registry=reg, files=files(r"C:\setup.exe"), env=ENV))
    assert "RunOnce" in entry.where and entry.toggle == {} and "próxima vez" in entry.trigger


def test_carpeta_de_inicio_lee_el_acceso_directo():
    link = lnk.build(r"C:\Program Files\Thing\thing.exe", "--tray")
    startup = r"C:\Users\Ana\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"
    f = {f"{startup}\\Thing.lnk": link, r"C:\Program Files\Thing\thing.exe": b"x"}
    (entry,) = sw.startup_folder_entries(Source(files=f, env=ENV))
    assert entry.name == "Thing" and entry.path == r"C:\Program Files\Thing\thing.exe"
    assert entry.toggle["kind"] == "startup-file"


def test_winlogon_secuestrado_se_marca():
    reg = {
        r"HKLM\Software\Microsoft\Windows NT\CurrentVersion\Winlogon": RegKey(
            values={"Shell": r"explorer.exe, C:\Malo\evil.exe", "Userinit": r"C:\Windows\system32\userinit.exe,"}
        )
    }
    entries = sw.special_entries(Source(registry=reg, files=files(r"C:\Malo\evil.exe"), env=ENV))
    assert len(entries) == 1  # userinit normal se ignora; el shell raro no
    assert entries[0].path == r"C:\Malo\evil.exe" and "raro" in entries[0].extra["unusual"]


def test_ifeo_debugger_se_marca():
    reg = {
        r"HKLM\Software\Microsoft\Windows NT\CurrentVersion\Image File Execution Options": RegKey(
            subkeys={"sethc.exe": RegKey(values={"Debugger": r"C:\Windows\System32\cmd.exe"})}
        )
    }
    (entry,) = sw.special_entries(Source(registry=reg, files=files(r"C:\Windows\System32\cmd.exe"), env=ENV))
    assert "sethc.exe" in entry.name and "IFEO" in entry.extra["unusual"]


def test_servicios_solo_los_automaticos_y_su_estado():
    reg = {
        r"HKLM\System\CurrentControlSet\Services": RegKey(
            subkeys={
                "Auto": RegKey(
                    values={
                        "Start": 2,
                        "Type": 16,
                        "ImagePath": r'"C:\a.exe"',
                        "DisplayName": "Auto Svc",
                        "DelayedAutostart": 1,
                    }
                ),
                "Manual": RegKey(values={"Start": 3, "Type": 16, "ImagePath": r"C:\m.exe"}),
                "Driver": RegKey(values={"Start": 1, "Type": 1, "ImagePath": r"system32\drivers\d.sys"}),
            }
        )
    }
    src = Source(registry=reg, files=files(r"C:\a.exe"), env=ENV)
    entries = wsvc.service_entries(src)
    assert [e.name for e in entries] == ["Auto Svc"]  # manual fuera, driver fuera (por defecto)
    assert entries[0].trigger == "automático (con retraso)" and entries[0].scope == "sistema"
    assert len(wsvc.service_entries(src, include_drivers=True)) == 2  # ahora con el driver


def test_servicio_imagepath_relativo_de_driver():
    assert wsvc._clean_image(r"\??\C:\x.sys") == r"C:\x.sys"
    assert wsvc._clean_image("system32\\drivers\\foo.sys") == r"C:\Windows\system32\drivers\foo.sys"


TASK_XML = """<?xml version="1.0" encoding="UTF-16"?>
<Task xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
 <RegistrationInfo><Author>Vendor</Author><Description>Busca updates</Description></RegistrationInfo>
 <Triggers>{trigger}</Triggers>
 <Settings><Enabled>{enabled}</Enabled></Settings>
 <Actions><Exec><Command>C:\\Vendor\\upd.exe</Command><Arguments>/check</Arguments></Exec></Actions>
</Task>"""


@pytest.mark.parametrize("encoding", ["utf-16", "utf-8"])
def test_tarea_programada(encoding):
    xml = TASK_XML.format(trigger="<BootTrigger><Enabled>true</Enabled></BootTrigger>", enabled="true").encode(encoding)
    f = {r"c:\windows\system32\tasks\vendor\upd".lower(): xml, r"c:\vendor\upd.exe".lower(): b"x"}
    (entry,) = wt.task_entries(Source(files=f, env=ENV))
    assert entry.when == "Al encender" and entry.path == r"C:\Vendor\upd.exe"
    assert entry.trigger == "al arrancar el equipo" and entry.extra["author"] == "Vendor"


def test_tarea_deshabilitada():
    xml = TASK_XML.format(trigger="<LogonTrigger/>", enabled="false").encode("utf-16")
    f = {r"c:\windows\system32\tasks\off".lower(): xml, r"c:\vendor\upd.exe".lower(): b"x"}
    (entry,) = wt.task_entries(Source(files=f, env=ENV))
    assert entry.enabled is False and entry.when == "Al iniciar sesión"


def test_tarea_xml_roto_se_ignora():
    assert wt.parse_task(b"no es xml") is None
    assert wt.parse_task(b"<otracosa/>") is None


def test_version_y_firma_llegan_a_la_entrada():
    reg = {r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run": RegKey(values={"X": r"C:\x.exe"})}
    ver = {r"c:\x.exe": {"company": "ACME", "product": "Thing", "version": "1.2"}}
    sig = {r"c:\x.exe": ("válida", "ACME Corp")}
    src = Source(registry=reg, files=files(r"C:\x.exe"), env=ENV, version=ver, signatures=sig)
    (entry,) = sw.run_key_entries(src)
    assert entry.company == "ACME" and entry.signature == "válida" and entry.signer == "ACME Corp"
    assert entry.exists is True


def test_archivo_que_no_existe():
    reg = {r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run": RegKey(values={"X": r"C:\gone.exe"})}
    (entry,) = sw.run_key_entries(Source(registry=reg, files={}, env=ENV))
    assert entry.exists is False


def test_machine_wide_run_keys_are_not_toggled_from_here():
    # boot-scout solo cambia lo de tu usuario: lo de todo el equipo (HKLM) se explica, no se toca.
    reg = {r"HKLM\Software\Microsoft\Windows\CurrentVersion\Run": RegKey(values={"X": r"C:\x.exe"})}
    (entry,) = sw.run_key_entries(Source(registry=reg, files=files(r"C:\x.exe"), env=ENV))
    assert entry.toggle == {}


def test_set_enabled_refuses_system_scope_even_if_asked():
    import pytest

    from bootscout.apply import CantDo, set_enabled
    from bootscout.entry import Entry

    for toggle in (
        {"kind": "run", "hive": "HKLM", "key": r"HKLM\x", "name": "X"},
        {"kind": "systemd", "unit": "ssh.service", "user": False},
    ):
        with pytest.raises(CantDo):
            set_enabled(Entry(id="x", name="X", when="", where="", toggle=toggle), False)
