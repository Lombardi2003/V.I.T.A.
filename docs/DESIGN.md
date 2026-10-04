<div align="center">

# 🏥 V.I.T.A. — Design decisions

</div>

<div align="justify">

This document records **why** the system is built the way it is. `ARCHITECTURE.md` describes how it is structured; this file explains the choices behind it, what was observed in real runs, and which alternatives were discarded.

Each entry has the same shape: the decision, the reason, and, where relevant, what was observed or rejected.

</div>

## Contents

1. [Conventions](#-1-conventions)
2. [Principles that apply everywhere](#-2-principles-that-apply-everywhere)
3. [Conversation flow and graph](#-3-conversation-flow-and-graph)
4. [Fiscal code and database](#-4-fiscal-code-and-database)
5. [Intake: personal data](#-5-intake-personal-data)
6. [Reviewer: symptoms](#-6-reviewer-symptoms)
7. [Photography](#-7-photography)
8. [Supervisor](#-8-supervisor)
9. [Round table of specialists](#-9-round-table-of-specialists)
10. [Primary: summary report](#-10-primary-summary-report)
11. [Model layer](#-11-model-layer)
12. [Guideline retrieval (RAG)](#-12-guideline-retrieval-rag)
13. [Testing](#-13-testing)
14. [Experimental findings](#-14-experimental-findings)
15. [Known limits and future work](#-15-known-limits-and-future-work)

---

<div align="justify">

## 📐 1. Conventions

**Who uses the app.** The emergency-department staff, not the patient. Every message in the chat is written for an operator: impersonal form, operational content, no "go to the emergency department".

**Terminology.** The primary's output is a *summary report* ("report di sintesi") and its content a *preliminary diagnostic hypothesis* ("ipotesi diagnostica preliminare"). The words "final diagnosis" are avoided: the system supports triage, it does not diagnose.

**Urgency scale.** The five Italian triage colour codes, from most to least urgent: ROSSO, ARANCIONE, AZZURRO, VERDE, BIANCO. One scale everywhere (group hypothesis, round-table entries, final report); two different scales used to coexist and a valid code from one was rejected by the other.

**Language.** Code, comments and tests are in English. What the operator reads, the prompts, the JSON fields the model returns (`azione`, `conferma`, `diagnosi`, ...) and their values (`proponi`, `rivedi`, ...) stay in Italian: the model reasons and answers in Italian, and renaming those fields would mean rewriting and re-validating every prompt for no functional gain.

**"Agent".** Used in the broad sense (perceives, decides, acts). Not every node calls a model: `persistence` and `router` are deterministic.

---

## 🧭 2. Principles that apply everywhere

**The model extracts, Python validates and decides.** A model's answer is never applied as it comes. Each node reads the JSON, keeps only the fields it is allowed to change, checks them, and decides the next step in code. *Why:* in real runs the model ignored instructions that were only written in the prompt (it invented values, changed fields it should not touch, confirmed when nothing had been asked).

**A mandatory field changes behaviour more than prose does.** When a behaviour matters (ask a colleague, check for anchoring, name a discarded alternative), the model must fill a dedicated field on every turn, and Python acts on it. *Observed:* text that merely "allowed" an option was never enough; the same option as a field to fill worked.

**A technical failure must never look like a clinical judgement.** A truncated or unreadable answer is counted as a failed turn; it is never read as a confirmation. *Observed:* a real objection, cut off before the JSON was complete, was being turned into silent agreement with a wrong hypothesis.

**Every node survives a bad answer.** Null fields, a text where a list is expected, an object where a name is expected, a missing key: the node keeps the previous state and asks again. No model answer can crash the conversation.

**Every model call has a fallback.** Supervisor, specialists and primary each have a defined behaviour when the call fails after the retries (see their sections). The conversation always reaches a report.

**Not reported is not absent.** A sign the patient did not report is unknown. It may not be stated as present, nor as absent, nor used to exclude a hypothesis; it goes in the "to verify" list. (See section 14 for how far the model actually follows this.)

**Blocking calls never run on the event loop.** Model calls and retrieval are synchronous; they always run through `asyncio.to_thread`. *Observed:* with a slow local model the whole interface froze for the duration of the call.

---

## 🔀 3. Conversation flow and graph

**One pause per operator message.** The graph stops before the `user` node and resumes when a message arrives. When a step is completed, the next node runs at once, without an extra pause: fiscal code accepted → card shown; card confirmed → symptoms requested; symptoms confirmed → photo requested; photo handled → supervisor. *Observed:* fixed edges back to `user` made the app wait silently for a message nobody knew they had to send.

**First pass without the model.** When a node is entered right after the previous one finished, the operator has not written anything yet, so the node only shows its request (card, "describe the symptoms", photo request). Three flags in the state record that this first pass happened.

**The `user` node adds nothing.** The message is put in the state by `app.py` before the graph resumes. Adding it again in the node would duplicate it, because the histories are concatenated.

**`patient_card` has no merge reducer.** It is always written whole. Anything that changes one part (for example `app.py` attaching a photo) reads the current card, changes that part and writes everything back; writing only the changed part would erase the rest.

**Step limit computed from the turn cap.** LangGraph stops a run after 25 steps by default. A discussion that reaches the 12-turn cap takes two steps per turn (router + specialist), then router, primary and save: 27. The limit is set to `2 * MAX_TOTAL_TURNS + 20` through `thread_config()`, which every caller uses. *Observed:* found by a unit test right after the save node was added; before, it fitted by one step. Setting the limit on the compiled graph has no effect on `astream_events`, which is why it travels with the config.

**Errors reach the operator as a short message.** A node error interrupts the graph and arrives in `app.py` as an exception. The traceback goes to the terminal; the chat shows one of three short messages (usage limit, service unreachable, generic), each saying to send the last message again. Provider details such as the account identifier never reach the chat.

**The model in use is shown, not selectable.** The settings panel displays the models actually loaded, read from the clients, and is disabled. The choice is made in one place in the code (`src/llm/factory.py`), so an experiment is reproducible and there is no doubt about which model produced a result.

---

## 🗄️ 4. Fiscal code and database

**The fiscal code is checked, not just measured.** Format, check character and omocodia letters are verified, after removing spaces and case. *Why:* with a length check only, one wrong letter on a registered patient was still "valid": the patient was not found and a second record was opened.

**Test code `1234`.** Always accepted, always a new patient, never saved. It exists to try the app without touching the database.

**A database error does not stop the triage.** On a read error the conversation continues with a new card (the fiscal code is kept). On a write error the report stays in the chat and the operator is told the data was not saved.

**One save node, after the report.** It creates the patient or updates every field, so corrections made during intake are kept for returning patients. *Replaced:* two nodes that had never been reconnected after the redesign, saved only part of the card (no sex, no allergies) and could not run on the current state.

**The hypothesis is saved among the previous conditions, labelled.** The entry reads: `Ipotesi al triage del 03/10/2026: <hypothesis> (codice ARANCIONE, non confermata)`. *Why here:* previous conditions are already read by the card, the supervisor, the specialists and the primary, so the next visit sees the entry with no change to state or prompts. *Why labelled:* an unconfirmed, possibly wrong hypothesis must not become an established condition. The date, the code and "non confermata" say what it is, to the operator and to the model. *How it is corrected:* at the next visit the card is shown for confirmation and the operator can remove the entry in plain words. Verified with the real model on three phrasings, including removing one of two entries, while a plain confirmation leaves the entry in place. *Alternative discarded for now:* a separate table of visits. Cleaner, but the data would be invisible to the agents unless state and prompts were changed too. It is listed as future work.

**No entry when there is no hypothesis.** If neither the table nor the primary produced one, the card is saved without adding anything.

**The photo is not saved.** The file is temporary; only its description is used, and only during the visit.

---

## 🪪 5. Intake: personal data

**The card is shown at every turn.** A compact card with what is known, then either what is missing or the confirmation request. The model's own sentence ("I understood that...") is not shown: the card already says it.

**Confirmation is explicit and strict.** A confirmation counts only if it had been asked for (the card was complete at the previous turn) and nothing changed in the same message. "Yes, but the age is 45" is a correction: the card is shown again and must be confirmed again.

**The model may change only the personal fields.** A whitelist limits it to name, surname, age, sex, allergies and previous conditions. *Observed:* without it, a fiscal code written by the model replaced the validated one.

**Lists accumulate, single values are replaced.** An allergy given at one turn is kept when another is given later; an age given later corrects the earlier one. Duplicates are dropped ignoring case.

**Explicit removals.** Since lists accumulate, a wrong entry could never be removed. The model returns the entries to remove in dedicated fields.

**"Addressed" flags for allergies and previous conditions.** An empty list is ambiguous: "none" or "not asked yet". Two flags record that the topic was addressed, even to deny it. They live in the conversation state, not in the card: they are bookkeeping, not clinical data.

**The flags only go one way, and keywords back them up.** Once true they never return to false, whatever the model says. If the message contains "allerg" or a condition keyword, the flag is set even if the model missed it. *Observed:* "he is male and has no allergies" → the model caught "male" and missed the allergies.

**Data is normalised in the card itself.** Sex becomes uomo/donna (maschio/ femmina for minors), names get capital initials. Normalising the stored value, not just the display, keeps the database uniform.

---

## 🩺 6. Reviewer: symptoms

**Each symptom is its own record.** A patient may report several, each with its own intensity and duration.

**Two separate free-text fields.** `characteristics` (how the symptom is: site, quality, radiation) and `trigger` (when it changes, or the event that caused it). *Observed:* without them "chest pain radiating to the left arm" reached the specialists as "chest pain", and "dizziness when standing up" as "dizziness".

**The event that caused the symptoms goes in the trigger of each.** A fall, a sting, a food or drug just taken is stored at once, for every symptom it explains. *Observed:* "fell off a scooter" was lost until the operator repeated it.

**Invented intensity and duration are discarded in code.** If the message contains no word related to intensity or to time, the value returned by the model is dropped. *Observed:* with "I have a headache" the model copied "strong"/"3 hours" from the prompt examples; telling it not to failed in 4 runs out of 4. *Detail:* the duration check uses whole words in a regular expression; an earlier list of word fragments discarded "since this morning" and "for an hour".

**An update must name its symptom when there is ambiguity.** With more than one incomplete symptom, an update is applied only if the message mentions that symptom. With a single symptom, or a single incomplete one, an implicit reference is accepted. *Observed:* "the blurred vision is mild" updated the headache instead and the conversation got stuck asking for the same data.

**Only the symptoms are read from the answer.** Whatever else the model returns is ignored: personal data belongs to intake and is already confirmed.

**Same confirmation and removal rules as intake.**

---

## 📷 7. Photography

**Observation only.** The vision model describes what the photo shows. It gives no judgement of severity: that needs the whole clinical picture.

**No confirmation step.** The photo is requested with a question; the operator attaches it or declines.

**An attached photo wins over the caption.** The photo is checked before the text refusal. *Observed:* "No, it is not worrying but here it is" was being read as a refusal.

**Refusals are recognised broadly but anchored at the start.** "no", "no grazie", "non ho foto", "salta"... An exact match was too fragile; anchoring at the beginning avoids words that merely contain "no".

**The original file is never modified.** If the image is within the provider limit and in a supported format it is sent as it is, with its real type. Only if it is too large or in an unsupported format, a reduced JPEG copy is sent, as large as the limit allows, with the EXIF rotation applied. *Why:* the provider rejects images above about 4 MB in base64, which a phone photo often exceeds.

**An unusable photo is asked again.** If the model answers "NON VALUTABILE", the photo is removed from the card and another one is requested. If the call or the answer fails, the conversation goes on without the photo.

---

## 🚦 8. Supervisor

**Routing only.** It chooses which specialists to involve; it gives no diagnosis.

**The final list is the union with the per-symptom analysis.** The prompt asks for a specialist per symptom and then a final list; the code merges the two. *Observed:* the dermatologist named for the rash was missing from the final list.

**At most three specialists.** More make the discussion long and expensive, and with the turn cap each would speak only a couple of times. When cutting, one specialist per symptom is kept first, so no symptom is left uncovered.

**Second opinion when there is a single specialist.** The general practitioner is added, with a dedicated instruction, and the chat says so. *Observed:* a lone specialist proposed and then, in the verification round, re-read itself with nobody checking. It is a fixed rule, with no extra model call, and it is declared because it is not a clinical choice of the supervisor.

**Fallback to the general practitioner.** On an unreadable answer or a failed call, the general practitioner is seated and the chat says it is a technical fallback, not a clinical choice.

**Names are understood in Italian too.** Roles, specialty names ("Dermatologia") and doctor names ("il dermatologo") all map to the internal role.

---

## 👥 9. Round table of specialists

**One shared hypothesis, not separate reports.** All specialists read, confirm or revise the same object. The discussion ends when everyone seated has confirmed its current version. A revision clears the confirmations: the others must confirm the new version. *Replaced:* independent reports that nobody actually compared.

**Four actions.** `proponi` (only if no hypothesis exists), `conferma`, `rivedi`, `consulta` (a clinical-knowledge question to a colleague not at the table). An action that does not fit the context falls back to the only valid one, without another model call. Questions about missing patient facts are forbidden: everyone sees the same card.

**Anti-anchoring.** Each specialist writes an independent assessment before judging the group hypothesis, and declares whether the two match. If they do not match, the turn becomes a revision whatever action was chosen. *Observed:* the model noticed a discrepancy in its own reasoning and confirmed anyway.

**A discarded alternative is always named.** Every turn states another explanation considered and why it was rejected. It gives colleagues something concrete to disagree with.

**Forced consult.** A mandatory field asks whether an absent colleague's opinion would be useful; if yes, a mini-consult is added **after** the specialist's own action, not instead of it. *Observed:* when the consult replaced the action, a proposal with code ARANCIONE was lost and the case closed on VERDE.

**A consult to a specialist the system does not have goes to the general practitioner.** The request is genuine even if the role does not exist (haematologist, paediatrician, allergist). The chat shows who was asked for. The prompt lists the ten available colleagues. If the general practitioner itself asks for a missing role, the rest of its answer counts as a normal turn.

**A consult is answered to whoever asked.** The answer is addressed to the asker explicitly, so the router gives them the word back. *Observed:* the question got an answer and then the discussion closed without the asker ever replying.

**Who speaks next.** The colleague addressed by the last entry speaks first, even if not yet at the table (recruitment). Otherwise the turn goes round those who have not confirmed, in order of arrival. This reads as a conversation, not a fixed A-B-A-B rotation.

**Reaction turn.** If everyone has confirmed but the last entry explicitly names a seated colleague, that colleague gets one more turn. Only an explicit recipient counts: a recipient filled in automatically does not, otherwise a reaction turn followed almost every confirmation.

**Final verification round.** When all have confirmed, each specialist gets one last turn to say whether, having read the others, their assessment changed. A revision here reopens the discussion. It happens once and does not count towards the personal limit. *Why:* "everyone confirms, close" rewarded whoever confirmed first.

**Limits.**

</div>

| Limit | Value | Reason |
|---|---|---|
| Total turns | 12 | Emergency brake: the table always reaches the primary. |
| Turns per specialist | 3 | Two specialists kept exchanging near-identical hypotheses for 4-5 turns each. |
| Failed turns per specialist | 2 | An unreadable answer was retried forever: 9 failures in a row, no discussion. |
| Recruited colleagues | 1 | Prevents the table from growing as specialists call each other. |
| Characters per entry in the transcript | 1200 | One entry reached ~850 tokens and the prompt exceeded the provider limit. |

<div align="justify">

**Passing without confirming is recorded as such.** A specialist who runs out of turns is moved on without being asked again and without a fake confirmation. It is listed separately from those who confirmed, and the primary is told that their silence is not agreement. *Observed:* a specialist with two failed turns was counted among those who confirmed.

**Every urgency stated is kept.** Each entry records the code its author supported. The primary sees all of them and is warned when the table disagreed. *Why:* the hypothesis holds only the last version; an earlier, higher code was lost.

**Notes added to the prompt by code.** A question addressed to this specialist, the verification-round instruction, the second-opinion instruction and the paediatric note are inserted only when they apply. The context is detected in code; the prompt adapts.

**Paediatric note.** For a minor, specialists and primary are told that the retrieved guidelines are written for adults. No dedicated node. *Observed:* a 14-year-old's knee was being assessed as an adult's.

**Compact prompt.** The specialist prompt was rewritten from about 3,700 to about 2,000 fixed tokens with the same rules and fields, and asks for short entries. It is paid on every turn, and with a growing discussion it exceeded the per-minute token limit (two turns lost per case before, none after).

---

## 📋 10. Primary: summary report

**It assembles, it does not re-diagnose.** It turns the table's hypothesis into the report for the staff: code, hypothesis, exams, data to verify, operational guidance, reasoning.

**The table's code is the floor.** The primary may confirm it or raise it, never lower it. This is asked in the prompt and enforced in code. *Observed:* the same case gave different final codes from one run to the next.

**Confirming is the rule, raising the exception.** The code is raised only when a precise piece of data clearly requires it, not out of general caution.

**Written for the staff.** Where to send the patient, what to monitor, what to start, whom to call, when to reassess.

**"To verify" list.** Data named in the discussion that the patient never reported goes here, each with how to check it, instead of being repeated as fact. In real runs this is where the primary corrected most of the specialists' unsupported assumptions.

**Exams from the table when the primary lists none.**

**Fallbacks.** If the call fails, the report is the table's hypothesis, declared as such. If there is no hypothesis either, the code is ARANCIONE as a precaution: for a technical failure the lowest code is the worst choice.

---

## 🤖 11. Model layer

**One place chooses the model.** `src/llm/factory.py`, under version control. The `.env` file holds only keys and temperature.

**One client for every provider.** Groq, Ollama and Gemini expose an OpenAI-compatible endpoint, so the same client is built with different parameters. Agents do not know which provider they use.

**Low reasoning effort.** With the default, one specialist turn used about 4,000 tokens of hidden reasoning and answers were cut mid-JSON (9 failed turns in a row in one run). With "low" it uses about 600.

**One retry layer.** Retries inside the client are disabled; only `call_with_retry` retries, reading the wait suggested by the provider. *Observed:* the two layers added up to as many as 9 attempts and silent waits of 40 seconds or more.

**Waits up to 65 seconds, then give up.** A per-minute limit clears within a minute, so waiting succeeds; a daily limit asks for minutes or hours, so it fails at once.

**`max_tokens` computed per call.** With a per-minute limit, prompt plus reserved answer must fit, or the request is rejected whatever the real answer length. The value shrinks as the prompt grows, with a floor below which a JSON answer would be cut.

**Request timeout per provider.** 120 seconds for cloud providers, none for a local model, which can legitimately take minutes.

**The answer is rebuilt at each attempt.** An error can arrive in the middle of the stream; partial output is discarded.

**One JSON reader for every node.** It removes reasoning blocks, code fences and surrounding text, and raises the standard error when no object is found, so each node keeps its own fallback.

---

## 📚 12. Guideline retrieval (RAG)

**Retrieval always runs; using it is optional.** One search per turn, not a choice of the model. The specialist may ignore what it gets and must say what it used, citing document and page.

**Local embedding model.** No quota and no cost. The model needs the prefixes `query: ` and `passage: `; without them quality drops.

**One query per symptom.** Plus one for a question addressed to the specialist. *Observed:* a single query with every symptom let symptoms from other fields pollute the search (mixed-symptom cases went from 11/27 to 24/27).

**Two chunks from the specialty, one from the general documents.** With a plain filter the general triage manual took the first places and left specialists without their own guidelines.

**The text is cleaned before indexing.** Repeated headers and footers, page numbers and words split across lines are fixed by comparing the pages of each document.

**Useless chunks are discarded by rule.** Too short, glued words, tables of contents, bibliographies, conflict-of-interest statements, indicators, search strategies, author lists, glossaries. Each rule was checked by reading every chunk it discards. *Rejected:* a generic rule for "lists", which also discarded real clinical tables.

**Some pages are excluded by hand.** Pages that only list names, titles or signatures: because they mention a bit of everything, they matched almost any query. Each exclusion carries its reason. *Observed:* an ophthalmologist received a list of authors as a guideline, and the benchmark counted it as a hit. The benchmark now ignores such chunks.

**A missing index does not stop the table.** Retrieval returns nothing and the discussion goes on.

**The index is built outside the project folder, then copied.** File synchronisation corrupted the index while it was being written. After the copy, the index is opened repeatedly until it is readable, instead of waiting a fixed time.

---

## 🧪 13. Testing

**Three kinds of check.**

</div>

| Kind | Checks | Model | Quota |
|---|---|---|---|
| Unit | that every node behaves as designed | fake | none |
| Benchmark | retrieval quality on fixed cases | none | none |
| Live | clinical reasoning on real cases | real | yes |

<div align="justify">

**Real graph, fake model.** Unit tests run the production graph; the test decides what the model "answers". The fake model is plugged in at a single point that every agent goes through, so no test can reach the real model by omission.

**Tests found real defects.** The step limit of the graph (section 3) was found by a test, not in use.

**Random malformed answers.** Each node is fed randomly broken answers and must always return a state update.

---

## 🔬 14. Experimental findings

**Functional behaviour is stable.** On four fixed reference cases and on full conversations in the app, the flow always reached a complete report, including when the quota ran out mid-discussion.

**Clinical quality depends mostly on the model.** On the same prompt and code, one model produced a hypothesis built on details nobody had reported (a rash described as purpuric, signs taken as absent), while another stayed within the data and asked to verify them.

**Prompt rules reduce invention, they do not remove it.** The "not reported is not absent" rule lowered the number of such statements and moved some to the "to verify" list, but the weaker model still produced them. The primary's "to verify" list is the effective safeguard.

**Free-tier limits shape the experience.** The per-minute token limit is hit on almost every turn; the system waits and resumes, so a case takes about five minutes instead of one or two. A provider with a daily request limit allows about one and a half cases per day.

**Specialists ask for colleagues the system does not have** in almost every case. Redirecting to the general practitioner works and keeps the question.

---

## 🚧 15. Known limits and future work

- **Visit history.** Hypotheses accumulate among the previous conditions, one entry per visit. A separate table of visits, read by the agents, is the clean solution.
- **Guidelines are for adults.** Minors are handled with a note in the prompt, not with paediatric sources.
- **Ten specialties.** Fields without a dedicated specialist go to the general practitioner.
- **Database location.** The patient database is a local file inside the project folder (`data/`), kept out of version control. In real use it would live outside the project, with access control, backups and encryption.
- **Terminal output.** Messages are plain prints and include the patient card; they should become levelled logs with personal data only in a detailed mode.
- **Model dependence.** The safeguards limit the effect of an unreliable model; they cannot make its reasoning correct.

</div>
