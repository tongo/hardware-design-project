#!/usr/bin/env python3
"""Aggiorna il PCB dallo schema senza interfaccia grafica (equivalente di "Aggiorna PCB da schema", F8).

Uso: tools/sch_to_pcb.py [dir-progetto] [--delete-extra] [--dry-run]

- esporta la netlist con kicad-cli;
- crea il PCB se non esiste (2 layer);
- aggiunge i footprint mancanti (in fila sotto l'area della scheda: poi vanno posizionati con uno script);
- aggiorna valore, campi, collegamento al simbolo (parità schema-PCB) e net di ogni pad;
- segnala i footprint cambiati (li sostituisce mantenendo posizione e lato) e quelli in più nel PCB
  (li cancella solo con --delete-extra).
Fare un commit git prima di lanciarlo e chiudere il PCB nell'app sul Mac.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwproj import ProjectError, build_dir, find_project  # noqa: E402
from sexp import find, find_all, parse  # noqa: E402

FP_DIR = Path(os.environ.get("KICAD10_FOOTPRINT_DIR", "/usr/share/kicad/footprints"))
SKIP_FIELDS = {"Reference", "Value", "Footprint"}


def die(msg, code=2):
    print(f"ERRORE: {msg}", file=sys.stderr)
    sys.exit(code)


def read_netlist(prj) -> tuple[list[dict], dict]:
    net = build_dir("netlist") / f"{prj['name']}.net"
    r = subprocess.run(["kicad-cli", "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(net),
                        str(prj["sch"])], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"export netlist: {(r.stderr or r.stdout).strip()[:400]}")
    t = parse(net.read_text())
    comps = []
    for c in find_all(find(t, "components"), "comp"):
        sp = find(c, "sheetpath")
        tst = find(c, "tstamps")
        fields = {}
        fl = find(c, "fields")
        if fl:
            for f in find_all(fl, "field"):
                nm = find(f, "name")
                fields[str(nm[1])] = str(f[2]) if len(f) > 2 and not isinstance(f[2], list) else ""
        props = {str(find(p, "name")[1]): str(find(p, "value")[1]) if find(p, "value") else ""
                 for p in find_all(c, "property")}
        comps.append({
            "ref": str(find(c, "ref")[1]),
            "value": str(find(c, "value")[1]) if find(c, "value") else "",
            "footprint": str(find(c, "footprint")[1]) if find(c, "footprint") else "",
            "path": str(find(sp, "tstamps")[1]) + str(tst[1]),
            "sheetname": str(find(sp, "names")[1]),
            "fields": fields, "props": props,
        })
    nets = {}
    for n in find_all(find(t, "nets"), "net"):
        name = str(find(n, "name")[1])
        nets[name] = [(str(find(nd, "ref")[1]), str(find(nd, "pin")[1])) for nd in find_all(n, "node")]
    return comps, nets


def load_fp(pcbnew, fpid: str, prj):
    if ":" not in fpid:
        die(f"footprint senza libreria: '{fpid}' (formato Libreria:Nome)")
    nick, name = fpid.split(":", 1)
    for d in (prj["dir"] / f"{nick}.pretty", prj["dir"] / "lib" / f"{nick}.pretty", FP_DIR / f"{nick}.pretty"):
        if (d / f"{name}.kicad_mod").exists():
            fp = pcbnew.FootprintLoad(str(d), name)
            if fp is None:
                die(f"impossibile caricare {fpid}")
            fp.SetFPID(pcbnew.LIB_ID(nick, name))
            return fp
    die(f"footprint {fpid} non trovato")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--delete-extra", action="store_true", help="cancella i footprint che non sono nello schema")
    ap.add_argument("--dry-run", action="store_true", help="mostra cosa cambierebbe senza salvare")
    a = ap.parse_args()
    try:
        prj = find_project(a.dir)
    except ProjectError as e:
        die(str(e))
    if not prj["sch"]:
        die("schema non trovato")
    import pcbnew  # import lento: solo dopo i controlli

    comps, nets = read_netlist(prj)
    pcb_path = prj["dir"] / f"{prj['name']}.kicad_pcb"
    new_board = not pcb_path.exists()
    board = pcbnew.NewBoard(str(pcb_path)) if new_board else pcbnew.LoadBoard(str(pcb_path))
    if new_board:
        board.SetCopperLayerCount(2)

    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    added, replaced, updated, extra = [], [], [], []
    # posizione di parcheggio: sotto l'ingombro attuale
    bb = board.GetBoardEdgesBoundingBox() if board.GetFootprints() or not new_board else None
    park_y = pcbnew.ToMM(bb.GetBottom()) + 10 if bb and bb.GetHeight() > 0 else 100.0
    park_x = 100.0

    for c in comps:
        if not c["footprint"]:
            print(f"  ATTENZIONE: {c['ref']} senza footprint nello schema: saltato")
            continue
        if c["props"].get("exclude_from_board") is not None or c["ref"].startswith("#"):
            continue
        fp = by_ref.get(c["ref"])
        if fp is not None and fp.GetFPIDAsString() != c["footprint"]:
            newfp = load_fp(pcbnew, c["footprint"], prj)
            newfp.SetPosition(fp.GetPosition())
            newfp.SetOrientation(fp.GetOrientation())
            if fp.IsFlipped():
                newfp.Flip(newfp.GetPosition(), pcbnew.FLIP_DIRECTION_TOP_BOTTOM)
            board.Delete(fp)
            board.Add(newfp)
            replaced.append(f"{c['ref']} {fp.GetFPIDAsString()} -> {c['footprint']}")
            fp = newfp
        elif fp is None:
            fp = load_fp(pcbnew, c["footprint"], prj)
            fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(park_x), pcbnew.FromMM(park_y)))
            park_x += 8
            board.Add(fp)
            added.append(c["ref"])
        before = (fp.GetValue(), str(fp.GetPath().AsString()))
        fp.SetReference(c["ref"])
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH(c["path"]))
        fp.SetSheetname(c["sheetname"])
        fp.SetSheetfile(prj["sch"].name)
        for k, v in c["fields"].items():
            if k in SKIP_FIELDS:
                continue
            f = fp.GetField(k) if hasattr(fp, "GetField") else None
            if f is None:
                fp.SetField(k, v)
                f = fp.GetField(k)
                if f is not None:
                    f.SetVisible(False)
            else:
                f.SetText(v)
        if "dnp" in c["props"]:
            fp.SetDNP(True)
        if before != (fp.GetValue(), str(fp.GetPath().AsString())) and c["ref"] not in added:
            updated.append(c["ref"])

    refs = {c["ref"] for c in comps}
    for fp in list(board.GetFootprints()):
        if fp.GetReference() not in refs:
            extra.append(fp.GetReference())
            if a.delete_extra:
                board.Delete(fp)

    # Net
    pads_by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    assigned = set()
    for name, nodes in nets.items():
        ni = board.FindNet(name)
        if ni is None:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
        for ref, pin in nodes:
            fp = pads_by_ref.get(ref)
            if fp is None:
                continue
            for pad in fp.Pads():
                if pad.GetNumber() == pin:
                    pad.SetNet(ni)
                    assigned.add((ref, pin))
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNumber() and (fp.GetReference(), pad.GetNumber()) not in assigned and pad.GetNetCode() != 0:
                pad.SetNetCode(0)

    print(f"PCB {'nuovo' if new_board else 'esistente'}: {pcb_path.name}")
    print(f"  aggiunti: {', '.join(added) or '-'}")
    print(f"  aggiornati: {', '.join(updated) or '-'}")
    print(f"  footprint sostituiti: {'; '.join(replaced) or '-'}")
    if extra:
        print(f"  nel PCB ma non nello schema: {', '.join(extra)}" + (" (cancellati)" if a.delete_extra else
                                                                       " (usa --delete-extra per cancellarli)"))
    print(f"  net: {len(nets)}")
    if a.dry_run:
        print("  --dry-run: nessun file salvato")
        return 0
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(pcb_path), board)
    print("Salvato. Ora posiziona i componenti (script in hardware/<nome>/scripts/) e lancia tools/check.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
