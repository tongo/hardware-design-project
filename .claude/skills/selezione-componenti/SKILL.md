---
name: selezione-componenti
description: Procedura per scegliere o sostituire un componente elettronico (chip, regolatore, connettore, passivo critico) partendo dai requisiti d'uso, con verifica del ciclo di vita, della disponibilità JLCPCB e del datasheet. Usala prima di inserire un nuovo componente nello schema.
---

# Selezione dei componenti

## 1. Requisiti d'uso (prima del chip)

Scrivi cosa deve fare la funzione **nel caso reale**, non le caratteristiche del chip:
- grandezze e range (tensioni, correnti, segnali);
- frequenza di campionamento o di aggiornamento, numero di canali, latenza;
- interfaccia verso il microcontrollore e **come la userà il firmware** (lettura continua, interrupt, DMA, polling);
- ambiente: temperatura, vibrazioni, disturbi (in un veicolo: transitori sull'alimentazione);
- vincoli: package assemblabile da JLC (minimo 0402, passo IC ≥ 0,4 mm in Economic), costo, ingombro.

Esempio di errore da evitare: un ADC "buono sulla carta" ma con un solo convertitore multiplexato, che per leggere più canali
in continuo va riconfigurato via I2C a ogni conversione, quindi è troppo lento per un datalogger.

## 2. Candidati

- Cerca nel database locale: `tools/jlc_parts.py search <parole> --package <pkg> --economic` (poi anche senza `--economic`).
- Per i chip non banali considera almeno 2–3 candidati, includendo le soluzioni consigliate dal produttore del microcontrollore.

## 3. Filtri obbligatori

Scarta il candidato se uno di questi controlli fallisce:
1. **Ciclo di vita**: stato **Active** sulla pagina del prodotto del produttore. Scarta Obsolete, NRND, Last Time Buy, "not recommended for new designs".
   Lo stock su LCSC/JLC **non** prova che il componente sia in produzione.
2. **JLCPCB**: esiste, assemblabile in **Economic**, stock con margine (`tools/jlc_parts.py info Cxxxx`).
   Priorità: Basic, poi Preferred Extended, poi Extended. Un Extended è ammesso solo se motivato.
3. **Datasheet** (skill `datasheet`): requisiti d'uso del punto 1 verificati uno per uno, senza dimenticare temporizzazioni,
   timeout interni, livelli logici, range di temperatura e limiti assoluti.
4. **Circuito di contorno**: quanti componenti servono attorno al chip (application circuit) e se sono Basic.

## 4. Passivi

- Usa valori standard già Basic e unifica i valori nel progetto (meno righe di BOM, meno Extended).
- Condensatori ceramici: tensione nominale almeno il doppio di quella di lavoro, dielettrico X7R/X5R, attenzione alla perdita di capacità con la tensione DC (DC bias).
- Resistenze: verifica la potenza dissipata (P = V²/R) e scegli il package di conseguenza.

## 5. Scheda di selezione

Crea `docs/components/<funzione>-<codice>.md` dal template `docs/components/_TEMPLATE.md` e compila tutti i campi.
Nel simbolo dello schema inserisci i campi `LCSC`, `MPN` (codice del produttore) e `Datasheet` (percorso locale del PDF).

## 6. Presentazione all'utente

Breve tabella dei candidati (stato, categoria JLC, prezzo, pro e contro per l'uso reale), la scelta consigliata e il motivo,
in italiano semplice. Aspetta la conferma prima di inserirlo nello schema.
