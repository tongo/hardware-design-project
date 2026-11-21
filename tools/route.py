#!/usr/bin/env python3
"""Sbroglio automatico con Freerouting (headless), per le piste NON critiche.

Uso: tools/route.py [dir-progetto] [--ignore-nets GND,+3V3] [--passes 20] [--timeout 600] [--no-commit-check]

Passi: carica la scheda con pcbnew, esporta il DSN, (sposta le net da ignorare in una classe che Freerouting
salta), lancia Freerouting, reimporta il SES, riempie le zone e salva. Log in build/route/.
Le piste già presenti restano (Freerouting le considera fisse solo se sono 'locked': blocca nell'app o via script
quelle tracciate a mano). Prima di lanciarlo: commit git e PCB chiuso nell'app sul Mac.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwproj import ProjectError, build_dir, find_project, repo_root  # noqa: E402

JAR = os.environ.get("FREEROUTING_JAR", "/opt/freerouting.jar")
IGNORE_CLASS = "fr_ignore"


def die(msg, code=2):
    print(f"ERRORE: {msg}", file=sys.stderr)
    sys.exit(code)


def _blocks(text: str, head: str):
    """Restituisce (inizio, fine) dei blocchi '(head ...' bilanciati nel testo DSN."""
    for m in re.finditer(r"\(" + re.escape(head) + r"\s", text):
        depth, i, instr = 0, m.start(), False
        while i < len(text):
            ch = text[i]
            if ch == '"':
                instr = not instr
            elif not instr:
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        yield m.start(), i + 1
                        break
            i += 1


def _net_tok(name: str) -> str:
    return name if re.fullmatch(r"[A-Za-z0-9_+./-]+", name) and not name.startswith("-") else f'"{name}"'


def isolate_nets(dsn: Path, nets: list[str]) -> list[str]:
    """Sposta le net indicate in una classe DSN separata (da far ignorare a Freerouting)."""
    text = dsn.read_text()
    found = []
    blocks = list(_blocks(text, "class"))
    if not blocks:
        return []
    out, last, template_rules = [], 0, ""
    for s, e in blocks:
        blk = text[s:e]
        head_end = blk.find("(", 1)
        head, rest = blk[:head_end], blk[head_end:]
        if not template_rules:
            template_rules = rest
        toks = re.findall(r'"[^"]*"|[^\s()]+', head)
        keep = [toks[0], toks[1]]
        for t in toks[2:]:
            if t.strip('"') in nets or t.strip('"').lstrip("/") in nets:
                found.append(t.strip('"'))
            else:
                keep.append(t)
        out.append(text[last:s] + "(" + " ".join(keep) + "\n      " + rest)
        last = e
    out.append(text[last:])
    new = "".join(out)
    if found:
        cls = f'(class {IGNORE_CLASS} {" ".join(_net_tok(n) for n in sorted(set(found)))}\n      {template_rules}'
        # inserisce la nuova classe subito dopo l'ultima classe esistente
        last_cls_end = list(_blocks(new, "class"))[-1][1]
        new = new[:last_cls_end] + "\n    " + cls + new[last_cls_end:]
    dsn.write_text(new)
    return sorted(set(found))


def git_dirty(path: Path) -> bool:
    r = subprocess.run(["git", "-C", str(repo_root()), "status", "--porcelain", "--", str(path)],
                       capture_output=True, text=True)
    return bool(r.stdout.strip())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?")
    ap.add_argument("--ignore-nets", default="", help="net da non sbrogliare, separate da virgola (es. GND; vale anche per /GND)")
    ap.add_argument("--passes", type=int, default=20, help="passaggi massimi dell'autorouter (default 20)")
    ap.add_argument("--timeout", type=int, default=600, help="secondi massimi per Freerouting (default 600)")
    ap.add_argument("--no-commit-check", action="store_true", help="non richiedere il commit git prima")
    a = ap.parse_args()
    try:
        prj = find_project(a.dir)
    except ProjectError as e:
        die(str(e))
    if not prj["pcb"]:
        die("PCB non trovato")
    if not Path(JAR).exists():
        die(f"Freerouting non trovato: {JAR}")
    if not a.no_commit_check and git_dirty(prj["pcb"]):
        die(f"{prj['pcb'].name} ha modifiche non salvate in git: fai prima un commit (o usa --no-commit-check)")

    import pcbnew

    out = build_dir("route")
    dsn, ses, log = out / f"{prj['name']}.dsn", out / f"{prj['name']}.ses", out / "freerouting.log"
    for f in (dsn, ses):
        f.unlink(missing_ok=True)
    board = pcbnew.LoadBoard(str(prj["pcb"]))
    n_tracks_before = sum(1 for t in board.GetTracks())
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        die("esportazione DSN non riuscita")
    ignore = [n.strip() for n in a.ignore_nets.split(",") if n.strip()]
    ignored = isolate_nets(dsn, ignore) if ignore else []
    missing = sorted(n for n in ignore if n not in ignored and "/" + n not in ignored)
    if missing:
        print(f"  ATTENZIONE: net non trovate nel DSN (già senza connessioni da fare?): {', '.join(missing)}")

    # Freerouting 2.5.0 accetta in -de solo .dsn/.ses/.rules/.json: le regole .kicad_dru NON gli arrivano
    # (il DSN porta solo le clearance delle net class). Per questo dopo lo sbroglio serve sempre tools/check.sh.
    cmd = ["java", "-Djava.awt.headless=true", "-jar", JAR, "-de", str(dsn), "-do", str(ses),
           "--gui.enabled=false", f"--router.autorouter.max_passes={a.passes}",
           "--usage_and_diagnostic_data.disable_analytics=true",
           f"--logging.file.location={out}", "--logging.console.level=INFO"]
    if ignored:
        cmd.append(f"--router.autorouter.ignore_net_classes={IGNORE_CLASS}")
    t0 = time.time()
    with open(log, "w") as lf:
        lf.write(" ".join(cmd) + "\n\n")
        lf.flush()
        try:
            r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT, timeout=a.timeout,
                               env={**os.environ, "FREEROUTING__USER_DATA_PATH": str(out)})
        except subprocess.TimeoutExpired:
            die(f"Freerouting oltre {a.timeout} s: interrotto (vedi {log.relative_to(repo_root())})")
    dt = time.time() - t0
    if r.returncode != 0 or not ses.exists():
        tail = log.read_text().splitlines()[-8:]
        die(f"Freerouting non ha prodotto il SES (codice {r.returncode}). Ultime righe del log:\n  " + "\n  ".join(tail))

    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        die("importazione SES non riuscita")
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    board.BuildConnectivity()
    pcbnew.SaveBoard(str(prj["pcb"]), board)

    unrouted = board.GetConnectivity().GetUnconnectedCount(False)
    n_tracks = sum(1 for t in board.GetTracks())
    shutil.copyfile(ses, out / "last.ses")
    print(f"Sbroglio completato in {dt:.0f} s: segmenti/via {n_tracks_before} -> {n_tracks}, "
          f"connessioni mancanti: {unrouted}")
    if ignored:
        print(f"  net ignorate: {', '.join(ignored)}")
    print(f"  log: {log.relative_to(repo_root())}. Ora: tools/check.sh")
    return 0 if unrouted == 0 or ignored else 1


if __name__ == "__main__":
    sys.exit(main())
