# VITA - Virtual Intelligent Triage Assistant

Assistente di triage medico multi-agente, con interfaccia Chainlit.

## Avvio

### 1. Dipendenze
```bash
    pip install -r requirements.txt
```

### 2. Chiavi/config esterne
Non serve creare `.env` a mano: al primo avvio (`chainlit run app.py`) i valori mancanti vengono controllati e richiesti in automatico, se `.env` è già completo non viene chiesto nulla. Questo controllo verifica solo che il valore sia presente, non che sia valido: una chiave scaduta/revocata va aggiornata a mano. Per lanciare il setup manualmente, o per aggiornare una chiave scaduta/revocata:
```bash
    python scripts/setup_env.py            # completa i valori mancanti
    python scripts/setup_env.py --update   # richiede di nuovo tutti i valori
```

### 3. Avvio del programma
```bash
    chainlit run app.py -w
```
