# Ordine JLCPCB – prova

Generato il 2026-11-21 16:06 da `tools/jlc_export.py`. Commit: `nessuno`

## File da caricare

| File | Dove |
|---|---|
| `prova-gerber.zip` | Add gerber file |
| `prova-bom.csv` | PCB Assembly → BOM |
| `prova-cpl.csv` | PCB Assembly → CPL |

## PCB

| Opzione | Valore | Note |
|---|---|---|
| Base material | FR-4 | |
| Layers | 2 | |
| Dimensions | 20.0 × 15.0 mm | dal bordo scheda; JLC le rilegge dal Gerber: devono coincidere |
| PCB Qty | 5 | **da confermare** |
| Product type | Industrial/Consumer electronics | |
| PCB thickness | 1.6 mm | |
| PCB color | Green | economico, compatibile con Economic PCBA |
| Surface finish | **da scegliere** | proposta: HASL lead-free (economico; ENIG se ci sono componenti a passo fine < 0,5 mm o BGA) |
| Outer copper weight | 1 oz | |
| Via covering | Tented | |
| Mark on PCB | **da scegliere** | "Remove mark" costa di più; altrimenti JLC stampa un numero sulla serigrafia |

## PCB Assembly

| Opzione | Valore |
|---|---|
| PCBA type | Economic |
| Assembly side | Top |
| PCBA Qty | **da confermare** (≤ 5) |
| Tooling holes | Added by JLCPCB |
| Confirm parts placement | Yes |

## Componenti

- Montati da JLC: 2 posizioni, 2 righe di BOM.
- Da saldare a mano (senza codice LCSC): J1
- Non montati (DNP): nessuno
- Rotazioni corrette automaticamente: nessuna

## Controlli durante l'ordine

- [ ] Pagina dei componenti: nessun componente mancante o sostituito, stock sufficiente (`tools/jlc_parts.py check-bom --qty 5`).
- [ ] Anteprima di posizionamento: pin 1 e polarità di: **D1**.
- [ ] Costo degli Extended coerente con il report `build/reports/bom-check.md`.
- [ ] Le dimensioni lette da JLC coincidono con 20.0 × 15.0 mm.

Le regole e i prezzi di JLC cambiano: se qualcosa nel modulo non corrisponde a questa checklist, fermati e chiedi.

## Registro dell'ordine

- Data:
- Numero d'ordine:
- Correzioni di rotazione fatte nell'anteprima (riportarle in `tools/jlc_rotations.csv`):
