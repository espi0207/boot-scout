import json

import pytest

from bootscout import __main__ as cli
from bootscout import demo


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOTSCOUT_HOME", str(tmp_path))
    monkeypatch.setenv("NO_COLOR", "1")


def test_demo(capsys):
    assert cli.main(["--demo"]) == 0
    out = capsys.readouterr().out
    assert "15 cosas arrancan solas" in out
    assert "AnyDesk" in out and "GoToMeeting" in out and "← nuevo" in out
    assert "Lo que conviene mirar" in out


def test_demo_detalle(capsys):
    assert cli.main(["--demo", "--detalle"]) == 0
    out = capsys.readouterr().out
    assert "Control remoto del ordenador" in out and "Firma digital" in out


@pytest.mark.parametrize("axis", ["veredicto", "cuando", "tipo"])
def test_agrupar(axis, capsys):
    assert cli.main(["--demo", "--agrupar", axis, "--todo"]) == 0
    assert "arrancan solas" in capsys.readouterr().out


def test_filtro_revisar(capsys):
    assert cli.main(["--demo", "--revisar"]) == 0
    out = capsys.readouterr().out
    assert "AnyDesk" in out and "Spotify" not in out.split("conviene")[0]


def test_filtro_tipo(capsys):
    assert cli.main(["--demo", "--tipo", "juegos", "--todo"]) == 0
    out = capsys.readouterr().out
    assert "Steam" in out and "OneDrive" not in out


def test_json_a_pantalla(capsys):
    assert cli.main(["--demo", "--json", "-"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["system"] == "Windows" and len(data["entries"]) == len(demo.entries())


def test_json_a_archivo(tmp_path, capsys):
    out = tmp_path / "x.json"
    assert cli.main(["--demo", "--json", str(out)]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["entries"]
    assert "Guardado" in capsys.readouterr().out


def test_desactivar_no_encontrado(capsys):
    assert cli.main(["--desactivar", "nombre que no existe zzz"]) == 1
    assert "No encuentro" in capsys.readouterr().err


def test_deshacer_sin_nada(capsys):
    assert cli.main(["--deshacer"]) == 1
    assert "deshacer" in capsys.readouterr().err.lower()


def test_desactivar_y_deshacer_de_verdad(tmp_path, monkeypatch, capsys):
    # Una entrada de autostart de Linux de verdad, en un HOME temporal.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    autostart = tmp_path / "config" / "autostart"
    autostart.mkdir(parents=True)
    desktop = autostart / "discord.desktop"
    desktop.write_text("[Desktop Entry]\nType=Application\nName=Discord\nExec=/usr/bin/discord\n")

    from bootscout import scan_linux

    def fake_scan():
        return scan_linux.autostart_entries({"usuario": [autostart]})

    monkeypatch.setattr(cli.scan, "_raw_scan", lambda system: fake_scan())
    monkeypatch.setattr(cli.scan, "current_system", lambda: "Linux")

    assert cli.main(["--desactivar", "Discord"]) == 0
    assert "Hidden=true" in desktop.read_text()
    assert cli.main(["--deshacer"]) == 0
    assert "Hidden=true" not in desktop.read_text()


def test_ambiguous_name_is_not_toggled_at_random(tmp_path, monkeypatch, capsys):
    # Dos «Updater» tuyos distintos: no se apaga el primero que salga, se pide cuál.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    autostart = tmp_path / "config" / "autostart"
    autostart.mkdir(parents=True)
    for name in ("a", "b"):
        (autostart / f"{name}.desktop").write_text(f"[Desktop Entry]\nName=Updater\nExec=/usr/bin/{name}-updater\n")

    from bootscout import scan_linux

    monkeypatch.setattr(cli.scan, "_raw_scan", lambda system: scan_linux.autostart_entries({"usuario": [autostart]}))
    monkeypatch.setattr(cli.scan, "current_system", lambda: "Linux")
    assert cli.main(["--desactivar", "Updater"]) == 1
    err = capsys.readouterr().err
    assert "varios" in err and "linux:" in err  # enseña los ids para elegir
    assert all("Hidden" not in p.read_text() for p in autostart.iterdir())
