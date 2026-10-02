# V.I.T.A. tests

Three folders, three different kinds of check. Every command runs from the
project folder.

| Folder | What it checks | Model | API quota | Outcome |
|---|---|---|---|---|
| `unit/` | that **every node works** (flow, confirmations, fallbacks, formats, limits) | fake | no | automatic: pass / fail |
| `benchmarks/` | the **retrieval quality** of the guidelines (RAG) | none | no | numbers to compare |
| `live/` | the table's **clinical reasoning** on real cases | real | **yes** | to be read |

## One command for everything

```bash
python -m tests.run all
```

Runs the unit tests and then the benchmark, one after the other, and ends
with a summary. Other forms:

| Command | Runs |
|---|---|
| `python -m tests.run` or `python -m tests.run unit` | all unit tests (~20 s) |
| `python -m tests.run unit test_intake test_router` | only those unit test files |
| `python -m tests.run benchmarks` | the RAG benchmark |
| `python -m tests.run live` | every live script (**uses quota**) |
| `python -m tests.run live correction` | only that live script |

`live` is never part of `all`: it has to be asked for explicitly.

## `unit/`: run after every code change

Real graph, fake model: each test decides what the model "answers" and checks
what the system does. Every test has a one-line description starting with
`TEST`, shown next to its name when it runs. Shared tools (fake model, fake
chat, temporary database, conversation on the real graph) are in
`unit/helpers.py`.

| File | Covers |
|---|---|
| `test_read_db.py` | fiscal code check, new / registered patient, database error |
| `test_intake.py` | personal data card, confirmation, corrections, anti-invention |
| `test_reviewer.py` | symptoms, confirmation, corrections, anti-invention |
| `test_photography.py` | photo request, refusal, analysis, large / rotated / odd images |
| `test_supervisor.py` | choice of specialists, cap, second opinion, fallbacks |
| `test_specialist.py` | reading the specialist's answer, consults, prompt notes |
| `test_router.py` | the router's rules and whole discussions at the table |
| `test_primary.py` | urgency code, fallbacks, summary report |
| `test_llm.py` | retries, token limits, JSON reading, clients, needed keys |
| `test_rag.py` | specialty / general split of the retrieval, index cleaning |
| `test_app.py` | operator error messages, photo attachment, resume after an error |
| `test_end_to_end.py` | whole conversations from the fiscal code to the report |
| `test_resilience.py` | random malformed model answers, same input same result |

They say nothing about clinical quality (the model is fake): that is what the
live scripts are for.

## `benchmarks/`: run when the documents or the RAG change

`rag_retrieval.py`: for a fixed set of clinical cases it checks whether the
retrieved chunks include the right specialty (hit@1, hit@3), the cases with
mixed symptoms and the noise in the index. It works on a temporary copy of the
index.

## `live/`: real model (uses quota)

| Script | What it tries |
|---|---|
| `round_table.py` | discussion between two specialists |
| `mini_consult.py` | mini-consult towards an absent colleague |
| `correction.py` | correction of a wrong hypothesis injected on purpose |
| `supervisor_selection.py` | choice of specialists with symptoms from different fields |

The output has to be read: there is no automatic outcome, the content is
written by the model. They use the model chosen in `src/llm/factory.py`.
