<div align=center>

<h1> 🩺 V.I.T.A. — Virtual Intelligent Triage Assistant</h1>
</div>
<div align=justify>
Assistente di triage medico multi-agente che simula il processo di pronto soccorso: raccoglie i dati del paziente, li smista tra specialisti AI e produce un referto clinico con codice di priorità.

## 📖 Descrizione

**V.I.T.A.** è costruito interamente in Python con **LangGraph** e **LangChain**, e orchestra una squadra di agenti AI specializzati che collaborano lungo un grafo a stati per riprodurre un flusso di triage realistico:

1. Un agente **Reviewer** raccoglie ed estrae i dati clinici dal linguaggio naturale del paziente, verificando che la scheda sia completa prima di proseguire.
2. Un agente **Photography** può analizzare una foto della lesione/zona interessata, stimandone gravità e descrizione clinica.
3. Un **Supervisor** decide quali tra i 10 specialisti disponibili (cardiologo, neurologo, dermatologo, ortopedico, gastroenterologo, pneumologo, otorino, oculista, urologo, medico generale) devono essere coinvolti, e un **Router** smista la cartella tra loro — permettendo anche consulti tra specialisti quando un sintomo esce dal proprio ambito.
4. Un **Primario** sintetizza tutti i referti in una diagnosi finale con codice colore (ROSSO / ARANCIONE / AZZURRO / VERDE / BIANCO).

I pazienti vengono riconosciuti tramite Codice Fiscale su un database SQLite persistente, che accumula lo storico delle patologie diagnosticate nel tempo. L'interfaccia conversazionale è servita tramite **Chainlit**, e il motore LLM è configurabile tra **Groq** (cloud) e **Ollama** (locale).

---

## 🚀 Come iniziare

### 1. Dipendenze
```bash
    pip install -r requirements.txt
```

### 2. Chiavi/config esterne
Non serve creare `.env` a mano: al primo avvio (`chainlit run app.py`) i valori mancanti vengono controllati e richiesti in automatico — se `.env` è già completo non viene chiesto nulla. Questo controllo verifica solo che il valore sia *presente*, non che sia *valido*: una chiave scaduta/revocata va aggiornata a mano.

```bash
    python scripts/setup_env.py            # completa i valori mancanti
    python scripts/setup_env.py --update   # richiede di nuovo tutti i valori (es. chiave scaduta)
```

### 3. Avvio del programma
```bash
    chainlit run app.py -w
```
