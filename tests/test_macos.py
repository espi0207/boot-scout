import plistlib

import pytest

from bootscout import scan_macos as sm
from bootscout.entry import AT_BOOT, AT_LOGON, ON_DEMAND, SCHEDULED


def plist(**d):
    return plistlib.dumps(d)


def one(files, scope="sistema", when=AT_LOGON, disabled=None):
    return sm.launchd_entries(files, when, "x", scope, disabled)


def test_agente_normal():
    f = {
        "/Library/LaunchAgents/com.vendor.helper.plist": plist(
            Label="com.vendor.helper", ProgramArguments=["/Applications/Vendor.app/Contents/x", "--run"], RunAtLoad=True
        )
    }
    (entry,) = one(f)
    assert entry.name == "com.vendor.helper" and entry.path == "/Applications/Vendor.app/Contents/x"
    assert entry.when == AT_LOGON and entry.enabled


def test_daemon_arranca_al_encender():
    f = {
        "/Library/LaunchDaemons/com.vendor.d.plist": plist(
            Label="com.vendor.d", Program="/usr/local/bin/d", RunAtLoad=True
        )
    }
    (entry,) = one(f, when=AT_BOOT)
    assert entry.when == AT_BOOT and "daemon" in entry.where


@pytest.mark.parametrize(
    ("keys", "when", "detail_has"),
    [
        ({"StartInterval": 3600}, SCHEDULED, "hora"),
        ({"StartInterval": 86400}, SCHEDULED, "24"),
        ({"StartCalendarInterval": {"Hour": 9, "Minute": 30}}, SCHEDULED, "09:30"),
        ({"KeepAlive": True}, AT_LOGON, "siempre"),
        ({"WatchPaths": ["/etc/hosts"]}, ON_DEMAND, "cambian"),
    ],
)
def test_cuando_arranca_segun_las_llaves(keys, when, detail_has):
    f = {"/Library/LaunchAgents/com.x.plist": plist(Label="com.x", Program="/bin/x", **keys)}
    (entry,) = one(f)
    assert entry.when == when and detail_has in entry.trigger


def test_desactivado_por_la_llave_o_por_launchd():
    f = {
        "/Library/LaunchAgents/com.off.plist": plist(Label="com.off", Program="/bin/x", Disabled=True, RunAtLoad=True),
        "/Library/LaunchAgents/com.off2.plist": plist(Label="com.off2", Program="/bin/y", RunAtLoad=True),
    }
    entries = {e.name: e for e in one(f, disabled={"com.off2"})}
    assert not entries["com.off"].enabled and not entries["com.off2"].enabled


def test_apple_se_distingue():
    f = {
        "/System/Library/LaunchAgents/com.apple.dock.plist": plist(
            Label="com.apple.dock", ProgramArguments=["/System/.../Dock"], KeepAlive=True
        )
    }
    (entry,) = sm.launchd_entries(f, AT_LOGON, "Apple", "sistema")
    assert entry.extra["apple"] is True and "Apple" in entry.where


def test_plist_roto_se_ignora():
    assert one({"/Library/LaunchAgents/x.plist": b"no plist"}) == []
    assert sm.parse_plist(b"<broken") is None


def test_elementos_de_inicio_de_sesion():
    btm = """  1  UUID 1234
     Executable Path: /Applications/Rewind.app/Contents/MacOS/Rewind
  2  URL: file:///Applications/Docker.app/
  3  Executable Path: /Applications/Rewind.app/Contents/MacOS/Rewind
"""
    entries = sm.parse_login_items(btm)
    assert [e.name for e in entries] == ["Rewind", "Docker"]  # el repetido, una vez
    assert entries[0].when == AT_LOGON


def test_program_key_is_the_real_executable():
    # Con Program y ProgramArguments, launchd ejecuta Program; argv[0] es solo el nombre que ve.
    plist = {"Label": "com.x.agent", "Program": "/opt/actual", "ProgramArguments": ["innocent", "--flag"]}
    entry = sm.agent_entry(plist, "/Library/LaunchAgents/com.x.agent.plist", "Al iniciar sesión", "", "sistema")
    assert entry.path == "/opt/actual" and "--flag" in entry.command and "innocent" not in entry.command
