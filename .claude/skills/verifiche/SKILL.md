---
name: verifiche
description: Verifiche, simulazioni e report da eseguire per chiudere un blocco dello schema elettrico o la fase PCB (ERC/DRC, regole del microcontrollore, livelli di tensione, SPICE con ngspice, calcoli, revisione kicad-happy, revisione indipendente). Usala prima di chiedere all'utente l'approvazione di un blocco o di una fase.
---

# Verifiche

L'utente non è un ingegnere elettronico: le verifiche servono a non dover dipendere dal suo giudizio tecnico.
Ogni controllo produce un esito chiaro e una spiegazione semplice.

## A. Blocco di schema

1. **ERC** – `tools/check.sh`: zero errori. I warning vanno risolti oppure motivati nel report. Niente esclusioni di comodo.
2. **Datasheet** – il circuito corrisponde all'application circuit (skill `datasheet`): disaccoppiamento, pull-up/pull-down, pin non usati, valori.
3. **Microcontrollore** – regole delle hardware design guidelines del produttore. Per l'ESP32 classico, per esempio:
   - pin di boot (GPIO0, 2, 5, 12, 15) nello stato corretto all'avvio (GPIO12 alto all'avvio blocca il boot con flash a 3,3 V);
   - GPIO 6–11 non usati (flash);
   - GPIO 34–39 solo ingressi, senza pull interne;
   - ADC2 non usato insieme al Wi-Fi;
   - circuito RC su EN.

   Se non esiste già, scrivi uno script in `sim/` che legga la netlist (`kicad-cli sch export netlist`) e controlli queste regole in automatico.
4. **Livelli di tensione** – su ogni net: nessun segnale a 5 V o 12 V su pin a 3,3 V senza adattamento; ingressi analogici entro il range dell'ADC.
5. **Simulazioni SPICE** (ngspice, in `sim/<blocco>/`), quando il blocco ha parti analogiche o di potenza:
   - circuito `.cir` con modelli del produttore se disponibili (indica nel report se il modello è semplificato);
   - lancio in batch: `ngspice -b sim/<blocco>/<file>.cir -o build/sim/<file>.log`, con istruzioni `.meas` che producono **numeri**, non grafici;
   - casi tipici in un veicolo: transitori ISO 7637-2 / ISO 16750-2 (load dump, impulsi negativi), inversione di polarità, avvio a freddo,
     condizionamento dei sensori (filtri, partitori), terminazioni dei bus;
   - per i grafici usa un PNG piccolo, solo se serve a spiegare qualcosa all'utente.
6. **Calcoli** (script Python in `sim/`):
   - consumi per ogni alimentazione e dissipazione dei regolatori;
   - margini su tensioni e potenze di tutti i componenti;
   - **Monte Carlo** sulle tolleranze delle catene di misura ("qual è l'errore massimo sulla misura?").
7. **kicad-happy** – analisi dello schema (output su file, nel contesto solo i punti rilevanti):
   ```bash
   KH=$KICAD_HAPPY_DIR/skills
   python3 $KH/kicad/scripts/analyze_schematic.py hardware/<nome> --analysis-dir build/kicad-happy --compact -o build/reports/kh-schematic.json
   python3 $KH/kicad/scripts/analyze_schematic.py hardware/<nome> --analysis-dir build/kicad-happy --text --audience designer > build/reports/kh-schematic.txt
   ```
   Leggi il `.txt` con `rg`/`head`, non per intero se è lungo. Per i dettagli vedi `$KH/kicad/SKILL.md`.

## B. Fase PCB

1. **DRC** – `tools/check.sh`: zero errori, parità schema–PCB senza differenze, regole JLC (`hardware/<nome>.kicad_dru`) presenti.
2. **Footprint** – per ogni componente attivo, pad e pin 1 confrontati con il land pattern del datasheet.
3. **Correnti e tensioni** – larghezza delle piste di potenza in base alla corrente (IPC-2221, con margine); distanze maggiori sulle linee a 12 V e oltre.
4. **Layout critico** – disaccoppiamento entro pochi mm dai pin; piano di massa continuo sotto i segnali; area libera sotto l'antenna;
   percorsi di ritorno; parte analogica lontana dallo switching.
5. **EMC e termica** – analisi kicad-happy (EMC pre-compliance, punti caldi):
   ```bash
   KH=$KICAD_HAPPY_DIR/skills; R=build/reports
   python3 $KH/kicad/scripts/analyze_schematic.py hardware/<nome> --analysis-dir build/kicad-happy --compact -o $R/kh-schematic.json
   python3 $KH/kicad/scripts/analyze_pcb.py hardware/<nome> --analysis-dir build/kicad-happy --schematic $R/kh-schematic.json --compact -o $R/kh-pcb.json
   python3 $KH/emc/scripts/analyze_emc.py --analysis-dir build/kicad-happy -s $R/kh-schematic.json -p $R/kh-pcb.json --standard cispr-class-b --text > $R/kh-emc.txt
   python3 $KH/kicad/scripts/analyze_thermal.py --analysis-dir build/kicad-happy -s $R/kh-schematic.json -p $R/kh-pcb.json --text > $R/kh-thermal.txt
   ```
   Standard: `cispr-class-b` per l'Europa (con `--market eu` lo script sceglie FCC), `cispr-25` per un veicolo.
6. **Render** – `tools/render.sh` e controllo visivo; ingombri e connettori sul bordo giusto.

## C. Report

Crea `docs/reports/<AAAA-MM-GG>-<blocco>.md`:
- tabella dei controlli con esito 🟢/🟡/🔴, spiegazione semplice, rischio se ignorato, **affidabilità** della verifica
  (alta: regole e calcoli; media: simulazione con modelli semplificati; bassa: stima);
- per ogni 🟡 e 🔴: cosa proponi di fare;
- numeri chiave (consumi, margini, errori di misura) in una tabella breve.

All'utente mostra solo il riassunto; il dettaglio resta nel file.

## D. Revisione indipendente

Prima di chiedere l'approvazione finale di una **fase** (schema completo, PCB completo), avvia un subagente con contesto pulito che
**non** ha visto la progettazione. Gli passi solo i file di progetto, i datasheet, le schede componenti e i requisiti, e gli chiedi una revisione critica.
Integra le sue osservazioni nel report e segnala dove eravate in disaccordo.

## E. Limiti da dichiarare sempre

- Una simulazione verifica il modello, non la realtà.
- Alcune cose si scoprono solo sul prototipo: il primo ordine è un prototipo con procedura di collaudo scritta
  (alimentatore con limite di corrente, misure sui test point, firmware di prova).
