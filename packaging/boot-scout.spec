# Receta de PyInstaller para el programa de Windows y la app de macOS:
#     pyinstaller --noconfirm packaging/boot-scout.spec
# Deja el resultado en dist/boot-scout (y dist/boot-scout.app en macOS).
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
sys.path.insert(0, str(root))
from bootscout import __version__  # noqa: E402

icon = str(root / "packaging" / "icon.png")  # PyInstaller lo pasa a .ico o .icns con Pillow

a = Analysis(
    [str(root / "packaging" / "boot-scout-app.py")],
    pathex=[str(root)],
    datas=collect_data_files("bootscout"),  # el icono
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="boot-scout", console=False, icon=icon)
coll = COLLECT(exe, a.binaries, a.datas, name="boot-scout")

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="boot-scout.app",
        icon=icon,
        bundle_identifier="io.github.espi0207.bootscout",
        version=__version__,
        info_plist={
            "CFBundleDisplayName": "boot-scout",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
