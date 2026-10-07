<div align="center">

# 📊 V.I.T.A. model benchmark: protocol

</div>

<div align="justify">

This document fixes what the benchmark measures and how, before any model is run. Cases, expected answers, measures and conditions are frozen by a commit made before the first real run: nothing is adapted to the results afterwards. The benchmark is run on the finished system: the system is not changed between one model and the next, nor in response to the results.

</div>

## 🎯 Questions

<div align="justify">

The benchmark answers two questions. The first: with the system unchanged, how much does the quality of the triage change with the language model? The second: does the multi-agent round table do better than the same model asked alone?

</div>

## 🩺 Cases

<div align="justify">

There are 15 cases, three for each of the five triage codes, in `cases.py`. Each case is built from one row of the regional triage manual *Il triage di pronto soccorso per l'adulto, Manuale operativo 2018* (Regione Friuli Venezia Giulia), which is among the guidelines of the project (`data/guidelines/generale_fvg_manuale_triage_adulto_2018.pdf`). The manual is a decision table: each of its 33 sheets lists clinical pictures, and each row gives a code from 1 to 5.

The expected code of a case is the code of its row. The text of the patient is written for the benchmark; the answer comes from the manual. Every case records the sheet, the row and the printed page.

The cases are written with these rules. The text contains the picture of the row and only neutral details, nothing that activates a more urgent row of the same or of another sheet. All the patients are adults, because the manual applies above 16 years of age. The patient card has no field for vital signs, so the signs observed by the staff are written in the description of the symptom. No case has a photo.

The manual numbers its codes from 1 (most urgent) to 5 and names only two colours. The benchmark maps the numbers to the five colours of the system in the same order: 1 ROSSO, 2 ARANCIONE, 3 AZZURRO, 4 VERDE, 5 BIANCO.

The expected specialty is the one named by the sheet when the sheet names one (for example *Oculistico*, *Urologico*). In cases 02, 03, 04, 05, 08 and 15 the sheet names none and the specialty was assigned by hand.

Five cases, one per code, are the core set (01, 04, 07, 10, 13). A model with very little free quota runs only these, and every model is compared on them.

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

Every model is run in two conditions, on the same cases.

**Full system.** The real graph runs from the supervisor to the summary report, starting from a patient card already filled in and confirmed. The collection of personal data and symptoms and the photo step are skipped: they are not what is being compared, and every model starts from the same card. The patients use the app's test fiscal code, so nothing is saved in the database.

**Model alone.** One request to the same model, with the same card and the guidelines retrieved as for a turn of the general practitioner, asking for the code and the specialists. The prompt is in `baseline.py`. Its shared rules are worded as in the specialist prompt, and the specialists are asked with the list and the rule on their names copied from the supervisor's prompt, so for the same task the two conditions receive the same instruction. The answer is read with the same function the app uses: a specialist written in a form the app does not recognise is not counted. The difference between the two conditions is the round table.

What stays the same for every model: the cases, the prompts, the guideline index and the retrieval, the temperature, the limits of the round table, the retry rules. The only thing that changes is the model, chosen from `src/llm/providers.py`.

Every model goes through the same three steps, in the same order, and stops at the step its quota allows. A step starts only when the one before is complete, so every model that reached a step has done exactly the same things.

</div>

| Step | What is run | Cases | Model calls | Tokens (measured on one model) |
|---|---|---|---|---|
| 1 - minimum | The model alone | all 15 | 15 | about 50,000 |
| 2 - intermediate | The full system | the 5 core cases | about 35 | about 285,000 |
| 3 - complete | The full system | the other 10 | about 70 | about 570,000 |

<div align="justify">

The first step costs about a seventeenth of the others and gives a result on every case, so even a model with very little quota enters the comparison. The second adds the round table on the five most representative cases, the same patients the model has already answered alone: the two answers side by side say whether the table helps. The third adds the other ten cases to the full system, which makes its numbers more solid without changing what is measured.

Each step has its own table, which lists only the models that completed it. Repetitions of a case, to see whether a model answers the same every time, are not part of the steps: they can be added afterwards for the models that still have quota, and the table reports how many records each row is built on.

</div>

## 🤖 Models

<div align="justify">

The benchmark compares text models. The models attached so far are listed below; a model is added to the table when it is attached, before it is run. Vision models are not part of the benchmark: no case has a photo, so they are never called.

</div>

| Text models | Developed by | Runs on |
|---|---|---|
| gpt-oss-120b | OpenAI | Groq |
| gpt-oss-20b | OpenAI | Groq |
| gemini-3.8-flash | Google | Google |
| llama3.2 (3B, 4-bit) | Meta | Ollama (local) |
| llama-3.2-3b-instruct | Meta | Hugging Face (Featherless AI) |
| llama-3.2-3b-instruct | Meta | Cloudflare |
| llama-3.2-1b-instruct | Meta | Cloudflare |
| granite-4.0-h-micro | IBM | Cloudflare |

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
| No answer | Records without a code: no report, or an unreadable answer of the model alone. Counted as wrong, in neither direction |
| Kappa | Quadratic weighted Cohen's kappa between expected and given codes, over the records with a code |
| Stable | Among the cases run more than once, those whose runs all gave the same code. A dash when no case was repeated |
| Specialty | Records where the expected specialist is among those chosen. In the full system, those chosen by the supervisor: a colleague recruited later or the second opinion does not count |
| Invalid answers | Answers the system could not use: failed turns at the table, a failed routing, a report replaced by the fallback; for the model alone, an unreadable answer |
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

A pilot on three cases (04, 10, 13) with one model was run to check the script and to measure what a case costs: about 6-9 model calls and 45,000-80,000 tokens for the full system, one call and about 3,500 tokens for the model alone. Its results are not part of the benchmark.

The pilot also showed that no prompt said what the five codes mean: the model used a scale of its own and called ARANCIONE what it described as a case to be seen within a few hours. The national definition of the codes (name, definition, maximum waiting time) was therefore added to the specialist prompt, to the primary prompt and to the prompt of the model alone, from one shared text. This was done before the freeze; the cases and the expected answers were not changed.

The first step was started once and restarted. With the first two models the model-alone prompt listed the specialists in its own wording, as `ent (Otorinolaringoiatria)`, without the areas of competence the supervisor is given; one model copied that form in two cases, which the app does not recognise. The reading was not changed, because it is the app's and is the same for every model. The question was: it now uses the supervisor's list and rule, so the two conditions are asked in the same way, and the step was run again from the start for both models. The two runs made with the first wording are not part of the results.

</div>

## ⚠️ Limits

<div align="justify">

Fifteen cases allow a descriptive comparison, not statistical conclusions. The expected answers come from a regional manual; the patient texts were written for the benchmark. The manual is in the guideline archive of the system, but the retrieval returns only a few passages per turn and does not guarantee the row a case was built from: a model may never see it. The benchmark therefore measures the code the system reaches with what it retrieves, not the ability to read a row it is shown; the model alone gets its guidelines through the same retrieval. The manual is a nursing triage tool that relies on measured vital signs, which the patient card holds only as text. Models with little free quota stop at the first or at the second step.

</div>

## ▶️ Running it

```bash
python -m benchmark.run --model GPT_OSS_120B --check    # one tiny request: key, model name, token counts
python -m benchmark.run --model GPT_OSS_120B --step 1   # minimum: the model alone, 15 cases
python -m benchmark.run --model GPT_OSS_120B --step 2   # intermediate: the full system, 5 core cases
python -m benchmark.run --model GPT_OSS_120B --step 3   # complete: the full system, the other 10 cases
python -m benchmark.table                               # the tables, from the saved results
```

<div align="justify">

The raw results are in `results/raw/`, one `.jsonl` file per model with one line per case, condition and run: codes, specialists, the whole discussion, the report, date, model, temperature and the commit of the code. A step interrupted by a daily limit is resumed by running the same command again. `benchmark.table` rebuilds three files from the raw results at every call: `results/TABLE.md`, with the step each model reached, one table per step and one table per condition with the code each model gave to each case; `results/table.csv`, the step tables as plain numbers; and `results/cases.csv`, one row per case run. The CSV files use commas and decimal points.

</div>
