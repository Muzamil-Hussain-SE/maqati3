# Admin guide

> **Partly superseded (2026-10-27).** Registering, assigning work and approving now happen
> in the admin dashboard, not in the register sheet; see `CLAUDE.md`, "The Admin Workflow",
> and `docs/BETRIEB.md`. The checks in section 3 (what to look for when reviewing a
> transcript or translation) still apply unchanged.

You are the last step before anything becomes public. Everything you approve can later be
quoted by a search tool and presented to someone as the words of a scholar. So approval is
not a formality.

Contributors never touch the library or the folder structure. You do.

---

## 1. Register a submission

A form response arrives. For each one:

1. **Decide attribution.** This comes first, because it decides everything else.

   | Value | When | Consequence |
   |---|---|---|
   | `Confirmed` | Official site or official channel of the scholar, or a well-known recording | can be published |
   | `Probably` | Serious re-upload, voice recognisable, no primary source | can be published, labelled as such on the site |
   | `Not sure` | Anything else | **never published**, stays in the archive |

   When in doubt, `Not sure`. One entry fewer harms nobody.

2. **Assign an ID**: `<scholar-id>-<6 digits>`, e.g. `uthaymin-000421`. Never changes, even
   if the title or topic turns out to be wrong later — those get corrected in the sheet.
3. **Create the entry folder** under `3 LIBRARY/<scholar-id>/<id>/`, move the audio in.
4. **Create the entry Doc** from the template, paste in the machine transcript, link it in
   the `doc_link` column.
5. **Set priority** (1–5). See below — this is your main steering tool.

## 2. Assign work

Put a contributor's name in `assignee_ar` / `assignee_en` / `assignee_de` and set the
status to `Draft ready`. Their "My tasks" view is just a filter on their own name, so they
see it immediately.

**Rule: never assign a translation before `status_ar` is `Approved`.** Otherwise someone
translates a version that is still changing, and does the work twice.

## 3. Review

Review per language, in the Doc, using comments.

**Arabic transcript:**
- Spot-check three rows against the audio — beginning, middle, one at random. Does the
  timestamp match what is said?
- Go through every `[?]` and `[...]`
- Were Qur'an verses put in `﴿ ﴾`?
- **Was it smoothed?** Suspiciously clean sentences, no repetitions, no forms of address.
  If so, send it back — smoothing breaks the link between text and audio.

**Translation:**
- Row count identical to the Arabic? If not, send back without reading further.
- Check every `[?]`
- **Look specifically at the ruling words:** harām / makrūh / mustahabb / wājib / mubāh.
  This is where the damaging errors are, and they are quiet.
- Did conditions survive as conditions?
- Was anything explained that the scholar did not explain?

Result: `Approved`, or `Needs fixes` with a **concrete** note ("rows 34 and 51: makrūh
translated as forbidden"), never "please look again".

## 4. Publish

`visibility` = `Public` is only allowed when `attribution` is not `Not sure` **and**
`status_ar` is `Approved`.

Translations that are not yet approved simply don't show. The entry is then Arabic-only —
that is fine and will be the normal case for a long time.

`Held back` exists on purpose. Some recordings are genuine and correctly transcribed and
still do not belong in a public archive: they are situation-bound, they concern named
people, or they are open to misunderstanding without the context of the question. Spotting
that is your job, not the software's. Write the reason in `notes`.

---

## Setting priority — your most important job

There is more material than there are people. Working through it in the order it arrives is
the surest way to spend two years on things nobody asks for.

1. **Arabic first, everywhere.** An approved Arabic transcript already makes an entry
   searchable and quotable. Cheapest step, largest effect.
2. **Translate on demand, not by stock.** Once the site is running, usage shows which
   topics are actually being asked about. Those get translated.
3. **Basics before edge cases.** Purification, prayer, foundations of ʿaqīda, questions
   about living as a Muslim in the West. Not the rare detail question.

Rough arithmetic for why: ~3,000 recordings at 8 minutes is about 400 hours of audio. With
a machine draft, Arabic correction runs 2–3 hours per audio hour, each translation 4–5.
That is roughly 4,000 person-hours — about two years for ten people at four hours a week.
Full coverage before usefulness is not a plan.

---

## Reading the quality of a contributor

- Someone who **never** writes `[?]` is not precise, they are inattentive. Marks are a good
  sign, not a bad one.
- A translation that reads more smoothly than the original is usually too free.
- When row counts don't match, **don't fix it yourself — send it back.** Otherwise it
  becomes a habit and you end up doing ten people's work.

Give feedback even when everything is right. Ten volunteers who need to keep going for two
years need that more than any technical solution.
