#!/bin/sh
# Construye dist/boot-scout-linux.deb para Ubuntu, Debian, Linux Mint y derivados.
#
# No lleva un Python dentro: instala el paquete tal cual y usa el Python del sistema, más
# python3-tk para la ventana. Por eso pesa unos pocos KB y vale para cualquier
# arquitectura. Uso: packaging/linux/build-deb.sh
set -eu

root=$(cd "$(dirname "$0")/../.." && pwd)
version=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$root/bootscout/__init__.py")
pkg=$(mktemp -d)
trap 'rm -rf "$pkg"' EXIT
chmod 755 "$pkg"  # mktemp la crea solo para su dueño, y es la raíz del paquete

mkdir -p "$pkg/DEBIAN" "$pkg/usr/bin" "$pkg/usr/lib/python3/dist-packages" \
  "$pkg/usr/share/applications" "$pkg/usr/share/doc/boot-scout" \
  "$pkg/usr/share/icons/hicolor/scalable/apps" "$pkg/usr/share/icons/hicolor/256x256/apps"

cp -r "$root/bootscout" "$pkg/usr/lib/python3/dist-packages/"
find "$pkg" -name __pycache__ -prune -exec rm -rf {} +

cat > "$pkg/usr/bin/boot-scout" <<'PY'
#!/usr/bin/python3
from bootscout.__main__ import main

raise SystemExit(main())
PY
cat > "$pkg/usr/bin/boot-scout-app" <<'PY'
#!/usr/bin/python3
from bootscout.gui import main

main()
PY
chmod 755 "$pkg/usr/bin/boot-scout" "$pkg/usr/bin/boot-scout-app"

cp "$root/packaging/linux/boot-scout.desktop" "$pkg/usr/share/applications/"
cp "$root/packaging/icon.svg" "$pkg/usr/share/icons/hicolor/scalable/apps/boot-scout.svg"
cp "$root/bootscout/icon.png" "$pkg/usr/share/icons/hicolor/256x256/apps/boot-scout.png"
cp "$root/LICENSE" "$pkg/usr/share/doc/boot-scout/copyright"

cat > "$pkg/DEBIAN/control" <<CONTROL
Package: boot-scout
Version: $version
Architecture: all
Maintainer: espi0207 <espi0207@users.noreply.github.com>
Depends: python3 (>= 3.10), python3-tk
Section: admin
Priority: optional
Homepage: https://github.com/espi0207/boot-scout
Description: lo que arranca con tu PC
 Enseña todo lo que se pone en marcha solo al encender el ordenador (programas,
 servicios de systemd, tareas de cron, autostart del escritorio...), qué es
 cada cosa y si hace falta. Avisa de lo nuevo y de lo que conviene revisar.
 Solo mira: no cambia nada salvo que se lo pidas.
CONTROL

# Compilar a bytecode al instalar (como hacen los paquetes de Python de Debian) y
# limpiarlo al desinstalar, que dpkg no sabe que esos archivos son del paquete.
cat > "$pkg/DEBIAN/postinst" <<'SH'
#!/bin/sh
set -e
python3 -m compileall -q /usr/lib/python3/dist-packages/bootscout >/dev/null 2>&1 || true
SH
cat > "$pkg/DEBIAN/prerm" <<'SH'
#!/bin/sh
set -e
rm -rf /usr/lib/python3/dist-packages/bootscout/__pycache__
SH
chmod 755 "$pkg/DEBIAN/postinst" "$pkg/DEBIAN/prerm"

mkdir -p "$root/dist"
dpkg-deb --build --root-owner-group "$pkg" "$root/dist/boot-scout-linux.deb"
