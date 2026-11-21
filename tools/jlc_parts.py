#!/usr/bin/env python3
"""Database locale dei componenti JLCPCB (in stock), da CDFER/jlcpcb-parts-database (derivato da yaqwsx/jlcparts).

Comandi:
  update                         scarica/aggiorna il database in $JLC_DB_DIR (~500 MB, con ripresa)
  schema                         tabelle e colonne del database
  search <parole...> [--package 0603] [--economic] [--basic] [--min-stock N] [--limit 15]
                                 cerca nel codice produttore, package e descrizione
  info <Cxxxx>                   dettaglio completo (datasheet, prezzi a scaglioni, attributi)
  check-bom [dir] [--qty N] [--margin 3]
                                 verifica i codici LCSC dello schema; dettaglio in build/reports/bom-check.md

Tipo: B = Basic, P = Preferred Extended, E = Extended. --economic = solo B e P.
ATTENZIONE: i dati sono un'istantanea (vedi la data con 'schema'): prima dell'ordine ricontrolla stock e prezzi
sul sito JLCPCB. Il ciclo di vita (Active/NRND/Obsolete) NON è in questo database: verificalo sul sito del produttore.
"""
import argparse
import csv
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwproj import ProjectError, build_dir, find_project, repo_root  # noqa: E402

DB_URL = "https://cdfer.github.io/jlcpcb-parts-database/jlcpcb-components.sqlite3"
CSV_URL = "https://cdfer.github.io/jlcpcb-parts-database/jlcpcb-components-basic-preferred.csv"
DB_DIR = Path(os.environ.get("JLC_DB_DIR", "/data/jlcparts"))
DB_FILE = DB_DIR / "jlcpcb-components.sqlite3"
STAMP = DB_DIR / "last-update.txt"
SNAPSHOT_NOTE = ("Dati = istantanea del {data}: prima dell'ordine ricontrolla stock e prezzi su jlcpcb.com. "
                 "Il ciclo di vita va verificato sul sito del produttore.")
EXTENDED_FEE_USD = 3.0  # commissione di caricamento indicativa per ogni Extended in Economic PCBA
LCSC_FIELDS = ["LCSC", "LCSC Part", "LCSC Part #", "JLCPCB Part #", "JLC"]


# ---------------------------------------------------------------- database

def db() -> sqlite3.Connection:
    if not DB_FILE.exists():
        print(f"ERRORE: database non trovato ({DB_FILE}). Scaricalo con: tools/jlc_parts.py update", file=sys.stderr)
        sys.exit(2)
    con = sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def data_date() -> str:
    if STAMP.exists():
        return STAMP.read_text().strip()
    if DB_FILE.exists():
        return datetime.fromtimestamp(DB_FILE.stat().st_mtime).strftime("%Y-%m-%d") + " (data del file)"
    return "sconosciuta"


def kind(row) -> str:
    keys = row.keys()
    lib = (row["library_type"] or "").lower() if "library_type" in keys else ""
    if lib == "base" or ("basic" in keys and row["basic"]):
        return "B"
    if lib == "preferred" or ("preferred" in keys and row["preferred"]):
        return "P"
    return "E"


def prices(row) -> list[tuple[int, int | None, float]]:
    """Scaglioni di prezzo [(da, a, prezzo_usd)].

    Formato attuale del database: "1-999:0.0043,1000-2999:0.0032,100000-:0.0022".
    Gestito anche il vecchio formato JSON [{"qFrom":1,"qTo":999,"price":0.0043}, ...].
    """
    txt = (row["price"] or "").strip()
    out = []
    if txt and not txt.startswith("["):
        for chunk in txt.split(","):
            m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d*)\s*:\s*([0-9.eE+-]+)\s*", chunk)
            if m:
                out.append((int(m.group(1)), int(m.group(2)) if m.group(2) else None, float(m.group(3))))
        return sorted(out)
    try:
        raw = json.loads(txt or "[]")
    except (TypeError, ValueError):
        return []
    for p in raw if isinstance(raw, list) else []:
        if not isinstance(p, dict):
            continue
        q_from = p.get("qFrom", p.get("q_from", p.get("from", 1)))
        q_to = p.get("qTo", p.get("q_to", p.get("to")))
        pr = p.get("price", p.get("unit_price"))
        try:
            out.append((int(q_from or 1), int(q_to) if q_to not in (None, "", -1) else None, float(pr)))
        except (TypeError, ValueError):
            continue
    return sorted(out)


def unit_price(row, qty: int = 1) -> float | None:
    ps = prices(row)
    if not ps:
        return None
    best = ps[0][2]
    for q_from, _q_to, pr in ps:
        if qty >= q_from:
            best = pr
    return best


def smt_ok(row) -> bool:
    """Economic PCBA monta solo componenti SMT (assembly_process = SMT). THT = saldatura manuale/Standard PCBA."""
    ap = (row["assembly_process"] or "").upper() if "assembly_process" in row.keys() else ""
    return ap in ("", "SMT")


def lcsc_int(code: str) -> int | None:
    m = re.fullmatch(r"\s*[Cc]?(\d+)\s*", code or "")
    return int(m.group(1)) if m else None


def get_part(con, code: str):
    n = lcsc_int(code)
    if n is None:
        return None
    return con.execute("SELECT * FROM jlc_components WHERE lcsc = ?", (n,)).fetchone()


def short(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------- comandi

def cmd_update(a) -> int:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    part = DB_FILE.with_name(DB_FILE.name + ".part")
    print(f"Scarico {DB_URL}")
    print(f"in {DB_FILE} (circa 500 MB, si può interrompere e riprendere)")
    # Se il file remoto è cambiato rispetto a un .part vecchio, la ripresa produrrebbe un file corrotto
    meta = part.with_suffix(".lastmod")
    head = subprocess.run(["curl", "-fsSIL", DB_URL], capture_output=True, text=True)
    if head.returncode != 0:
        print("ERRORE: server non raggiungibile (firewall? cdfer.github.io deve essere consentito)", file=sys.stderr)
        return 1
    lastmod = next((l.split(":", 1)[1].strip() for l in head.stdout.splitlines()
                    if l.lower().startswith("last-modified:")), "")
    if part.exists() and (not meta.exists() or meta.read_text().strip() != lastmod):
        part.unlink()
    meta.write_text(lastmod)
    r = subprocess.run(["curl", "-fL", "-C", "-", "--retry", "3", "-o", str(part), DB_URL])
    if r.returncode not in (0, 33):  # 33 = range non supportato quando il file è già completo
        print(f"ERRORE: download interrotto (curl {r.returncode}). Rilancia 'update' per riprendere.", file=sys.stderr)
        return 1
    try:
        con = sqlite3.connect(f"file:{part}?mode=ro", uri=True)
        n = con.execute("SELECT count(*) FROM jlc_components").fetchone()[0]
        con.close()
    except sqlite3.Error as e:
        print(f"ERRORE: il file scaricato non è un database valido ({e}). Cancello e riprova.", file=sys.stderr)
        part.unlink(missing_ok=True)
        return 1
    part.replace(DB_FILE)
    meta.unlink(missing_ok=True)
    try:
        d = datetime.strptime(lastmod, "%a, %d %b %Y %H:%M:%S %Z").strftime("%Y-%m-%d")
    except ValueError:
        d = time.strftime("%Y-%m-%d")
    STAMP.write_text(d + "\n")
    print(f"OK: {n} componenti in stock, dati del {d}.")
    return 0


def cmd_schema(_a) -> int:
    con = db()
    print(f"Database: {DB_FILE} ({DB_FILE.stat().st_size // 2**20} MB), dati del {data_date()}")
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') "
                               "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '%_fts_%' ORDER BY name"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info('{name}')")]
        print(f"- {name}: {', '.join(cols)}")
    try:
        for r in con.execute("SELECT key, value FROM meta"):
            print(f"  meta {r[0]} = {short(str(r[1]), 80)}")
    except sqlite3.Error:
        pass
    return 0


def cmd_search(a) -> int:
    con = db()
    where, params = [], []
    for w in a.parole:
        where.append("(mfr LIKE ? OR description LIKE ? OR package LIKE ? OR subcategory LIKE ?)")
        params += [f"%{w}%"] * 4
    if a.package:
        where.append("package LIKE ?")
        params.append(f"%{a.package}%")
    if a.basic:
        where.append("(library_type = 'base' OR basic = 1)")
    elif a.economic:
        where.append("(library_type = 'base' OR basic = 1 OR preferred = 1)")
    if a.min_stock:
        where.append("stock >= ?")
        params.append(a.min_stock)
    sql = (f"SELECT * FROM jlc_components WHERE {' AND '.join(where) or '1'} "
           "ORDER BY (library_type = 'base' OR basic = 1) DESC, preferred DESC, stock DESC LIMIT ?")
    rows = con.execute(sql, params + [a.limit]).fetchall()
    if not rows:
        print("Nessun risultato. Prova parole diverse (es. '100nF' invece di '0.1uF') o togli dei filtri.")
        return 1
    print(f"{'LCSC':<10} T {'stock':>8} {'$/pz':>8}  {'produttore / codice':<38} {'package':<12} descrizione"
          "   (* = non SMT: niente Economic)")
    for r in rows:
        up = unit_price(r, 10)
        print(f"C{r['lcsc']:<9} {kind(r)}{' ' if smt_ok(r) else '*'}{r['stock']:>8} "
              f"{('%.4f' % up) if up is not None else '-':>8}  "
              f"{short(r['manufacturer'] + ' ' + r['mfr'], 38):<38} {short(r['package'], 12):<12} "
              f"{short(r['description'], 60)}")
    if len(rows) == a.limit:
        print(f"(primi {a.limit} risultati: aggiungi filtri o --limit)")
    print(SNAPSHOT_NOTE.format(data=data_date()))
    return 0


def cmd_info(a) -> int:
    con = db()
    r = get_part(con, a.codice)
    if r is None:
        print(f"{a.codice}: non presente nel database (codice inesistente, oppure stock < 5 alla data {data_date()}).")
        return 1
    label = {"B": "Basic", "P": "Preferred Extended", "E": "Extended"}[kind(r)]
    print(f"C{r['lcsc']}  {r['manufacturer']} {r['mfr']}")
    print(f"  Categoria JLC : {label}  (library_type={r['library_type']}, preferred={r['preferred']})")
    print(f"  Classe        : {r['category']} / {r['subcategory']}")
    print(f"  Package       : {r['package']}   giunti: {r['joints']}")
    print(f"  Descrizione   : {r['description']}")
    print(f"  Stock         : {r['stock']}")
    for k in ("assembly_process", "assembly_mode"):
        if k in r.keys() and r[k]:
            print(f"  {k:<14}: {r[k]}")
    print(f"  Datasheet     : {r['datasheet'] or '-'}")
    ps = prices(r)
    if ps:
        print("  Prezzi (USD)  : " + "  ".join(f"{f}+ {p:.4f}" for f, _t, p in ps))
    try:
        attrs = json.loads(r["attributes"] or "{}")
        if isinstance(attrs, dict) and attrs:
            print("  Attributi     :")
            for k, v in list(attrs.items())[:25]:
                print(f"    {k}: {short(str(v), 80)}")
    except ValueError:
        pass
    print(SNAPSHOT_NOTE.format(data=data_date()))
    return 0


def export_bom(prj: dict) -> list[dict]:
    """Esporta la BOM dallo schema con kicad-cli e restituisce righe raggruppate."""
    out = build_dir("bom") / f"{prj['name']}-bom-raw.csv"
    fields = ["Reference", "Value", "Footprint", *LCSC_FIELDS, "MPN", "${QUANTITY}", "${DNP}"]
    cmd = ["kicad-cli", "sch", "export", "bom", str(prj["sch"]), "-o", str(out),
           "--fields", ",".join(fields), "--labels", ",".join(f.strip("${}") for f in fields),
           "--group-by", ",".join(["Value", "Footprint", *LCSC_FIELDS, "${DNP}"]),
           "--ref-range-delimiter", "", "--ref-delimiter", ","]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        raise RuntimeError(f"kicad-cli sch export bom fallito: {(r.stderr or r.stdout).strip()[:400]}")
    rows = []
    for row in csv.DictReader(io.StringIO(out.read_text())):
        lcsc = next((row.get(f, "").strip() for f in LCSC_FIELDS if row.get(f, "").strip()), "")
        refs = [x.strip() for x in row["Reference"].split(",") if x.strip()]
        rows.append({
            "refs": refs, "value": row.get("Value", ""), "footprint": row.get("Footprint", ""),
            "lcsc": lcsc, "mpn": row.get("MPN", ""), "qty": int(row.get("QUANTITY") or len(refs) or 0),
            "dnp": bool(row.get("DNP", "").strip()),
        })
    return rows


def cmd_check_bom(a) -> int:
    try:
        prj = find_project(a.dir)
    except ProjectError as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 2
    if not prj["sch"]:
        print("ERRORE: schema non trovato", file=sys.stderr)
        return 2
    try:
        bom = export_bom(prj)
    except RuntimeError as e:
        print(f"ERRORE: {e}", file=sys.stderr)
        return 2
    con = db()
    res = {"B": [], "P": [], "E": []}
    problems, nocode, dnp = [], [], []
    ext_cost = 0.0
    lines = [f"# Verifica BOM – {prj['name']}", "",
             f"- Data verifica: {time.strftime('%Y-%m-%d %H:%M')}; dati JLC del {data_date()}",
             f"- Schede: {a.qty}, margine di stock: x{a.margin}", "",
             "| Rif. | Valore | Footprint | LCSC | Tipo | Q/scheda | Serve | Stock | $/pz | Esito |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for it in bom:
        refs = ",".join(it["refs"])
        fp = it["footprint"].split(":")[-1]
        if it["dnp"]:
            dnp.append(refs)
            lines.append(f"| {refs} | {it['value']} | {fp} | {it['lcsc']} | - | {it['qty']} | - | - | - | DNP |")
            continue
        if not it["lcsc"]:
            nocode.append(refs)
            lines.append(f"| {refs} | {it['value']} | {fp} | - | - | {it['qty']} | - | - | - | SENZA CODICE |")
            continue
        need = it["qty"] * a.qty * a.margin
        p = get_part(con, it["lcsc"])
        if p is None:
            problems.append(f"{refs} {it['lcsc']}: non trovato (inesistente o stock < 5)")
            lines.append(f"| {refs} | {it['value']} | {fp} | {it['lcsc']} | ? | {it['qty']} | {need} | - | - | NON TROVATO |")
            continue
        k = kind(p)
        res[k].append(refs)
        up = unit_price(p, it["qty"] * a.qty)
        esito = "OK"
        if not smt_ok(p):
            esito = "NON SMT"
            problems.append(f"{refs} C{p['lcsc']}: montaggio {p['assembly_process']} (non assemblabile in Economic)")
        if p["stock"] < need:
            esito = "STOCK BASSO"
            problems.append(f"{refs} C{p['lcsc']}: stock {p['stock']} < {need} richiesti")
        if k == "E":
            ext_cost += EXTENDED_FEE_USD + (up or 0) * it["qty"] * a.qty
        lines.append(f"| {refs} | {it['value']} | {fp} | C{p['lcsc']} | {k} | {it['qty']} | {need} | {p['stock']} | "
                     f"{('%.4f' % up) if up is not None else '-'} | {esito} |")
    lines += ["", f"- Basic: {len(res['B'])}, Preferred: {len(res['P'])}, Extended: {len(res['E'])}",
              f"- Extended: {', '.join(res['E']) or 'nessuno'}",
              f"- Costo stimato degli Extended per {a.qty} schede: {ext_cost:.2f} USD "
              f"(componenti + ~{EXTENDED_FEE_USD:.0f} USD di caricamento ciascuno, indicativo)",
              f"- Senza codice LCSC (da saldare a mano o da completare): {', '.join(nocode) or 'nessuno'}",
              f"- DNP: {', '.join(dnp) or 'nessuno'}", "", SNAPSHOT_NOTE.format(data=data_date()), ""]
    rep = build_dir("reports") / "bom-check.md"
    rep.write_text("\n".join(lines))

    print(f"BOM {prj['name']}: {sum(len(v) for v in res.values())} righe con codice, "
          f"{len(nocode)} senza codice, {len(dnp)} DNP  (schede: {a.qty}, margine x{a.margin})")
    print(f"  Basic {len(res['B'])} | Preferred {len(res['P'])} | Extended {len(res['E'])}"
          + (f" -> {', '.join(res['E'])}" if res["E"] else ""))
    if res["E"]:
        print(f"  Costo stimato Extended: {ext_cost:.2f} USD (indicativo)")
    if nocode:
        print(f"  Senza codice LCSC: {', '.join(nocode)}")
    for pr in problems:
        print(f"  PROBLEMA: {pr}")
    print(f"  Dettaglio: {rep.relative_to(repo_root())}")
    print("  " + SNAPSHOT_NOTE.format(data=data_date()))
    return 1 if problems else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("update", help="scarica/aggiorna il database")
    sub.add_parser("schema", help="tabelle e colonne del database")
    s = sub.add_parser("search", help="cerca componenti")
    s.add_argument("parole", nargs="+")
    s.add_argument("--package")
    s.add_argument("--economic", action="store_true", help="solo Basic e Preferred")
    s.add_argument("--basic", action="store_true", help="solo Basic")
    s.add_argument("--min-stock", type=int, default=0)
    s.add_argument("--limit", type=int, default=15)
    i = sub.add_parser("info", help="dettaglio di un codice LCSC")
    i.add_argument("codice")
    c = sub.add_parser("check-bom", help="verifica i codici LCSC dello schema")
    c.add_argument("dir", nargs="?")
    c.add_argument("--qty", type=int, default=5, help="numero di schede (default 5)")
    c.add_argument("--margin", type=float, default=3, help="margine sullo stock (default 3)")
    a = ap.parse_args()
    return {"update": cmd_update, "schema": cmd_schema, "search": cmd_search, "info": cmd_info,
            "check-bom": cmd_check_bom}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
