#!/usr/bin/env python3
"""Genera (o rigenera) uno schema KiCad da una descrizione JSON, senza interfaccia grafica.

Uso: tools/sch_gen.py <descrizione.json> [--out hardware/<nome>/<nome>.kicad_sch]

Ogni pin elencato riceve un pezzo di filo e un'etichetta (label) con il nome della net:
pin con la stessa etichetta sono collegati. Pin con net "NC" ricevono il simbolo di non connesso;
i pin non elencati restano scollegati (l'ERC li segnalerà). Il risultato è normalizzato con
'kicad-cli sch upgrade', quindi è nel formato della versione installata e si apre con l'app sul Mac.

Formato JSON (coordinate in mm, multipli di 2.54; rot = 0/90/180/270):
{
  "name": "prova", "title": "Scheda di prova", "rev": "0.1",
  "symbols": [
    {"ref": "R1", "lib": "Device:R", "value": "1k", "footprint": "Resistor_SMD:R_0603_1608Metric",
     "at": [101.6, 76.2], "rot": 0, "unit": 1,
     "fields": {"LCSC": "C21190", "MPN": "0603WAF1001T5E"},
     "pins": {"1": "VIN", "2": "LED_A"}}
  ],
  "power_flags": ["VIN", "GND"],
  "notes": [{"text": "Circuito da datasheet X rev A pag. 12", "at": [30, 30]}]
}
ATTENZIONE: rigenerare lo schema sovrascrive le modifiche fatte a mano nell'app. Gli UUID dei simboli
restano stabili tra una generazione e l'altra (derivano da nome progetto + riferimento), così il PCB resta allineato.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sexp import Q, dumps, find, find_all, parse  # noqa: E402

SYM_DIRS = [Path(os.environ.get("KICAD10_SYMBOL_DIR", "/usr/share/kicad/symbols"))]
TEMPLATE_PRO = Path("/usr/share/kicad/template/kicad.kicad_pro")
_lib_cache: dict[str, list] = {}


def die(msg):
    print(f"ERRORE: {msg}", file=sys.stderr)
    sys.exit(1)


def uid(*parts) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "hw-sch-gen/" + "/".join(map(str, parts))))


def load_lib(nick: str, project_dir: Path) -> list:
    if nick in _lib_cache:
        return _lib_cache[nick]
    cands = [project_dir / f"{nick}.kicad_sym", project_dir / "lib" / f"{nick}.kicad_sym"] + \
            [d / f"{nick}.kicad_sym" for d in SYM_DIRS]
    for c in cands:
        if c.exists():
            _lib_cache[nick] = parse(c.read_text())
            return _lib_cache[nick]
    die(f"libreria di simboli '{nick}' non trovata (cercata in {', '.join(str(c.parent) for c in cands)})")


def lib_symbol(lib_id: str, project_dir: Path) -> list:
    """Definizione del simbolo pronta per lib_symbols (nome 'Lib:Nome', 'extends' risolto)."""
    nick, name = lib_id.split(":", 1)
    lib = load_lib(nick, project_dir)
    syms = {s[1]: s for s in find_all(lib, "symbol")}
    if name not in syms:
        die(f"simbolo '{name}' non trovato nella libreria '{nick}'")
    s = syms[name]
    ext = find(s, "extends")
    if ext:
        parent = syms.get(ext[1])
        if parent is None:
            die(f"{lib_id}: simbolo padre '{ext[1]}' non trovato")
        props = {p[1]: p for p in find_all(s, "property")}
        out = [c for c in parent if not (isinstance(c, list) and c and c[0] == "property" and c[1] in props)]
        out = [c for c in out if not (isinstance(c, list) and c and c[0] == "extends")]
        out += list(props.values())
        for c in out:
            if isinstance(c, list) and c and c[0] == "symbol" and isinstance(c[1], str):
                c[1] = Q(name + c[1][len(ext[1]):])
        s = out
    s = [c for c in s]  # copia superficiale
    s[1] = Q(lib_id)
    return s


def pins_of(sym: list, unit: int) -> dict:
    """{numero: (x, y, angolo, tipo)} dei pin del simbolo (coordinate della libreria, Y verso l'alto)."""
    out = {}
    base = str(sym[1]).split(":", 1)[1]
    for sub in find_all(sym, "symbol"):
        tail = str(sub[1])[len(base) + 1:]
        try:
            u = int(tail.split("_")[0])
        except ValueError:
            u = 0
        if u not in (0, unit):
            continue
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            num = find(p, "number")
            out[str(num[1])] = (float(at[1]), float(at[2]), float(at[3]) if len(at) > 3 else 0.0, p[1])
    return out


def rot(x, y, deg):
    """Ruota (x, y) in coordinate schermo (Y verso il basso) di deg gradi in senso antiorario."""
    r = math.radians(deg)
    return (round(x * math.cos(r) + y * math.sin(r), 4), round(-x * math.sin(r) + y * math.cos(r), 4))


def effects(hide=False, justify=None, size=1.27):
    e = ["effects", ["font", ["size", size, size]]]
    if justify:
        e.append(["justify", *justify])
    if hide:
        e.append(["hide", "yes"])
    return e


def build(spec: dict, out: Path) -> list:
    name = spec.get("name") or out.stem
    root = uid(name, "root")
    pdir = out.parent
    libs, items = {}, []
    stub = 2.54

    def add_label(net, x, y, ang):
        just = {0: ["left", "bottom"], 90: ["left", "bottom"], 180: ["right", "bottom"], 270: ["right", "bottom"]}[ang]
        items.append(["label", Q(net), ["at", x, y, ang], ["fields_autoplaced", "yes"],
                      effects(justify=just), ["uuid", Q(uid(name, "label", net, x, y))]])

    def add_wire(x1, y1, x2, y2):
        items.append(["wire", ["pts", ["xy", x1, y1], ["xy", x2, y2]], ["stroke", ["width", 0], ["type", "default"]],
                      ["uuid", Q(uid(name, "wire", x1, y1, x2, y2))]])

    symbols = list(spec.get("symbols", []))
    # PWR_FLAG automatici, in colonna a sinistra
    for i, net in enumerate(spec.get("power_flags", [])):
        symbols.append({"ref": f"#FLG{i + 1:02d}", "lib": "power:PWR_FLAG", "value": "PWR_FLAG",
                        "at": [25.4, 25.4 + 12.7 * i], "rot": 0, "pins": {"1": net}, "_power": True})

    for s in symbols:
        lib_id, ref = s["lib"], s["ref"]
        if lib_id not in libs:
            libs[lib_id] = lib_symbol(lib_id, pdir)
        lsym = libs[lib_id]
        unit = int(s.get("unit", 1))
        X, Y = float(s["at"][0]), float(s["at"][1])
        angle = int(s.get("rot", 0)) % 360
        is_power = s.get("_power") or find(lsym, "power") is not None
        pins = pins_of(lsym, unit)
        props = {str(p[1]): p for p in find_all(lsym, "property")}
        sid = uid(name, "sym", ref)
        inst = ["symbol", ["lib_id", Q(lib_id)], ["at", X, Y, angle], ["unit", unit],
                ["exclude_from_sim", "no"], ["in_bom", "no" if is_power else "yes"],
                ["on_board", "no" if is_power else "yes"], ["dnp", "yes" if s.get("dnp") else "no"],
                ["uuid", Q(sid)]]
        fields = {"Reference": ref, "Value": s.get("value") or str(props.get("Value", [0, 0, ""])[2]),
                  "Footprint": s.get("footprint", str(props.get("Footprint", [0, 0, ""])[2])),
                  "Datasheet": s.get("datasheet", str(props.get("Datasheet", [0, 0, ""])[2]))}
        if "Description" in props:
            fields["Description"] = str(props["Description"][2])
        fields.update(s.get("fields", {}))
        ys = [p[1] for p in pins.values()] or [0]
        top, bot = Y - max(ys) - 2.54, Y - min(ys) + 2.54
        for k, v in fields.items():
            if k == "Reference":
                at, hide = [X + 2.54, top, 0], is_power
            elif k == "Value":
                at, hide = [X + 2.54, bot, 0], False
            else:
                at, hide = [X, Y, 0], True
            inst.append(["property", Q(k), Q(str(v)), ["at", *at], effects(hide=hide, justify=["left"])])
        for num in pins:
            inst.append(["pin", Q(num), ["uuid", Q(uid(name, "pin", ref, num))]])
        inst.append(["instances", ["project", Q(name), ["path", Q("/" + root), ["reference", Q(ref)], ["unit", unit]]]])
        items.append(inst)

        for num, net in s.get("pins", {}).items():
            if str(num) not in pins:
                die(f"{ref}: il simbolo {lib_id} non ha il pin '{num}' (pin: {', '.join(sorted(pins))})")
            px, py, pa, _ptype = pins[str(num)]
            ox, oy = rot(px, -py, angle)
            cx, cy = round(X + ox, 4), round(Y + oy, 4)
            if str(net).upper() == "NC":
                items.append(["no_connect", ["at", cx, cy], ["uuid", Q(uid(name, "nc", ref, num))]])
                continue
            dx, dy = rot(-math.cos(math.radians(pa)), math.sin(math.radians(pa)), angle)
            ex, ey = round(cx + dx * stub, 4), round(cy + dy * stub, 4)
            add_wire(cx, cy, ex, ey)
            lang = {(-1, 0): 180, (1, 0): 0, (0, -1): 90, (0, 1): 270}[(round(dx), round(dy))]
            add_label(str(net), ex, ey, lang)

    for i, n in enumerate(spec.get("notes", [])):
        items.append(["text", Q(n["text"]), ["exclude_from_sim", "no"], ["at", n["at"][0], n["at"][1], 0],
                      effects(justify=["left", "bottom"]), ["uuid", Q(uid(name, "note", i))]])

    doc = ["kicad_sch", ["version", 20231120], ["generator", Q("hw_sch_gen")], ["generator_version", Q("10.0")],
           ["uuid", Q(root)], ["paper", Q(spec.get("paper", "A4"))],
           ["title_block", ["title", Q(spec.get("title", name))], ["date", Q(spec.get("date", date.today().isoformat()))],
            ["rev", Q(spec.get("rev", "0.1"))]],
           ["lib_symbols", *libs.values()], *items,
           ["sheet_instances", ["path", Q("/"), ["page", Q("1")]]]]
    return doc


def ensure_project(out: Path):
    pro = out.with_suffix(".kicad_pro")
    if pro.exists():
        return
    if TEMPLATE_PRO.exists():
        data = json.loads(TEMPLATE_PRO.read_text())
        data.setdefault("meta", {})["filename"] = pro.name
        pro.write_text(json.dumps(data, indent=2) + "\n")
    else:
        pro.write_text(json.dumps({"meta": {"filename": pro.name, "version": 3}}, indent=2) + "\n")
    print(f"Creato {pro}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec", type=Path)
    ap.add_argument("--out", type=Path, help="default: hardware/<name>/<name>.kicad_sch")
    a = ap.parse_args()
    spec = json.loads(a.spec.read_text())
    name = spec.get("name") or a.spec.stem
    out = a.out or Path(__file__).resolve().parent.parent / "hardware" / name / f"{name}.kicad_sch"
    out.parent.mkdir(parents=True, exist_ok=True)
    ensure_project(out)
    if out.exists():
        shutil.copyfile(out, out.with_suffix(".kicad_sch.bak"))
    out.write_text(dumps(build(spec, out)) + "\n")
    r = subprocess.run(["kicad-cli", "sch", "upgrade", "--force", str(out)], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"kicad-cli sch upgrade: {(r.stderr or r.stdout).strip()[:500]}")
    print(f"Schema scritto: {out} ({len(spec.get('symbols', []))} simboli). Ora: tools/check.sh {out.parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
