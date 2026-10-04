<div align="center">

# 🩺 V.I.T.A. — Virtual Intelligent Triage Assistant

</div>

<div align="justify">

A multi-agent assistant that supports emergency-department triage: it collects the patient's data in conversation with the staff, lets a table of AI specialists discuss the case on the basis of clinical guidelines, and produces a summary report with a priority code.

</div>

---

## 📖 What it does

<div align="justify">

V.I.T.A. is written in Python with **LangGraph** and **LangChain**, and is used through a **Chainlit** chat by the emergency-department staff (not by the patient). A conversation follows the path of a real triage:

1. 🗂️ **Patient lookup.** The operator enters the patient's fiscal code. It is validated (format and check character) and searched in the database: a returning patient's card is loaded, a new one is opened.
2. 🪪 **Intake.** Personal data, allergies and previous conditions are collected from natural language. The card is shown at every turn and must be confirmed.
3. 🩺 **Reviewer.** Symptoms are collected one by one, each with intensity, duration, characteristics and circumstances, and confirmed.
4. 📷 **Photography.** An optional photo of the affected area is described by a vision model.
5. 🚦 **Supervisor.** Chooses which of the 10 specialists to involve (at most three; a single specialist gets the general practitioner for a second opinion).
6. 👥 **Round table.** The specialists discuss a single shared hypothesis: they propose, confirm, revise it, or ask a colleague for a consult, citing the retrieved guidelines. A router decides who speaks next and when the discussion is over.
7. 📋 **Primary.** Turns the table's hypothesis into the summary report for the staff: priority code, preliminary hypothesis, exams, data to verify, operational guidance, reasoning.
8. 💾 **Save.** The confirmed card is saved, with the hypothesis recorded as *not confirmed*.

</div>

| | |
|---|---|
| **Specialists** | cardiology, neurology, dermatology, orthopaedics, gastroenterology, pulmonology, otorhinolaryngology, ophthalmology, urology, general medicine |
| **Priority codes** | ROSSO · ARANCIONE · AZZURRO · VERDE · BIANCO (Italian triage colour codes) |
| **Guidelines** | 23 Italian emergency-department documents, searched locally (see [data/README.md](data/README.md)) |
| **Models** | any OpenAI-compatible provider: Groq and Gemini (cloud), Ollama (local) |
| **Language** | the app speaks Italian; code, comments and tests are in English |

---

## 🚀 Getting started

### 1. Requirements

<div align="justify">

Python 3.12 (the version the project was developed and tested with) and the packages in `requirements.txt`:

</div>

```bash
pip install -r requirements.txt
```

### 2. Keys

<div align="justify">

There is no `.env` to write by hand. At the first start, the app asks only for the API keys of the providers its models actually use; a local Ollama setup needs none. The check verifies that a key is present, not that it is valid.

</div>

```bash
python scripts/setup_env.py            # asks for the missing values
python scripts/setup_env.py --update   # asks for every value again (e.g. an expired key)
```

### 3. Run

```bash
chainlit run app.py -w
```

<div align="justify">

The guideline index is included in the repository, so nothing has to be built before the first run. At startup the terminal shows the models in use; during a conversation it shows the flow, without patient data. Set the environment variable `VITA_LOG_LEVEL=DEBUG` before starting to also see the patient card and the model's answers (development only).

</div>

---

## 💬 Using the app

<div align="justify">

- Start by entering a **fiscal code**. The code `1234` is a test code: it is always accepted, always opens a new patient and is never saved.
- Answer in plain Italian. When the card or the symptoms are complete, the app asks for confirmation; a correction is always possible ("sì, ma l'età è 45", "togli la nausea").
- When asked for a **photo**, attach an image or write "no".
- From there the discussion runs on its own, up to the summary report.

</div>

---

## ⚙️ Choosing the models

<div align="justify">

The models are chosen in one place, at the top of `src/llm/factory.py`: `TEXT_MODEL` for every text agent and `VISION_MODEL` for the photo. The available names are listed in `src/llm/models.py`. The choice is in the code, not in `.env`, so every commit records which models the system ran with.

Free-tier limits affect speed: with a per-minute token limit the app waits and resumes by itself, and a discussion can take a few minutes.

</div>

---

## 🧪 Tests

```bash
python -m tests.run all
```

<div align="justify">

Runs the unit tests (real graph, fake model, no API quota) and the retrieval benchmark. Scripts that use the real model are run separately, on request. See [tests/README.md](tests/README.md).

</div>

---

## 📂 Project structure

```
app.py                  Chainlit entry point
src/
  state.py              data model shared by the whole graph
  graph.py              the graph: nodes, edges, pauses
  database.py           patient table
  settings.py           keys and temperature, read from .env
  log.py                terminal log (normal and detailed level)
  agents/               one file per agent (intake, reviewer, photography,
                        supervisor, specialist, router, primary) + persistence
  llm/                  model catalogue, clients, calls and retries
  rag/                  guideline index and retrieval
scripts/setup_env.py    creates or completes .env
tests/                  unit tests, benchmark, live scripts
data/                   guidelines (PDF), search index, patient database (not versioned)
docs/                   architecture and design decisions
public/, .chainlit/     interface: avatars, style, configuration
chainlit.md             the "Leggimi" page shown inside the app
```

---

## 📚 Documentation

| Document | Answers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the system is built: flow, state, and what each file does. |
| [docs/DESIGN.md](docs/DESIGN.md) | Why it is built that way: decisions, observations, discarded alternatives, known limits. |
| [tests/README.md](tests/README.md) | How to run the tests and what each kind checks. |
| [data/README.md](data/README.md) | How the guidelines are organised and how to rebuild the index. |