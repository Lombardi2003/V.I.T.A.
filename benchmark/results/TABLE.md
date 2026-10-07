# Benchmark results

Built by `python -m benchmark.table` from the raw results in `raw/`. The steps and the measures are defined in `benchmark/PROTOCOL.md`, the cases in `benchmark/CASES.md`. The same numbers are in `table.csv` and, case by case, in `cases.csv`.

## Progress

| Model | Step reached | Model alone | Full system |
|---|---|---|---|
| GPT_OSS_120B | 3 - complete | 15/15 | 15/15 |
| GPT_OSS_20B | 3 - complete | 15/15 | 15/15 |
| LLAMA3_2 | 3 - complete | 15/15 | 15/15 |

## Step 1 - minimum: the model alone, on the 15 cases

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_120B | Model alone | 15 | 15 | 8/15 | 15/15 | 0 | 7 | 0 | 0.89 | - | 15/15 | 5/15 | 0 | - | 1 | 11 | 1.0 | 4202 |
| GPT_OSS_20B | Model alone | 15 | 15 | 5/15 | 13/15 | 2 | 8 | 0 | 0.76 | - | 15/15 | 5/15 | 0 | - | 1 | 11 | 1.0 | 4137 |
| LLAMA3_2 | Model alone | 15 | 15 | 4/15 | 6/15 | 0 | 10 | 1 | 0.19 | - | 9/15 | 5/15 | 1 | - | 3 | 0 | 1.0 | 2083 |

## Step 2 - intermediate: full system and model alone, on the 5 core cases

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_120B | Full system | 5 | 5 | 2/5 | 5/5 | 0 | 3 | 0 | 0.86 | - | 5/5 | 3/5 | 0 | 5.2 | 21 | 200 | 7.2 | 61872 |
| GPT_OSS_120B | Model alone | 5 | 5 | 2/5 | 5/5 | 0 | 3 | 0 | 0.86 | - | 5/5 | 1/5 | 0 | - | 2 | 11 | 1.0 | 4325 |
| GPT_OSS_20B | Full system | 5 | 5 | 3/5 | 5/5 | 0 | 2 | 0 | 0.92 | - | 5/5 | 2/5 | 0 | 4.6 | 15 | 171 | 6.6 | 52687 |
| GPT_OSS_20B | Model alone | 5 | 5 | 2/5 | 3/5 | 0 | 3 | 0 | 0.61 | - | 5/5 | 1/5 | 0 | - | 2 | 9 | 1.0 | 4203 |
| LLAMA3_2 | Full system | 5 | 5 | 2/5 | 3/5 | 0 | 3 | 0 | 0.30 | - | 5/5 | 2/5 | 0 | 11.0 | 114 | 0 | 13.0 | 61162 |
| LLAMA3_2 | Model alone | 5 | 5 | 2/5 | 2/5 | 0 | 2 | 1 | 0.20 | - | 4/5 | 1/5 | 1 | - | 4 | 0 | 1.0 | 2133 |

## Step 3 - complete: full system and model alone, on the 15 cases

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_120B | Full system | 15 | 15 | 6/15 | 15/15 | 1 | 8 | 0 | 0.87 | - | 14/15 | 12/15 | 0 | 5.3 | 20 | 205 | 7.3 | 64020 |
| GPT_OSS_120B | Model alone | 15 | 15 | 8/15 | 15/15 | 0 | 7 | 0 | 0.89 | - | 15/15 | 5/15 | 0 | - | 1 | 11 | 1.0 | 4202 |
| GPT_OSS_20B | Full system | 15 | 15 | 8/15 | 15/15 | 1 | 6 | 0 | 0.88 | - | 13/15 | 7/15 | 0 | 4.3 | 15 | 159 | 6.3 | 49326 |
| GPT_OSS_20B | Model alone | 15 | 15 | 5/15 | 13/15 | 2 | 8 | 0 | 0.76 | - | 15/15 | 5/15 | 0 | - | 1 | 11 | 1.0 | 4137 |
| LLAMA3_2 | Full system | 15 | 15 | 5/15 | 9/15 | 1 | 9 | 0 | 0.19 | - | 12/15 | 7/15 | 12 | 10.4 | 121 | 0 | 12.4 | 60149 |
| LLAMA3_2 | Model alone | 15 | 15 | 4/15 | 6/15 | 0 | 10 | 1 | 0.19 | - | 9/15 | 5/15 | 1 | - | 3 | 0 | 1.0 | 2083 |

## Case by case: model alone

`▲` more urgent than expected (over-triage), `▼` less urgent than expected (under-triage), `-` not run yet; several codes in a cell are the runs of that case, in order. ★ marks the core cases.

| Case | Expected | GPT_OSS_120B | GPT_OSS_20B | LLAMA3_2 |
|---|---|---|---|---|
| 01 ★ | ROSSO | ROSSO | ROSSO | ROSSO |
| 02 | ROSSO | ROSSO | ROSSO | ROSSO |
| 03 | ROSSO | ROSSO | ROSSO | ROSSO |
| 04 ★ | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ARANCIONE |
| 05 | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ |
| 06 | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ |
| 07 ★ | AZZURRO | ARANCIONE ▲ | ROSSO ▲ | ROSSO ▲ |
| 08 | AZZURRO | ARANCIONE ▲ | AZZURRO | ROSSO ▲ |
| 09 | AZZURRO | AZZURRO | VERDE ▼ | ROSSO ▲ |
| 10 ★ | VERDE | VERDE | VERDE | ARANCIONE ▲ |
| 11 | VERDE | VERDE | BIANCO ▼ | ROSSO ▲ |
| 12 | VERDE | VERDE | AZZURRO ▲ | ARANCIONE ▲ |
| 13 ★ | BIANCO | VERDE ▲ | AZZURRO ▲ | no answer |
| 14 | BIANCO | VERDE ▲ | VERDE ▲ | ARANCIONE ▲ |
| 15 | BIANCO | BIANCO | VERDE ▲ | ARANCIONE ▲ |

## Case by case: full system

| Case | Expected | GPT_OSS_120B | GPT_OSS_20B | LLAMA3_2 |
|---|---|---|---|---|
| 01 ★ | ROSSO | ROSSO | ROSSO | ROSSO |
| 02 | ROSSO | ROSSO | ROSSO | ARANCIONE ▼ |
| 03 | ROSSO | ROSSO | ARANCIONE ▼ | ROSSO |
| 04 ★ | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ARANCIONE |
| 05 | ARANCIONE | ROSSO ▲ | ARANCIONE | ARANCIONE |
| 06 | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ARANCIONE |
| 07 ★ | AZZURRO | ARANCIONE ▲ | ARANCIONE ▲ | ROSSO ▲ |
| 08 | AZZURRO | ARANCIONE ▲ | ARANCIONE ▲ | ARANCIONE ▲ |
| 09 | AZZURRO | ARANCIONE ▲ | AZZURRO | ARANCIONE ▲ |
| 10 ★ | VERDE | VERDE | VERDE | AZZURRO ▲ |
| 11 | VERDE | VERDE | VERDE | ARANCIONE ▲ |
| 12 | VERDE | BIANCO ▼ | VERDE | ARANCIONE ▲ |
| 13 ★ | BIANCO | VERDE ▲ | BIANCO | ARANCIONE ▲ |
| 14 | BIANCO | VERDE ▲ | VERDE ▲ | ARANCIONE ▲ |
| 15 | BIANCO | BIANCO | VERDE ▲ | ARANCIONE ▲ |
