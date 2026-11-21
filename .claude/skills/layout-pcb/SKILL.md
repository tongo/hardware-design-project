---
name: layout-pcb
description: Come impostare e modificare il PCB in KiCad 10 senza interfaccia grafica, tramite script Python pcbnew (posizionamento, piste, zone di rame, sbroglio con Freerouting), con regole di layout e controlli. Usala nella fase PCB, solo dopo l'approvazione dello schema completo.
---

# Layout PCB

## Principi

- Il file `.kicad_pcb` **non si legge e non si modifica a mano**. Usa script Python con `pcbnew` (in `/opt/venv`), salvati in `hardware/scripts/`
  così si possono rilanciare e restano in git.
- Commit git prima di ogni script che modifica la scheda.
- Note sull'API `pcbnew` di KiCad 10 (verificate):
  - per togliere un oggetto usa `board.Delete(oggetto)`: `board.Remove(oggetto)` manda in crash Python (segmentation fault);
  - le net con etichette locali si chiamano `/NOME` (es. `/GND`): cerca con `board.FindNet("GND") or board.FindNet("/GND")`;
  - dopo aver creato o spostato zone: `pcbnew.ZONE_FILLER(board).Fill(board.Zones())`, poi `pcbnew.SaveBoard(percorso, board)`.
- L'utente non deve avere il PCB aperto nell'app sul Mac mentre lo modifichi.
- Dopo ogni passo: `tools/check.sh` e, nei punti chiave, `tools/render.sh`.

## Impostazione iniziale

1. Copia le regole del produttore: `cp rules/jlcpcb-2layer.kicad_dru hardware/<nome>.kicad_dru`.
2. Definisci le net class (segnale, potenza, 12 V, analogico) con larghezze e distanze adeguate.
3. Importa i componenti dallo schema con `tools/sch_to_pcb.py hardware/<nome>` (kicad-cli 10 non ha un comando
   "Aggiorna PCB da schema"; lo script fa lo stesso via netlist + pcbnew: footprint, valori, campi, collegamento ai simboli, net).
   Rilancialo dopo ogni modifica dello schema; i footprint in più si cancellano solo con `--delete-extra`.
   In alternativa l'utente può usare F8 nell'app sul Mac. Esempio completo di script di posizionamento:
   `hardware/prova/scripts/place.py`.
4. Disegna il bordo scheda (Edge.Cuts) secondo dimensioni e fori di fissaggio dei requisiti.

## Posizionamento (prima di qualsiasi pista)

Script che posiziona i componenti con coordinate esplicite, in quest'ordine:
1. connettori e componenti con posizione obbligata (bordo, fori, antenna sul bordo con keep-out);
2. componenti di potenza e protezioni, vicino all'ingresso dell'alimentazione;
3. microcontrollore e chip principali;
4. condensatori di disaccoppiamento il più vicino possibile ai pin di alimentazione;
5. il resto, raggruppato per blocco funzionale, come nello schema.

Tutti i componenti SMD vanno sul lato top (Economic PCBA monta un solo lato).

## Piste

1. **A mano, via script**: alimentazione, linee a 12 V, segnali analogici, coppie differenziali (CAN, USB), cristalli e clock.
2. **Con Freerouting** (`tools/route.py`): il resto. Escludi le net già sbrogliate o servite dai piani (`--ignore-nets GND`).
3. Zone di rame: piano GND su entrambi i lati (2 layer) o su un layer interno (4 layer), via di cucitura, riempimento delle zone a fine script.

## Regole di layout da rispettare

- Piano di massa il più continuo possibile; nessuna pista che lo tagli sotto segnali veloci o analogici.
- Anello stretto ingresso → protezioni → regolatore; induttanza e diodo dello switching vicini al chip.
- Parte analogica (sensori, ADC) lontana dallo switching, con massa ben collegata.
- Keep-out sotto l'antenna del modulo radio, secondo il datasheet.
- Test point su alimentazioni, bus e segnali principali, raggiungibili con i puntali.
- Serigrafia: riferimenti leggibili, pin 1, polarità, nome della scheda, versione e data.

## Controlli finali

Segui la sezione "B. Fase PCB" della skill `verifiche`.
