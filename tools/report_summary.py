#!/usr/bin/env python3
"""Riassunto compatto dei report JSON di ERC/DRC di kicad-cli.

Uso: tools/report_summary.py [--max N] report.json [altro.json ...]
Stampa conteggi per gravità e per tipo, poi i primi N problemi (errori prima dei warning)
con descrizione, elementi coinvolti e coordinate. Gestisce le sezioni
violations / unconnected_items / schematic_parity e i fogli dell'ERC.
Uscita 1 se c'è almeno un errore.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

SEV_ORDER = {"error": 0, "warning": 1, "info": 2, "exclusion": 3, "ignore": 4}


def collect(report: dict) -> list[dict]:
    """Restituisce una lista piatta di problemi con la sezione di provenienza."""
    items = []
    for sheet in report.get("sheets", []):  # ERC
        for v in sheet.get("violations", []):
            items.append({**v, "_section": "erc", "_where": sheet.get("path", "/")})
    for sec in ("violations", "unconnected_items", "schematic_parity"):  # DRC
        for v in report.get(sec, []):
            items.append({**v, "_section": sec, "_where": ""})
    return items


def fmt_item(it: dict, units: str) -> str:
    pos = it.get("pos") or {}
    xy = f"({pos.get('x', 0):.2f}, {pos.get('y', 0):.2f}){units}" if pos else ""
    return f"{it.get('description', '?')} {xy}".strip()


def summarize(path: Path, maxn: int) -> int:
    try:
        rep = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"{path.name}: impossibile leggere ({e})")
        return 1
    kind = "ERC" if "sheets" in rep else "DRC"
    units = rep.get("coordinate_units", "mm")
    units = "mm" if units in ("mm", "millimeters") else f" {units}"
    items = collect(rep)
    active = [i for i in items if not i.get("excluded")]
    sev = Counter(i.get("severity", "?") for i in active)
    nerr = sev.get("error", 0)
    head = f"== {kind}: {nerr} errori, {sev.get('warning', 0)} warning"
    if sev.get("info"):
        head += f", {sev['info']} info"
    excl = len(items) - len(active)
    if excl:
        head += f", {excl} esclusi"
    print(head + f"  ({path.relative_to(Path.cwd()) if path.is_relative_to(Path.cwd()) else path})")
    if kind == "DRC":
        parts = []
        for sec, label in (("violations", "violazioni"), ("unconnected_items", "non connessi"),
                           ("schematic_parity", "parità schema-PCB")):
            n = sum(1 for i in active if i["_section"] == sec)
            parts.append(f"{label}: {n}")
        print("   " + " | ".join(parts))
    if not active:
        return 0
    types = Counter((i.get("severity", "?"), i.get("type", "?")) for i in active)
    print("   per tipo: " + ", ".join(f"{t} [{s[0].upper()}] x{n}" for (s, t), n in
                                       sorted(types.items(), key=lambda kv: (SEV_ORDER.get(kv[0][0], 9), -kv[1]))))
    active.sort(key=lambda i: SEV_ORDER.get(i.get("severity"), 9))
    for n, it in enumerate(active[:maxn], 1):
        where = f" [foglio {it['_where']}]" if it.get("_where") not in ("", "/") else ""
        print(f"  {n:2}. {it.get('severity', '?')[0].upper()} {it.get('type', '?')}: {it.get('description', '')}{where}")
        for el in it.get("items", [])[:4]:
            print(f"        - {fmt_item(el, units)}")
        if len(it.get("items", [])) > 4:
            print(f"        - ... altri {len(it['items']) - 4}")
    if len(active) > maxn:
        print(f"  ... altri {len(active) - maxn} problemi nel file JSON")
    return 1 if nerr else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reports", nargs="+", type=Path)
    ap.add_argument("--max", type=int, default=15, help="numero massimo di problemi da elencare (default 15)")
    a = ap.parse_args()
    rc = 0
    for p in a.reports:
        rc |= summarize(p.resolve(), a.max)
    print("ESITO: " + ("ERRORI da correggere" if rc else "nessun errore"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
