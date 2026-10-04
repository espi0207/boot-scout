import os
import sys

import pytest

tk = pytest.importorskip("tkinter")

from bootscout import gui  # noqa: E402


@pytest.mark.skipif(
    sys.platform.startswith("linux") and not os.environ.get("DISPLAY"),
    reason="en Linux hace falta una pantalla (en la CI, xvfb-run)",
)
def test_la_ventana_carga_la_demo_agrupa_y_exporta(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOTSCOUT_HOME", str(tmp_path))
    assert gui.self_check() == 0
