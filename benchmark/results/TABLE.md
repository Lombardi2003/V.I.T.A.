# Benchmark results

Built by `python -m benchmark.table` from the raw results in `raw/`. The steps and the measures are defined in `benchmark/PROTOCOL.md`, the cases in `benchmark/CASES.md`. The same numbers are in `table.csv` and, case by case, in `cases.csv`.

## Progress

| Model | Step reached | Bare model | Model with guidelines | Single agent | Full system |
|---|---|---|---|---|---|
| GPT_OSS_20B | 4 - full system | 15/15 | 15/15 | 15/15 | 15/15 |

## Step 1 - bare model: the patient, the names of the codes and of the specialists

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_20B | Bare model | 15 | 15 | 9/15 | 14/15 | 0 | 6 | 0 | 0.84 | - | 14/15 | 0/15 | 0 | - | 1 | 1 | 1.0 | 1468 |

## Step 2 - model with guidelines: the same, with the retrieved guidelines

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_20B | Model with guidelines | 15 | 15 | 5/15 | 15/15 | 1 | 9 | 0 | 0.84 | - | 15/15 | 5/15 | 0 | - | 2 | 8 | 1.0 | 3150 |

## Step 3 - single agent: the same, with the definition of the codes and the rules of a specialist

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_20B | Single agent | 15 | 15 | 7/15 | 12/15 | 1 | 7 | 0 | 0.73 | - | 15/15 | 5/15 | 0 | - | 2 | 8 | 1.0 | 3746 |

## Step 4 - full system: supervisor, round table and primary

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_20B | Full system | 15 | 15 | 5/15 | 15/15 | 3 | 7 | 0 | 0.85 | - | 13/15 | 10/15 | 0 | 4.3 | 17 | 158 | 6.3 | 49561 |

## The conditions side by side, model by model

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_20B | Bare model | 15 | 15 | 9/15 | 14/15 | 0 | 6 | 0 | 0.84 | - | 14/15 | 0/15 | 0 | - | 1 | 1 | 1.0 | 1468 |
| GPT_OSS_20B | Model with guidelines | 15 | 15 | 5/15 | 15/15 | 1 | 9 | 0 | 0.84 | - | 15/15 | 5/15 | 0 | - | 2 | 8 | 1.0 | 3150 |
| GPT_OSS_20B | Single agent | 15 | 15 | 7/15 | 12/15 | 1 | 7 | 0 | 0.73 | - | 15/15 | 5/15 | 0 | - | 2 | 8 | 1.0 | 3746 |
| GPT_OSS_20B | Full system | 15 | 15 | 5/15 | 15/15 | 3 | 7 | 0 | 0.85 | - | 13/15 | 10/15 | 0 | 4.3 | 17 | 158 | 6.3 | 49561 |

## Case by case: bare model

`▲` more urgent than expected (over-triage), `▼` less urgent than expected (under-triage), `-` not run yet; several codes in a cell are the runs of that case, in order.

| Case | Expected | GPT_OSS_20B |
|---|---|---|
| 01 | ROSSO | ROSSO |
| 02 | ROSSO | ROSSO |
| 03 | ROSSO | ROSSO |
| 04 | ARANCIONE | ROSSO ▲ |
| 05 | ARANCIONE | ARANCIONE |
| 06 | ARANCIONE | ARANCIONE |
| 07 | AZZURRO | ARANCIONE ▲ |
| 08 | AZZURRO | ARANCIONE ▲ |
| 09 | AZZURRO | AZZURRO |
| 10 | VERDE | VERDE |
| 11 | VERDE | VERDE |
| 12 | VERDE | VERDE |
| 13 | BIANCO | AZZURRO ▲ |
| 14 | BIANCO | VERDE ▲ |
| 15 | BIANCO | VERDE ▲ |

## Case by case: model with guidelines

| Case | Expected | GPT_OSS_20B |
|---|---|---|
| 01 | ROSSO | ROSSO |
| 02 | ROSSO | ROSSO |
| 03 | ROSSO | ROSSO |
| 04 | ARANCIONE | ROSSO ▲ |
| 05 | ARANCIONE | ROSSO ▲ |
| 06 | ARANCIONE | ROSSO ▲ |
| 07 | AZZURRO | ARANCIONE ▲ |
| 08 | AZZURRO | ARANCIONE ▲ |
| 09 | AZZURRO | VERDE ▼ |
| 10 | VERDE | VERDE |
| 11 | VERDE | AZZURRO ▲ |
| 12 | VERDE | VERDE |
| 13 | BIANCO | VERDE ▲ |
| 14 | BIANCO | VERDE ▲ |
| 15 | BIANCO | VERDE ▲ |

## Case by case: single agent

| Case | Expected | GPT_OSS_20B |
|---|---|---|
| 01 | ROSSO | ROSSO |
| 02 | ROSSO | ROSSO |
| 03 | ROSSO | ROSSO |
| 04 | ARANCIONE | ROSSO ▲ |
| 05 | ARANCIONE | ARANCIONE |
| 06 | ARANCIONE | ROSSO ▲ |
| 07 | AZZURRO | ROSSO ▲ |
| 08 | AZZURRO | ARANCIONE ▲ |
| 09 | AZZURRO | AZZURRO |
| 10 | VERDE | VERDE |
| 11 | VERDE | BIANCO ▼ |
| 12 | VERDE | VERDE |
| 13 | BIANCO | AZZURRO ▲ |
| 14 | BIANCO | AZZURRO ▲ |
| 15 | BIANCO | VERDE ▲ |

## Case by case: full system

| Case | Expected | GPT_OSS_20B |
|---|---|---|
| 01 | ROSSO | ROSSO |
| 02 | ROSSO | ROSSO |
| 03 | ROSSO | ARANCIONE ▼ |
| 04 | ARANCIONE | ROSSO ▲ |
| 05 | ARANCIONE | ROSSO ▲ |
| 06 | ARANCIONE | ROSSO ▲ |
| 07 | AZZURRO | ARANCIONE ▲ |
| 08 | AZZURRO | ARANCIONE ▲ |
| 09 | AZZURRO | VERDE ▼ |
| 10 | VERDE | VERDE |
| 11 | VERDE | BIANCO ▼ |
| 12 | VERDE | VERDE |
| 13 | BIANCO | BIANCO |
| 14 | BIANCO | VERDE ▲ |
| 15 | BIANCO | VERDE ▲ |
