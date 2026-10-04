<div align="center">

# 🔬 V.I.T.A. — Results of the real runs

</div>

<div align="justify">

The logs of the runs made with the real models, and of the retrieval benchmark, with what each one shows. The runs use the four fixed reference cases of `tests/live/reference_cases.py`: the patient card is given already confirmed, and the run goes from the supervisor to the summary report. All patients are fictional.

Each log in `logs/` contains the terminal output of the run and, at the end, the discussion entry by entry, the group hypothesis and the report. The account identifier of the provider has been removed from the error messages.

</div>

## 🩺 The four reference cases

| Case | Patient | Symptoms |
|---|---|---|
| 1 | 14 years old | Knee pain after a bike fall, unbearable; photo of an abrasion. |
| 2 | 63 years old, hypertension | Oppressive chest pain radiating to the left arm; sweating. |
| 3 | 34 years old | Cramping abdominal pain; itchy red rash. |
| 4 | 65 years old, known atrial fibrillation | Irregular palpitations; large spontaneous bruises. |

## 🧪 Runs

<div align="justify">

"Baseline" is the system before the changes to the specialist prompt and to the round table. Codes are the Italian triage colour codes.

</div>

| Log | Date | Model | Hypothesis in the report | Code | Notes |
|---|---|---|---|---|---|
| `01_baseline_120b_case1` | 1 Oct | gpt-oss-120b | Epiphyseal fracture of the knee | ROSSO | Signs never reported are taken as facts. |
| `01_baseline_120b_case2` | 1 Oct | gpt-oss-120b | Suspected acute coronary syndrome | ROSSO | One specialist only: no second opinion yet. |
| `01_baseline_120b_case3` | 1 Oct | gpt-oss-120b | IgA vasculitis | ARANCIONE | Two requests rejected for size (error 413), two failed turns. |
| `01_baseline_120b_case4` | 1 Oct | gpt-oss-120b | Atrial fibrillation with possible excess anticoagulation | ROSSO | Anticoagulant therapy assumed; two requests rejected for size. |
| `02_baseline_gemini_case1_incomplete` | 1 Oct | gemini-3.8-flash | — | — | Stopped by the daily request limit and a provider overload. |
| `02_baseline_gemini_case3` | 1 Oct | gemini-3.8-flash | Systemic allergic reaction, or scombroid syndrome | ARANCIONE | Same prompt and code as the baseline: no invented details. |
| `03_compact_prompt_120b_case2` | 1 Oct | gpt-oss-120b | Acute myocardial infarction (suspected) | ROSSO | With the second opinion of the general practitioner. |
| `03_compact_prompt_120b_case3` | 1 Oct | gpt-oss-120b | IgA vasculitis | ARANCIONE | No rejected request, no failed turn. |
| `03_compact_prompt_120b_case4` | 1 Oct | gpt-oss-120b | Atrial fibrillation with possible excess anticoagulation or thrombocytopenia | ARANCIONE | No rejected request; a longer discussion with revisions. |
| `04_all_changes_120b_case1` | 1 Oct | gpt-oss-120b | Possible fracture of the knee | ARANCIONE | The primary moves the unreported signs to the list to verify. |
| `04_all_changes_120b_case2` | 1 Oct | gpt-oss-120b | Acute myocardial infarction (suspected) | ROSSO | Complete report, with data to verify. |
| `04_all_changes_120b_case3_quota_exhausted` | 1 Oct | gpt-oss-120b | IgA vasculitis | ARANCIONE | Daily quota running out: three failed turns, the table still closes. |
| `04_all_changes_120b_case4_quota_exhausted` | 1 Oct | gpt-oss-120b | Not determined (technical error) | ARANCIONE | Quota exhausted: the specialists' and the primary's calls fail and the precautionary fallback applies. |
| `05_final_120b_cases3_4` | 2 Oct | gpt-oss-120b | Case 3: IgA vasculitis. Case 4: bleeding complication of anticoagulant therapy | ARANCIONE, ARANCIONE | Full quota: 9 and 7 turns, no failed turn. |
| `05_final_gemini_cases2_4` | 2 Oct | gemini-3.8-flash | Case 2: suspected acute coronary syndrome. Case 4: recurrent atrial fibrillation with bleeding tendency to be determined | ROSSO, ARANCIONE | Case 2: the primary's call fails and the report is the table's hypothesis. |
| `06_not_reported_rule_120b_case3` | 2 Oct | gpt-oss-120b | IgA vasculitis | ARANCIONE | After the "not reported is not absent" rule: fewer such statements, not none. |

## 📚 Retrieval benchmark

<div align="justify">

Fixed clinical cases, one or more per specialist. *hit@1*: the first chunk comes from the right specialty. *hit@3*: at least one of the three does. *Mixed*: for charts with symptoms of different specialties, how many chunks match those retrieved with the pertinent symptom alone.

</div>

| Log | Index | Cases | hit@1 | hit@3 | Chunks from the right specialty | Mixed |
|---|---|---|---|---|---|---|
| `rag_1_before_new_documents` | 21 documents, 2,448 chunks | 30 | 22 | 30 | 63/90 | 24/27 |
| `rag_2_after_new_documents` | 23 documents, 2,478 chunks | 32 | 24 | 32 | 67/96 | 24/27 |
| `rag_3_before_excluding_credit_pages` | same index, credit pages no longer counted as hits | 32 | 23 | 31 | 65/96 | 24/27 |
| `rag_4_current` | credit pages excluded, 2,443 chunks | 32 | 24 | 32 | 67/96 | 24/27 |

<div align="justify">

`rag_index_build.log` is the output of the index build: pages and chunks per document, and how many chunks each rule discarded.

</div>

## 📌 What the runs show

<div align="justify">

- **The flow always completes.** Every run reaches a report, including those in which the provider quota ran out halfway.
- **Technical limits were removed by changes to the system.** The compact prompt and the shortened transcript eliminated the requests rejected for size.
- **Clinical quality depends mostly on the model.** On the same prompt, case 3 gives an allergic reaction with one model and a vasculitis built on unreported details with the other.
- **Rules reduce unsupported statements, they do not remove them.** The list of data to verify, written by the primary, is the safeguard that works.

The full reasoning is in section 14 of [DESIGN.md](../DESIGN.md).

</div>

## 📊 Model benchmark

<div align="justify">

The runs above were read one by one. The comparison between models on fixed cases with an expected code is the model benchmark: its protocol is in [benchmark/PROTOCOL.md](../../benchmark/PROTOCOL.md) and its results, with the table, are in `benchmark/results/`.

</div>

## ℹ️ Not included

<div align="justify">

The conversations made in the app (a patient with eye pain, a child after a fall with a photo, a returning patient, and others) were followed in the browser and are not saved as logs. Their overall outcome is in section 14 of [DESIGN.md](../DESIGN.md).

</div>
