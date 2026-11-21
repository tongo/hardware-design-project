---
name: datasheet
description: Come scaricare, archiviare, consultare in modo economico (pochi token) e applicare datasheet, application note e linee guida hardware dei componenti. Usala ogni volta che devi scegliere un componente, disegnare il circuito attorno a un chip o controllarne i limiti.
---

# Datasheet

## Archiviazione

- Scarica con `tools/datasheet.py get <url> <produttore>_<codice>_<revisione>`. Il comando salva il PDF in `docs/datasheets/`,
  estrae il testo (`.txt`) e crea un indice delle sezioni chiave con i numeri di pagina (`.index.md`).
- Preferisci il PDF dal **sito del produttore** (ultima revisione) a quello di LCSC.
- Se il firewall blocca il sito, non aggirarlo: chiedi all'utente di lanciare `sudo fw-allow <dominio>` oppure di salvare lui il PDF in `docs/datasheets/`.
- Archivia anche i documenti collegati: application note, reference design, **hardware design guidelines** (per i microcontrollori sono fondamentali:
  per esempio le linee guida hardware di Espressif per l'ESP32).

## Lettura economica

1. Leggi prima `<nome>.index.md`, che dice in quali pagine si trova cosa.
2. Usa `tools/datasheet.py find <nome> <parola>` per le ricerche mirate.
3. Leggi solo le pagine necessarie con `tools/datasheet.py page <nome> <n>`.
4. Per schemi, figure e disegni del package usa `page <nome> <n> --png` e guarda solo quell'immagine.
5. Non aprire mai l'intero PDF.

## Cosa estrarre sempre

- **Absolute maximum ratings** e **recommended operating conditions**: confrontali con le condizioni reali (con margine).
- **Pin description**: funzione di ogni pin, quali vanno a massa, a VCC o lasciati liberi, e cosa succede ai pin non usati.
- **Typical application / application information**: il circuito di contorno consigliato, con valori e note.
- **Layout guidelines**: posizione dei condensatori, piani di massa, piste critiche, area sotto antenne o pad termici.
- **Temporizzazioni e comportamenti particolari**: timeout, stati all'accensione, pin di boot, tempi di conversione.
- **Package e land pattern** consigliato, da confrontare con il footprint KiCad.
- **Ordering information**: il codice completo corrisponde a quello LCSC scelto (package, range di temperatura, imballo)?

## Applicazione

- Il circuito attorno al chip segue l'application circuit del datasheet.
- Ogni scostamento va motivato nella scheda del componente (`docs/components/`), con la pagina del datasheet di riferimento.
- Nello schema, accanto al blocco, aggiungi una nota breve: "Circuito da <datasheet> rev X, pag. N".
