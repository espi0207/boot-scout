## Novedades en 1.0.1

- **Linux: ya casi nada se queda en «Sin datos».** boot-scout pregunta ahora al gestor de
  paquetes (dpkg, rpm o pacman) de qué paquete viene cada cosa, y reconoce las apps snap y
  flatpak. En un Ubuntu 24.04 de escritorio pasa de 47 cosas sin datos a ninguna.
- **Unos 50 servicios de Linux más en la lista**, explicados en cristiano: cron, el registro
  del sistema, los discos y USB, cloud-init, los informes de fallos, Ubuntu Pro, el servidor
  web, las máquinas virtuales…
- **«Qué es» sale de la sección del paquete** (red, sonido, juegos, programación…) cuando
  no está en la lista, en vez de «Otros».
- **Arranques rotos en Linux**: lo que apunta a un archivo que ya no existe sale como «Roto».
- **Lo que se abre en una terminal** (`gnome-terminal -- btop`, `xterm -e htop`…) se reconoce
  por el programa de dentro, y no por la terminal ni por lo que recoloca la ventana.
- **Arreglado**: `unattended-upgrades` salía como «Signal».
- **Ventana**: los nombres repetidos llevan al lado con qué nombre están apuntados
  («Impresoras (cups-browsed)»), las columnas se reparten para que no se corte el texto y la
  barra de desplazamiento ya no desaparece con la ventana estrecha.

## Descargas

| Sistema | Descarga |
|---|---|
| Windows 10 y 11 | `boot-scout-windows.exe` (instalador) |
| macOS 11 o posterior, con chip de Apple (M1 o más nuevo) | `boot-scout-mac.dmg` |
| Ubuntu, Debian, Linux Mint... | `boot-scout-linux.deb` |

No están firmados (firmar cuesta dinero cada año), así que la primera vez el sistema
avisa:

- **Windows**: "Windows protegió su PC". Pulsa *Más información* y luego *Ejecutar de
  todas formas*.
- **macOS**: arrastra boot-scout a Aplicaciones y ábrelo. Dirá que no se puede comprobar;
  ve a *Ajustes del Sistema > Privacidad y seguridad*, baja hasta el aviso de boot-scout y
  pulsa *Abrir igualmente*.
- **Linux**: `sudo apt install ./boot-scout-linux.deb`
