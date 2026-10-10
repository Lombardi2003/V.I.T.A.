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
python scripts/setup_env.py --key NAME # asks for one key the app does not use (a benchmark model, a second account)
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
- The **sidebar** on the left lists the past chats, by day. A chat is titled "Nuovo triage" with its time, and with the patient's name once the card is confirmed; the fiscal code never appears as a title. A past chat can be reopened and read, not continued, and it can be deleted from its menu.

</div>

---

## ⚙️ Choosing the models

<div align="justify">

The models the app starts with are chosen in one place, at the top of `src/llm/factory.py`: `TEXT_MODEL` for every text agent and `VISION_MODEL` for the photo. The available models, with the provider each one belongs to, are listed in `src/llm/providers.py`: adding a provider or a model means adding a few lines there. The choice is in the code, not in `.env`, so every commit records which models the system ran with.

While the app runs, the settings panel (the icon beside the message box) lets the operator pick another text or vision model among those whose key is set. The model can be changed only before the first message: a triage runs on one model from start to end, and a new chat is needed to change it. The choice made in the panel lasts until the app is restarted. Keys are never entered in the app: they are set with `scripts/setup_env.py`.

</div>

| Text models | Developed by | Runs on |
|---|---|---|
| gpt-oss-120b (active) | OpenAI | Groq |
| gpt-oss-20b | OpenAI | Groq |
| gemini-3.8-flash | Google | Google |
| llama3.2 | Meta | Ollama (local) |
| llama3.1 (8B) | Meta | Ollama (local) |
| qwen3 (8B) | Alibaba | Ollama (local) |
| qwen3 (14B) | Alibaba | Ollama (local) |
| ministral-3 (8B) | Mistral AI | Ollama (local) |
| ministral-3 (14B) | Mistral AI | Ollama (local) |
| llama-3.2-3b-instruct | Meta | Hugging Face (Featherless AI) |
| llama-3.2-3b-instruct | Meta | Cloudflare |
| llama-3.2-1b-instruct | Meta | Cloudflare |

| Vision models | Developed by | Runs on |
|---|---|---|
| qwen3.8-27b (active) | Alibaba | Groq |
| gemini-3.8-flash | Google | Google |
| moondream | M87 Labs | Ollama (local) |

<div align="justify">

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

## 📊 Model benchmark

<div align="justify">

The `benchmark/` folder compares language models on the same 15 triage cases, three per priority code, each built from one row of a regional triage manual that gives the expected code. Every model is run in three conditions: the full system, from the supervisor to the report; the model alone, asked once with the guidelines and the rules but without the round table; and the bare model, asked once with the patient only. Every model goes through the same four steps in the same order and stops where its quota allows. It uses API quota, saves each case as soon as it ends and restarts from where it stopped.

</div>

```bash
python -m benchmark.run --model GPT_OSS_120B --step 1   # the model alone, on the 15 cases
python -m benchmark.run --model GPT_OSS_120B --step 2   # the full system, on the 5 core cases
python -m benchmark.run --model GPT_OSS_120B --step 3   # the full system, on the other 10 cases
python -m benchmark.run --model GPT_OSS_120B --step 4   # the bare model, on the 15 cases
python -m benchmark.table                               # the tables (Markdown and CSV), from the saved results
```

<div align="justify">

What is measured and how is fixed in [benchmark/PROTOCOL.md](benchmark/PROTOCOL.md); the patients and the expected answers are in [benchmark/CASES.md](benchmark/CASES.md).

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
  model_choice.py       settings panel: models that can be chosen, changing the model
  chat_history.py       chat archive: its tables, the chat title
  agents/               one file per agent (intake, reviewer, photography,
                        supervisor, specialist, router, primary) + persistence
  llm/                  model catalogue, clients, calls and retries
  rag/                  guideline index and retrieval
scripts/setup_env.py    creates or completes .env
tests/                  unit tests, retrieval benchmark, live scripts
benchmark/              model benchmark: cases, protocol, runner, measures, results
data/                   guidelines (PDF), search index, patient database and chat archive (not versioned)
docs/                   architecture, design decisions, results of the real runs
public/, .chainlit/     interface: avatars, style, configuration
chainlit.md             the "Leggimi" page shown inside the app
```

---

## 📚 Documentation

| Document | Answers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the system is built: flow, state, and what each file does. |
| [docs/DESIGN.md](docs/DESIGN.md) | Why it is built that way: decisions, observations, discarded alternatives, known limits. |
| [docs/results/RESULTS.md](docs/results/RESULTS.md) | What the runs with the real models showed, with their logs. |
| [tests/README.md](tests/README.md) | How to run the tests and what each kind checks. |
| [benchmark/PROTOCOL.md](benchmark/PROTOCOL.md) | How the models are compared: cases, conditions, measures, limits. |
| [benchmark/CASES.md](benchmark/CASES.md) | The 15 benchmark patients, each with the expected code and specialty. |
| [data/README.md](data/README.md) | How the guidelines are organised and how to rebuild the index. |