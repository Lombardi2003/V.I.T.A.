# 🩺 VITA - Virtual Intelligent Triage Assistant

**VITA** (Virtual Intelligent Triage Assistant) è un sistema avanzato di **Multi-Agent AI** progettato per simulare un processo di triage medico di emergenza.

Costruito interamente in Python utilizzando **LangGraph** e **LangChain**, il sistema orchestra una squadra di agenti AI specializzati (alimentati da **Llama 3** via Ollama) che collaborano per analizzare i sintomi, formulare diagnosi differenziali e assegnare un codice di priorità.

---

## 🚀 Caratteristiche Principali

* **🧠 Architettura Multi-Agente:** Utilizza il pattern *Supervisor-Worker*. Un agente supervisore coordina il flusso, attivando specialisti (Cardiologo, Neurologo) solo quando necessario.
* **🔒 Privacy-First:** Esegue l'intero processo in locale utilizzando **Ollama** e per migliorare la velocità esegue tramite *API-KEY* su architettura **GROQ**.
* **📝 Memoria di Stato Persistente:** Grazie a `MedicalState`, il sistema mantiene una cronologia coerente ("general_hisory") di tutta la conversazione tra gli agenti.
* **📄 Output Strutturato:** Fornisce un report clinico finale chiaro

---

## 🛠️ Architettura del Sistema

Il progetto si basa su un grafo a stati (**StateGraph**) che gestisce il flusso decisionale:

```mermaid
graph
    Start(**USER**) --Input--> Revisore
    Start(**USER**) -- Input Foto --> Fotografo
    Revisore --> Fotografo
    Fotografo -- Richiesta Foto --> Start(**USER**)
    Fotografo ---> Supervisor{Decisione Supervisore}
    Revisore --Insufficiente--> Start(**USER**)

    subgraph Specialisti
        Cardio[Agente Cardiologo]
        Neuro[Agente Neurologo]
    end
    
    Supervisor --"Cardiologo"--> Cardio
    Supervisor --"Neurologo"--> Neuro

    Cardio --> Supervisor
    Neuro --> Supervisor

    Supervisor --"FINISH"--> Primary[Agente Primario/Synthesizer]
    Primary --> End(**MEDICAL REPORT**)

    style Start fill:#bfb,stroke:#333,stroke-width:2px
    style End fill:#f88,stroke:#333,stroke-width:2px
```

---

## I Ruoli degli Agenti (Nodi)
1. **🧐 Revisore**: Analizza l'input e determina se sono necessari altre informazioni
2. **👮 Supervisor (Router)**: Analizza l'input e decide quale specialista consultare o se terminare il consulto.
3. **🫀 Cardiologo**: Specialista in patologie cardiovascolari. Interviene su dolori toracici, aritmie, dispnea.
4. **🧠 Neurologo**: Specialista in patologie del sistema nervoso. Interviene su emicranie, svenimenti, parestesie.
5. **👨‍⚕️ Primario (Synthesizer)**: Non dialoga. Rilegge l'intera conversazione tra gli specialisti e compila il Referto Clinico finale.

## 📂 Struttura del Progetto
```bash
    VITA/
    ├── main.py         # Entry point: costruisce ed esegue il Grafo
    ├── nodes.py        # Logica degli agenti (funzioni dei nodi)
    ├── state.py        # Definizione della struttura dati (MedicalState)
    ├── config.py       # Gestione dei Prompt e configurazione Modello
    └── README.md       # Documentazione
```

## ▶️ Utilizzo
Avvia il sistema eseguendo il file principale:
```bash
    python main.py
```
Il terminale chiederà di inserire i sintomi del paziente. **Esempio**:
*"Il paziente lamenta forte dolore al petto irradiato al braccio sinistro e sudorazione fredda."*
Il sistema mostrerà a schermo il ragionamento degli agenti in tempo reale e concluderà con il referto.

## ⚙️ Personalizzazione
Cambiare modello o modificare il comportamento?
- Cambiare Modello (es. Mistral, Gemma): Modifica la variabile llm in nodes.py.
- Modificare i Prompt: Vai su config.py per cambiare le istruzioni date agli specialisti o le regole di assegnazione dei codici colore.

```mermaid
graph TD
    Triage --> FanOut1[Inizio Parallelo]
    
    subgraph FASE 1: BOZZE
        FanOut1 --> DraftCardio
        FanOut1 --> DraftNeuro
    end
    
    DraftCardio --> Sync1[Sincronizzazione]
    DraftNeuro --> Sync1
    
    Sync1 --> FanOut2[Inizio Revisione]
    
    subgraph FASE 2: REVISIONE
        FanOut2 --> ReviewCardio
        FanOut2 --> ReviewNeuro
    end
    
    ReviewCardio --> Sync2[Fine]
    ReviewNeuro --> Sync2
    
    Sync2 --> Primario
```