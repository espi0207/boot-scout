from datetime import datetime, timedelta

from bootscout import demo, judge, scan
from bootscout.entry import (
    BROKEN,
    CHECK,
    KEEP,
    KIND_REMOTE,
    KIND_SYSTEM,
    OPTIONAL,
    REMOVABLE,
    UNKNOWN,
    Entry,
)
from bootscout.history import History


def e(**kw):
    kw.setdefault("when", "Al iniciar sesión")
    kw.setdefault("where", "Registro: Run")
    return Entry(id=kw.get("id", "x"), name=kw.pop("name", "X"), **{k: v for k, v in kw.items() if k != "id"})


def test_conocido_gana():
    entry = judge.judge(e(name="Spotify", command=r"C:\Spotify.exe", path=r"C:\Spotify.exe"))
    assert entry.known == "Spotify" and entry.verdict == OPTIONAL and entry.kind


def test_archivo_roto_es_broken():
    entry = judge.judge(e(name="Vieja", path=r"C:\gone.exe", exists=False))
    assert entry.verdict == BROKEN and "no existe" in entry.reasons[0]


def test_firma_valida_desconocido_es_opcional():
    entry = judge.judge(e(name="Cosa", path=r"C:\cosa.exe", exists=True, signature="válida", signer="Cosa SL"))
    assert entry.verdict == OPTIONAL and "Cosa SL" in entry.reasons[0]


def test_sin_firma_desconocido_hay_que_revisarlo():
    entry = judge.judge(e(name="Cosa", path=r"C:\cosa.exe", exists=True, signature="sin firma"))
    assert entry.verdict == CHECK


def test_firma_no_valida_siempre_revisar():
    entry = judge.judge(e(name="Spotify", command="spotify", path=r"C:\s.exe", exists=True, signature="no válida"))
    assert entry.verdict == CHECK and any("firma" in r for r in entry.reasons)


def test_carpeta_temporal_revisar():
    entry = judge.judge(
        e(name="X", path=r"C:\Users\A\AppData\Local\Temp\x\svc.exe", exists=True, signature="válida", signer="Algo")
    )
    assert entry.verdict == CHECK and any("temporal" in r for r in entry.reasons)


def test_ajuste_del_sistema_raro_es_check():
    entry = judge.judge(e(name="Shell", path=r"C:\evil.exe", exists=True, extra={"unusual": "raro"}))
    assert entry.verdict == CHECK and entry.kind == KIND_SYSTEM


def test_control_remoto_es_check():
    entry = judge.judge(e(name="AnyDesk", command=r"C:\AnyDesk.exe --tray", path=r"C:\AnyDesk.exe", exists=True))
    assert entry.kind == KIND_REMOTE and entry.verdict == CHECK


def test_demo_pasa_por_el_clasificador():
    result = demo.result()
    verdicts = {e.display_name(): e.verdict for e in result.entries}
    assert verdicts["AnyDesk"] == CHECK
    assert verdicts["GoToMeeting"] == BROKEN
    assert verdicts["uTorrent / BitTorrent"] == REMOVABLE
    assert verdicts["Seguridad de Windows"] == KEEP
    assert sum(e.is_new for e in result.entries) == 1


def test_clasificar_ordena_y_quita_duplicados():
    entries = [
        e(id="a", name="A", path="/x", verdict=UNKNOWN),
        e(id="a", name="A", path="/x"),  # mismo id: se queda uno
        e(id="b", name="B", command="", path="", inline=""),
    ]  # sin nada: fuera
    out = scan.classify(entries)
    assert len(out) == 1 and out[0].id == "a"


def test_historial_marca_lo_nuevo(tmp_path):
    h = History(tmp_path / "v.json", system="Windows")
    day1 = datetime(2026, 10, 1, 9, 0)
    first = [e(id="a", name="A", path="/a"), e(id="b", name="B", path="/b")]
    assert h.record(first, day1) == []  # primera vez: nada es nuevo
    assert not any(x.is_new for x in first)
    h.save()

    again = History(tmp_path / "v.json", system="Windows")
    second = [e(id="a", name="A", path="/a"), e(id="c", name="C", path="/c")]
    gone = again.record(second, day1 + timedelta(days=1))
    assert [x.is_new for x in second] == [False, True]
    assert [g["id"] for g in gone] == ["b"]
    assert not again.is_first_scan()


def test_historial_por_sistema_separado(tmp_path):
    path = tmp_path / "v.json"
    History(path, system="Windows").record([e(id="w", name="W", path="/w")])
    hw = History(path, system="Windows")
    hw.record([e(id="w", name="W", path="/w")])
    hw.save()
    hl = History(path, system="Linux")
    assert hl.is_first_scan()  # Linux no ha visto nada aunque Windows sí


def test_historial_roto_no_rompe(tmp_path):
    path = tmp_path / "v.json"
    path.write_text("{roto", encoding="utf-8")
    h = History(path, system="Linux")
    h.record([e(id="a", name="A", path="/a")])
    h.save()
    assert "a" in History(path, system="Linux")._bucket()["entries"]
