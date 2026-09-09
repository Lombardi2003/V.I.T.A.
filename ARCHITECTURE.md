<div align=center>

# 🏗️ V.I.T.A. — Architecture
</div>
<div align=justify>
Technical reference for how V.I.T.A. is built internally: the runtime flow, and what each file is responsible for. For installation/usage, see [README.md](README.md).

📌 **Status note**: this document describes the system as it exists today, including known limitations that are still being worked on (flagged inline where relevant). It will be kept up to date as the codebase evolves.

---

## 🔄 How it works

**Startup**: `app.py` first makes sure `.env` is complete (`scripts/setup_env.py`), then builds the LangGraph state machine (`src/graph.py`), which wires together all the reasoning nodes defined in the `src/agents/` package. The LLM clients (Groq or Ollama, depending on `USE_CLOUD_ACCELERATION`) and the SQLite connection are created once at startup, not on every message.

**Per-conversation flow**: each chat session gets a `thread_id`. Every message updates a shared `MedicalState` (defined in `src/state.py`) and resumes the graph from wherever it last paused. The graph itself flows:

```
read_db (loops until a valid tax ID is given) → user
        → intake (loops until the anagraphic record is complete)
        → reviewer (loops until the clinical record is complete)
        → photography (optional photo analysis)
        → supervisor → router → specialist(s) (may consult each other) → router → ...
        → chief_physician (final diagnosis)
        → save_db (new patient) / modify_db (returning patient)
        → END
```

* 📂 `read_db` recognizes returning patients from their tax ID before the conversation starts, and keeps re-asking for it if what it received isn't a valid tax ID.
* 🪪 `intake` extracts anagraphic data (name, age, sex, allergies, previous conditions) from natural language, looping back to `user` until every field is filled — allergies/previous conditions are only considered "addressed" once the patient has explicitly mentioned them (or explicitly denied having any), never assumed.
* 🧐 `reviewer` extracts structured clinical data from natural language until the record is complete.
* 👮 `supervisor`/🔀 `router` decide which of the 10 specialists to involve and dispatch the record between them.
* 👨‍⚕️ `chief_physician` synthesizes all specialist reports into a final diagnosis with a priority color.

> 🚧 **Work in progress**: the graph is being reviewed and re-activated one node at a time. As of this writing, `src/graph.py` has `read_db`, `user`, `intake`, `reviewer`, `photography` and `supervisor` wired in; `supervisor` currently terminates the graph directly (not yet connected to `router`) as an intermediate observation point. `router` onward is still commented out (not removed) pending the same review. This section describes the graph's intended full shape once that work is complete.

**Prompts** (`src/agents/prompts.py`) instruct the LLM to return JSON matching the `src/state.py` schema exactly — the two must stay in sync whenever a field is added or renamed.

**Persistence**: `medical_database.db` (`src/database.py`) stores only finalized patient records, separate from the in-progress conversation state (currently held in memory by the graph's checkpointer — see ⚠️ note under `src/graph.py` below).

---

## 📂 File-by-file reference

### 🚪 `app.py`
The Chainlit entry point. Ensures `.env` is complete (`ensure_env()`) before importing anything that depends on it, builds the compiled graph once at import time (`app = generate_graph()`), and defines the two Chainlit event handlers:
- `on_chat_start`: generates a fresh `thread_id` and registers an empty `MedicalState` for it.
- `on_message`: folds the incoming message (and, if present, an uploaded image's path) into the graph state, then resumes graph execution with `app.astream_events(...)`, streaming intermediate "thinking" messages and the chief physician's final answer back to the chat UI.

### 🧬 `src/state.py`
Defines the Pydantic data model shared by the whole graph:
- `MedicalState`: the top-level graph state — conversation history, `patient_card`, routing flags (`next_step`, `triage_complete`, `patient_exists`), `needed_specialists`, `group_hypothesis`, `final_diagnosis`.
- `PatientCard` / `SymptomProfile` / `PhotoAnalysis`: the structured clinical record being built up during triage.
- `GroupHypothesis`: the SHARED diagnostic hypothesis the round table proposes/confirms/revises together turn by turn, instead of N independent per-specialist reports. `FinalDiagnosis`: the output shape the chief physician must produce from it.

Every field name here must match the JSON keys the LLM is asked to return in `src/agents/prompts.py`'s prompts — they're kept in sync by hand, not enforced automatically.

### 🕸️ `src/graph.py`
Builds the `StateGraph` from `langgraph`: registers every node (imported from `src/agents/`) and the edges/conditional routing between them, then compiles it with a checkpointer and `interrupt_before=["user"]` (the mechanism that lets the graph pause between messages and resume later for the same `thread_id`).

> ⚠️ **Known limitation**: the checkpointer is currently `MemorySaver`, which keeps all in-progress conversation state in the process's RAM. It does not survive a process restart — patients mid-triage would lose their progress. This was deliberately deferred pending a decision on a persistent (SQLite-backed) checkpointer, to be revisited together with a possible chat-history feature.

### ⚙️ `src/agents/`
The implementation of every graph node, split by responsibility instead of one large file:

- **`common.py`** — shared setup: the LLM clients (`llm_agents`, `llm_photography`), built via `src/llm/` and instantiated once at import time, the `MedicalDatabase` instance (`mdb`), and small shared utilities (e.g. `stream_response`).
- **`persistence.py`** — everything that reads or writes the patients database: `read_db_node` (looks up a patient by tax ID, looping back to ask again on an invalid one), `save_db_node` (new patient), `modify_db_node` (returning patient), plus the standalone `is_valid_fiscal_code` check.
- **`intake.py`** — data acquisition from the patient: `user_node` (the interrupt point that receives each chat message), `intake_node` (anagraphic data collection), `reviewer_node` (clinical data collection), `photography_node` (photo analysis).
- **`clinical.py`** — clinical evaluation: `supervisor_node`, `specialist_node` (shared logic for all ten specialists, each with a thin wrapper function), `primary_node` (the chief physician).
- **`prompts.py`** — all LLM prompts: `REVIEWER_PROMPT`, `SUPERVISOR_PROMPT`, `SPECIALIST_PROMPT`, `PRIMARY_PROMPT`, `PHOTO_PROMPT`, plus `ALL_SPECIALISTS` (the list of valid specialist identifiers the supervisor is allowed to pick from). The instructional text is in Italian (the app's conversation language), but every JSON key requested from the LLM matches the English field names in `src/state.py`.

`src/agents/__init__.py` re-exports all of the above, so the rest of the project (in particular `graph.py`) imports everything with a single `from src.agents import ...`.

### 🤖 `src/llm/`
Everything about choosing/building LLM clients, split like `src/agents/`:

- **`factory.py`** — Groq and Ollama both expose an OpenAI-compatible REST endpoint, so a single `get_llm(vision=False, temperature=None, model_name=None)` function returns a `ChatOpenAI` instance pointed at whichever one is active (`Settings.use_cloud_acceleration`), instead of maintaining two separate client implementations (`ChatGroq`/`ChatOllama`). `vision=True` selects the vision-capable model instead of the text one; explicit `model_name`/`temperature` override `Settings`, which in turn falls back to a per-provider default (from `models.py`) when unset.
- **`models.py`** — a small catalog of known model names, grouped by provider (`Models.Groq.TEXT_8B`, `Models.Groq.TEXT_70B`, `Models.Ollama.TEXT_LLAMA3`, etc.) — a single source of truth instead of the same string literal typed by hand in multiple places (`factory.py`'s defaults, future test scripts). Doesn't replace the `.env`'s `MODEL_NAME` (still a plain string, since environment variables can't reference Python constants), just gives a reliable place to look up/copy the exact value.

`src/settings.py` deliberately stays outside this package: it reads configuration for the whole project, not just the LLM. `src/llm/__init__.py` re-exports `get_llm`/`Models`, so callers just do `from src.llm import get_llm, Models`.

### 🗄️ `src/database.py`
The persistence layer for finalized patient records — separate from the graph's own (in-memory) conversation state. `PatientRecord` is the SQLModel table (primary key: `fiscal_code`); `MedicalDatabase` wraps the SQLite engine and exposes `save_patient`, `update_patient_conditions`, `read_patient`, `verify_patient_exists`. The database path is always resolved relative to the project root, regardless of the working directory the app is launched from.

### 🔐 `src/settings.py`
The single source of truth for configuration coming from outside the codebase (`.env`). `Settings` (a `pydantic-settings` model) declares every required/optional external value — `groq_api_key` (required only when `use_cloud_acceleration` is true), `use_cloud_acceleration` (defaults to `True`), and optional overrides consumed by `src/llm/factory.py` (`model_name`, `vision_model_name`, `temperature`) — and validates the relationship between them. `get_settings()` lazily instantiates and caches it.

### 🧰 `scripts/setup_env.py`
Interactive `.env` setup, driven entirely by introspecting `Settings.model_fields` — adding a field to `Settings` is enough for this script to start asking for it, with no separate template file to keep in sync. `ensure_env()` (called automatically at startup) only asks for genuinely missing values; `update_env()` (`--update` flag) re-asks for everything, showing a masked preview of the current value. See the module docstring in the file itself for the full behavior, including how it skips asking for `GROQ_API_KEY` when cloud acceleration is disabled.
