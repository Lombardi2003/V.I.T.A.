<div align=center>

# 🩺 V.I.T.A. — Virtual Intelligent Triage Assistant
</div>
<div align=justify>
A multi-agent medical triage assistant that simulates the emergency room process: it collects patient data, routes it among AI specialists, and produces a clinical report with a priority code.

---

## 📖 Description

**V.I.T.A.** is built entirely in Python with **LangGraph** and **LangChain**, and orchestrates a team of specialized AI agents that collaborate along a state graph to reproduce a realistic triage flow:

1. A **Reviewer** agent collects and extracts clinical data from the patient's natural language, checking that the record is complete before proceeding.
2. A **Photography** agent can analyze a photo of the injury/affected area, estimating its severity and clinical description.
3. A **Supervisor** decides which of the 10 available specialists (cardiologist, neurologist, dermatologist, orthopedist, gastroenterologist, pulmonologist, ENT, ophthalmologist, urologist, general practitioner) need to be involved, and a **Router** routes the patient record among them — also allowing consultations between specialists when a symptom falls outside their field.
4. A **Chief Physician** synthesizes all reports into a final diagnosis with a color-coded priority (RED / ORANGE / BLUE / GREEN / WHITE).

Patients are recognized via their Tax ID (Codice Fiscale) on a persistent SQLite database, which accumulates the history of diagnosed conditions over time. The conversational interface is served via **Chainlit**, and the LLM engine is configurable between **Groq** (cloud) and **Ollama** (local).

---

## 🚀 Getting Started

### 1. Dependencies
```bash
    pip install -r requirements.txt
```

### 2. External keys/config
No need to create `.env` by hand: on first startup (`chainlit run app.py`) any missing values are checked and requested automatically — if `.env` is already complete, nothing is asked. This check only verifies that the value is *present*, not that it is *valid*: an expired/revoked key must be updated manually.

```bash
    python scripts/setup_env.py            # fills in missing values
    python scripts/setup_env.py --update   # asks for all values again (e.g. expired key)
```

### 3. Running the program
```bash
    chainlit run app.py -w
```

---

For a deeper technical breakdown of how the system works internally and what each file does, see [ARCHITECTURE.md](ARCHITECTURE.md).
