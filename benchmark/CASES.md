<div align="center">

# 🩺 V.I.T.A. model benchmark: the cases

</div>

<div align="justify">

The 15 patients of the benchmark, as the models receive them, each with what is expected. This file is written by `python -m benchmark.cases_doc` from `cases.py`: it is not edited by hand. The rules used to write the cases and the measures are in `PROTOCOL.md`.

Every expected code comes from one row of the regional triage manual (`data/guidelines/generale_fvg_manuale_triage_adulto_2018.pdf`); the page is the one printed on the manual. The patient texts are in Italian, the language of the app. The cases marked ★ are the core set, one per code: their reports are the ones read by hand (`python -m benchmark.review`).

</div>

## Case 01 ★: Facial droop, weak arm and speech trouble for one hour

**Patient.** uomo, 68 anni. Previous conditions: ipertensione. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| bocca storta verso destra | forte | 1 ora | comparsa all'improvviso, ora di esordio certa; non assume anticoagulanti | - |
| mancanza di forza al braccio destro | forte | 1 ora | - | - |
| difficoltà a parlare | forte | 1 ora | parole biascicate | - |

| Expected | |
|---|---|
| Code | **ROSSO** (code 1 of the manual) |
| Specialty | **Neurologia** |
| Manual sheet | Disturbi neurologici |
| Manual row | Alterazione di mimica facciale / motilità arti / disturbi del linguaggio entro le 5 ore |
| Manual page | 36 |

## Case 02: Asthmatic who cannot speak, blue lips

**Patient.** donna, 45 anni. Previous conditions: asma. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| difficoltà a respirare | insopportabile | 40 minuti | non riesce a parlare per la fatica a respirare, labbra bluastre | - |

| Expected | |
|---|---|
| Code | **ROSSO** (code 1 of the manual) |
| Specialty | **Pneumologia** (assigned by hand: the sheet names none) |
| Manual sheet | Compromissione respiratoria |
| Manual row | Severa |
| Manual page | 15 |

## Case 03: Deep knife wound to the thigh, heavy bleeding

**Patient.** uomo, 30 anni. Previous conditions: none. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| ferita profonda alla coscia sinistra | forte | 20 minuti | ferita penetrante, sanguinamento abbondante | colpo di coltello |

| Expected | |
|---|---|
| Code | **ROSSO** (code 1 of the manual) |
| Specialty | **Ortopedia** (assigned by hand: the sheet names none) |
| Manual sheet | Trauma: arti |
| Manual row | Ferita penetrante inguine / coscia |
| Manual page | 25 |

## Case 04 ★: Oppressive chest pain radiating to the left arm, with sweating

**Patient.** uomo, 63 anni. Previous conditions: ipertensione. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| dolore al petto | forte | 30 minuti | oppressivo, irradiato al braccio sinistro | - |
| sudorazione | moderata | 20 minuti | - | - |

| Expected | |
|---|---|
| Code | **ARANCIONE** (code 2 of the manual) |
| Specialty | **Cardiologia** (assigned by hand: the sheet names none) |
| Manual sheet | Dolore toracico |
| Manual row | Dolore toracico in atto |
| Manual page | 28 |

## Case 05: One episode of dark blood in the vomit, now only weak

**Patient.** uomo, 55 anni. Previous conditions: none. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| vomito con sangue scuro | moderata | 2 ore | un solo episodio, sangue scuro tipo fondo di caffè | - |
| debolezza | lieve | 2 ore | - | - |

| Expected | |
|---|---|
| Code | **ARANCIONE** (code 2 of the manual) |
| Specialty | **Gastroenterologia** (assigned by hand: the sheet names none) |
| Manual sheet | Emorragie non traumatiche |
| Manual row | Ematemesi / vomito caffeano |
| Manual page | 41 |

## Case 06: Sudden painless loss of sight in one eye

**Patient.** donna, 70 anni. Previous conditions: none. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| perdita della vista dall'occhio sinistro | forte | 1 ora | improvvisa, completa, senza dolore | - |

| Expected | |
|---|---|
| Code | **ARANCIONE** (code 2 of the manual) |
| Specialty | **Oftalmologia** |
| Manual sheet | Problema specifico - Oculistico |
| Manual row | Cecità monoculare improvvisa |
| Manual page | 49 |

## Case 07 ★: Unable to pass urine for eight hours

**Patient.** uomo, 72 anni. Previous conditions: ipertrofia prostatica. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| impossibilità a urinare | moderata | 8 ore | tensione moderata al basso ventre | - |

| Expected | |
|---|---|
| Code | **AZZURRO** (code 3 of the manual) |
| Specialty | **Urologia** |
| Manual sheet | Problema specifico - Urologico |
| Manual row | Ritenzione acuta d'urina |
| Manual page | 53 |

## Case 08: Swollen painful wrist after a fall at home, no deformity

**Patient.** donna, 50 anni. Previous conditions: none. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| dolore al polso destro | forte | 3 ore | polso gonfio, non riesce a muoverlo, nessuna deformità visibile | caduta in casa sulla mano |

| Expected | |
|---|---|
| Code | **AZZURRO** (code 3 of the manual) |
| Specialty | **Ortopedia** (assigned by hand: the sheet names none) |
| Manual sheet | Trauma: arti |
| Manual row | Sospetta frattura |
| Manual page | 25 |

## Case 09: Usual migraine attack that does not respond to the usual drug

**Patient.** donna, 38 anni. Previous conditions: emicrania. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| mal di testa | forte | 6 ore | uguale alle crisi di emicrania abituali, non passa con il farmaco abituale | - |

| Expected | |
|---|---|
| Code | **AZZURRO** (code 3 of the manual) |
| Specialty | **Neurologia** |
| Manual sheet | Cefalea |
| Manual row | Crisi di cefalea nota o senza criteri di priorità |
| Manual page | 35 |

## Case 10 ★: Nausea, vomiting and diarrhoea for one day, no fever

**Patient.** uomo, 28 anni. Previous conditions: none. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| nausea e vomito | moderata | 1 giorno | temperatura 36,8 °C, nessun dolore addominale importante | - |
| diarrea | moderata | 1 giorno | senza sangue | - |

| Expected | |
|---|---|
| Code | **VERDE** (code 4 of the manual) |
| Specialty | **Gastroenterologia** |
| Manual sheet | Problema specifico - Chirurgico / Gastrointestinale |
| Manual row | Nausea / vomito / diarrea |
| Manual page | 54 |

## Case 11: Feeling of a fish bone in the throat, swallows and breathes normally

**Patient.** donna, 40 anni. Previous conditions: none. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| sensazione di lisca di pesce in gola | lieve | 2 ore | deglutisce e respira normalmente | dopo aver mangiato pesce |

| Expected | |
|---|---|
| Code | **VERDE** (code 4 of the manual) |
| Specialty | **Otorinolaringoiatria** |
| Manual sheet | Problema specifico - Otoiatrico |
| Manual row | Corpo estraneo orecchio / naso / gola |
| Manual page | 50 |

## Case 12: Low back pain for two days after an effort

**Patient.** uomo, 45 anni. Previous conditions: none. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| mal di schiena lombare | moderata | 2 giorni | non irradiato, nessun disturbo urinario | dopo uno sforzo, peggiora con i movimenti |

| Expected | |
|---|---|
| Code | **VERDE** (code 4 of the manual) |
| Specialty | **Ortopedia** |
| Manual sheet | Problema specifico - Muscolo-scheletrico |
| Manual row | Lombalgia |
| Manual page | 55 |

## Case 13 ★: Ear pain for two days, temperature 37.5

**Patient.** uomo, 58 anni. Previous conditions: none. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| dolore all'orecchio destro | moderata | 2 giorni | - | - |
| febbre | lieve | 1 giorno | temperatura 37,5 °C | - |

| Expected | |
|---|---|
| Code | **BIANCO** (code 5 of the manual) |
| Specialty | **Otorinolaringoiatria** |
| Manual sheet | Problema specifico - Otoiatrico |
| Manual row | Otalgia / otorragia (with: Alterazione della temperatura < 38 °C, p. 29) |
| Manual page | 50 |

## Case 14: Ingrown toenail, red and sore for a week

**Patient.** donna, 25 anni. Previous conditions: none. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| unghia incarnita all'alluce destro | moderata | 1 settimana | arrossata e dolente, temperatura 36,6 °C | - |

| Expected | |
|---|---|
| Code | **BIANCO** (code 5 of the manual) |
| Specialty | **Dermatologia** |
| Manual sheet | Problema specifico - Cute e tessuti molli |
| Manual row | Lesione cutanea non traumatica / tumefazione |
| Manual page | 48 |

## Case 15: Cough and blocked nose for four days, no fever

**Patient.** uomo, 35 anni. Previous conditions: none. Allergies: none.

| Symptom | Intensity | Duration | Characteristics | Trigger |
|---|---|---|---|---|
| tosse | lieve | 4 giorni | - | - |
| naso chiuso | lieve | 4 giorni | temperatura 36,7 °C, respira bene | - |

| Expected | |
|---|---|
| Code | **BIANCO** (code 5 of the manual) |
| Specialty | **Medicina** (assigned by hand: the sheet names none) |
| Manual sheet | Problema specifico - Medicina generale |
| Manual row | Tosse, rinite ed altri sintomi aspecifici delle prime vie aeree |
| Manual page | 46 |
