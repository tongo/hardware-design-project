#!/usr/bin/env python3
"""Pacchetto di produzione JLCPCB in production/.

Uso: tools/jlc_export.py [dir-progetto] [--qty 5] [--no-render]

Crea:
  production/<nome>-gerber.zip   Gerber (estensioni Protel) + foratura Excellon (mm, decimali, PTH/NPTH separati, mappa)
  production/<nome>-bom.csv      Comment, Designator, Footprint, JLCPCB Part #  (senza DNP e componenti senza LCSC)
  production/<nome>-cpl.csv      Designator, Mid X, Mid Y, Layer, Rotation      (solo componenti della BOM)
  production/ORDINE.md           checklist d'ordine con i dati reali della scheda
  production/<nome>-top.png / -bottom.png   render
Impostazioni Gerber e foratura secondo la guida JLCPCB per KiCad (verificata il 2026-11-21).
"""
import argparse
import csv
import io
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwproj import ProjectError, build_dir, find_project, repo_root  # noqa: E402
from jlc_parts import export_bom  # noqa: E402

TOOLS = Path(__file__).resolve().parent
ROT_FILE = TOOLS / "jlc_rotations.csv"
CHECK_PIN1 = re.compile(r"^(U|IC|D|LED|Q|J|P|CN|X|Y|SW|BT|M|MOD)\d", re.I)


def die(msg, code=2):
    print(f"ERRORE: {msg}", file=sys.stderr)
    sys.exit(code)


def run(cmd: list[str], what: str):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        die(f"{what}: {(r.stderr or r.stdout).strip()[:500]}")
    return r


def load_rotations() -> list[tuple[re.Pattern, float, str]]:
    rules = []
    if not ROT_FILE.exists():
        return rules
    for line in ROT_FILE.read_text().splitlines():
        line = line.split("  #")[0].strip()
        if not line or line.startswith("#") or line.startswith("pattern,"):
            continue
        pat, _, deg = line.rpartition(",")
        try:
            rules.append((re.compile(pat), float(deg), pat))
        except (re.error, ValueError):
            print(f"  ATTENZIONE: riga non valida in jlc_rotations.csv: {line}")
    return rules


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--qty", type=int, default=5, help="numero di schede da ordinare (per ORDINE.md)")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    try:
        prj = find_project(a.dir)
    except ProjectError as e:
        die(str(e))
    if not prj["pcb"] or not prj["sch"]:
        die("servono schema e PCB")
    name, pcb = prj["name"], str(prj["pcb"])
    prod = repo_root() / "production"
    prod.mkdir(exist_ok=True)
    warnings = []

    import pcbnew
    board = pcbnew.LoadBoard(pcb)
    ncu = board.GetCopperLayerCount()
    # dimensioni dal contorno (linea centrale del bordo), non dall'ingombro che include lo spessore della linea
    outline = pcbnew.SHAPE_POLY_SET()
    if board.GetBoardPolygonOutlines(outline, False) and outline.OutlineCount():
        bb = outline.BBox()
    else:
        bb = board.GetBoardEdgesBoundingBox()
    w, h = pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight())
    thick = pcbnew.ToMM(board.GetDesignSettings().GetBoardThickness())
    if w <= 0 or h <= 0:
        warnings.append("bordo scheda (Edge.Cuts) assente o non chiuso")

    # 1. Gerber + foratura
    gdir = build_dir("gerber")
    shutil.rmtree(gdir)
    gdir.mkdir(parents=True)
    layers = ["F.Cu"] + [f"In{i}.Cu" for i in range(1, ncu - 1)] + ["B.Cu", "F.Paste", "B.Paste",
              "F.Silkscreen", "B.Silkscreen", "F.Mask", "B.Mask", "Edge.Cuts"]
    run(["kicad-cli", "pcb", "export", "gerbers", pcb, "-o", str(gdir) + "/", "-l", ",".join(layers),
         "--subtract-soldermask", "--check-zones"], "export gerbers")
    run(["kicad-cli", "pcb", "export", "drill", pcb, "-o", str(gdir) + "/", "--format", "excellon",
         "--drill-origin", "absolute", "--excellon-zeros-format", "decimal", "--excellon-oval-format", "alternate",
         "-u", "mm", "--excellon-separate-th", "--generate-map", "--map-format", "gerberx2"], "export drill")
    gzip = prod / f"{name}-gerber.zip"
    npth = next(gdir.glob("*-NPTH.drl"), None)
    if npth and not re.search(r"^T\d+C", npth.read_text(), re.M):  # nessun foro non metallizzato
        for p in gdir.glob("*-NPTH*"):
            p.unlink()
    files = sorted(p for p in gdir.iterdir() if p.is_file() and p.suffix != ".gbrjob")
    with zipfile.ZipFile(gzip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.name)

    # 2. BOM
    bom = export_bom(prj)
    jlc_rows, hand, dnp = [], [], []
    mounted = set()
    for it in bom:
        refs = it["refs"]
        if it["dnp"]:
            dnp += refs
            continue
        if not it["lcsc"]:
            hand += refs
            continue
        mounted.update(refs)
        jlc_rows.append([it["value"], ",".join(refs), it["footprint"].split(":")[-1], it["lcsc"].upper()])
    bom_csv = prod / f"{name}-bom.csv"
    with open(bom_csv, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["Comment", "Designator", "Footprint", "JLCPCB Part #"])
        wr.writerows(jlc_rows)

    # 3. CPL
    pos = build_dir("bom") / f"{name}-pos.csv"
    run(["kicad-cli", "pcb", "export", "pos", pcb, "--format", "csv", "--units", "mm", "--side", "both",
         "-o", str(pos)], "export pos")
    rules = load_rotations()
    cpl_rows, rotated, check_list, bottom_smd = [], [], [], []
    seen = set()
    for r in csv.DictReader(io.StringIO(pos.read_text())):
        ref = r["Ref"]
        if ref not in mounted:
            continue
        seen.add(ref)
        rot = float(r["Rot"])
        for rx, deg, pat in rules:
            if rx.search(r["Package"]):
                rot = (rot + deg) % 360
                rotated.append(f"{ref} ({r['Package']}: {pat} {deg:+g}°)")
                break
        layer = "Top" if r["Side"].lower().startswith("top") else "Bottom"
        if layer == "Bottom":
            bottom_smd.append(ref)
        if CHECK_PIN1.match(ref):
            check_list.append(ref)
        cpl_rows.append([ref, f"{float(r['PosX']):.4f}mm", f"{float(r['PosY']):.4f}mm", layer, f"{rot:g}"])
    missing_pos = sorted(mounted - seen)
    if missing_pos:
        warnings.append(f"componenti in BOM senza posizione nel PCB: {', '.join(missing_pos)}")
    if bottom_smd:
        warnings.append(f"componenti sul lato Bottom (Economic PCBA monta un solo lato): {', '.join(bottom_smd)}")
    cpl_csv = prod / f"{name}-cpl.csv"
    with open(cpl_csv, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
        wr.writerows(cpl_rows)

    # 5. Render
    renders = []
    if not a.no_render:
        r = subprocess.run([str(TOOLS / "render.sh"), str(prj["dir"]), "--no-sch"], capture_output=True, text=True)
        for side in ("top", "bottom"):
            src = repo_root() / "build" / "render" / f"pcb-{side}.png"
            if src.exists():
                dst = prod / f"{name}-{side}.png"
                shutil.copyfile(src, dst)
                renders.append(dst.name)
        if r.returncode != 0:
            warnings.append("render non riuscito (vedi build/render/render.log)")

    # 4. ORDINE.md
    surface = "HASL lead-free (economico; ENIG se ci sono componenti a passo fine < 0,5 mm o BGA)"
    md = f"""# Ordine JLCPCB – {name}

Generato il {time.strftime('%Y-%m-%d %H:%M')} da `tools/jlc_export.py`. Commit: `{subprocess.run(['git', '-C', str(repo_root()), 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip() or 'nessuno'}`

## File da caricare

| File | Dove |
|---|---|
| `{gzip.name}` | Add gerber file |
| `{bom_csv.name}` | PCB Assembly → BOM |
| `{cpl_csv.name}` | PCB Assembly → CPL |

## PCB

| Opzione | Valore | Note |
|---|---|---|
| Base material | FR-4 | |
| Layers | {ncu} | |
| Dimensions | {w:.1f} × {h:.1f} mm | dal bordo scheda; JLC le rilegge dal Gerber: devono coincidere |
| PCB Qty | {a.qty} | **da confermare** |
| Product type | Industrial/Consumer electronics | |
| PCB thickness | {thick:.1f} mm | |
| PCB color | Green | economico, compatibile con Economic PCBA |
| Surface finish | **da scegliere** | proposta: {surface} |
| Outer copper weight | 1 oz | |
| Via covering | Tented | |
| Mark on PCB | **da scegliere** | "Remove mark" costa di più; altrimenti JLC stampa un numero sulla serigrafia |

## PCB Assembly

| Opzione | Valore |
|---|---|
| PCBA type | Economic |
| Assembly side | Top |
| PCBA Qty | **da confermare** (≤ {a.qty}) |
| Tooling holes | Added by JLCPCB |
| Confirm parts placement | Yes |

## Componenti

- Montati da JLC: {len(cpl_rows)} posizioni, {len(jlc_rows)} righe di BOM.
- Da saldare a mano (senza codice LCSC): {', '.join(hand) or 'nessuno'}
- Non montati (DNP): {', '.join(dnp) or 'nessuno'}
- Rotazioni corrette automaticamente: {', '.join(rotated) or 'nessuna'}

## Controlli durante l'ordine

- [ ] Pagina dei componenti: nessun componente mancante o sostituito, stock sufficiente (`tools/jlc_parts.py check-bom --qty {a.qty}`).
- [ ] Anteprima di posizionamento: pin 1 e polarità di: **{', '.join(check_list) or 'nessun componente polarizzato'}**.
- [ ] Costo degli Extended coerente con il report `build/reports/bom-check.md`.
- [ ] Le dimensioni lette da JLC coincidono con {w:.1f} × {h:.1f} mm.

Le regole e i prezzi di JLC cambiano: se qualcosa nel modulo non corrisponde a questa checklist, fermati e chiedi.

## Registro dell'ordine

- Data:
- Numero d'ordine:
- Correzioni di rotazione fatte nell'anteprima (riportarle in `tools/jlc_rotations.csv`):
"""
    if warnings:
        md += "\n## Avvisi\n\n" + "\n".join(f"- {x}" for x in warnings) + "\n"
    (prod / "ORDINE.md").write_text(md)

    print(f"Pacchetto JLC per {name} in production/:")
    print(f"  {gzip.name} ({len(files)} file: {ncu} layer rame, foratura, mappa)")
    print(f"  {bom_csv.name} ({len(jlc_rows)} righe)  {cpl_csv.name} ({len(cpl_rows)} posizioni)  ORDINE.md"
          + (f"  {' '.join(renders)}" if renders else ""))
    print(f"  scheda {w:.1f} × {h:.1f} mm, {ncu} layer, spessore {thick:.1f} mm")
    print(f"  rotazioni corrette: {len(rotated)}; da saldare a mano: {', '.join(hand) or '-'}; DNP: {', '.join(dnp) or '-'}")
    for x in warnings:
        print(f"  ATTENZIONE: {x}")
    return 1 if warnings else 0


if __name__ == "__main__":
    sys.exit(main())
