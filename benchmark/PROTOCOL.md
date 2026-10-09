<div align="center">

# 📊 V.I.T.A. model benchmark: protocol

</div>

<div align="justify">

This document fixes what the benchmark measures and how, before any model is run. Cases, expected answers, measures and conditions are frozen by a commit made before the first real run: nothing is adapted to the results afterwards. The benchmark is run on the finished system: the system is not changed between one model and the next, nor in response to the results.

This is the second version of the benchmark. Its conditions were decided after the first version had been run and before any run of this one; what changed, and why, is in *Previous version*.

</div>

## 🎯 Questions

<div align="justify">

The benchmark answers three questions. The first: with the system unchanged, how much does the quality of the triage change with the language model? The second: what does the system add to a model used as it is? The third: where does that come from, the retrieved guidelines, the instructions given to the agents, or the multi-agent round table?

</div>

## 🩺 Cases

<div align="justify">

There are 15 cases, three for each of the five triage codes, in `cases.py`. Each case is built from one row of the regional triage manual *Il triage di pronto soccorso per l'adulto, Manuale operativo 2018* (Regione Friuli Venezia Giulia), which is among the guidelines of the project (`data/guidelines/generale_fvg_manuale_triage_adulto_2018.pdf`). The manual is a decision table: each of its 33 sheets lists clinical pictures, and each row gives a code from 1 to 5.

The expected code of a case is the code of its row. The text of the patient is written for the benchmark; the answer comes from the manual. Every case records the sheet, the row and the printed page.

The cases are written with these rules. The text contains the picture of the row and only neutral details, nothing that activates a more urgent row of the same or of another sheet. All the patients are adults, because the manual applies above 16 years of age. The patient card has no field for vital signs, so the signs observed by the staff are written in the description of the symptom. No case has a photo.

The manual numbers its codes from 1 (most urgent) to 5 and names only two colours. The benchmark maps the numbers to the five colours of the system in the same order: 1 ROSSO, 2 ARANCIONE, 3 AZZURRO, 4 VERDE, 5 BIANCO.

The expected specialty is the one named by the sheet when the sheet names one (for example *Oculistico*, *Urologico*). In cases 02, 03, 04, 05, 08 and 15 the sheet names none and the specialty was assigned by hand.

Five cases, one per code, are the core set (01, 04, 07, 10, 13), marked ★: their reports are the ones read by hand to count the invented details.

The table below is a summary. The full text of every patient, with what is expected, is in `CASES.md`, written from `cases.py` by `python -m benchmark.cases_doc`.

</div>

| Case | Expected code | Sheet and row | Page | Expected specialty |
|---|---|---|---|---|
| 01 ★ | ROSSO | Disturbi neurologici: alterazione di mimica / motilità / linguaggio entro le 5 ore | 36 | Neurologia |
| 02 | ROSSO | Compromissione respiratoria: severa | 15 | Pneumologia |
| 03 | ROSSO | Trauma arti: ferita penetrante inguine / coscia | 25 | Ortopedia |
| 04 ★ | ARANCIONE | Dolore toracico: dolore toracico in atto | 28 | Cardiologia |
| 05 | ARANCIONE | Emorragie non traumatiche: ematemesi / vomito caffeano | 41 | Gastroenterologia |
| 06 | ARANCIONE | Oculistico: cecità monoculare improvvisa | 49 | Oftalmologia |
| 07 ★ | AZZURRO | Urologico: ritenzione acuta d'urina | 53 | Urologia |
| 08 | AZZURRO | Trauma arti: sospetta frattura | 25 | Ortopedia |
| 09 | AZZURRO | Cefalea: crisi di cefalea nota | 35 | Neurologia |
| 10 ★ | VERDE | Chirurgico / gastrointestinale: nausea / vomito / diarrea | 54 | Gastroenterologia |
| 11 | VERDE | Otoiatrico: corpo estraneo orecchio / naso / gola | 50 | Otorinolaringoiatria |
| 12 | VERDE | Muscolo-scheletrico: lombalgia | 55 | Ortopedia |
| 13 ★ | BIANCO | Otoiatrico: otalgia; temperatura < 38 °C (p. 29) | 50 | Otorinolaringoiatria |
| 14 | BIANCO | Cute e tessuti molli: lesione cutanea non traumatica | 48 | Dermatologia |
| 15 | BIANCO | Medicina generale: tosse, rinite, sintomi aspecifici | 46 | Medicina |

## ⚙️ Conditions

<div align="justify">

Every model is run in four conditions, on the same cases. Each condition adds one thing to the one before.

**Bare model.** One request to the model with the patient card, the names of the five codes in order of urgency and the names of the ten specialists. No guideline, no definition of the codes, no rule. The names of the codes and of the specialists are given because without them an answer could not be compared with the others.

**Model with guidelines.** The same request, with the guidelines retrieved for the patient: the passages the general practitioner of the table would receive.

**Single agent.** The same request, with what a specialist of the table is given besides the guidelines: the definition of the five codes, with the instruction to choose by the definition and not out of caution, and the rule to use as facts only what the patient reported. It is one agent of the system, without the table.

**Full system.** The real graph runs from the supervisor to the summary report, starting from a patient card already filled in and confirmed. The collection of personal data and symptoms and the photo step are skipped: they are not what is being compared, and every model starts from the same card. The patients use the app's test fiscal code, so nothing is saved in the database.

The three single-call prompts are in `baseline.py` and are built from the same pieces: same opening, same patient, same list of specialists, same answer format. The definitions of the codes and the rule on the facts are those of the specialist prompt. The specialists are listed by name, with the rule on their names copied from the supervisor's prompt; the areas of competence of each specialist are given only to the supervisor, in the full system. The answers are read with the same functions the app uses: a specialist written in a form the app does not recognise is not counted.

What stays the same for every model: the cases, the prompts, the guideline index and the retrieval, the temperature, the limits of the round table, the retry rules. The only thing that changes is the model, chosen from `src/llm/providers.py`.

Every model goes through the same four steps, in the same order, and stops at the step its quota allows. Every step runs the 15 cases, in order. A step starts only when the one before is complete, so every model that reached a step has done exactly the same things.

</div>

| Step | What is run | Cases | Model calls |
|---|---|---|---|
| 1 - bare model | One request: patient, names of the codes and of the specialists | all 15 | 15 |
| 2 - model with guidelines | One request: the same, with the retrieved guidelines | all 15 | 15 |
| 3 - single agent | One request: the same, with the definition of the codes and the rules of a specialist | all 15 | 15 |
| 4 - full system | Supervisor, round table and primary | all 15 | about 105 |

<div align="justify">

The first three steps cost one call per case, so even a model with very little quota reaches them. The first and the last step side by side say what the system adds to the model. The steps in between say where it comes from: from the first to the second the guidelines, from the second to the third the definitions and the rules, from the third to the fourth the round table.

Each step has its own table, which lists only the models that completed it, and one more table puts the steps side by side, model by model. Repetitions of a case, to see whether a model answers the same every time, are not part of the steps: they can be added afterwards for the models that still have quota, and the table reports how many records each row is built on.

</div>

## 🤖 Models

<div align="justify">

The benchmark compares text models. The models attached so far are listed below; a model is added to the table when it is attached, before it is run. Vision models are not part of the benchmark: no case has a photo, so they are never called.

</div>

| Text models | Developed by | Runs on |
|---|---|---|
| gpt-oss-120b | OpenAI | Groq |
| gpt-oss-20b | OpenAI | Groq |
| qwen3.8-27b | Alibaba | Groq |
| gemini-3.8-flash | Google | Google |
| llama3.2 (3B, 4-bit) | Meta | Ollama (local) |
| llama3.1 (8B, 4-bit) | Meta | Ollama (local) |
| qwen3 (8B, 4-bit) | Alibaba | Ollama (local) |
| qwen3 (14B, 4-bit) | Alibaba | Ollama (local) |
| ministral-3 (8B, 4-bit) | Mistral AI | Ollama (local) |
| ministral-3 (14B, 4-bit) | Mistral AI | Ollama (local) |
| llama-3.2-3b-instruct | Meta | Hugging Face (Featherless AI) |
| llama-3.2-3b-instruct | Meta | Cloudflare |
| llama-3.2-1b-instruct | Meta | Cloudflare |

<div align="justify">

The models on Ollama run on a GPU of Google Colab, with a context of 16,384 tokens. The app asks every model for answers of at most 4,096 tokens, but Ollama ignores the field that carries this limit, and an answer that falls into a repetition would never end: for these models the limit is set inside Ollama, at 8,192 tokens. In the first version, a run of llama3.2 with the limit at 4,096 gave the same codes and the same specialists in all the 15 cases.

</div>

<div align="justify">

This version is run on nine of these models: gpt-oss-120b, gpt-oss-20b and qwen3.8-27b on Groq; llama3.2, llama3.1, qwen3 8B, qwen3 14B, ministral-3 8B and ministral-3 14B on Ollama. They are the eight models of the first version and ministral-3 14B, which was in its list and had not been run yet. A model on Groq may be run with the keys of two accounts, because of the daily limit of the provider.

</div>

## 📏 Measures

<div align="justify">

All the measures are computed by `metrics.py` from the raw results, and the computation is checked by `tests/unit/test_benchmark_metrics.py`.

</div>

| Measure | Definition |
|---|---|
| Exact | Records whose code equals the expected one |
| Within one | Records whose code is at most one level from the expected one |
| Under | Records with a code less urgent than expected (under-triage, the dangerous error) |
| Over | Records with a code more urgent than expected (over-triage) |
| No answer | Records without a code: no report, or an unreadable answer to a single call. Counted as wrong, in neither direction |
| Kappa | Quadratic weighted Cohen's kappa between expected and given codes, over the records with a code |
| Stable | Among the cases run more than once, those whose runs all gave the same code. A dash when no case was repeated |
| Specialty | Records where the expected specialist is among those chosen. In the full system, those chosen by the supervisor: a colleague recruited later or the second opinion does not count |
| Invalid answers | Answers the system could not use: failed turns at the table, a failed routing, a report replaced by the fallback; in a single call, an unreadable answer |
| Turns | Mean turns of the round table (full system only) |
| Sheet seen | Records in which the manual page the case was built from was among the guideline passages delivered. It explains an error, it is not a score of the model |
| Seconds, Wait | Mean time per record without the waits a provider imposes before a retry, and the mean of those waits. The waits say how tight a plan is, not how fast a model is |
| Calls, Tokens | Mean model calls and tokens per record. Tokens only where the provider reports them |

<div align="justify">

A case in which a model call fails for a reason that is not the model's answer (daily limit, connection, rejected request) is not saved: the run stops and restarts from that case. A case in which the model gives unusable answers is saved and counted, because that is the model's behaviour.

Invented details are not counted automatically. They are counted by hand, with a fixed grid, on the five core cases: every statement of the report about the patient that is not in the card and is not marked as "to verify". The sheet for the count, with the patient and the report of each core case, is written by `python -m benchmark.review --model <NAME>`.

</div>

## 🧭 Before the freeze

<div align="justify">

A pilot on three cases (04, 10, 13) with one model was run to check the script and to measure what a case costs: about 6-9 model calls and 45,000-80,000 tokens for the full system, one call and about 3,500 tokens for a single call. Its results are not part of the benchmark.

The pilot also showed that no prompt said what the five codes mean: the model used a scale of its own and called ARANCIONE what it described as a case to be seen within a few hours. The national definition of the codes (name, definition, maximum waiting time) was therefore added to the specialist prompt, to the primary prompt and to the prompt of the single agent, from one shared text. This was done before the freeze; the cases and the expected answers were not changed.

</div>

## 🔁 Previous version

<div align="justify">

A first version of this benchmark compared two conditions: the full system and a single agent that was also given the supervisor's list of specialists with their areas of competence. It was run on eight models. Its raw results and its tables are in the commit `b23ef6e` of the repository and are not part of the results of this version.

This version changes three things, decided before running it. The bare model and the model with guidelines were added, to measure what the system adds to a model used as it is and where it comes from. The single agent no longer receives the areas of competence of the specialists, so that it is given what one specialist of the table is given; the specialists are listed by name in quotes, as in the supervisor's list, because a list written as `ent (Otorinolaringoiatria)` had been copied whole by one model, a form the app does not recognise. The full system runs the 15 cases in one step, instead of the five core cases first. Every model is run again from the start, in all the conditions.

</div>

## ⚠️ Limits

<div align="justify">

Fifteen cases allow a descriptive comparison, not statistical conclusions. The expected answers come from a regional manual; the patient texts were written for the benchmark. The manual is in the guideline archive of the system, but the retrieval returns only a few passages per turn and does not guarantee the row a case was built from: a model may never see it. The benchmark therefore measures the code the system reaches with what it retrieves, not the ability to read a row it is shown. The single calls get their guidelines through the same retrieval, as a general practitioner would, while each specialist of the table retrieves for its own specialty: from the single agent to the full system the guidelines change together with the table. The conditions of this version were chosen knowing the results of the first one, on the same 15 cases. The manual is a nursing triage tool that relies on measured vital signs, which the patient card holds only as text. Models with little free quota stop at an earlier step.

</div>

## ▶️ Running it

```bash
python -m benchmark.run --model GPT_OSS_120B --check    # one tiny request: key, model name, token counts
python -m benchmark.run --model GPT_OSS_120B --step 1   # the bare model, 15 cases
python -m benchmark.run --model GPT_OSS_120B --step 2   # the model with guidelines, 15 cases
python -m benchmark.run --model GPT_OSS_120B --step 3   # the single agent, 15 cases
python -m benchmark.run --model GPT_OSS_120B --step 4   # the full system, 15 cases
python -m benchmark.table                               # the tables, from the saved results
```

<div align="justify">

The raw results are in `results/raw/`, one `.jsonl` file per model with one line per case, condition and run: codes, specialists, the whole discussion, the report, date, model, temperature and the commit of the code. A step interrupted by a daily limit is resumed by running the same command again. `benchmark.table` rebuilds three files from the raw results at every call: `results/TABLE.md`, with the step each model reached, one table per step, the steps side by side model by model, and one table per condition with the code each model gave to each case; `results/table.csv`, the step tables as plain numbers; and `results/cases.csv`, one row per case run. The CSV files use commas and decimal points.

</div>
