import sys

import pytest

from bootscout import apply
from bootscout import scan_linux as sl
from bootscout.entry import AT_BOOT, AT_LOGON, SCHEDULED

# Estas pruebas dependen de cosas propias de Linux (los bits de ejecución de los archivos,
# las rutas /etc…); el código que prueban solo corre en Linux, así que fuera de Linux se
# saltan. Las de parseo de texto, en cambio, valen en cualquier sistema.
linux_only = pytest.mark.skipif(not sys.platform.startswith("linux"), reason="comportamiento propio de Linux")


def test_autostart_el_de_usuario_tapa_al_del_sistema(tmp_path):
    system = tmp_path / "xdg"
    user = tmp_path / "user"
    system.mkdir()
    user.mkdir()
    (system / "foo.desktop").write_text("[Desktop Entry]\nName=Foo\nExec=/usr/bin/foo\n")
    (user / "foo.desktop").write_text("[Desktop Entry]\nName=Foo\nExec=/usr/bin/foo\nHidden=true\n")
    (system / "bar.desktop").write_text("[Desktop Entry]\nName=Bar\nExec=/usr/bin/bar\n")
    entries = {e.name: e for e in sl.autostart_entries({"sistema": [system], "usuario": [user]})}
    assert entries["Foo"].enabled is False  # la copia del usuario con Hidden=true gana
    assert entries["Bar"].enabled is True and entries["Bar"].scope == "sistema"


def test_autostart_gnome_disabled(tmp_path):
    user = tmp_path / "user"
    user.mkdir()
    (user / "x.desktop").write_text("[Desktop Entry]\nName=X\nExec=/usr/bin/x\nX-GNOME-Autostart-enabled=false\n")
    (entry,) = sl.autostart_entries({"usuario": [user]})
    assert entry.enabled is False


def test_systemd_solo_habilitados():
    out = (
        "cups.service enabled\nfstrim.timer enabled\nssh@.service enabled\n"
        "getty@tty1.service static-enabled\nbluetooth.service disabled\n"
    )
    entries = {e.name: e for e in sl.systemd_entries("sistema", out, out)}
    assert "cups.service" in entries and "fstrim.timer" in entries
    assert "bluetooth.service" not in entries  # disabled no arranca solo
    assert entries["fstrim.timer"].when == SCHEDULED and entries["cups.service"].when == AT_BOOT


def test_cron_de_usuario():
    cron = "# comentario\nPATH=/usr/bin\n@reboot /opt/x/run.sh --bg\n0 10 * * * /usr/bin/backup.sh\n"
    entries = sl.parse_crontab(cron, "tu usuario", "usuario")
    assert [e.when for e in entries] == [AT_BOOT, SCHEDULED]
    assert entries[0].trigger == "al arrancar" and entries[1].trigger == "cada día a las 10:00"


def test_cron_del_sistema_con_usuario():
    cron = "17 * * * * root cd / && run-parts /etc/cron.hourly\n"
    (entry,) = sl.parse_crontab(cron, "/etc/crontab", "sistema", with_user=True)
    assert entry.path == "/usr/bin/run-parts" or entry.path.endswith("run-parts") or entry.command.startswith("cd")


@linux_only
def test_run_parts_salta_los_que_no_tocan(tmp_path):
    (tmp_path / "ok").write_text("#!/bin/sh\n")
    (tmp_path / "ok").chmod(0o755)
    (tmp_path / "skip.dpkg-old").write_text("x")
    (tmp_path / "skip.dpkg-old").chmod(0o755)
    (tmp_path / "noexec").write_text("#!/bin/sh\n")
    entries = sl.run_parts_entries(tmp_path, "cada día", "cron.daily")
    assert [e.name for e in entries] == ["ok"]


def test_rc_local_salta_la_preparacion():
    rc = "#!/bin/sh -e\n/opt/vendor/agent --daemon &\ntouch /var/run/x\nmodprobe foo\nexit 0\n"
    entries = sl.rc_local_entries(rc)
    assert [e.name for e in entries] == ["agent"] and entries[0].when == AT_BOOT


def test_shell_solo_lo_que_lanza_algo():
    read = {"/home/ana/.profile": "nm-applet &\nexport X=1\nnohup syncthing serve >/dev/null 2>&1 &\n# c\ntrue\n"}
    entries = sl.shell_entries(read)
    assert {e.name for e in entries} == {"nm-applet", "syncthing"}
    assert all(e.when == AT_LOGON for e in entries)


def test_shell_del_sistema_es_de_sistema():
    (entry,) = sl.shell_entries({"/etc/profile.d/z.sh": "agent --tray &\n"})
    assert entry.scope == "sistema" and entry.when == AT_LOGON


@linux_only
def test_desactivar_y_reactivar_un_desktop(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = tmp_path / "autostart" / "discord.desktop"
    path.parent.mkdir(parents=True)
    path.write_text("[Desktop Entry]\nType=Application\nName=Discord\nExec=/usr/bin/discord\n")
    from bootscout.entry import Entry

    entry = Entry(id="x", name="Discord", when="", where="", toggle={"kind": "desktop", "file": str(path)})
    apply.set_enabled(entry, False)
    assert "Hidden=true" in path.read_text() and entry.enabled is False
    apply.set_enabled(entry, True)
    assert "Hidden=true" not in path.read_text() and entry.enabled is True


@linux_only
def test_desactivar_uno_del_sistema_crea_copia(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    from bootscout.entry import Entry

    entry = Entry(
        id="x", name="Foo", when="", where="", toggle={"kind": "desktop", "file": "/etc/xdg/autostart/foo.desktop"}
    )
    apply.set_enabled(entry, False)
    copy = tmp_path / "config" / "autostart" / "foo.desktop"
    assert copy.is_file() and "Hidden=true" in copy.read_text()
    apply.set_enabled(entry, True)  # reactivar quita la copia
    assert not copy.exists()
