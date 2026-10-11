<div align="center">

# 📈 V.I.T.A. model benchmark: results

</div>

<div align="justify">

What the benchmark showed, read from the tables. This file is written by hand; every number comes from `results/table.csv`, `results/cases.csv` and the raw files in `results/raw/`, which `python -m benchmark.table` rebuilds. How the benchmark is made is in [PROTOCOL.md](PROTOCOL.md), the patients are in [CASES.md](CASES.md), the complete tables are in [results/TABLE.md](results/TABLE.md).

Nine models were run, each on the same 15 cases and in three conditions: the **bare model** (the patient only), the **model alone** (one agent of the system: guidelines, definitions and rules, without the round table) and the **full system**. That is 135 cases per condition, one run each, between 6 and 10 October 2026.

</div>

## 🧾 In short

<div align="justify">

- **Against the bare model, the full system assigns the triage code clearly better.** Its agreement with the manual is higher in seven models out of nine, it gives more exact codes (60 against 48) and about half the serious errors (16 against 29).
- **Against the model alone, the full system is equivalent.** Three models do better in the system, three the same, three worse. The system makes fewer serious errors (16 against 25); the model alone has a slightly higher mean agreement (0.71 against 0.69).
- **Most of the gain over the bare model comes from the guidelines, the definitions of the codes and the rules**, which the model alone also has. The round table adds regularity: no case without an answer, and the fewest serious errors.
- **The system depends on the model.** With models of 20 billion parameters or more its agreement with the manual is 0.87-0.88; below, it ranges from 0.19 to 0.81.
- **Its weak point is under-triage on emergencies.** In 7 cases out of 27 a ROSSO case is given ARANCIONE; the bare model recognises all 27.
- **The preliminary diagnosis is not improved by the system.** With capable models the three conditions are equivalent; with the two smallest models the bare model does better.

</div>

## 📊 Agreement with the manual, model by model

<div align="justify">

Quadratic weighted kappa between the expected code and the given one (1 is perfect agreement, 0 is chance), and the number of exact codes out of 15. The models are ordered by size.

</div>

| Model | Size | Bare model | Model alone | Full system |
|---|---|---|---|---|
| gpt-oss-120b | 120B | 0.76 (5) | 0.89 (8) | 0.87 (6) |
| qwen3.8-27b | 27B | 0.83 (8) | 0.89 (11) | 0.88 (10) |
| gpt-oss-20b | 20B | 0.84 (9) | 0.76 (5) | 0.88 (8) |
| ministral-3 14B | 14B | 0.88 (7) | 0.90 (9) | 0.74 (7) |
| qwen3 14B | 14B | 0.73 (4) | 0.79 (5) | 0.69 (5) |
| ministral-3 8B | 8B | 0.71 (6) | 0.77 (6) | 0.81 (8) |
| qwen3 8B | 8B | 0.45 (3) | 0.83 (7) | 0.73 (7) |
| llama3.1 8B | 8B | 0.22 (3) | 0.35 (3) | 0.44 (4) |
| llama3.2 | 3B | 0.07 (3) | 0.19 (4) | 0.19 (5) |
| **Mean of the nine kappas** | | **0.61** | **0.71** | **0.69** |

<div align="justify">

The full system is above the bare model in seven models; the exceptions are the two models of 14 billion parameters. Against the model alone it is above in three (gpt-oss-20b, ministral-3 8B, llama3.1), within 0.02 in three (gpt-oss-120b, qwen3.8-27b, llama3.2) and below in three (ministral-3 14B, qwen3 14B, qwen3 8B).

The full system is the condition that changes least from one capable model to another: 0.87, 0.88 and 0.88 with the three models on Groq, where the bare model ranges from 0.76 to 0.84 and the model alone from 0.76 to 0.89. This was noticed in the results, not predicted before them.

</div>

## 🔢 The 135 cases together

| Measure | Bare model | Model alone | Full system |
|---|---|---|---|
| Exact code | 48 | 58 | 60 |
| Within one level | 106 | 110 | 119 |
| Serious errors (two or more levels, or no answer) | 29 | 25 | 16 |
| Over-triage | 85 | 69 | 65 |
| Under-triage | 2 | 3 | 10 |
| No answer | 0 | 5 | 0 |
| Expected specialty among those chosen | 120 | 119 | 122 |
| Invalid answers | 0 | 5 | 60 |

<div align="justify">

The bare model errs on the side of urgency: it gives a code more urgent than expected in 85 cases out of 135, and the three smallest models answer ROSSO or ARANCIONE to almost every patient. With the definitions of the codes in front of them, the model alone and the full system separate the less serious cases better.

</div>

## 🚨 Emergencies and the other cases

<div align="justify">

This split was made after the results were seen, to check one reading of them: a model that gives the most urgent code to most patients gets the three ROSSO cases right without telling the cases apart. It is reported whole, with both halves.

</div>

| | Bare model | Model alone | Full system |
|---|---|---|---|
| **The 27 ROSSO cases** | | | |
| Given ROSSO | 27 | 24 | 20 |
| Given ARANCIONE | 0 | 0 | 7 |
| No answer | 0 | 3 | 0 |
| **The other 108 cases** | | | |
| Exact code | 21 | 34 | 40 |
| Within one level | 79 | 86 | 92 |
| Serious errors | 29 | 22 | 16 |
| Under-triage | 2 | 3 | 3 |

<div align="justify">

Of the 48 exact codes of the bare model, 27 are the ROSSO cases. On the other cases the full system gives the exact code almost twice as often as the bare model (40 against 21) and makes about half the serious errors (16 against 29). The price is on the emergencies: the full system gives ARANCIONE to 7 ROSSO cases out of 27, with six different models, and never goes lower than ARANCIONE. Seven of its ten under-triages are these.

</div>

## 🪑 How the round table decides

<div align="justify">

- **The final code is the first proposal.** In 133 system cases out of 135 the code of the report is the one the first specialist proposed, and in 133 cases a single code is voiced during the whole discussion. The specialists revise the hypothesis 41 times in all, but the code does not change.
- **The primary keeps the table's code.** The code of the report equals the table's in 134 cases out of 135.
- **The right page of the manual is often there and is not used.** The page a case was built from reached the table in 74 system cases out of 135; the code was exact in 30 of those 74 and in 30 of the other 61.
- **The system absorbs unusable answers.** Sixty answers could not be used (failed turns, or a report of the primary replaced by the fallback), 48 of them with the two ministral-3 models, whose JSON the app's reader discards. A report with a code was delivered in all the 135 cases; in 34 of them it is the fallback built from the table's hypothesis.

Together these explain the two sides of the result. The table does not add accuracy to the code, because nobody questions the first proposal; when the first specialist is wrong, or is not the most pertinent one, the error stays. In the same way an emergency proposed as ARANCIONE remains ARANCIONE: the definitions of the codes ask to choose by the definition and not out of caution, and the primary is told to confirm the table's code as a rule.

</div>

## 🧪 The two predictions written before running

<div align="justify">

**Between 8 and 20 billion parameters the full system gives a better code than the model alone** (written before the three Qwen models were run). Not confirmed: with qwen3 8B and qwen3 14B the system is below the model alone (0.73 against 0.83, 0.69 against 0.79), with qwen3.8-27b it is equal (0.88 against 0.89).

**A model whose mean distance alone is 0.8 levels or more gets closer to the expected code in the full system; a model below 0.8 does not** (written before the two ministral-3 models were run). Confirmed by both: ministral-3 8B goes from 1.27 levels alone to 0.53 in the system; ministral-3 14B, at 0.60 alone, does not improve (0.67).

</div>

## ⏱️ What a case costs

| | Bare model | Model alone | Full system |
|---|---|---|---|
| Model calls per case | 1 | 1 | 6 to 13, 7.7 on average |
| Tokens per case, models on Groq | about 1,300 | about 4,100 | about 59,000 |
| Seconds per case, models on Groq | 1 to 3 | about 1 | 15 to 20 |
| Seconds per case, models on Ollama (Colab, T4) | 2 to 48 | 4 to 51 | 150 to 460 |

## 🩺 The preliminary diagnosis

<div align="justify">

The benchmark does not score the diagnosis. The 405 diagnoses were read one by one against the row of the manual each case was built from, and counted as right when they named the clinical picture of the row. It is an informal reading made during the analysis, with the help of an AI assistant and without a clinician: the counts are indicative.

With the seven models from 8 billion parameters up (excluding llama3.1) the three conditions are equivalent: 103, 99 and 98 right out of 105 for the bare model, the model alone and the full system. With llama3.1 and llama3.2 the bare model is right more often (20 out of 30) than the model alone (9) and the full system (8): given the guidelines and the discussion, these two models copy titles of retrieved passages or repeat a hypothesis from one case to another. One error of the system recurs across models: in case 06, a sudden painless loss of sight, four models propose an acute glaucoma at the table.

</div>

## ⚠️ What these results do not say

<div align="justify">

Fifteen cases per model allow a description, not statistical conclusions: one case is almost seven points of a percentage. Each case was run once; with the models on Groq a few codes change from one run to another at temperature 0, so differences of one or two cases between conditions are within that variation. The mean of the nine kappas gives every model the same weight, whatever its size. The expected codes come from one regional manual and the patient texts were written for the benchmark. The split between emergencies and other cases and the remark on stability were made after seeing the results. Nothing here is a clinical validation.

</div>
