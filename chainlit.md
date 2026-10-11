# V.I.T.A. — Virtual Intelligent Triage Assistant

Assistente di supporto al triage di pronto soccorso. È pensato per il **personale sanitario**, non per il paziente: raccoglie i dati in conversazione, fa discutere il caso a un tavolo di specialisti virtuali sulla base di linee guida cliniche e produce un **report di sintesi** con un codice di priorità.

> **Prototipo accademico.** V.I.T.A. è uno strumento sperimentale di supporto: non sostituisce la valutazione del personale sanitario e non è validato per l'uso clinico. Il contenuto del report è un'ipotesi diagnostica preliminare, da confermare con la valutazione medica.

## Come si usa

1. **Codice fiscale.** Scrivere il codice fiscale del paziente. Se è già registrato, la sua scheda viene recuperata.
2. **Dati anagrafici.** Indicare nome, cognome, età, sesso, allergie e patologie pregresse, anche in una sola frase. La scheda va confermata.
3. **Sintomi.** Descrivere ogni sintomo con intensità e durata. Anche i sintomi vanno confermati.
4. **Foto.** Allegare una foto della zona interessata, oppure scrivere "no".
5. **Report.** Gli specialisti discutono il caso e il primario scrive il report di sintesi.

Una correzione è sempre possibile, in parole semplici: "sì, ma l'età è 45", "togli la nausea".

## Codici di priorità

| Codice | Significato | Accesso |
|---|---|---|
| 🔴 ROSSO | Emergenza: funzioni vitali interrotte o compromesse | immediato |
| 🟠 ARANCIONE | Urgenza: rischio di compromissione delle funzioni vitali | entro 15 minuti |
| 🔵 AZZURRO | Urgenza differibile | entro 60 minuti |
| 🟢 VERDE | Urgenza minore | entro 120 minuti |
| ⚪ BIANCO | Non urgenza | entro 240 minuti |

## Da sapere

- **Codice di prova.** Il codice `1234` serve a provare l'applicazione: apre sempre un paziente nuovo e non salva nulla, né nel database né nella cronologia.
- **Modello.** L'icona delle impostazioni accanto alla casella dei messaggi permette di scegliere il modello, solo prima del primo messaggio di una chat.
- **Cronologia.** La barra laterale elenca le chat passate: si possono rileggere, non continuare.
- **Tempi.** La discussione tra specialisti può richiedere qualche minuto.
