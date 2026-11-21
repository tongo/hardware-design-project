# Ambiente hardware – KiCad 10 + Claude Code

Questo repository contiene un progetto hardware in KiCad. Lavori in un **devcontainer** (sandbox con firewall).
L'utente apre gli stessi file con l'**app KiCad 10.0.8 sul Mac**. L'utente non è un ingegnere elettronico:
spiega sempre in italiano semplice e segnala chiaramente i rischi.

## Struttura

```
hardware/          progetto KiCad (.kicad_pro, .kicad_sch, .kicad_pcb, .kicad_dru)
docs/datasheets/   PDF dei datasheet + testo estratto (.txt) + indice (.index.md)
docs/components/   una scheda di selezione per ogni componente attivo
docs/reports/      report di verifica (uno per blocco/fase)
sim/               simulazioni ngspice e script di calcolo
tools/             script del flusso di lavoro (usali sempre, vedi sotto)
rules/             regole DRC per il produttore (JLCPCB)
build/             output temporanei (ignorato da git)
production/        pacchetto per l'ordine (versionato a ogni rilascio)
```

## Regole d'oro

1. **Risparmio di token.**
   - Non leggere mai interi file `.kicad_pcb`, Gerber o PDF: usa gli script in `tools/`.
   - I report completi vanno su file in `build/reports/`; nel contesto porta solo riassunti ed errori.
   - Per vedere la scheda usa i render a bassa risoluzione, e solo nei punti chiave.
2. **Coesistenza con l'app sul Mac.**
   - Prima di modificare un file KiCad, chiedi all'utente se è aperto nell'app e, se sì, di chiuderlo.
   - Dopo la modifica, digli di riaprirlo o ricaricarlo.
3. **Git.**
   - Commit prima e dopo ogni intervento, con messaggi chiari.
   - Non fare mai `git push`: lo fa l'utente.
4. **Rete.**
   - Il firewall blocca tutto tranne i domini consentiti. Non cercare di aggirarlo e non usare `sudo`.
   - Se ti serve un sito bloccato, chiedi all'utente di lanciare `sudo fw-allow <dominio>` oppure di scaricare lui il file.
5. **Versione KiCad.** `kicad-cli version` deve essere 10.0.x, la stessa versione principale dell'app sul Mac. Se non lo è, fermati e avvisa.
6. **Componenti.**
   - Solo componenti in stato **Active** presso il produttore, disponibili su JLCPCB e assemblabili in **Economic PCBA**.
   - Priorità: Basic, poi Preferred Extended, poi Extended (solo se non c'è alternativa).
   - Non inventare mai codici LCSC.
   - Ogni componente attivo ha una scheda in `docs/components/` e il datasheet in `docs/datasheets/`.
7. **Fasi.** Requisiti, poi schema (un blocco alla volta), poi PCB, poi produzione.
   Non passare al blocco o alla fase successiva senza l'approvazione esplicita dell'utente.
8. **Report.** Ogni blocco si chiude con un report in `docs/reports/`: semaforo verde/giallo/rosso, cosa significa ogni controllo,
   cosa si rischia e quanto è affidabile la verifica.

## Comandi

| Comando | A cosa serve |
|---|---|
| `tools/check.sh [dir]` | ERC + DRC (regole JLC, parità schema–PCB) con riassunto compatto |
| `tools/render.sh [dir]` | Render PNG del PCB (sopra e sotto) e PDF/PNG dello schema, in `build/render/` |
| `tools/datasheet.py get <url> <nome>` | Scarica il datasheet, estrae il testo e crea un indice delle sezioni con i numeri di pagina |
| `tools/datasheet.py find <nome> <parola>` | Cerca nel testo estratto e indica le pagine |
| `tools/jlc_parts.py search ...` | Cerca componenti nel database JLC locale (filtri: package, Basic/Preferred, stock) |
| `tools/jlc_parts.py info C12345` | Dettagli di un codice LCSC |
| `tools/jlc_parts.py check-bom` | Verifica tutti i codici LCSC dello schema: esistenza, stock, categoria |
| `tools/jlc_parts.py update` | Aggiorna il database JLC locale |
| `tools/sch_gen.py <file.json>` | Genera/rigenera uno schema da una descrizione JSON (simboli, campi, net tramite etichette) |
| `tools/sch_to_pcb.py [dir]` | "Aggiorna PCB da schema" senza interfaccia: footprint, campi, net |
| `tools/route.py [dir]` | Sbroglio automatico con Freerouting (solo per le piste non critiche) |
| `tools/jlc_export.py [dir]` | Pacchetto di produzione JLCPCB in `production/` |

Strumenti di sistema: `kicad-cli`, Python con `pcbnew` (in `/opt/venv`), `ngspice`, `pdftotext`/`pdftoppm`,
kicad-happy in `$KICAD_HAPPY_DIR`, Freerouting in `$FREEROUTING_JAR`.

## Skill (caricale quando servono)

- `selezione-componenti`: per scegliere o sostituire un componente.
- `datasheet`: per scaricare, leggere e applicare un datasheet.
- `verifiche`: per chiudere un blocco dello schema o la fase PCB (ERC/DRC, SPICE, calcoli, report, revisione indipendente).
- `layout-pcb`: per posizionare componenti, sbrogliare, creare zone di rame e controllare il layout.
- `produzione-jlc`: per preparare il pacchetto d'ordine e la checklist JLCPCB.

## Progetto corrente

<!-- Da compilare per ogni progetto: nome, documento dei requisiti, blocchi dello schema e stato di avanzamento. -->
