<div align="center">

# 📚 V.I.T.A. — Clinical guidelines and index

</div>

<div align="justify">

This folder holds the clinical guidelines the specialists consult during the round table, the search index built from them, and the patient database. How retrieval works is described in `docs/ARCHITECTURE.md`; why it works that way, in section 12 of `docs/DESIGN.md`.

</div>

| Folder | Content |
|---|---|
| `guidelines/` | The source documents: 23 PDF files, in Italian. |
| `chroma_db/` | The search index built from them (2,443 chunks). Generated: never edited by hand. |
| `medical_database.db` | The patient records (SQLite). Created at the first start; **not under version control**, because it holds personal and health data. |

---

## 🏷️ File names decide who reads a document

<div align="justify">

The part of the file name before the first underscore is the **specialty**. A specialist receives chunks from the documents of its own specialty, plus one chunk from the `generale` documents, which every specialist shares. A document with the wrong prefix is silently given to the wrong specialist, or to none.

</div>

| Prefix | Specialist |
|---|---|
| `cardio_` | Cardiology |
| `neuro_` | Neurology |
| `dermatologia_` | Dermatology |
| `ortopedia_` | Orthopaedics |
| `gastro_` | Gastroenterology |
| `pneumo_` | Pulmonology |
| `ent_` | Otorhinolaryngology |
| `oftalmologia_` | Ophthalmology |
| `urologia_` | Urology |
| `generale_` | All specialists, and the only source of the general practitioner |

<div align="justify">

The mapping lives in `ROLE_SPECIALTY` in `src/rag/retriever.py`.

</div>

---

## 🚫 What is left out

<div align="justify">

**Pages excluded by hand.** Some pages contain only authors, signatures, acknowledgements or lists of titles. Because they mention a bit of everything, they matched almost any search. They are listed, each with its reason, in `EXCLUDED_PAGES` in `src/rag/build_index.py` (currently 20 pages in 10 documents).

**Chunks discarded by rule.** Tables of contents, bibliographies, glossaries, indicators, search strategies, conflict-of-interest statements and fragments that are too short or have glued words are dropped while building the index.

**One document not included.** An article on anaphylaxis in the emergency department was considered and left out, because it carries a notice forbidding redistribution.

</div>

---

## 🔧 Adding, removing or replacing a document

<div align="justify">

1. Put the PDF in `guidelines/`, named `<prefix>_<source>_<topic>.pdf` with one of the prefixes above.
2. Rebuild the index (a few minutes, no API quota: the embedding model runs locally):

</div>

```bash
python -m src.rag.build_index
```

<div align="justify">

3. Read the summary it prints: pages and chunks per document, and how many chunks each rule discarded. A document that yields very few chunks probably has text that could not be extracted.
4. Run the benchmark and compare it with the previous result:

</div>

```bash
python -m tests.run benchmarks
```

<div align="justify">

5. If the new document brings pages of authors or signatures into the results, add them to `EXCLUDED_PAGES` and rebuild.

The index is written in a temporary folder and then copied here, replacing the old one: the folder inside `chroma_db/` changes name at every rebuild.

</div>
