#!/usr/bin/env python3
"""Trova il progetto KiCad (l'unico .kicad_pro) in una cartella. Modulo comune agli script di tools/.

Uso da riga di comando:
  tools/hwproj.py [dir]            stampa i percorsi del progetto
  tools/hwproj.py --shell [dir]    stampa variabili per bash (eval "$(tools/hwproj.py --shell dir)")
Uscita 2 se non c'è nessun progetto o se ce n'è più di uno (in quel caso indicare la sottocartella).
"""
import os
import shlex
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP_PARTS = ("-backups", "/build/", "/production/", "/.git/")


class ProjectError(Exception):
    pass


def repo_root() -> Path:
    return REPO


def build_dir(sub: str = "") -> Path:
    d = REPO / "build" / sub if sub else REPO / "build"
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_project(directory: str | None = None) -> dict:
    base = Path(directory) if directory else REPO / "hardware"
    if not base.is_absolute():
        base = (Path.cwd() / base).resolve()
    if base.is_file() and base.suffix == ".kicad_pro":
        pros = [base]
    else:
        if not base.is_dir():
            raise ProjectError(f"cartella non trovata: {base}")
        pros = sorted(p for p in base.glob("*.kicad_pro"))
        if not pros:
            pros = sorted(p for p in base.rglob("*.kicad_pro")
                          if not any(s in str(p) + "/" for s in SKIP_PARTS))
    if not pros:
        raise ProjectError(f"nessun file .kicad_pro in {base}")
    if len(pros) > 1:
        lst = "\n".join(f"  {p.parent.relative_to(REPO) if p.is_relative_to(REPO) else p.parent}" for p in pros)
        raise ProjectError(f"più progetti trovati, indica quale cartella usare:\n{lst}")
    pro = pros[0]
    d = pro.parent
    name = pro.stem
    sch = d / f"{name}.kicad_sch"
    pcb = d / f"{name}.kicad_pcb"
    dru = d / f"{name}.kicad_dru"
    return {
        "dir": d, "name": name, "pro": pro,
        "sch": sch if sch.exists() else None,
        "pcb": pcb if pcb.exists() else None,
        "dru": dru if dru.exists() else None,
    }


def main(argv: list[str]) -> int:
    shell = "--shell" in argv
    args = [a for a in argv if a != "--shell"]
    if args and args[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    try:
        p = find_project(args[0] if args else None)
    except ProjectError as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 2
    if shell:
        for k in ("dir", "name", "pro", "sch", "pcb", "dru"):
            v = "" if p[k] is None else str(p[k])
            print(f"PRJ_{k.upper()}={shlex.quote(v)}")
    else:
        for k, v in p.items():
            print(f"{k:5}: {v if v is not None else '(manca)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
