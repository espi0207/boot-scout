"""La ventana de boot-scout: la lista agrupada a la izquierda y la ficha a la derecha.

Tkinter viene con Python, así que no hace falta instalar nada más. La pasada por el sistema
va en un hilo aparte para que la ventana no se congele; Tkinter no se puede tocar desde
otro hilo, así que el hilo deja el resultado en una cola que la ventana mira cada 100 ms.
"""

from __future__ import annotations

import json
import queue
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from . import __version__, apply, demo, report, scan
from .entry import BROKEN, CHECK, KEEP, VERDICTS, WHEN, Entry
from .history import History
from .scan import Result

ICON = Path(__file__).with_name("icon.png")
AXES = [("Qué hacer", "verdict"), ("Cuándo arranca", "when"), ("Qué es", "kind")]
COLORS = {CHECK: "#b42318", BROKEN: "#b54708", KEEP: "#067647"}
ABOUT = (
    "boot-scout mira todo lo que se pone en marcha solo al encender el ordenador y te dice qué es cada cosa "
    "y si hace falta.\n\nMira en todos los sitios donde se puede programar un arranque:\n\n"
    "• Windows: las claves Run del registro, la carpeta de Inicio, las tareas programadas, los servicios, "
    "y rincones como Winlogon o los depuradores de IFEO.\n"
    "• macOS: los agentes y daemons de launchd, los elementos de inicio de sesión y cron.\n"
    "• Linux: el autostart del escritorio, systemd, cron y los perfiles de shell.\n\n"
    "Solo mira: no cambia nada salvo que tú le pidas desactivar algo, y siempre se puede deshacer. Solo toca "
    "cosas de tu usuario; lo del sistema te dice cómo cambiarlo, pero no lo hace."
)


class App:
    def __init__(self, root: tk.Tk, scan_on_start: bool = True):
        self.root = root
        self.jobs: queue.Queue = queue.Queue()
        self.busy = False
        self.result: Result | None = None
        self.history: History | None = None
        self.is_demo = False
        self.axis = tk.StringVar(value="verdict")
        self.show_all = tk.BooleanVar(value=False)
        self.items: dict[str, Entry] = {}

        root.title("boot-scout · Lo que arranca con tu PC")
        root.geometry("1060x680")
        root.minsize(780, 480)
        if ICON.exists():
            root.iconphoto(True, tk.PhotoImage(file=str(ICON)))
        self.build()
        root.after(100, self.poll)
        if scan_on_start:
            root.after(200, self.rescan)

    def build(self) -> None:
        root = self.root
        style = ttk.Style(root)
        if style.theme_use() == "default" and "clam" in style.theme_names():
            style.theme_use("clam")
        base = tkfont.nametofont("TkDefaultFont")
        self.bold = base.copy()
        self.bold.configure(weight="bold")
        self.big = base.copy()
        self.big.configure(size=base.cget("size") + 4, weight="bold")
        style.configure("Treeview", rowheight=base.metrics("linespace") + 8)
        style.configure("Accent.TButton", font=self.bold)

        menu = tk.Menu(root)
        file_menu = tk.Menu(menu, tearoff=False)
        file_menu.add_command(label="Mirar otra vez", command=self.rescan, accelerator="F5")
        file_menu.add_command(label="Ver un ordenador de ejemplo", command=self.open_demo)
        file_menu.add_command(label="Exportar…", command=self.export, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Salir", command=root.destroy)
        menu.add_cascade(label="Archivo", menu=file_menu)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(
            label="Qué mira boot-scout", command=lambda: messagebox.showinfo("Qué mira boot-scout", ABOUT, parent=root)
        )
        help_menu.add_command(label="Acerca de boot-scout", command=self.about)
        menu.add_cascade(label="Ayuda", menu=help_menu)
        root.config(menu=menu)
        root.bind_all("<F5>", lambda _: self.rescan())
        root.bind_all("<Control-s>", lambda _: self.export())

        top = ttk.Frame(root, padding=(14, 12, 14, 6))
        top.pack(fill="x")
        ttk.Label(top, text="Agrupar por:").pack(side="left")
        for label, value in AXES:
            ttk.Radiobutton(top, text=label, value=value, variable=self.axis, command=self.redraw).pack(
                side="left", padx=(8, 0)
            )
        ttk.Checkbutton(
            top, text="Enseñar también lo que puedes dejar", variable=self.show_all, command=self.redraw
        ).pack(side="left", padx=(16, 0))
        ttk.Button(top, text="Mirar otra vez", command=self.rescan, style="Accent.TButton").pack(side="right")

        self.summary = ttk.Label(root, padding=(14, 2, 14, 8), justify="left", wraplength=1020)
        self.summary.pack(fill="x")
        root.bind("<Configure>", lambda e: e.widget is root and self.summary.config(wraplength=max(300, e.width - 40)))

        panes = ttk.PanedWindow(root, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=14)
        left = ttk.Frame(panes)
        self.tree = ttk.Treeview(left, columns=("info",), selectmode="browse")
        self.tree.heading("#0", text="Qué arranca", anchor="w")
        self.tree.heading("info", text="", anchor="w")
        self.tree.column("#0", width=320, stretch=True)
        self.tree.column("info", width=240, stretch=True)
        self.tree.tag_configure("group", font=self.bold)
        self.tree.tag_configure("new", foreground="#067647", font=self.bold)
        self.tree.tag_configure("off", foreground="#6b7280")
        for v, c in COLORS.items():
            self.tree.tag_configure(f"v:{v}", foreground=c)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")  # la barra primero: si falta sitio, que encoja la lista y no ella
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.show_selected())
        self.tree.bind("<Configure>", lambda _: self.fit_columns())
        panes.add(left, weight=3)

        right = ttk.Frame(panes)
        self.detail = tk.Text(
            right,
            wrap="word",
            relief="flat",
            padx=12,
            pady=10,
            width=44,
            font=base,
            background=root.cget("background") if sys.platform == "darwin" else "#ffffff",
        )
        self.detail.tag_configure("title", font=self.big, spacing3=2)
        self.detail.tag_configure("subtitle", foreground="#4b5563", spacing3=10)
        self.detail.tag_configure("label", foreground="#6b7280")
        self.detail.tag_configure("value", lmargin2=16, spacing3=4)
        self.detail.tag_configure("tip", foreground="#1f2937", spacing1=4, spacing3=4)
        dscroll = ttk.Scrollbar(right, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=dscroll.set, state="disabled")
        dscroll.pack(side="right", fill="y")
        self.detail.pack(side="left", fill="both", expand=True)
        panes.add(right, weight=2)

        bottom = ttk.Frame(root, padding=(14, 10, 14, 12))
        bottom.pack(fill="x")
        self.progress = ttk.Progressbar(bottom, mode="indeterminate", length=120)
        self.status = ttk.Label(bottom, foreground="#4b5563")
        self.status.pack(side="left")
        self.export_btn = ttk.Button(bottom, text="Exportar…", command=self.export)
        self.export_btn.pack(side="right")
        self.undo_btn = ttk.Button(bottom, text="Deshacer", command=self.undo)
        self.undo_btn.pack(side="right", padx=(0, 8))
        self.toggle_btn = ttk.Button(bottom, text="Que no arranque", command=self.toggle)
        self.toggle_btn.pack(side="right", padx=(0, 8))
        self.update_buttons()

    def update_buttons(self) -> None:
        ready = self.result is not None and not self.busy
        self.export_btn.state(["!disabled"] if ready else ["disabled"])
        self.undo_btn.state(["!disabled"] if ready and not self.is_demo else ["disabled"])
        entry = self.selected()
        can = ready and isinstance(entry, Entry) and report.can_toggle(entry) and not self.is_demo
        self.toggle_btn.state(["!disabled"] if can else ["disabled"])
        if isinstance(entry, Entry):
            self.toggle_btn.config(text="Volver a activar" if not entry.enabled else "Que no arranque")

    def selected(self):
        sel = self.tree.selection()
        return self.items.get(sel[0]) if sel else None

    def show_result(self, result: Result) -> None:
        self.result = result
        self.redraw()
        review = sum(1 for e in result.entries if e.verdict in (CHECK, BROKEN))
        new = sum(1 for e in result.entries if e.is_new)
        text = f"{report.headline(result)}\n{report.summary(result)}."
        extras = []
        if new:
            extras.append(f"{new} nuevo{'s' if new > 1 else ''} desde la última vez (en verde)")
        elif result.first_scan:
            extras.append("Es la primera vez que miro este ordenador: desde la próxima te diré qué ha aparecido")
        if review:
            extras.append(f"{review} para revisar (en rojo)")
        if extras:
            text += "\n" + ". ".join(extras) + "."
        self.summary.config(text=text)
        self.update_buttons()

    def redraw(self) -> None:
        if self.result is None:
            return
        remembered = self.selected()
        self.tree.delete(*self.tree.get_children())
        self.items.clear()
        axis = self.axis.get()
        entries = self.result.entries
        if not self.show_all.get():
            entries = [e for e in entries if e.verdict != KEEP or not e.enabled]
        order = {"verdict": VERDICTS, "when": WHEN}.get(axis)
        groups: dict = {}
        for e in entries:
            groups.setdefault(getattr(e, axis), []).append(e)
        keys = [k for k in order if k in groups] if order else sorted(groups, key=lambda k: -len(groups[k]))
        names = report.list_names(self.result.entries)
        for key in keys:
            node = self.tree.insert("", "end", text=f"{key}  ({len(groups[key])})", open=True, tags=("group",))
            for entry in groups[key]:
                tags = []
                if entry.is_new:
                    tags.append("new")
                elif entry.verdict in COLORS:
                    tags.append(f"v:{entry.verdict}")
                if not entry.enabled:
                    tags.append("off")
                info = self._info(entry, axis)
                name = names[entry.id] + ("  (desactivado)" if not entry.enabled else "")
                item = self.tree.insert(node, "end", text=name, values=(info,), tags=tags)
                self.items[item] = entry
        self.fit_columns()
        self.update_buttons()
        if remembered:
            for item, entry in self.items.items():
                if entry.id == remembered.id:
                    self.tree.selection_set(item)
                    break

    def fit_columns(self) -> None:
        """Reparte el ancho entre las dos columnas para que no se corte nada si cabe: se mide
        el nombre y el texto de la derecha («Hardware y controladores · al encender») más
        largos. Si no cabe todo, manda el nombre, y la de la derecha se queda con lo que sobra."""
        font = tkfont.nametofont("TkDefaultFont")
        names = max((font.measure(self.tree.item(i, "text")) for i in self.items), default=0) + 48
        infos = max((font.measure(self.tree.set(i, "info")) for i in self.items), default=0) + 24
        room = self.tree.winfo_width() - 4
        if room < 100:  # todavía sin dibujar
            room = names + infos
        info = max(min(infos, room - names), 140)
        self.tree.column("#0", width=max(room - info, 160), stretch=True)
        self.tree.column("info", width=info, minwidth=140, stretch=False)

    def _info(self, entry: Entry, axis: str) -> str:
        if axis == "verdict":
            return f"{entry.kind} · {entry.when.lower()}"
        if axis == "when":
            return f"{entry.verdict} · {entry.kind}"
        return f"{entry.verdict} · {entry.when.lower()}"

    def show_selected(self) -> None:
        entry = self.selected()
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if isinstance(entry, Entry):
            self.detail.insert("end", entry.display_name() + "\n", "title")
            self.detail.insert("end", f"{entry.verdict} · {entry.kind}\n", "subtitle")
            if entry.tip:
                self.detail.insert("end", entry.tip + "\n\n", "tip")
            for label, value in report.details(entry):
                if label in ("Consejo",):
                    continue
                self.detail.insert("end", f"{label}\n", "label")
                self.detail.insert("end", f"{value}\n", "value")
        self.detail.configure(state="disabled")
        self.update_buttons()

    # Acciones

    def rescan(self) -> None:
        if self.busy:
            return
        self.is_demo = False
        self.history = History()
        history = self.history
        self.in_background(lambda: scan.scan(history=history), self.show_result, "Mirando qué arranca…")

    def open_demo(self) -> None:
        if self.busy:
            return
        self.is_demo = True
        self.in_background(demo.result, self.show_result, "Cargando el ordenador de ejemplo…")

    def toggle(self) -> None:
        entry = self.selected()
        if not isinstance(entry, Entry) or not report.can_toggle(entry) or self.busy:
            return
        enable = not entry.enabled
        verb = "volver a activar" if enable else "desactivar"
        if not messagebox.askokcancel(
            "boot-scout",
            f"¿Quieres {verb} «{entry.display_name()}»?\n\nNo se borra nada y se puede deshacer.",
            parent=self.root,
        ):
            return
        was = entry.enabled
        try:
            log = apply.ChangeLog()
            message = apply.set_enabled(entry, enable)
            log.add(entry, was, enable)
            log.save()
        except apply.CantDo as exc:
            messagebox.showwarning("boot-scout", f"No se pudo: {exc}", parent=self.root)
            return
        self.status.config(text=message)
        self.redraw()
        self.show_selected()

    def undo(self) -> None:
        if self.busy:
            return
        try:
            message = apply.undo_last(apply.ChangeLog())
        except apply.CantDo as exc:
            messagebox.showinfo("boot-scout", str(exc), parent=self.root)
            return
        self.status.config(text=message)
        self.rescan()

    def export(self, path: str | None = None) -> None:
        if self.result is None or self.busy:
            return
        if path is None:
            path = filedialog.asksaveasfilename(
                parent=self.root,
                title="Guardar la lista",
                defaultextension=".json",
                initialfile=f"boot-scout-{self.result.started[:10]}.json",
                filetypes=[("JSON", "*.json"), ("Texto", "*.txt")],
            )
            if not path:
                return
        if path.endswith(".txt"):
            text = self.as_text()
        else:
            text = json.dumps(self.result.to_dict(), ensure_ascii=False, indent=2) + "\n"
        Path(path).write_text(text, encoding="utf-8")
        self.status.config(text=f"Guardado en {path}")

    def as_text(self) -> str:
        assert self.result is not None
        lines = [report.headline(self.result), report.summary(self.result), ""]
        for entry in self.result.entries:
            lines.append(f"{entry.display_name()}" + (" (nuevo)" if entry.is_new else ""))
            lines += [f"    {label}: {value}" for label, value in report.details(entry)]
            lines.append("")
        return "\n".join(lines)

    def about(self) -> None:
        messagebox.showinfo(
            "Acerca de boot-scout",
            f"boot-scout {__version__}\n\nLo que arranca con tu PC, qué es y si hace falta.\n\n"
            "https://github.com/espi0207/boot-scout",
            parent=self.root,
        )

    # Segundo plano

    def in_background(self, work, done, message: str) -> None:
        self.busy = True
        self.status.config(text=message)
        self.progress.pack(side="left", before=self.status, padx=(0, 10))
        self.progress.start(12)
        self.update_buttons()

        def worker():
            try:
                self.jobs.put((done, work(), None))
            except Exception as exc:  # noqa: BLE001
                self.jobs.put((done, None, exc))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self) -> None:
        try:
            while True:
                done, result, error = self.jobs.get_nowait()
                self.busy = False
                self.progress.stop()
                self.progress.pack_forget()
                if error:
                    self.status.config(text="")
                    messagebox.showerror("boot-scout", f"Algo ha fallado: {error}", parent=self.root)
                    self.update_buttons()
                else:
                    self.status.config(text="")
                    done(result)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)


def self_check() -> int:
    """Para la CI: abre la ventana con el ordenador de ejemplo, cambia de agrupación y
    exporta, sin que nadie toque nada. Así se sabe que la ventana funciona de verdad."""
    root = tk.Tk()
    app = App(root, scan_on_start=False)
    outcome = {"code": 1}
    steps = iter(["demo", "check"])

    def step():
        if app.busy:
            root.after(100, step)
            return
        which = next(steps)
        if which == "demo":
            app.open_demo()
            root.after(300, step)
            return
        try:
            rows = len(app.items)
            app.axis.set("when")
            app.redraw()
            new = next((i for i, e in app.items.items() if e.is_new), None)
            if new:
                app.tree.selection_set(new)
                app.show_selected()
            shown = app.detail.get("1.0", "end")
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "lista.json"
                app.export(str(out))
                data = json.loads(out.read_text(encoding="utf-8"))
            ok = rows > 5 and len(data["entries"]) == len(demo.entries()) and "Qué hacer" in shown
            outcome["code"] = 0 if ok else 1
        finally:
            root.destroy()

    root.after(500, step)
    root.after(60_000, root.destroy)
    root.mainloop()
    return outcome["code"]


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    if "--comprobar" in args:
        sys.exit(self_check())
    root = tk.Tk()
    app = App(root, scan_on_start="--demo" not in args)
    if "--demo" in args:
        root.after(200, app.open_demo)
    root.mainloop()


if __name__ == "__main__":
    main()
