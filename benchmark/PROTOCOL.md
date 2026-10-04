<div align="center">

# 📊 V.I.T.A. model benchmark: protocol

</div>

<div align="justify">

This document fixes what the benchmark measures and how, before any model is run. Cases, expected answers, measures and conditions are frozen by a commit made before the first real run: nothing is adapted to the results afterwards.

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

**Model alone.** One request to the same model, with the same card and the guidelines retrieved as for a turn of the general practitioner, asking for the code and the specialists. The prompt is in `baseline.py`; its shared rules are worded as in the specialist prompt. The difference between the two conditions is the round table.

What stays the same for every model: the cases, the prompts, the guideline index and the retrieval, the temperature, the limits of the round table, the retry rules. The only thing that changes is the model, chosen from `src/llm/providers.py`.

One run per case is the minimum. Where the free quota allows it, a case is run three times; the table reports how many records each row is built on. The order of priority, the same for every model, is: full system once per case, then the model alone, then the repetitions.

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
| No answer | Records without a code: no report, or an unreadable answer of the model alone. Counted as wrong, in neither direction |
| Kappa | Quadratic weighted Cohen's kappa between expected and given codes, over the records with a code |
| Specialty | Records where the expected specialist is among those chosen. In the full system, those chosen by the supervisor: a colleague recruited later or the second opinion does not count |
| Invalid answers | Answers the system could not use: failed turns at the table, a failed routing, a report replaced by the fallback; for the model alone, an unreadable answer |
| Turns | Mean turns of the round table (full system only) |
| Seconds, Calls, Tokens | Mean time, model calls and tokens per record. Tokens only where the provider reports them |

<div align="justify">

A case in which a model call fails for a reason that is not the model's answer (daily limit, connection, rejected request) is not saved: the run stops and restarts from that case. A case in which the model gives unusable answers is saved and counted, because that is the model's behaviour.

Invented details are not counted automatically. They are counted by hand, with a fixed grid, on the five core cases: every statement of the report about the patient that is not in the card and is not marked as "to verify".

</div>

## ⚠️ Limits

<div align="justify">

Fifteen cases allow a descriptive comparison, not statistical conclusions. The expected answers come from a regional manual and the patient texts were not validated by a physician. The manual is among the guidelines the system retrieves, so the benchmark measures whether a model applies the guidelines it is given, which is what the system asks of it; the model alone receives the same guidelines. The manual is a nursing triage tool that relies on measured vital signs, which the patient card holds only as text. Models with little free quota are run once per case, or only on the core set.

</div>

## ▶️ Running it

```bash
python -m benchmark.run --model GPT_OSS_120B
python -m benchmark.run --model GEMINI_FLASH --cases core
python -m benchmark.table
```

<div align="justify">

The raw results are in `results/`, one `.jsonl` file per model with one line per case, condition and run: codes, specialists, the whole discussion, the report, date, model, temperature and the commit of the code. `results/TABLE.md` is rebuilt from them at every call of `benchmark.table`.

</div>
