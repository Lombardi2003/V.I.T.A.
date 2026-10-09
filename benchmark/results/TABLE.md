# Benchmark results

Built by `python -m benchmark.table` from the raw results in `raw/`. The steps and the measures are defined in `benchmark/PROTOCOL.md`, the cases in `benchmark/CASES.md`. The same numbers are in `table.csv` and, case by case, in `cases.csv`.

## Progress

| Model | Step reached | Model alone | Full system |
|---|---|---|---|
| GPT_OSS_120B | 3 - complete | 15/15 | 15/15 |
| GPT_OSS_20B | 3 - complete | 15/15 | 15/15 |
| LLAMA3_1 | 3 - complete | 15/15 | 15/15 |
| LLAMA3_2 | 3 - complete | 15/15 | 15/15 |
| MINISTRAL3_8B | 3 - complete | 15/15 | 15/15 |
| QWEN3_14B | 3 - complete | 15/15 | 15/15 |
| QWEN3_8B | 3 - complete | 15/15 | 15/15 |
| QWEN_27B | 3 - complete | 15/15 | 15/15 |

## Step 1 - minimum: the model alone, on the 15 cases

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_120B | Model alone | 15 | 15 | 8/15 | 15/15 | 0 | 7 | 0 | 0.89 | - | 15/15 | 5/15 | 0 | - | 1 | 11 | 1.0 | 4202 |
| GPT_OSS_20B | Model alone | 15 | 15 | 5/15 | 13/15 | 2 | 8 | 0 | 0.76 | - | 15/15 | 5/15 | 0 | - | 1 | 11 | 1.0 | 4137 |
| LLAMA3_1 | Model alone | 15 | 15 | 3/15 | 9/15 | 0 | 12 | 0 | 0.35 | - | 12/15 | 5/15 | 0 | - | 9 | 0 | 1.0 | 2079 |
| LLAMA3_2 | Model alone | 15 | 15 | 4/15 | 6/15 | 0 | 10 | 1 | 0.19 | - | 9/15 | 5/15 | 1 | - | 4 | 0 | 1.0 | 2083 |
| MINISTRAL3_8B | Model alone | 15 | 15 | 6/15 | 11/15 | 0 | 6 | 3 | 0.77 | - | 12/15 | 5/15 | 3 | - | 15 | 0 | 1.0 | 2935 |
| QWEN3_14B | Model alone | 15 | 15 | 5/15 | 14/15 | 1 | 9 | 0 | 0.79 | - | 14/15 | 5/15 | 0 | - | 51 | 0 | 1.0 | 2595 |
| QWEN3_8B | Model alone | 15 | 15 | 7/15 | 14/15 | 0 | 8 | 0 | 0.83 | - | 15/15 | 5/15 | 0 | - | 31 | 0 | 1.0 | 2665 |
| QWEN_27B | Model alone | 15 | 15 | 11/15 | 14/15 | 0 | 4 | 0 | 0.89 | - | 14/15 | 5/15 | 0 | - | 1 | 11 | 1.0 | 3900 |

## Step 2 - intermediate: full system and model alone, on the 5 core cases

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_120B | Full system | 5 | 5 | 2/5 | 5/5 | 0 | 3 | 0 | 0.86 | - | 5/5 | 3/5 | 0 | 5.2 | 21 | 200 | 7.2 | 61872 |
| GPT_OSS_120B | Model alone | 5 | 5 | 2/5 | 5/5 | 0 | 3 | 0 | 0.86 | - | 5/5 | 1/5 | 0 | - | 2 | 11 | 1.0 | 4325 |
| GPT_OSS_20B | Full system | 5 | 5 | 3/5 | 5/5 | 0 | 2 | 0 | 0.92 | - | 5/5 | 2/5 | 0 | 4.6 | 15 | 171 | 6.6 | 52687 |
| GPT_OSS_20B | Model alone | 5 | 5 | 2/5 | 3/5 | 0 | 3 | 0 | 0.61 | - | 5/5 | 1/5 | 0 | - | 2 | 9 | 1.0 | 4203 |
| LLAMA3_1 | Full system | 5 | 5 | 2/5 | 4/5 | 0 | 3 | 0 | 0.35 | - | 4/5 | 1/5 | 0 | 5.0 | 121 | 0 | 7.0 | 27735 |
| LLAMA3_1 | Model alone | 5 | 5 | 1/5 | 3/5 | 0 | 4 | 0 | 0.29 | - | 5/5 | 1/5 | 0 | - | 9 | 0 | 1.0 | 2119 |
| LLAMA3_2 | Full system | 5 | 5 | 2/5 | 3/5 | 0 | 3 | 0 | 0.30 | - | 5/5 | 2/5 | 0 | 11.0 | 120 | 0 | 13.0 | 61162 |
| LLAMA3_2 | Model alone | 5 | 5 | 2/5 | 2/5 | 0 | 2 | 1 | 0.20 | - | 4/5 | 1/5 | 1 | - | 5 | 0 | 1.0 | 2133 |
| MINISTRAL3_8B | Full system | 5 | 5 | 2/5 | 4/5 | 1 | 2 | 0 | 0.57 | - | 5/5 | 3/5 | 11 | 4.0 | 274 | 0 | 6.0 | 33630 |
| MINISTRAL3_8B | Model alone | 5 | 5 | 1/5 | 3/5 | 0 | 3 | 1 | 0.57 | - | 4/5 | 1/5 | 1 | - | 19 | 0 | 1.0 | 2972 |
| QWEN3_14B | Full system | 5 | 5 | 3/5 | 4/5 | 0 | 2 | 0 | 0.71 | - | 5/5 | 2/5 | 0 | 5.4 | 523 | 0 | 7.4 | 35830 |
| QWEN3_14B | Model alone | 5 | 5 | 1/5 | 4/5 | 0 | 4 | 0 | 0.63 | - | 5/5 | 1/5 | 0 | - | 59 | 0 | 1.0 | 2750 |
| QWEN3_8B | Full system | 5 | 5 | 2/5 | 4/5 | 0 | 3 | 0 | 0.48 | - | 5/5 | 1/5 | 0 | 6.6 | 325 | 0 | 8.6 | 42764 |
| QWEN3_8B | Model alone | 5 | 5 | 2/5 | 4/5 | 0 | 3 | 0 | 0.75 | - | 5/5 | 1/5 | 0 | - | 32 | 0 | 1.0 | 2729 |
| QWEN_27B | Full system | 5 | 5 | 2/5 | 4/5 | 0 | 3 | 0 | 0.70 | - | 5/5 | 1/5 | 0 | 5.8 | 18 | 209 | 7.8 | 66712 |
| QWEN_27B | Model alone | 5 | 5 | 2/5 | 4/5 | 0 | 3 | 0 | 0.70 | - | 5/5 | 1/5 | 0 | - | 2 | 9 | 1.0 | 3990 |

## Step 3 - complete: full system and model alone, on the 15 cases

| Model | Condition | Cases | Records | Exact | Within one | Under | Over | No answer | Kappa | Stable | Specialty | Sheet seen | Invalid answers | Turns | Seconds | Wait | Calls | Tokens |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| GPT_OSS_120B | Full system | 15 | 15 | 6/15 | 15/15 | 1 | 8 | 0 | 0.87 | - | 14/15 | 12/15 | 0 | 5.3 | 20 | 205 | 7.3 | 64020 |
| GPT_OSS_120B | Model alone | 15 | 15 | 8/15 | 15/15 | 0 | 7 | 0 | 0.89 | - | 15/15 | 5/15 | 0 | - | 1 | 11 | 1.0 | 4202 |
| GPT_OSS_20B | Full system | 15 | 15 | 8/15 | 15/15 | 1 | 6 | 0 | 0.88 | - | 13/15 | 7/15 | 0 | 4.3 | 15 | 159 | 6.3 | 49326 |
| GPT_OSS_20B | Model alone | 15 | 15 | 5/15 | 13/15 | 2 | 8 | 0 | 0.76 | - | 15/15 | 5/15 | 0 | - | 1 | 11 | 1.0 | 4137 |
| LLAMA3_1 | Full system | 15 | 15 | 4/15 | 12/15 | 2 | 9 | 0 | 0.44 | - | 13/15 | 7/15 | 0 | 6.2 | 162 | 0 | 8.2 | 35440 |
| LLAMA3_1 | Model alone | 15 | 15 | 3/15 | 9/15 | 0 | 12 | 0 | 0.35 | - | 12/15 | 5/15 | 0 | - | 9 | 0 | 1.0 | 2079 |
| LLAMA3_2 | Full system | 15 | 15 | 5/15 | 9/15 | 1 | 9 | 0 | 0.19 | - | 12/15 | 7/15 | 10 | 10.5 | 152 | 0 | 12.5 | 61422 |
| LLAMA3_2 | Model alone | 15 | 15 | 4/15 | 6/15 | 0 | 10 | 1 | 0.19 | - | 9/15 | 5/15 | 1 | - | 4 | 0 | 1.0 | 2083 |
| MINISTRAL3_8B | Full system | 15 | 15 | 8/15 | 14/15 | 1 | 6 | 0 | 0.81 | - | 14/15 | 9/15 | 30 | 4.5 | 300 | 0 | 6.5 | 38895 |
| MINISTRAL3_8B | Model alone | 15 | 15 | 6/15 | 11/15 | 0 | 6 | 3 | 0.77 | - | 12/15 | 5/15 | 3 | - | 15 | 0 | 1.0 | 2935 |
| QWEN3_14B | Full system | 15 | 15 | 5/15 | 13/15 | 2 | 8 | 0 | 0.69 | - | 14/15 | 9/15 | 1 | 4.6 | 460 | 0 | 6.6 | 30369 |
| QWEN3_14B | Model alone | 15 | 15 | 5/15 | 14/15 | 1 | 9 | 0 | 0.79 | - | 14/15 | 5/15 | 0 | - | 51 | 0 | 1.0 | 2595 |
| QWEN3_8B | Full system | 15 | 15 | 7/15 | 14/15 | 0 | 8 | 0 | 0.73 | - | 14/15 | 8/15 | 1 | 6.1 | 335 | 0 | 8.1 | 40336 |
| QWEN3_8B | Model alone | 15 | 15 | 7/15 | 14/15 | 0 | 8 | 0 | 0.83 | - | 15/15 | 5/15 | 0 | - | 31 | 0 | 1.0 | 2665 |
| QWEN_27B | Full system | 15 | 15 | 10/15 | 14/15 | 0 | 5 | 0 | 0.88 | - | 13/15 | 7/15 | 0 | 5.5 | 19 | 198 | 7.5 | 63966 |
| QWEN_27B | Model alone | 15 | 15 | 11/15 | 14/15 | 0 | 4 | 0 | 0.89 | - | 14/15 | 5/15 | 0 | - | 1 | 11 | 1.0 | 3900 |

## Case by case: model alone

`▲` more urgent than expected (over-triage), `▼` less urgent than expected (under-triage), `-` not run yet; several codes in a cell are the runs of that case, in order. ★ marks the core cases.

| Case | Expected | GPT_OSS_120B | GPT_OSS_20B | LLAMA3_1 | LLAMA3_2 | MINISTRAL3_8B | QWEN3_14B | QWEN3_8B | QWEN_27B |
|---|---|---|---|---|---|---|---|---|---|
| 01 ★ | ROSSO | ROSSO | ROSSO | ROSSO | ROSSO | no answer | ROSSO | ROSSO | ROSSO |
| 02 | ROSSO | ROSSO | ROSSO | ROSSO | ROSSO | ROSSO | ROSSO | ROSSO | ROSSO |
| 03 | ROSSO | ROSSO | ROSSO | ROSSO | ROSSO | no answer | ROSSO | ROSSO | ROSSO |
| 04 ★ | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ |
| 05 | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ | ARANCIONE | ROSSO ▲ | ARANCIONE | ARANCIONE |
| 06 | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ | no answer | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ |
| 07 ★ | AZZURRO | ARANCIONE ▲ | ROSSO ▲ | ARANCIONE ▲ | ROSSO ▲ | ARANCIONE ▲ | ARANCIONE ▲ | ROSSO ▲ | ARANCIONE ▲ |
| 08 | AZZURRO | ARANCIONE ▲ | AZZURRO | ARANCIONE ▲ | ROSSO ▲ | ARANCIONE ▲ | VERDE ▼ | ARANCIONE ▲ | AZZURRO |
| 09 | AZZURRO | AZZURRO | VERDE ▼ | ARANCIONE ▲ | ROSSO ▲ | AZZURRO | ARANCIONE ▲ | ARANCIONE ▲ | AZZURRO |
| 10 ★ | VERDE | VERDE | VERDE | ARANCIONE ▲ | ARANCIONE ▲ | VERDE | AZZURRO ▲ | VERDE | VERDE |
| 11 | VERDE | VERDE | BIANCO ▼ | ARANCIONE ▲ | ROSSO ▲ | VERDE | AZZURRO ▲ | VERDE | VERDE |
| 12 | VERDE | VERDE | AZZURRO ▲ | ARANCIONE ▲ | ARANCIONE ▲ | VERDE | VERDE | VERDE | VERDE |
| 13 ★ | BIANCO | VERDE ▲ | AZZURRO ▲ | ARANCIONE ▲ | no answer | AZZURRO ▲ | AZZURRO ▲ | VERDE ▲ | AZZURRO ▲ |
| 14 | BIANCO | VERDE ▲ | VERDE ▲ | AZZURRO ▲ | ARANCIONE ▲ | VERDE ▲ | VERDE ▲ | VERDE ▲ | BIANCO |
| 15 | BIANCO | BIANCO | VERDE ▲ | ARANCIONE ▲ | ARANCIONE ▲ | VERDE ▲ | BIANCO | VERDE ▲ | BIANCO |

## Case by case: full system

| Case | Expected | GPT_OSS_120B | GPT_OSS_20B | LLAMA3_1 | LLAMA3_2 | MINISTRAL3_8B | QWEN3_14B | QWEN3_8B | QWEN_27B |
|---|---|---|---|---|---|---|---|---|---|
| 01 ★ | ROSSO | ROSSO | ROSSO | ROSSO | ROSSO | ARANCIONE ▼ | ROSSO | ROSSO | ROSSO |
| 02 | ROSSO | ROSSO | ROSSO | ARANCIONE ▼ | ARANCIONE ▼ | ROSSO | ROSSO | ROSSO | ROSSO |
| 03 | ROSSO | ROSSO | ARANCIONE ▼ | ARANCIONE ▼ | ROSSO | ROSSO | ARANCIONE ▼ | ROSSO | ROSSO |
| 04 ★ | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ARANCIONE | ARANCIONE | ARANCIONE | ARANCIONE | ROSSO ▲ | ROSSO ▲ |
| 05 | ARANCIONE | ROSSO ▲ | ARANCIONE | ROSSO ▲ | ARANCIONE | ARANCIONE | ARANCIONE | ARANCIONE | ARANCIONE |
| 06 | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ARANCIONE | ARANCIONE | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ | ROSSO ▲ |
| 07 ★ | AZZURRO | ARANCIONE ▲ | ARANCIONE ▲ | ARANCIONE ▲ | ROSSO ▲ | ARANCIONE ▲ | ARANCIONE ▲ | ARANCIONE ▲ | ARANCIONE ▲ |
| 08 | AZZURRO | ARANCIONE ▲ | ARANCIONE ▲ | ARANCIONE ▲ | ARANCIONE ▲ | ARANCIONE ▲ | ARANCIONE ▲ | ARANCIONE ▲ | ARANCIONE ▲ |
| 09 | AZZURRO | ARANCIONE ▲ | AZZURRO | AZZURRO | ARANCIONE ▲ | AZZURRO | VERDE ▼ | ARANCIONE ▲ | AZZURRO |
| 10 ★ | VERDE | VERDE | VERDE | AZZURRO ▲ | AZZURRO ▲ | VERDE | VERDE | VERDE | VERDE |
| 11 | VERDE | VERDE | VERDE | AZZURRO ▲ | ARANCIONE ▲ | VERDE | ARANCIONE ▲ | VERDE | VERDE |
| 12 | VERDE | BIANCO ▼ | VERDE | AZZURRO ▲ | ARANCIONE ▲ | VERDE | AZZURRO ▲ | VERDE | VERDE |
| 13 ★ | BIANCO | VERDE ▲ | BIANCO | ARANCIONE ▲ | ARANCIONE ▲ | AZZURRO ▲ | AZZURRO ▲ | ARANCIONE ▲ | AZZURRO ▲ |
| 14 | BIANCO | VERDE ▲ | VERDE ▲ | AZZURRO ▲ | ARANCIONE ▲ | VERDE ▲ | VERDE ▲ | VERDE ▲ | BIANCO |
| 15 | BIANCO | BIANCO | VERDE ▲ | AZZURRO ▲ | ARANCIONE ▲ | VERDE ▲ | VERDE ▲ | VERDE ▲ | BIANCO |
