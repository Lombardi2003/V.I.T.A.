<div align=center>

# 🏗️ V.I.T.A. — Architecture
</div>
<div align=justify>
Technical reference for how V.I.T.A. is built internally: the runtime flow, and what each file is responsible for. For installation/usage, see [README.md](README.md).

📌 **Status note**: this document describes the system as it exists today, including known limitations that are still being worked on (flagged inline where relevant). It will be kept up to date as the codebase evolves.

---

## 🔄 How it works

**Startup**: `app.py` first makes sure `.env` is complete (`scripts/setup_env.py`), then builds the LangGraph state machine (`src/graph.py`), which wires together all the reasoning nodes defined in the `src/agents/` package. The LLM clients (the models chosen at the top of `src/llm/factory.py`, printed in the terminal at startup) and the SQLite connection are created once at startup, not on every message.

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

- **`common.py`** — shared setup: the two LLM clients (`llm` for every text node, `llm_vision` for the photo), requested from `src/llm/` with `get_llm(...)` and instantiated once at import time, the `MedicalDatabase` instance (`mdb`), and `stream_response` (a thin wrapper around `src/llm/calls.py`). Agents never know which provider/model they run on.
- **`persistence.py`** — everything that reads or writes the patients database: `read_db_node` (looks up a patient by tax ID, looping back to ask again on an invalid one), `save_db_node` (new patient), `modify_db_node` (returning patient), plus the standalone `is_valid_fiscal_code` check.
- **`intake.py`** — data acquisition from the patient: `user_node` (the interrupt point that receives each chat message), `intake_node` (anagraphic data collection), `reviewer_node` (clinical data collection), `photography_node` (photo analysis).
- **`clinical.py`** — clinical evaluation: `supervisor_node`, `specialist_node` (shared logic for all ten specialists, each with a thin wrapper function), `primary_node` (the chief physician).
- **`prompts.py`** — all LLM prompts: `REVIEWER_PROMPT`, `SUPERVISOR_PROMPT`, `SPECIALIST_PROMPT`, `PRIMARY_PROMPT`, `PHOTO_PROMPT`, plus `ALL_SPECIALISTS` (the list of valid specialist identifiers the supervisor is allowed to pick from). The instructional text is in Italian (the app's conversation language), but every JSON key requested from the LLM matches the English field names in `src/state.py`.

`src/agents/__init__.py` re-exports all of the above, so the rest of the project (in particular `graph.py`) imports everything with a single `from src.agents import ...`.

### 🤖 `src/llm/`
"Here's your LLM": the **only** part of the project that knows which provider/model is in use. The clinical logic in `src/agents/` asks for its client and stays the same whatever model runs underneath — the system keeps working with any model (answers may change in quality, but no node breaks: every node has a fallback for an unusable answer). Three files, one job each:

- **`models.py`** — the list of available models, as plain names grouped by provider (`Models.Groq.TEXT_120B`, `Models.Ollama.TEXT_LLAMA3`, …). The class a name belongs to tells its provider, so it doesn't need to be written anywhere else. A new model only needs its name under its provider. The history of the models tried is kept here as comments.
- **`factory.py`** — *which* models the app uses and builds their clients. At the top, the **active models**: `TEXT_MODEL` (every text node — intake, reviewer, supervisor, specialists, chief physician) and `VISION_MODEL` (photo). This is the only place where a model is chosen; being in git, every commit records which models the system ran with. Every client is built the same way for every provider — `ChatOpenAI(api_key, base_url, model, temperature)`, since Groq, Ollama and Gemini all expose an OpenAI-compatible endpoint — from the provider's address/key (`_PROVIDERS`). `get_llm()` / `get_llm(vision=True)` return the ready client; `describe_llm(llm)` tells which model a client *actually* uses — printed at startup ("🤖 Modelli attivi: …") and shown in the app's settings panel, so tests and benchmarks always know what ran. `TOKENS_PER_MINUTE` holds each provider's per-minute token limit (Groq's free tier: 8000).
- **`calls.py`** — *how* a client is used, the same for every node and model: `call_with_retry` (retries after temporary API errors such as Groq's 429, waiting the time suggested by the API, capped), `stream_text` (full streamed answer, with `max_tokens` computed per call so that prompt + reserved answer stay within the provider's per-minute limit — otherwise Groq rejects the request with 413) and `extract_json` (the JSON object inside an answer, tolerating `<think>...</think>` reasoning blocks, code fences and surrounding text).

`src/settings.py` deliberately stays outside this package: `.env` only holds the API keys (secret, outside git) and the temperature — which models run is decided in `factory.py`, not in `.env`. `scripts/setup_env.py` asks only for the keys of the providers the active models use. `src/llm/__init__.py` re-exports the public functions (`from src.llm import get_llm, stream_text, extract_json, ...`).

### 🔍 `src/rag/` — Retrieval-Augmented Generation

Gives each specialist access to real clinical guidelines instead of relying only on the LLM's parametric knowledge. The corpus (`data/guidelines/`) is 21 Italian, emergency-department-oriented documents from official sources (Friuli Venezia Giulia/ARCS PDTAs and adult triage manual, SIMEU, regional PDTAs, SIOT, SOI, SIDeMaST…), all text PDFs (no scans). Each file's name starts with its specialty (`cardio_`, `neuro_`, `dermatologia_`, `ortopedia_`, `gastro_`, `pneumo_`, `ent_`, `oftalmologia_`, `urologia_`, or `generale_` for cross-cutting triage/sepsis documents): **the prefix decides which specialist receives the document**. Two files:

- **`build_index.py`** — one-off script (`python -m src.rag.build_index`, not part of the app's runtime flow) that reads every PDF, cleans the text, splits it into chunks, embeds each chunk locally and persists the result as a Chroma vector index in `data/chroma_db/` (tracked by git, so a fresh clone works without rebuilding). Run it again whenever `data/guidelines/` changes; it prints, per file, how many chunks were kept and how many were discarded and why.
  - *Text cleaning* (per document): removes headers/footers repeated on many pages, page-number-only lines, re-joins words hyphenated across lines, normalizes whitespace.
  - *Chunk filtering*: discards chunks that aren't clinical content — tables of contents, too-short fragments, bibliography, literature search strategies, glossaries of abbreviations, author/revision lists, statistical indicator sheets, conflict-of-interest statements, garbled text. Every rule was checked by hand against all the chunks it discards (a generic "list" rule was tried and dropped because it also discarded real clinical tables).
  - *Excluded pages* (`EXCLUDED_PAGES`): a short, commented list of pages excluded by hand — lists of titles/pathology names that looked "similar" to almost every query and kept showing up in results.
  - *Metadata* on each chunk: `source_file`, `specialty` (from the file prefix) and `page_number` (1-based, for citations).
- **`retriever.py`** — `retrieve(queries, role, k=3)`, called from `specialist_node` (`src/agents/clinical.py`) on every specialist turn. Returns `[]` (never raises) if the index hasn't been built yet, so RAG degrades gracefully rather than crashing the graph. Each result carries its text, source file, page and score; the prompt shows it as `- [document, p. N] text`, so the specialist can cite a real, checkable source in `fonti_consultate`.

**Design decisions, and why:**
- **Mechanical retrieval, not agentic** (i.e. not an LLM-decided "should I call the retrieval tool now" pattern). Retrieval always runs, on every specialist turn — the decision left to the model is only whether the *result* is relevant enough to use (and cite). Testing the round table showed the model reliably under-fires optional, judgment-gated actions, so an optional retrieval tool would likely be under-used.
- **Specialty filtering**: each turn retrieves `k-1` chunks from the speaking specialist's own documents plus 1 from the `generale` ones (usually the matching triage sheet, useful for the urgency code). Without it, the general documents crowded out the specialty ones.
- **One query per symptom**: `build_queries` makes one query per symptom (`"<specialty> - <symptom>"`, plus one for a pending consult question) and keeps the best chunks overall. A single query with all the symptoms let the symptoms outside the specialist's field pollute the search (e.g. the gastroenterologist got boilerplate pages instead of the abdominal-pain document when the chart also had a rash). No rule decides which symptom belongs to which specialist: the most similar passages win, and the specialist still sees and discusses the whole chart.
- **Embedding model**: `intfloat/multilingual-e5-small`, run locally via `sentence-transformers`/`langchain-huggingface` (no external API, no extra quota). Chosen for Italian-language support. Requires a `"query: "` prefix on queries and a `"passage: "` prefix on indexed chunks. `load_embeddings()` loads it from the local Hugging Face cache when present (no network calls at startup), downloading it only the first time.
- **Measured, not guessed**: `tests/test_rag_retrieval.py` measures retrieval on a fixed set of clinical cases (30 single-specialty cases + 9 mixed-symptom cases), on a temporary copy of the index. Every change to corpus/indexing/retrieval was checked against it — the one-query-with-all-symptoms baseline scored 11/27 on mixed cases, the current design 24/27.

> ℹ️ **Note**: `build_index.py` builds the index in a temporary directory and then replaces `data/chroma_db/`, so a failed build never leaves the app without an index. It still contains retry loops written when the project lived in a OneDrive-synced folder. Opening the index (the app and the round-table test do) makes Chroma rewrite `chroma.sqlite3`, so git may show it as modified even without a rebuild — the content is unchanged (`git restore` it if needed).

### 🗄️ `src/database.py`
The persistence layer for finalized patient records — separate from the graph's own (in-memory) conversation state. `PatientRecord` is the SQLModel table (primary key: `fiscal_code`); `MedicalDatabase` wraps the SQLite engine and exposes `save_patient`, `update_patient_conditions`, `read_patient`, `verify_patient_exists`. The database path is always resolved relative to the project root, regardless of the working directory the app is launched from.

### 🔐 `src/settings.py`
The single source of truth for configuration coming from outside the codebase (`.env`). `Settings` (a `pydantic-settings` model) declares every required/optional external value — `groq_api_key` (required only when `use_cloud_acceleration` is true), `use_cloud_acceleration` (defaults to `True`), and optional overrides consumed by `src/llm/factory.py` (`model_name`, `vision_model_name`, `temperature`) — and validates the relationship between them. `get_settings()` lazily instantiates and caches it.

### 🧰 `scripts/setup_env.py`
Interactive `.env` setup, driven entirely by introspecting `Settings.model_fields` — adding a field to `Settings` is enough for this script to start asking for it, with no separate template file to keep in sync. `ensure_env()` (called automatically at startup) only asks for genuinely missing values; `update_env()` (`--update` flag) re-asks for everything, showing a masked preview of the current value. See the module docstring in the file itself for the full behavior, including how it skips asking for `GROQ_API_KEY` when cloud acceleration is disabled.
