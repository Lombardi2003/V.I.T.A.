<div align="center">

# 🏗️ V.I.T.A. — Architecture

</div>

<div align="justify">

How V.I.T.A. is built: the runtime flow, the shared state, and what each file is responsible for. For installation and usage see the [README](../README.md); for the reasons behind the choices see [DESIGN.md](DESIGN.md).

</div>

## Contents

1. [Overview](#-1-overview)
2. [Conversation flow](#-2-conversation-flow)
3. [Shared state](#-3-shared-state)
4. [The round table](#-4-the-round-table)
5. [File reference](#-5-file-reference)
6. [Outside the code](#-6-outside-the-code)
7. [Known limitations](#-7-known-limitations)

---

<div align="justify">

## 🧩 1. Overview

V.I.T.A. is a state graph. Every step of the triage is a **node**; the nodes read and update one shared **state**; the **edges** decide which node runs next. The graph pauses whenever it needs the operator and resumes when a message arrives.

</div>

| Layer | Where | Role |
|---|---|---|
| Interface | `app.py`, `public/`, `.chainlit/` | The Chainlit chat: receives messages and files, shows what the nodes send. |
| Graph | `src/graph.py` | Wires the nodes together and defines the pauses. |
| State | `src/state.py` | The data every node reads and writes. |
| Agents | `src/agents/` | One file per node: what each step does. |
| Models | `src/llm/` | The only part that knows which provider and model are in use. |
| Guidelines | `src/rag/`, `data/` | The index of clinical guidelines and its retrieval. |
| Database | `src/database.py` | The table of patients. |

<div align="justify">

Two rules hold across the layers. The agents never know which model they run on: they ask `src/llm/` for a client. And a model's answer is never applied as it comes: each node reads it, validates it in code and decides the next step itself.

</div>

---

<div align="justify">

## 🔄 2. Conversation flow

**Startup.** `app.py` makes sure `.env` is complete, builds the graph once, and loads the embedding model and the guideline index so the first specialist is not slower than the others.

**Per conversation.** Each chat gets a `thread_id`. Every operator message is added to the state of that thread, and the graph resumes from where it paused.

</div>

```
START
  │
  ▼
read_db ──(invalid fiscal code)──► user ──► read_db
  │ valid
  ▼
intake ──(data missing or not confirmed)──► user ──► intake
  │ card confirmed
  ▼
reviewer ──(symptoms missing or not confirmed)──► user ──► reviewer
  │ symptoms confirmed
  ▼
photography ──(no photo and no refusal yet)──► user ──► photography
  │ photo analysed or declined
  ▼
supervisor
  │
  ▼
router ◄────────────────────┐
  │                         │
  ├──► specialist (one of 10) ┘      repeated until the table agrees
  │
  ▼
chief_physician
  │
  ▼
save_db
  │
  ▼
END
```

<div align="justify">

**Pauses.** The graph is compiled with an interruption before the `user` node. A node that still needs something from the operator routes to `user`, and the run stops there. When a step is complete, the next node runs at once, so there is exactly one pause per operator message.

**What each node shows.** Every node sends its own chat messages, under its own name and avatar. Model calls appear as collapsed steps.

</div>

| Node | File | Uses a model | What it does |
|---|---|---|---|
| `read_db` | `persistence.py` | no | Validates the fiscal code and looks the patient up. |
| `user` | `graph.py` | no | The pause point: the message is already in the state. |
| `intake` | `intake.py` | text | Collects and confirms the personal data. |
| `reviewer` | `reviewer.py` | text | Collects and confirms the symptoms. |
| `photography` | `photography.py` | vision | Requests the photo and has it described. |
| `supervisor` | `supervisor.py` | text | Chooses the specialists. |
| `router` | `router.py` | no | Decides who speaks next at the table. |
| 10 specialists | `specialist.py` | text | One turn each time: propose, confirm, revise, consult. |
| `chief_physician` | `primary.py` | text | Writes the summary report. |
| `save_db` | `persistence.py` | no | Saves the card. |

---

<div align="justify">

## 🧬 3. Shared state

`src/state.py` defines the state as Pydantic models. `MedicalState` is the top level; the others are nested in it.

</div>

| Model | Content |
|---|---|
| `PatientCard` | Fiscal code, name, age, sex, allergies, previous conditions, and the `SymptomProfile`. |
| `SymptomProfile` | The list of `Symptom` and the optional `PhotoAnalysis`. |
| `Symptom` | Description, intensity, duration, characteristics, trigger. |
| `PhotoAnalysis` | Path of the photo, type of lesion, description. |
| `GroupHypothesis` | The table's shared hypothesis: diagnosis, urgency code, exams, discarded alternative, who confirmed the current version. |
| `RoundTableEntry` | One entry of the discussion: author, recipient, action, content, urgency. |
| `FinalDiagnosis` | The summary report: preliminary hypothesis, code, specialists, exams, data to verify, guidance, reasoning. |

<div align="justify">

Besides these, `MedicalState` holds the conversation histories, the routing value `next_step`, who is seated at the table (`needed_specialists`), the counters and queues of the discussion (turns, failed turns, recruited colleagues, verification round) and the flags that record what has already been shown or confirmed.

**How fields are updated.** Histories and the discussion are accumulated: each node returns only the new items. Everything else is replaced. In particular `patient_card` is always written whole, so anything that changes one part of it reads the card, changes that part and writes it all back.

**Field names and prompts.** The JSON keys the model is asked to return are defined in `src/agents/prompts.py` and read by the nodes; the two are kept in sync by hand.

</div>

---

<div align="justify">

## 👥 4. The round table

The specialists do not write separate reports: they work on one shared hypothesis. A turn is one model call for one specialist, who sees the patient card, the current hypothesis, the whole discussion so far and the retrieved guidelines.

</div>

| Action | Meaning |
|---|---|
| `proponi` | Opens the discussion with a first hypothesis. Only when none exists. |
| `conferma` | Agrees with the current hypothesis. |
| `rivedi` | Rewrites it; everyone else must confirm the new version. |
| `consulta` | Asks a clinical question to a colleague who is not at the table. |

<div align="justify">

**The router** (`src/agents/router.py`) is plain code. At each step it decides who speaks: first whoever was addressed by the last entry, otherwise the next specialist who has not confirmed. It can bring in a colleague who was asked for a consult. When everyone has confirmed, it runs one **verification round** in which each specialist says whether reading the others changed their assessment; then it hands over to the primary.

**The limits** that keep the discussion finite are constants in `src/agents/roundtable.py`.

</div>

| Constant | Value | Meaning |
|---|---|---|
| `MAX_TOTAL_TURNS` | 12 | Turns in the whole discussion. |
| `MAX_SPEAKS_PER_SPECIALIST` | 3 | Turns per specialist, verification excluded. |
| `MAX_FAILED_TURNS` | 2 | Unreadable or failed turns before a specialist is moved on. |
| `MAX_RECRUITED_SPECIALISTS` | 1 | Colleagues added during the discussion. |
| `MAX_SELECTED_SPECIALISTS` | 3 | Specialists chosen by the supervisor (`supervisor.py`). |

<div align="justify">

**The primary** (`src/agents/primary.py`) receives the hypothesis, the discussion, every urgency code stated at the table and the list of who confirmed and who did not. It may confirm the table's code or raise it, never lower it.

</div>

---

<div align="justify">

## 📂 5. File reference

### 🚪 `app.py`

The Chainlit entry point. It registers the chat archive and the automatic user, which together make Chainlit show the history sidebar. `on_chat_start` creates the thread and shows the settings panel; `on_settings_update` applies what the operator confirmed in it; `on_message` locks the model choice at the first message, adds the message (and the path of an attached image) to the state, resumes the graph, and titles the chat once the patient card is confirmed. A node error arrives here as an exception: the traceback goes to the terminal, the chat gets a short message.

### 🎛️ `src/model_choice.py`

The logic of the settings panel, without interface code. `choices` lists the text or vision models whose provider has its key set or needs none; `missing_keys_note` names those left out and how to set their key; `choose` replaces the client the agents use, after checking that a local model is actually served. The agents read the client at every call, so a change takes effect at once and no agent code is involved.

### 🗂️ `src/chat_history.py`

The chat archive. `build_data_layer` creates the file `data/chat_history.db` with the tables Chainlit expects and returns Chainlit's own SQL archive pointed at it; from then on Chainlit saves every message and step by itself. `chat_title` builds the title of a chat from the patient's name and `rename_chat` writes it to the archive and to the sidebar. No file storage is configured, so attached photos are not archived.

### 🕸️ `src/graph.py`

`generate_graph()` registers the nodes and the edges and compiles the graph with an in-memory checkpointer and the pause before `user`. `thread_config(thread_id)` returns the configuration every caller must use: the thread and the step limit of a run, computed from the turn cap.

### 🧬 `src/state.py`

The models described in section 3.

### 🗄️ `src/database.py`

`PatientRecord` is the table (primary key: the fiscal code). `MedicalDatabase` exposes `read_patient`, `upsert_patient` (creates or updates the whole card) and `verify_patient_exists`. The file is `data/medical_database.db`: it is created at the first start and is not under version control.

### 📝 `src/log.py`

The terminal log. `get_logger(name)` gives each part of the project its logger. The normal level shows the flow and the problems without patient data; setting the environment variable `VITA_LOG_LEVEL=DEBUG` before starting the app adds the patient card, the model's answers and the retrieved text.

### 🔐 `src/settings.py`

Reads `.env`: the provider keys and the temperature. Which models run is not here (see `src/llm/factory.py`).

### ⚙️ `src/agents/`

</div>

| File | Content |
|---|---|
| `common.py` | The two model clients (text and vision), created once; the database object; helpers that bring a model's answer back to the expected type (`as_list`, `as_text`, `is_yes`, `is_no`). |
| `prompts.py` | Every prompt, the definition of the five triage codes shared by the prompts that ask for one, and the list of the ten specialist roles. |
| `authors.py` | The names shown in the chat; each matches an avatar in `public/avatars/`. |
| `persistence.py` | Fiscal code validation, `read_db_node`, `save_db_node`. |
| `intake.py` | `intake_node`: the card, its normalisation, confirmation and corrections. |
| `reviewer.py` | `reviewer_node`: symptoms, with the checks against invented values. |
| `photography.py` | `photography_node`: request, refusal, image preparation, vision call. |
| `supervisor.py` | `supervisor_node`: selection, cap, second opinion, fallback. |
| `roundtable.py` | What the table shares: specialist names, limits, urgency codes, transcript, paediatric note. |
| `specialist.py` | `specialist_node` (the logic of a turn) and the ten thin nodes that call it. |
| `router.py` | `router`: who speaks next and when the discussion ends. |
| `primary.py` | `primary_node`: the report, the code floor, the fallbacks. |

<div align="justify">

`__init__.py` re-exports the nodes, so the graph imports them from `src.agents`.

### 🤖 `src/llm/`

</div>

| File | Content |
|---|---|
| `providers.py` | Everything needed to reach a model, in one place: each provider (address, key, limits) and each model (its provider and what is particular about it). |
| `factory.py` | The **active models** (`TEXT_MODEL`, `VISION_MODEL`) and `build_llm()`, which builds the client of a model. Every provider is reached through the same OpenAI-compatible client. |
| `calls.py` | `call_with_retry` (retries after temporary errors, waiting the time the provider suggests), `stream_text` (a full answer, with the answer size kept within the per-minute limit), `extract_json` (the JSON object inside an answer). |

<div align="justify">

### 🔍 `src/rag/`

</div>

| File | Content |
|---|---|
| `build_index.py` | Run by hand (`python -m src.rag.build_index`): reads the PDFs, cleans the text, splits it into chunks, discards the useless ones, embeds the rest locally and writes the index. |
| `retriever.py` | `build_queries` (one query per symptom) and `retrieve` (chunks from the specialist's own documents plus one from the general ones, each with document and page). Returns nothing, without failing, if there is no index. |

<div align="justify">

The embedding model is `intfloat/multilingual-e5-small`, run locally. The corpus and the file-name convention are described in [data/README.md](../data/README.md).

### 🧰 `scripts/setup_env.py`

Creates or completes `.env`. The values to ask for are read from the `Settings` class; a provider key is requested only if one of the active models needs it. `ensure_env()` runs at startup, followed by `ensure_session_secret()`, which generates once the secret that signs the user's session and keeps it in `.env`; `--update` asks for everything again, `--key NAME` asks for one key that no active model needs (a model of the benchmark, a second account).

### 🧪 `tests/`

Unit tests on the real graph with a fake model, the retrieval benchmark, and the scripts that use the real model. See [tests/README.md](../tests/README.md).

### 📊 `benchmark/`

The model benchmark: the same cases run with different models. It drives the real graph and reads the prompts of `src/agents/prompts.py`, so it always measures the system as it is; nothing in `src/` depends on it. Its rules are in [benchmark/PROTOCOL.md](../benchmark/PROTOCOL.md).

</div>

| File | Content |
|---|---|
| `PROTOCOL.md` | What is measured and how: cases, conditions, measures, limits. |
| `cases.py` | The 15 cases: the patient card, and the manual row that gives the expected code and specialty. |
| `CASES.md`, `cases_doc.py` | The readable version of the cases, and the script that writes it from `cases.py`. |
| `run.py` | Runs one model on the cases in the two conditions, counts calls and tokens, saves each case as it ends and resumes. |
| `baseline.py` | The "model alone" condition: one request with the card and the retrieved guidelines. |
| `metrics.py` | The measures, computed from the raw results. |
| `table.py` | Builds the results table. |
| `results/` | One `.jsonl` file of raw results per model, and `TABLE.md`. Created at the first run. |

---

<div align="justify">

## 🎨 6. Outside the code

Chainlit looks for these in the folder the app is started from, which is why they sit at the top of the project.

</div>

| Path | Content |
|---|---|
| `.chainlit/config.toml` | Interface configuration, including the upload rules (images only, one file, 20 MB). |
| `public/avatars/` | One avatar per chat author; the file name is the author's name. |
| `public/style.css`, `public/icon/`, `public/favicon.svg` | Style and logo. |
| `chainlit.md` | The page shown by "Leggimi" inside the app. |
| `.files/` | Uploaded photos, created at run time and not under version control. |

---

<div align="justify">

## ⚠️ 7. Known limitations

- **Conversations live in memory.** The checkpointer keeps the state of open conversations in the process; it does not survive a restart. Patient records, once saved, are in the database, and the text of every chat is in the chat archive: a past chat can be read again, not resumed.
- **The model in use determines the clinical quality.** The code limits the effect of a wrong or unusable answer; it cannot make the reasoning correct.
- **Guidelines are written for adults.**

The full list, with the planned developments, is in section 15 of [DESIGN.md](DESIGN.md).

</div>
