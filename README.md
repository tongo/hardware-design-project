# Ambiente hardware: KiCad 10 + Claude Code (devcontainer)

Template di repository per progettare schede elettroniche con **KiCad 10.0.8** e **Claude Code**,
dentro un container isolato (sandbox con firewall). Tu apri gli stessi file con l'app KiCad sul Mac.

## Cosa c'è dentro

- **KiCad 10.0.8** a riga di comando (`kicad-cli`) e modulo Python `pcbnew`, dal PPA ufficiale di KiCad (build arm64 nativa).
- **ngspice** per le simulazioni, **Freerouting 2.5** (Java 25) per lo sbroglio automatico, **kicad-happy** per le analisi.
- Database locale dei componenti **JLCPCB** (in stock), condiviso tra tutti i progetti.
- Script in `tools/` che producono riassunti brevi (risparmio di token); i dettagli vanno in `build/`.
- Firewall in uscita: il container raggiunge solo i siti dell'elenco `.devcontainer/allowed-domains.txt`.

## Requisiti sul Mac

1. **Docker Desktop** (o OrbStack) avviato. Consigliati almeno 4 GB di RAM assegnati a Docker.
2. **VS Code** con l'estensione **Dev Containers**.
3. **App KiCad 10.0.8**. La versione deve coincidere con quella del container (`KICAD_VERSION` in
   `.devcontainer/devcontainer.json`): un file salvato da una versione più nuova non si apre con una più vecchia.

## Primo avvio

1. Apri la cartella in VS Code → **"Reopen in Container"** (oppure palette: *Dev Containers: Reopen in Container*).
   La prima build richiede 5–10 minuti.
2. Alla fine il terminale mostra le versioni (`kicad-cli 10.0.8`, ecc.) e i messaggi `[firewall]`.
3. Scarica il database dei componenti JLC (una sola volta, ~500 MB, condiviso tra i progetti):
   ```bash
   tools/jlc_parts.py update
   ```
4. Avvia Claude Code (pannello Claude di VS Code o `claude` nel terminale) ed esegui il **login**:
   si apre un link da aprire nel browser del Mac; incolla il codice nel terminale.
   Il login resta salvato in un volume Docker anche dopo un *Rebuild*.

## Firewall: consentire un sito

Se Claude (o uno script) non riesce a scaricare qualcosa, di solito è il firewall. **Tu**, dal terminale del container:

```bash
sudo fw-allow www.esempio.com          # vale fino al prossimo riavvio del container
```

Per renderlo permanente: aggiungi il dominio a `.devcontainer/allowed-domains.txt` e fai **Rebuild Container**.
Claude non può usare `sudo` (è vietato nelle sue impostazioni): te lo chiederà.

## Iniziare un nuovo progetto

1. Crea un nuovo repository partendo da questo template (su GitHub "Use this template", oppure copia la cartella
   senza `.git`, `build/`, `production/` e `hardware/prova/`).
2. Crea il progetto KiCad in `hardware/<nome>/` (con l'app sul Mac, oppure chiedi a Claude).
3. Copia le regole del produttore nella cartella del progetto, con lo stesso nome del progetto:
   ```bash
   cp rules/jlcpcb-2layer.kicad_dru hardware/<nome>/<nome>.kicad_dru     # oppure jlcpcb-4layer
   ```
4. Compila la sezione "Progetto corrente" di `CLAUDE.md` (nome, requisiti, blocchi).
5. Chiedi a Claude di partire dai requisiti: lavora per fasi e chiede la tua approvazione a ogni blocco.

## Convivenza con l'app KiCad sul Mac

- I file sono gli stessi (cartella montata): **non modificare lo stesso file in due posti contemporaneamente**.
- Prima che Claude modifichi uno schema o un PCB, **chiudilo nell'app** (Claude te lo chiede).
  Dopo la modifica riaprilo (o *File → Revert*).
- Se KiCad sul Mac chiede di aggiornare il formato del file, fermati: le versioni non coincidono.
- Fai i commit spesso: Claude fa `git commit`, ma **il `git push` lo fai tu**.
- Il primo PCB di un progetto lo crea `tools/sch_to_pcb.py` (non serve "Aggiorna PCB da schema" nell'app),
  ma puoi usare anche F8 nell'app: il risultato è lo stesso.

## Comandi principali (li usa Claude, ma puoi lanciarli anche tu)

| Comando | A cosa serve |
|---|---|
| `tools/check.sh [dir]` | ERC + DRC (regole JLC, parità schema–PCB), riassunto |
| `tools/render.sh [dir]` | Immagini del PCB e PDF/PNG dello schema in `build/render/` |
| `tools/datasheet.py get <url> <nome>` | Scarica un datasheet, estrae il testo, crea l'indice delle sezioni |
| `tools/jlc_parts.py search 100nF --package 0603 --economic` | Cerca componenti JLC |
| `tools/jlc_parts.py check-bom --qty 5` | Verifica tutti i codici LCSC dello schema |
| `tools/sch_gen.py <file.json>` | Genera uno schema da una descrizione JSON |
| `tools/sch_to_pcb.py [dir]` | Porta componenti e collegamenti dallo schema al PCB |
| `tools/route.py [dir] --ignore-nets GND` | Sbroglio automatico (Freerouting) |
| `tools/jlc_export.py [dir]` | Pacchetto d'ordine JLCPCB in `production/` |

## Progetto di prova

`hardware/prova/` è il progetto usato per collaudare l'ambiente: connettore a 2 pin, resistenza 1 kΩ e LED 0603,
scheda 20 × 15 mm. Puoi aprirlo con l'app sul Mac per verificare che si apra senza avvisi di versione,
poi cancellarlo nei progetti veri (insieme a `production/`).

## Aggiornamenti

- **KiCad**: aggiorna prima l'app sul Mac, poi `KICAD_VERSION` in `.devcontainer/devcontainer.json`, poi *Rebuild Container*.
  La build si ferma con un messaggio se il PPA non ha la versione richiesta.
- **Claude Code**: si aggiorna con *Rebuild Container* (l'aggiornamento automatico è disattivato perché il firewall lo bloccherebbe).
- **Freerouting / kicad-happy**: `FREEROUTING_VERSION` e `KICAD_HAPPY_REF` in `devcontainer.json`.
- **Modelli 3D** nei render: `INSTALL_3D_MODELS: "true"` in `devcontainer.json` (circa 6 GB in più).

## Limiti noti

- Il firewall risolve gli indirizzi dei domini all'avvio: se un sito cambia indirizzo durante la sessione può
  risultare bloccato. Rimedio: `sudo fw-allow <dominio>` o riavvio del container.
- Il divieto di leggere i `.kicad_pcb` vale per lo strumento di lettura di Claude; non è una protezione assoluta,
  serve a evitare di consumare token.
- I dati JLC sono un'istantanea giornaliera: prima di ordinare, stock e prezzi si ricontrollano sul sito.
