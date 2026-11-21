#!/usr/bin/env python3
"""Datasheet: download, estrazione del testo, indice delle sezioni, ricerca e lettura per pagina.

Comandi:
  get <url|file> <nome>            salva docs/datasheets/<nome>.pdf, crea <nome>.txt e <nome>.index.md
  find <nome> <parola> [--context N] [--max M]
                                   righe che contengono la parola (senza maiuscole/minuscole), con il numero di pagina
  page <nome> <n> [--png] [--dpi D]
                                   testo della pagina n; con --png crea build/ds/<nome>-p<n>.png da guardare
  list                             elenco dei datasheet archiviati

<nome> consigliato: <produttore>_<codice>_<revisione>, es. ti_tps62160_revF
Le pagine si contano dai form feed (\\f) di pdftotext: pagina 1 = prima pagina del PDF.
"""
import argparse
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hwproj import build_dir, repo_root  # noqa: E402

DS_DIR = repo_root() / "docs" / "datasheets"
UA = "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"

SECTIONS = [
    ("Absolute maximum ratings", r"absolute\s+maximum\s+ratings?|absolute\s+max(imum)?\b"),
    ("Recommended operating conditions", r"recommended\s+operating\s+conditions?"),
    ("Pin configuration / description", r"pin\s+(configuration|description|functions?|assignment|out)s?|pinout|pin\s+definitions?"),
    ("Electrical characteristics", r"electrical\s+characteristics|dc\s+characteristics"),
    ("Typical application / application information",
     r"typical\s+applications?|application\s+(information|circuit|schematic)s?|applications?\s+and\s+implementation"),
    ("Layout guidelines", r"layout\s+(guidelines?|considerations?|recommendations?|example)|pcb\s+layout"),
    ("Package / land pattern",
     r"package\s+(information|outline|dimensions?|drawing)|mechanical\s+(data|dimensions)|land\s+pattern|"
     r"recommended\s+(footprint|pad|solder)|footprint"),
    ("Ordering information", r"ordering\s+information|order(ing)?\s+codes?|part\s+numbering|device\s+options"),
]


def die(msg: str, code: int = 1):
    print(f"ERRORE: {msg}", file=sys.stderr)
    sys.exit(code)


def check_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9._+-]+", name):
        die("nome non valido: usa solo lettere, numeri, '_', '-', '.', '+' (es. ti_tps62160_revF)")
    return name


def pages_of(name: str) -> list[str]:
    txt = DS_DIR / f"{name}.txt"
    if not txt.exists():
        die(f"{txt.relative_to(repo_root())} non esiste: prima 'datasheet.py get'")
    pages = txt.read_text(errors="replace").split("\f")
    if pages and not pages[-1].strip():
        pages = pages[:-1]
    return pages


def download(url: str, dest: Path) -> None:
    host = urllib.parse.urlparse(url).hostname or "?"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
    except urllib.error.HTTPError as e:
        die(f"il server {host} ha risposto {e.code} {e.reason}. Prova a scaricare il PDF a mano nel browser "
            f"e salvalo in docs/datasheets/, poi: tools/datasheet.py get docs/datasheets/<file>.pdf <nome>")
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        reason = getattr(e, "reason", e)
        die(f"impossibile raggiungere {host} ({reason}).\n"
            f"Probabilmente il firewall blocca il dominio. Chiedi all'utente di lanciare nel terminale:\n"
            f"    sudo fw-allow {host}\n"
            f"oppure di scaricare il PDF a mano e salvarlo in docs/datasheets/.")


def find_meta(pages: list[str]) -> dict:
    first = "\n".join(pages[:2])
    alltxt = "\n".join(pages)
    meta = {}
    rx = r"\b(?:Rev(?:ision)?|REV(?:ISION)?)(?:\.|:|\s)\s*:?\s*(?!History|HISTORY|Date|DATE|No\b|Number)([A-Z0-9][A-Za-z0-9.]{0,6})\b"
    m = re.search(rx, first) or re.search(rx, pages[-1] if pages else "")
    if not m:  # documenti TI/simili: codice tipo SLVSAM4D, la revisione è l'ultima lettera
        m = re.search(r"\b(?:SL|SB|SN|SC)[A-Z]{2}[A-Z0-9]{2,4}?([A-Z])\b(?=\s*[–-])", first)
    if m:
        meta["revisione"] = m.group(1)
    months = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
    dm = re.search(rf"\b{months}\s+(?:\d{{1,2}},?\s+)?(?:19|20)\d\d\b", first) or \
        re.search(r"\b(?:19|20)\d\d[-/.](?:0[1-9]|1[0-2])(?:[-/.]\d\d)?\b", first) or \
        re.search(rf"\b{months}\s+(?:\d{{1,2}},?\s+)?(?:19|20)\d\d\b", alltxt[-6000:])
    if dm:
        meta["data"] = dm.group(0)
    return meta


def build_index(name: str, pdf: Path, pages: list[str], source: str) -> Path:
    meta = find_meta(pages)
    lines = [f"# Indice datasheet: {name}", "",
             f"- File: `docs/datasheets/{pdf.name}` (testo: `{name}.txt`)",
             f"- Origine: {source}",
             f"- Pagine: {len(pages)}",
             f"- Revisione: {meta.get('revisione', 'non trovata (controllare la prima o l ultima pagina)')}",
             f"- Data: {meta.get('data', 'non trovata')}", "",
             "## Sezioni chiave (pagine)", "",
             "| Sezione | Pagine (prima = probabile titolo di sezione) |", "|---|---|"]
    for label, rx in SECTIONS:
        rgx = re.compile(rx, re.I)
        heads, mentions = [], []
        for i, p in enumerate(pages, 1):
            hit_head = any(rgx.search(l) and len(l.strip()) < 70 and not re.search(r"\.{4,}", l)
                           for l in p.splitlines())
            if hit_head:
                heads.append(i)
            elif rgx.search(p):
                mentions.append(i)
        cell = ", ".join(map(str, heads[:8])) or "-"
        if mentions:
            cell += f" (citata anche a pag. {', '.join(map(str, mentions[:6]))}{'...' if len(mentions) > 6 else ''})"
        lines.append(f"| {label} | {cell} |")
    lines += ["", "Pagine trovate con una ricerca automatica: verificare con "
              "`tools/datasheet.py page <nome> <n>` prima di usarle.", ""]
    idx = DS_DIR / f"{name}.index.md"
    idx.write_text("\n".join(lines))
    return idx


def cmd_get(a) -> int:
    name = check_name(a.nome)
    DS_DIR.mkdir(parents=True, exist_ok=True)
    pdf = DS_DIR / f"{name}.pdf"
    src = a.sorgente
    if re.match(r"https?://", src):
        if pdf.exists() and not a.force:
            print(f"{pdf.name} esiste già (usa --force per riscaricarlo); rigenero testo e indice")
        else:
            tmp = pdf.with_suffix(".part")
            download(src, tmp)
            tmp.replace(pdf)
    else:
        p = Path(src).expanduser().resolve()
        if not p.exists():
            die(f"file non trovato: {src}")
        if p != pdf:
            shutil.copyfile(p, pdf)
    with open(pdf, "rb") as f:
        if f.read(5) != b"%PDF-":
            pdf.rename(pdf.with_suffix(".notpdf"))
            die("il file scaricato non è un PDF (forse una pagina HTML o un captcha). "
                "Scaricalo a mano nel browser e salvalo in docs/datasheets/.")
    txt = DS_DIR / f"{name}.txt"
    r = subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], capture_output=True, text=True)
    if r.returncode != 0:
        die(f"pdftotext: {r.stderr.strip()[:300]}")
    pages = pages_of(name)
    nchars = sum(len(p.strip()) for p in pages)
    idx = build_index(name, pdf, pages, src)
    print(f"Salvato: docs/datasheets/{pdf.name} ({pdf.stat().st_size // 1024} kB, {len(pages)} pagine)")
    print(f"Testo:   docs/datasheets/{txt.name}")
    print(f"Indice:  docs/datasheets/{idx.name}  <- leggi prima questo")
    if nchars < 200 * max(1, len(pages)) // 4:
        print("ATTENZIONE: poco testo estratto: il PDF potrebbe essere una scansione (usa 'page --png').")
    return 0


def cmd_find(a) -> int:
    pages = pages_of(check_name(a.nome))
    rgx = re.compile(re.escape(a.parola), re.I)
    hits = 0
    for i, p in enumerate(pages, 1):
        lines = p.splitlines()
        for j, l in enumerate(lines):
            if rgx.search(l):
                hits += 1
                if hits > a.max:
                    continue
                lo, hi = max(0, j - a.context), min(len(lines), j + a.context + 1)
                if a.context:
                    print(f"--- pag. {i}")
                    for k in range(lo, hi):
                        print(("> " if k == j else "  ") + lines[k].rstrip()[:200])
                else:
                    print(f"p{i:>3}: {l.strip()[:200]}")
    if hits > a.max:
        print(f"... {hits - a.max} altre righe (usa --max)")
    if not hits:
        print("nessun risultato")
        return 1
    pg = sorted({i for i, p in enumerate(pages, 1) if rgx.search(p)})
    print(f"[{hits} righe in {len(pg)} pagine: {', '.join(map(str, pg[:30]))}]")
    return 0


def cmd_page(a) -> int:
    name = check_name(a.nome)
    pages = pages_of(name)
    if not 1 <= a.n <= len(pages):
        die(f"pagina fuori intervallo (1-{len(pages)})")
    if a.png:
        out = build_dir("ds") / f"{name}-p{a.n}"
        r = subprocess.run(["pdftoppm", "-f", str(a.n), "-l", str(a.n), "-r", str(a.dpi), "-png", "-singlefile",
                            str(DS_DIR / f"{name}.pdf"), str(out)], capture_output=True, text=True)
        if r.returncode != 0:
            die(f"pdftoppm: {r.stderr.strip()[:300]}")
        print(f"{out.relative_to(repo_root())}.png")
        return 0
    print(f"=== {name} pag. {a.n}/{len(pages)}")
    print("\n".join(l.rstrip() for l in pages[a.n - 1].splitlines() if l.strip()))
    return 0


def cmd_list(_a) -> int:
    pdfs = sorted(DS_DIR.glob("*.pdf"))
    if not pdfs:
        print("nessun datasheet in docs/datasheets/")
    for p in pdfs:
        idx = p.with_suffix(".index.md")
        print(f"{p.stem}{'' if idx.exists() else '  (senza indice: rilancia get)'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("get", help="scarica/importa un PDF e crea testo e indice")
    g.add_argument("sorgente", help="URL oppure percorso di un PDF locale")
    g.add_argument("nome", help="es. ti_tps62160_revF")
    g.add_argument("--force", action="store_true", help="riscarica anche se il PDF esiste")
    f = sub.add_parser("find", help="cerca una parola nel testo")
    f.add_argument("nome")
    f.add_argument("parola")
    f.add_argument("--context", type=int, default=0, help="righe di contesto (default 0)")
    f.add_argument("--max", type=int, default=40, help="righe massime stampate (default 40)")
    p = sub.add_parser("page", help="testo (o PNG) di una pagina")
    p.add_argument("nome")
    p.add_argument("n", type=int)
    p.add_argument("--png", action="store_true", help="crea un PNG della pagina in build/ds/")
    p.add_argument("--dpi", type=int, default=80, help="risoluzione del PNG (70-100, default 80)")
    sub.add_parser("list", help="elenco dei datasheet archiviati")
    a = ap.parse_args()
    return {"get": cmd_get, "find": cmd_find, "page": cmd_page, "list": cmd_list}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
