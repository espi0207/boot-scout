import struct

import pytest

from bootscout import lnk


def test_ida_y_vuelta():
    data = lnk.build(r"C:\Program Files\App\app.exe", "--tray", r"C:\Program Files\App", "La App")
    link = lnk.parse(data)
    assert link.target == r"C:\Program Files\App\app.exe"
    assert link.arguments == "--tray"
    assert link.working_dir == r"C:\Program Files\App"
    assert link.description == "La App"


def test_acceso_directo_con_acentos():
    link = lnk.parse(lnk.build(r"C:\Users\José\App\café.exe", "--ñ"))
    assert link.target == r"C:\Users\José\App\café.exe" and link.arguments == "--ñ"


@pytest.mark.parametrize(
    "data", [b"", b"\x00" * 10, b"\x4c\x00\x00\x00" + b"\x00" * 100, struct.pack("<I", 0x4C) + b"\xff" * 100]
)
def test_acceso_directo_roto_no_rompe(data):
    with pytest.raises(lnk.BadLink):
        lnk.parse(data)
