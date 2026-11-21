---
name: produzione-jlc
description: Preparazione del pacchetto d'ordine per JLCPCB (Gerber, foratura, BOM, CPL con rotazioni corrette, verifica dei componenti) e della checklist delle impostazioni da selezionare nel modulo d'ordine. Usala quando il PCB è approvato e si prepara un ordine.
---

# Produzione JLCPCB

## Prerequisiti

- `tools/check.sh` pulito (ERC, DRC, parità schema–PCB).
- Report della fase PCB approvato dall'utente.
- Commit git e tag di versione, per esempio `hw-v0.1`.

## 1. Verifica dei componenti

1. Aggiorna il database: `tools/jlc_parts.py update`.
2. Esegui `tools/jlc_parts.py check-bom --qty <numero schede>`.
3. Ogni componente deve esistere, essere assemblabile in Economic e avere stock sufficiente.
4. Riporta il numero di Basic, Preferred e Extended, con il costo stimato degli Extended.
5. Se ci sono problemi di stock o componenti diventati Extended, proponi alternative (skill `selezione-componenti`) prima di proseguire.

## 2. Pacchetto

Esegui `tools/jlc_export.py`, che crea in `production/`:
- `<nome>-gerber.zip`
- `<nome>-bom.csv`
- `<nome>-cpl.csv`
- `ORDINE.md`
- i render della scheda

## 3. Controlli sul pacchetto

- Il numero di righe della BOM e di posizioni della CPL corrisponde ai componenti da montare.
- I componenti esclusi (DNP, da saldare a mano) sono elencati in `ORDINE.md`.
- Rotazioni: per IC, diodi, LED, condensatori polarizzati, connettori e moduli segnala in `ORDINE.md` di controllare
  pin 1 e polarità nell'anteprima di posizionamento JLC. È l'errore più comune.

## 4. `ORDINE.md` – checklist per l'utente

Compilala con i valori reali e indica quali scelte restano all'utente.

**PCB**
- Base material: FR-4
- Layers: <2/4>
- Dimensions: <L × H mm> (lette automaticamente dal Gerber)
- PCB Qty: <n>
- Product type: Industrial/Consumer electronics
- PCB thickness: <1,6 mm>
- PCB color: verde (economico e compatibile con Economic PCBA)
- Surface finish: <HASL lead-free / ENIG> (motivare la scelta)
- Outer copper weight: <1 oz>
- Via covering: Tented
- Mark on PCB: <posizione del numero d'ordine, se prevista sulla serigrafia>

**PCB Assembly**
- PCBA type: Economic
- Assembly side: Top
- PCBA Qty: <n>
- Tooling holes: Added by JLCPCB
- Confirm parts placement: Yes
- File da caricare: `<nome>-bom.csv` e `<nome>-cpl.csv`

**Controlli durante l'ordine**
- Nella pagina dei componenti: nessun componente mancante o sostituito, stock sufficiente.
- Nell'anteprima di posizionamento: pin 1 e polarità di ogni componente elencato al punto 3.
- Costo degli Extended coerente con il report.

Le regole e i prezzi di JLC cambiano: se qualcosa nel modulo non corrisponde alla checklist, l'utente deve fermarsi e chiedere.

## 5. Dopo l'ordine

- Registra in `production/ORDINE.md` la data, il numero d'ordine, le eventuali correzioni di rotazione fatte nell'anteprima
  (e aggiorna `tools/jlc_rotations.csv`).
- Prepara la procedura di collaudo del prototipo (skill `verifiche`, sezione E).
