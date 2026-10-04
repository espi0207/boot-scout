"""Uso desde la terminal. Sin nada más, enseña todo lo que arranca solo en este ordenador."""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap

from . import __version__, apply, demo, report, scan
from .ansi import clean, paint
from .entry import BROKEN, CHECK, KEEP, VERDICTS, WHEN
from .history import History
from .report import ago
from .scan import Result

AXES = {"veredicto": "verdict", "cuando": "when", "tipo": "kind"}


def _color(entry) -> str:
    return report.VERDICT_COLOR.get(entry.verdict, "gray")


def print_table(result: Result, axis: str, show_all: bool) -> None:
    entries = result.entries if show_all else [e for e in result.entries if e.verdict != KEEP or not e.enabled]
    hidden = len(result.entries) - len(entries)
    grouped = _group(entries, axis)
    for group, items in grouped:
        print("\n" + paint(f"{group}  ({len(items)})", "bold"))
        for entry in items:
            mark = report.VERDICT_MARK.get(entry.verdict, " ")
            name = clean(entry.display_name())
            tag = "" if entry.enabled else paint("  [desactivado]", "gray")
            new = paint("  ← nuevo", "green", "bold") if entry.is_new else ""
            extra = _secondary(entry, axis)
            line = f"  {paint(mark, _color(entry), 'bold')} {name}"
            if extra:
                line += paint(f"  · {extra}", "gray")
            print(line + tag + new)
    if hidden and not show_all:
        print(paint(f"\n(+{hidden} que puedes dejar como están; con --todo salen también)", "gray"))


def _secondary(entry, axis: str) -> str:
    """Lo que se enseña a la derecha, según por qué eje estemos agrupando."""
    if axis == "verdict":
        return f"{entry.kind} · {entry.when.lower()}"
    if axis == "when":
        return f"{entry.verdict} · {entry.kind}"
    return f"{entry.verdict} · {entry.when.lower()}"


def _group(entries, axis: str):
    order = {"verdict": VERDICTS, "when": WHEN}.get(axis)
    groups: dict = {}
    for entry in entries:
        groups.setdefault(getattr(entry, axis), []).append(entry)
    keys = [k for k in order if k in groups] if order else sorted(groups, key=lambda k: -len(groups[k]))
    return [(k, groups[k]) for k in keys]


def print_details(result: Result) -> None:
    for entry in result.entries:
        head = clean(entry.display_name())
        print("\n" + paint(head, "bold", _color(entry)) + (paint("  ← nuevo", "green", "bold") if entry.is_new else ""))
        rows = report.details(entry)
        width = max((len(label) for label, _ in rows), default=0) + 2
        for label, value in rows:
            lines = textwrap.wrap(clean(str(value)), width=max(40, 96 - width)) or [""]
            print(f"  {paint(label.ljust(width), 'gray')}{lines[0]}")
            for more in lines[1:]:
                print(f"  {' ' * width}{more}")


def print_result(result: Result, args) -> None:
    print(paint(report.headline(result), "bold"))
    print(paint(report.summary(result), "gray"))
    if args.detalle:
        print_details(result)
    else:
        print_table(result, AXES[args.agrupar], args.todo)
    review = [e for e in result.entries if e.verdict in (CHECK, BROKEN)]
    if review and not args.detalle:
        print("\n" + paint("Lo que conviene mirar:", "bold"))
        for entry in review:
            reason = entry.tip or (entry.reasons[0] if entry.reasons else "")
            text = f"{clean(entry.display_name())}: {clean(reason)}"
            print(
                "  "
                + paint(report.VERDICT_MARK.get(entry.verdict, "!"), _color(entry), "bold")
                + " "
                + "\n    ".join(textwrap.wrap(text, width=94))
            )
    new = [e for e in result.entries if e.is_new]
    if new:
        print(
            "\n"
            + paint(f"Nuevo desde la última vez: {len(new)}.", "green", "bold")
            + " Si no lo reconoces, mira su ficha con --detalle."
        )
    elif result.first_scan:
        print("\nEs la primera vez que miro este ordenador. Desde la próxima te diré qué ha aparecido nuevo.")
    if result.gone:
        print("\n" + paint("Antes arrancaba y ya no:", "bold"))
        for g in result.gone[:8]:
            print(f"  {clean(g.get('name', '?'))} ({g.get('where', '')}) — visto {ago(g.get('last_seen', ''))}")


def run_scan(args) -> int:
    history = History()
    result = scan.scan(history=history)
    return output(result, args)


def output(result: Result, args) -> int:
    result = _filter(result, args)
    if args.json:
        data = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        if args.json == "-":
            print(data)
            return 0
        with open(args.json, "w", encoding="utf-8") as f:
            f.write(data + "\n")
    print_result(result, args)
    if args.json:
        print(f"\nGuardado en {args.json}.")
    elif not args.detalle:
        print(paint("\nPara ver la ficha de cada cosa: boot-scout --detalle", "gray"))
    return 0


def _filter(result: Result, args) -> Result:
    entries = result.entries
    if args.tipo:
        entries = [e for e in entries if args.tipo.lower() in e.kind.lower()]
    if args.cuando:
        want = args.cuando.lower()
        entries = [e for e in entries if want in e.when.lower()]
    if args.revisar:
        entries = [e for e in entries if e.verdict in (CHECK, BROKEN)]
    filtered = Result(
        system=result.system,
        started=result.started,
        seconds=result.seconds,
        first_scan=result.first_scan,
        entries=entries,
        gone=result.gone,
    )
    return filtered


def _find(result: Result, who: str):
    who = who.strip().lower()
    for entry in result.entries:
        if who in (entry.id.lower(), entry.name.lower(), entry.display_name().lower()):
            return entry
    for entry in result.entries:  # por coincidencia parcial del nombre
        if who in entry.display_name().lower():
            return entry
    return None


def run_toggle(args, enable: bool) -> int:
    who = args.activar if enable else args.desactivar
    result = scan.scan()
    entry = _find(result, who)
    if entry is None:
        print(f"No encuentro «{who}». Mira la lista con boot-scout, y usa el nombre tal cual.", file=sys.stderr)
        return 1
    if not report.can_toggle(entry):
        print(f"No puedo cambiar «{clean(entry.display_name())}» desde aquí.", file=sys.stderr)
        if entry.hint:
            print(f"  {clean(entry.hint)}", file=sys.stderr)
        return 1
    was = entry.enabled
    try:
        log = apply.ChangeLog()
        message = apply.set_enabled(entry, enable)
        log.add(entry, was, enable)
        log.save()
    except apply.CantDo as exc:
        print(f"No se pudo: {exc}", file=sys.stderr)
        return 1
    print(paint(message, "green"))
    print("Para deshacerlo: boot-scout --deshacer")
    return 0


def run_undo() -> int:
    try:
        print(paint(apply.undo_last(apply.ChangeLog()), "green"))
    except apply.CantDo as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = argparse.ArgumentParser(
        prog="boot-scout",
        description="Enseña todo lo que arranca solo al encender el ordenador (programas, servicios, tareas "
        "programadas…), qué es cada cosa y si hace falta. Solo mira: no cambia nada salvo que se lo pidas.",
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--demo", action="store_true", help="un ordenador de ejemplo, sin mirar el tuyo")
    action.add_argument("--desactivar", metavar="NOMBRE", help="que algo tuyo deje de arrancar (reversible)")
    action.add_argument("--activar", metavar="NOMBRE", help="volver a activar algo que desactivaste")
    action.add_argument("--deshacer", action="store_true", help="deshacer el último cambio")
    parser.add_argument("--detalle", action="store_true", help="la ficha completa de cada cosa")
    parser.add_argument(
        "--agrupar", choices=list(AXES), default="veredicto", help="agrupar por veredicto (por defecto), cuando o tipo"
    )
    parser.add_argument("--todo", action="store_true", help="enseñar también lo que puedes dejar como está")
    parser.add_argument("--revisar", action="store_true", help="solo lo que conviene mirar")
    parser.add_argument("--tipo", metavar="TIPO", help="solo de un tipo (actualizador, juegos, hardware…)")
    parser.add_argument("--cuando", metavar="CUÁNDO", help="solo de un momento (encender, sesión, programado…)")
    parser.add_argument("--json", metavar="ARCHIVO", help="guardarlo todo en JSON (- para sacarlo por pantalla)")
    parser.add_argument("--version", action="version", version=f"boot-scout {__version__}")
    args = parser.parse_args(argv)

    try:
        if args.demo:
            return output(demo.result(), args)
        if args.desactivar is not None:
            return run_toggle(args, enable=False)
        if args.activar is not None:
            return run_toggle(args, enable=True)
        if args.deshacer:
            return run_undo()
        return run_scan(args)
    except BrokenPipeError:
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        print("\nCancelado.", file=sys.stderr)
        return 130
    except OSError as exc:
        print(f"No se puede seguir: {exc.strerror or exc}.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
