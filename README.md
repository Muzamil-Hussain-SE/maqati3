# Fatwa Archive — project status

A central multilingual platform (Arabic / English / German) for the video and audio fatāwā
of the scholars, with transcripts, translations, and a search tool that answers questions by
pointing at the scholars' own words — linked to the exact second in the recording.

**Status: bulk upload built, not yet deployed.** See `CLAUDE.md` for the current state,
architecture, and the constraints the whole system is built around.

---

## What's here

```
intake/              Everything about contribution -> goes into Drive as "1 START HERE"
  START-HERE.md      The one page contributors read. Two links, nothing else.
  FORM-SETUP.md      Exact field list for the Google Form
  DOC-TEMPLATE.md    What the per-entry document looks like
  ADMIN-GUIDE.md     Registering, reviewing, approving, setting priority
  DRIVE-SETUP.md     Checklist to build the Drive

reference/           Master data. Read directly by the backend later.
  scholars.csv       18 scholars / bodies with permanent ids  (DRAFT — check it)
  topics.yml         8 main topics, ~60 sub-topics
  REGISTER.md        Columns and status model of the register sheet

ARCHITECTURE.md      Stack, data model, pipelines, roadmap (German, internal)
PIPELINE.md          Ingest flow and the five deduplication layers (German, internal)
COSTS.md             Cost model for three scales (German, internal)
RISKS.md             What realistically kills this project (German, internal)
docs/raw/            Raw research output, 16 agents
```

---

## The design in one paragraph

Contributors never see the Drive. They get **two links**: a Google Form to submit material,
and a filtered view of the register showing only their own tasks. Transcription and
translation happen in a Google Doc — a table with one row per moment in the recording,
columns for Arabic, English and German. There is nothing to download, nothing to upload,
nothing to name. The admin registers submissions, creates the entry Docs with machine
drafts already in them, assigns work, and reviews everything before it becomes public.

---

## Four decisions everything else rests on

**1. The register sheet is the only source of truth.**
Status lives in a table, never in a folder name or a file location. Files are never moved.
The backend later reads one sheet instead of guessing at folder states.

**2. Status is per language, not per entry.**
The material arrives unevenly — some already has an Arabic transcript, some is audio only.
Three independent status columns represent that; a linear pipeline could not.

**3. One row per moment, in a table.**
Row 7 of the Arabic column is row 7 of the English column, with the same timestamp. This is
what lets the site say "he said this at 0:23" and jump there. A table makes the
correspondence physical, so non-technical contributors can't quietly break it.

**4. Attribution is its own field and it blocks publication.**
`Confirmed` / `Probably` / `Not sure`. An entry marked `Not sure` is never published, no
matter how good the transcript is. A fatwa attributed to the wrong scholar is the worst
mistake this project can make, so the block is structural rather than a matter of care in
the individual case.

---

## Order of work

1. **Arabic first, everywhere.** An approved Arabic transcript already makes an entry
   searchable and quotable. Cheapest step, largest effect.
2. **Translate on demand, not by stock.** Once the site runs, usage shows which topics are
   actually asked about.

~3,000 recordings at 8 minutes is ~400 hours of audio; with machine drafts that is roughly
4,000 person-hours of correction and translation — about two years for ten people at four
hours a week. Full coverage before usefulness is not a plan.

---

## Open / next

- [ ] Check and extend `scholars.csv` — the selection and the death dates are a draft
- [ ] Review the topic list, especially `contemporary`
- [ ] Build the Drive and the Form (see `intake/DRIVE-SETUP.md`)
- [ ] Survey existing material: how much already has an Arabic transcript?
- [ ] Run the first 20 entries by hand before onboarding all ten contributors
- [ ] Apps Script in the sheet: duplicate pre-check on form submit (no backend needed)
- [ ] Week-1 throughput measurement — decides the realistic corpus size
- [ ] Permission letters to binothaimeen.net, miraath.net, al-Fawzan office (months of lead time)
