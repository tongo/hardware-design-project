# Istruzioni per Claude Code: creare l'ambiente hardware

Questo documento è per te, Claude Code. Il tuo compito è creare un **template di repository riutilizzabile**,
indipendente da qualsiasi progetto, per progettare schede elettroniche con KiCad in un devcontainer.
Sotto trovi le bozze dei file e le specifiche degli script: implementali, verificali e correggi i punti segnati **DA VERIFICARE**.

## 0. Obiettivi

- **Sandbox**: il container isola il Mac; un firewall in uscita permette solo i domini necessari.
- **Lavoro in locale**: tutto gira nel container con strumenti da riga di comando (kicad-cli, pcbnew Python, ngspice, Freerouting).
  Niente server MCP: con KiCad 10 l'API IPC richiede l'interfaccia grafica, e lo schema non ha comandi IPC.
- **Risparmio di token**: gli script producono riassunti brevi; i dettagli vanno su file.
- **Coesistenza**: l'utente apre gli stessi file con l'app KiCad sul Mac (cartella montata).

## 1. Ambiente dell'utente

- Mac con Apple Silicon M1 (arm64).
- App KiCad 10.0.8 arm64. Il container deve usare **KiCad 10.0.8**: i file salvati da una versione più nuova non si aprono con una più vecchia.
- VS Code con l'estensione Dev Containers e Docker (Docker Desktop oppure OrbStack).
- Il firmware ha un suo devcontainer separato: questo ambiente è solo per l'hardware.

## 2. Struttura da creare

```
.devcontainer/
  devcontainer.json
  Dockerfile
  allowed-domains.txt
  init-firewall.sh
  fw-allow.sh
  post-create.sh
.claude/
  settings.json
  skills/
    selezione-componenti/SKILL.md   ← da SKILL-selezione-componenti.md
    datasheet/SKILL.md              ← da SKILL-datasheet.md
    verifiche/SKILL.md              ← da SKILL-verifiche.md
    layout-pcb/SKILL.md             ← da SKILL-layout-pcb.md
    produzione-jlc/SKILL.md         ← da SKILL-produzione-jlc.md
CLAUDE.md                           ← fornito
README.md                           ← da scrivere (istruzioni per l'utente, in italiano)
.gitignore
rules/jlcpcb-2layer.kicad_dru
rules/jlcpcb-4layer.kicad_dru
tools/
  check.sh
  report_summary.py
  render.sh
  datasheet.py
  jlc_parts.py
  jlc_export.py
  jlc_rotations.csv
  route.py
docs/datasheets/.gitkeep
docs/components/_TEMPLATE.md        ← da TEMPLATE-scheda-componente.md
docs/reports/.gitkeep
hardware/.gitkeep
sim/.gitkeep
```

## 3. Devcontainer (bozze)

### 3.1 `devcontainer.json`

```jsonc
{
  "name": "KiCad HW devenv (KiCad 10.0.8)",
  "build": {
    "dockerfile": "Dockerfile",
    "args": {
      "KICAD_IMAGE": "kicad/kicad:10.0.8",   // DA VERIFICARE: deve esistere per linux/arm64
      "FREEROUTING_VERSION": "2.2.4",         // DA VERIFICARE: ultima release
      "KICAD_HAPPY_REF": "main"               // fissare un tag o un commit dopo la prima prova
    }
  },
  "features": {
    "ghcr.io/devcontainers/features/node:1": { "version": "22" },
    "ghcr.io/anthropics/devcontainer-features/claude-code:1": {}
  },
  "overrideFeatureInstallOrder": [
    "ghcr.io/devcontainers/features/node",
    "ghcr.io/anthropics/devcontainer-features/claude-code"
  ],
  "remoteUser": "kicad",
  "workspaceMount": "source=${localWorkspaceFolder},target=/workspace,type=bind,consistency=delegated",
  "workspaceFolder": "/workspace",
  "runArgs": ["--cap-add=NET_ADMIN", "--cap-add=NET_RAW"],
  "mounts": [
    "source=claude-code-config-${devcontainerId},target=/home/kicad/.claude,type=volume",
    "source=hw-jlcparts-db,target=/data/jlcparts,type=volume",
    "source=hw-history-${devcontainerId},target=/commandhistory,type=volume"
  ],
  "containerEnv": {
    "CLAUDE_CONFIG_DIR": "/home/kicad/.claude",
    "JLC_DB_DIR": "/data/jlcparts",
    "FREEROUTING_JAR": "/opt/freerouting.jar",
    "KICAD_HAPPY_DIR": "/opt/kicad-happy",
    "HISTFILE": "/commandhistory/.bash_history",
    "PYTHONDONTWRITEBYTECODE": "1"
  },
  "postCreateCommand": "bash .devcontainer/post-create.sh",
  "postStartCommand": "sudo /usr/local/bin/init-firewall.sh",
  "waitFor": "postStartCommand",
  "customizations": {
    "vscode": { "extensions": ["anthropic.claude-code", "ms-python.python", "timonwong.shellcheck"] }
  }
}
```

Note:
- Il volume `hw-jlcparts-db` ha un nome fisso: il database dei componenti JLC (~1 GB) si scarica una volta sola ed è condiviso tra tutti i progetti.
- Il volume della configurazione di Claude conserva il login tra un rebuild e l'altro.

### 3.2 `Dockerfile`

```dockerfile
ARG KICAD_IMAGE=kicad/kicad:10.0.8
FROM ${KICAD_IMAGE}
ARG FREEROUTING_VERSION=2.2.4
ARG KICAD_HAPPY_REF=main

USER root
ENV DEBIAN_FRONTEND=noninteractive

# firewall: iptables ipset dnsutils aggregate iproute2 | datasheet: poppler-utils
# simulazione: ngspice | Freerouting: Java (DA VERIFICARE: versione minima richiesta da Freerouting 2.x)
RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates jq sudo less nano zip unzip sqlite3 ripgrep \
      poppler-utils ngspice default-jre-headless python3-venv python3-pip \
      iptables ipset dnsutils aggregate iproute2 procps shellcheck \
    && rm -rf /var/lib/apt/lists/*

# Venv che vede anche il modulo di sistema 'pcbnew'
RUN python3 -m venv --system-site-packages /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir easyeda2kicad kicad-skip
ENV PATH=/opt/venv/bin:/workspace/tools:${PATH}

# Se pcbnew o kicad-cli mancano, la build fallisce subito
RUN python3 -c "import pcbnew; print('pcbnew', pcbnew.Version())" && kicad-cli version

RUN curl -fsSL -o /opt/freerouting.jar \
  "https://github.com/freerouting/freerouting/releases/download/v${FREEROUTING_VERSION}/freerouting-${FREEROUTING_VERSION}.jar"

RUN git clone https://github.com/aklofas/kicad-happy /opt/kicad-happy \
    && git -C /opt/kicad-happy checkout "${KICAD_HAPPY_REF}"

# Firewall: file di root. L'utente kicad può solo eseguirli con sudo, non modificarli.
COPY init-firewall.sh /usr/local/bin/init-firewall.sh
COPY fw-allow.sh /usr/local/bin/fw-allow
COPY allowed-domains.txt /etc/hw-firewall/allowed-domains.txt
RUN chmod 755 /usr/local/bin/init-firewall.sh /usr/local/bin/fw-allow \
 && chmod 644 /etc/hw-firewall/allowed-domains.txt \
 && echo "kicad ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh, /usr/local/bin/fw-allow" > /etc/sudoers.d/hw-firewall \
 && chmod 0440 /etc/sudoers.d/hw-firewall

# Cartelle dei volumi con il proprietario giusto (DA VERIFICARE: utente 'kicad', home /home/kicad)
RUN mkdir -p /home/kicad/.claude /data/jlcparts /commandhistory \
 && chown -R kicad:kicad /home/kicad/.claude /data/jlcparts /commandhistory
USER kicad
```

### 3.3 `allowed-domains.txt`

Un dominio per riga, `#` per i commenti. Gli intervalli IP di GitHub si aggiungono automaticamente da `api.github.com/meta`.

```
# Claude Code
api.anthropic.com
statsig.anthropic.com
statsig.com
sentry.io
claude.ai
console.anthropic.com
platform.claude.com
# VS Code
marketplace.visualstudio.com
vscode.blob.core.windows.net
update.code.visualstudio.com
# Registri di pacchetti
registry.npmjs.org
pypi.org
files.pythonhosted.org
# GitHub
github.com
api.github.com
raw.githubusercontent.com
objects.githubusercontent.com
codeload.github.com
release-assets.githubusercontent.com
# Database componenti JLC
cdfer.github.io
yaqwsx.github.io
# JLCPCB / LCSC / EasyEDA
jlcpcb.com
www.jlcpcb.com
lcsc.com
www.lcsc.com
wmsc.lcsc.com
datasheet.lcsc.com
easyeda.com
modules.easyeda.com
# KiCad
kicad.org
www.kicad.org
docs.kicad.org
gitlab.com
# Produttori (datasheet e stato del ciclo di vita)
www.ti.com
www.st.com
www.nxp.com
www.microchip.com
ww1.microchip.com
www.analog.com
www.onsemi.com
www.infineon.com
www.espressif.com
documentation.espressif.com
docs.espressif.com
www.diodes.com
www.vishay.com
www.nexperia.com
assets.nexperia.com
fscdn.rohm.com
www.monolithicpower.com
```

DA VERIFICARE: i domini necessari al login di Claude Code. Se il login fallisce, controlla quali host vengono bloccati e aggiungili.

### 3.4 `init-firewall.sh` (eseguito come root a ogni avvio)

Basato sul devcontainer di riferimento di Claude Code. Comportamento:
1. Salva le regole NAT del DNS interno di Docker (`127.0.0.11`), poi azzera iptables e l'ipset `allowed-domains`.
2. Permette DNS (porta 53, UDP/TCP) e loopback.
3. Crea l'ipset `hash:net`. Aggiunge gli intervalli `web`, `api` e `git` di `https://api.github.com/meta` (solo IPv4, compattati con `aggregate`).
4. Risolve con `dig +short A` ogni dominio di `/etc/hw-firewall/allowed-domains.txt` e aggiunge gli IP. Se un dominio non si risolve, avvisa e prosegue.
5. Permette la rete dell'host (gateway di default /24), necessaria a VS Code.
6. Politiche di default DROP; accetta il traffico ESTABLISHED/RELATED e quello verso l'ipset; tutto il resto REJECT (`icmp-admin-prohibited`).
7. Verifica: `example.com` deve essere **bloccato** (altrimenti exit 1); `api.github.com` deve rispondere (altrimenti avviso).

Script con `set -euo pipefail`, messaggi in italiano con prefisso `[firewall]`.

### 3.5 `fw-allow.sh` (installato come `/usr/local/bin/fw-allow`)

L'utente lo lancia **dal terminale** con `sudo fw-allow <dominio> [...]` per consentire un dominio fino al prossimo riavvio.
Controlla che il nome sia valido (`^[A-Za-z0-9.-]+$`), risolve gli IP e li aggiunge all'ipset. Per renderlo permanente:
aggiungere il dominio ad `allowed-domains.txt` e fare Rebuild.

### 3.6 `post-create.sh`

- `git config --global --add safe.directory /workspace`
- rende eseguibili gli script di `tools/` e crea le cartelle mancanti (`build`, `docs/*`, `hardware`, `sim`);
- stampa le versioni di kicad-cli, pcbnew, ngspice, java e claude;
- se il database JLC non c'è, dice come scaricarlo (`tools/jlc_parts.py update`). Non scaricarlo in automatico.

## 4. `.claude/settings.json` (bozza)

```json
{
  "permissions": {
    "allow": [
      "Bash(kicad-cli:*)", "Bash(tools/*)", "Bash(python3:*)", "Bash(ngspice:*)",
      "Bash(pdftotext:*)", "Bash(pdftoppm:*)", "Bash(pdfinfo:*)", "Bash(sqlite3:*)",
      "Bash(rg:*)", "Bash(jq:*)", "Bash(ls:*)", "Bash(mkdir:*)",
      "Bash(git status:*)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git add:*)", "Bash(git commit:*)",
      "Bash(java -jar /opt/freerouting.jar:*)"
    ],
    "deny": [
      "Bash(sudo:*)", "Bash(fw-allow:*)", "Bash(git push:*)",
      "Read(./**/*.kicad_pcb)", "Read(./**/*-backups/**)", "Read(./production/**/*.zip)"
    ]
  }
}
```

DA VERIFICARE: la sintassi dei pattern di `Read(...)` nella versione installata di Claude Code. Lo scopo è impedire la lettura integrale dei PCB:
si modificano solo tramite script `pcbnew`.

## 5. Script `tools/` (specifiche)

Regole comuni: Python 3 standard (più `pcbnew` dove indicato), `--help` chiaro, output **breve** sullo stdout,
dettagli completi su file in `build/`, codice di uscita diverso da 0 se ci sono errori. Il progetto KiCad si trova
cercando l'unico `.kicad_pro` nella cartella indicata (default `hardware/`); se ce ne sono di più, chiedere quale.

### 5.1 `check.sh` + `report_summary.py`
- ERC: `kicad-cli sch erc <root>.kicad_sch --format json --severity-all -o build/reports/erc.json`
- DRC, se esiste il PCB: `kicad-cli pcb drc <pcb> --format json --severity-all --schematic-parity -o build/reports/drc.json`
- `report_summary.py` legge i JSON e stampa: conteggi per gravità e per tipo, poi i primi N errori (default 15) con descrizione, elementi coinvolti e coordinate.
  Gestisce `violations`, `unconnected_items` e `schematic_parity`.
- Uscita 1 se ci sono errori.
- Avvisa se il progetto non ha un file `.kicad_dru` (le regole JLC non sono applicate).

### 5.2 `render.sh`
- `kicad-cli pcb render` lato top e bottom → `build/render/pcb-top.png`, `pcb-bottom.png` (circa 1200 px).
- `kicad-cli sch export pdf` → `build/render/schema.pdf`, poi `pdftoppm -r 70 -png` una pagina per foglio.
- Stampa solo l'elenco dei file creati.

### 5.3 `datasheet.py`
- `get <url|file> <nome>`: salva `docs/datasheets/<nome>.pdf` (se l'URL è bloccato dal firewall, spiegalo e suggerisci `sudo fw-allow` o il download manuale),
  estrae `<nome>.txt` con `pdftotext -layout`, poi crea `<nome>.index.md` con: numero di pagine, revisione/data se trovate, e le pagine in cui
  compaiono le sezioni chiave: absolute maximum ratings, recommended operating conditions, pin configuration/description, electrical characteristics,
  typical application / application information, layout guidelines, package/land pattern, ordering information. Il numero di pagina si ricava contando i form feed (`\f`) di pdftotext.
- `find <nome> <parola> [--context N]`: righe trovate con il numero di pagina.
- `page <nome> <n>`: stampa il testo di una pagina; con `--png` crea `build/ds/<nome>-p<n>.png` (70–100 dpi) da guardare con Read, per schemi e figure.

### 5.4 `jlc_parts.py` (database locale dei componenti JLC)
- `update`: scarica il database SQLite dei componenti JLC in stock (progetto cdfer/jlcpcb-parts-database, derivato da yaqwsx/jlcparts) in `$JLC_DB_DIR`.
  DA VERIFICARE: URL attuali del file SQLite e dell'eventuale CSV dei componenti Basic/Preferred. Scarica con ripresa (curl `-C -`) e indica la data dei dati.
- `schema`: elenca tabelle e colonne (serve ad adattare le query se lo schema cambia).
- `search <parole...> [--package 0603] [--economic] [--basic] [--min-stock N] [--limit 15]`: risultati in tabella compatta:
  LCSC, tipo (B = Basic, P = Preferred, E = Extended), stock, prezzo unitario, produttore e codice, package, descrizione accorciata.
  `--economic` = solo Basic e Preferred.
- `info <Cxxxx>`: dettaglio completo, compresi URL del datasheet e prezzi a scaglioni.
- `check-bom [dir] [--qty N] [--margin 3]`: esporta la BOM con `kicad-cli sch export bom` (campi Reference, Value, Footprint, LCSC, `${QUANTITY}`, `${DNP}`)
  e per ogni riga controlla: codice presente, esiste nel database, stock ≥ quantità × schede × margine, categoria.
  Stampa un riassunto (quanti B/P/E, quali Extended, costo stimato degli Extended, componenti senza codice) e salva il dettaglio in `build/reports/bom-check.md`.
- Ricorda sempre che i dati sono un'istantanea: prima dell'ordine stock e prezzi vanno ricontrollati sul sito JLC.
- Il ciclo di vita (Active/NRND/Obsolete) **non** si ricava da questo database: va verificato sul sito del produttore.

### 5.5 `jlc_export.py` (pacchetto di produzione)
In `production/` (crearla se manca):
1. Gerber: `kicad-cli pcb export gerbers` con i layer F/B.Cu, eventuali In*.Cu, F/B.Paste, F/B.SilkS, F/B.Mask, Edge.Cuts;
   foratura `kicad-cli pcb export drill` (Excellon, mm, zeri decimali, mappa). Zip in `production/<nome>-gerber.zip`.
   DA VERIFICARE: opzioni consigliate dalla guida JLCPCB per KiCad (estensioni Protel, file PTH/NPTH, origine).
2. BOM JLC `production/<nome>-bom.csv`: colonne `Comment, Designator, Footprint, JLCPCB Part #`, raggruppate per valore, footprint e LCSC,
   escludendo DNP e componenti senza LCSC (elencati a parte come "da saldare a mano").
3. CPL JLC `production/<nome>-cpl.csv`: da `kicad-cli pcb export pos --format csv --units mm --side both`, colonne
   `Designator, Mid X, Mid Y, Layer (Top/Bottom), Rotation`, solo i componenti presenti nella BOM, con le correzioni di rotazione di `jlc_rotations.csv`.
4. `production/ORDINE.md`: checklist d'ordine compilata con i dati reali (dimensioni dal bordo scheda, layer, spessore, quantità) e le scelte ancora aperte.
5. Render top/bottom copiati in `production/`.
6. Stampa un riassunto: file creati, numero di componenti, rotazioni corrette, avvisi.

### 5.6 `jlc_rotations.csv`
Colonne `pattern,correzione_gradi` (regex sul nome del footprint). Parti con poche righe commentate come candidati,
da confermare sull'anteprima di JLC prima di renderle attive. Ogni correzione confermata va annotata con la data e il componente usato per la prova.

### 5.7 `route.py` (Freerouting)
Con `pcbnew`: carica la scheda, esporta il DSN (`pcbnew.ExportSpecctraDSN`), lancia `java -jar $FREEROUTING_JAR` in modalità headless con un numero
massimo di passaggi, reimporta il SES (`pcbnew.ImportSpecctraSES`), riempie le zone e salva. Opzioni: `--ignore-nets GND,...`, `--passes N`.
Commit git prima di lanciarlo. DA VERIFICARE: le opzioni headless di Freerouting 2.x e la firma di `ImportSpecctraSES` in KiCad 10.

### 5.8 Regole DRC JLC (`rules/*.kicad_dru`)
Valori **più prudenti** dei minimi JLC, ricontrollati sulla pagina delle capacità JLCPCB. Bozza per 2 layer:
```
(version 1)
(rule "Larghezza pista minima" (constraint track_width (min 0.15mm)))
(rule "Isolamento minimo" (constraint clearance (min 0.15mm)))
(rule "Diametro via" (condition "A.Type == 'Via'") (constraint via_diameter (min 0.6mm)))
(rule "Foro via" (condition "A.Type == 'Via'") (constraint hole_size (min 0.3mm)))
(rule "Anello rame" (constraint annular_width (min 0.15mm)))
(rule "Distanza tra fori" (constraint hole_to_hole (min 0.5mm)))
(rule "Distanza dal bordo" (constraint edge_clearance (min 0.3mm)))
(rule "Testo serigrafia" (layer "?.Silkscreen") (constraint text_height (min 0.8mm)) (constraint text_thickness (min 0.15mm)))
```
Si copia in `hardware/<nome>.kicad_dru` all'inizio di ogni progetto. DA VERIFICARE: la sintassi esatta con kicad-cli 10 (il DRC deve leggerlo senza errori).

### 5.9 `.gitignore`
`build/`, `*-backups/`, `*.lck`, `~*.lck`, `_autosave-*`, `fp-info-cache`, `*.kicad_prl`, `sim/*.raw`, `__pycache__/`.
I PDF dei datasheet e `production/` si versionano.

## 6. Punti DA VERIFICARE (riepilogo)

1. Il tag `kicad/kicad:10.0.8` esiste per arm64? Se no: provare `kicad/kicad:10.0`, oppure costruire da Ubuntu 24.04 con il PPA ufficiale di KiCad 10 (che ha build arm64).
2. Utente `kicad` con home `/home/kicad`; modulo `pcbnew` importabile dal venv.
3. Versione di Java richiesta da Freerouting 2.x e disponibile nella distribuzione dell'immagine; opzioni headless.
4. URL e schema del database JLC (cdfer / yaqwsx).
5. Impostazioni Gerber e foratura consigliate da JLCPCB per KiCad.
6. Correzioni di rotazione per JLC.
7. Domini per il login di Claude Code ed eventuali altri host bloccati durante l'uso.
8. Percorsi e comandi degli script di kicad-happy (`analyze_schematic.py`, `analyze_pcb.py`, `analyze_emc.py`).
9. Sintassi delle regole di permesso in `.claude/settings.json`.

## 7. Collaudo dell'ambiente

1. Build e avvio del container: nessun errore; `post-create.sh` stampa le versioni (kicad-cli 10.0.8).
2. Firewall: `curl https://example.com` deve fallire; `curl https://api.github.com/zen` deve funzionare; `sudo fw-allow example.com` lanciato dall'utente deve sbloccarlo.
3. `tools/jlc_parts.py update`, poi `search "100nF" --package 0603 --economic` deve restituire componenti Basic.
4. **Progetto di prova** in `hardware/prova/`: connettore a 2 pin, resistenza 1 kΩ 0603 e LED 0603 (entrambi Basic), scheda 20 × 15 mm.
   Percorso completo: schema → `check.sh` (ERC pulito) → PCB con posizionamento via `pcbnew` → `route.py` → `check.sh` (DRC pulito e parità) →
   `render.sh` → `jlc_parts.py check-bom` → `jlc_export.py`.
5. L'utente apre il progetto di prova con l'app KiCad sul Mac e verifica che si apra senza avvisi di versione.
6. Scrivi il `README.md` per l'utente: requisiti sul Mac, primo avvio, login di Claude, uso di `fw-allow`, come iniziare un nuovo progetto
   (copiare il template, creare il progetto in `hardware/`, copiare il file `.kicad_dru`), regole di convivenza con l'app sul Mac.

## 8. Cosa riportare all'utente alla fine

Un riassunto breve: cosa funziona, cosa hai cambiato rispetto alle bozze (soprattutto i punti DA VERIFICARE) e cosa resta aperto.
