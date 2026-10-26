# CLAUDE.md — masdar

## What This Repo Is

**Masdar** (مصدر, "source") is an archive of the recorded fatāwā of the scholars:
audio with an Arabic transcript and English and German translations, every line anchored
to the exact second in the recording, organised by topic and scholar. On top of it sits a
search tool that answers a question by pointing at the scholars' own words.

The product is one sentence: **show me where he said it.**

`masdar` is a working name — cheap to change while the site is not public, expensive
after. The repo is public and open source.

**Status: bulk upload is built and deployed** on one Hetzner server behind a provisional
DuckDNS name (`docs/BETRIEB.md`). Contributors upload up to 20 files at once
(`/{locale}/upload#k=<UPLOAD_KEY>`), every file is checked live against the archive and
against other pending uploads (SHA-256, then Chromaprint by bit error rate), the
contributor decides on candidates, and kept uploads wait in `python -m masdar inbox` for
an admin. Not built yet: the ASR draft pipeline, and registering an upload as an entry.

## The Constraint Everything Else Bends Around

A fatwa attributed to the wrong scholar, translated with a flipped nuance, or quoted out
of the situation it was given in, is a real harm — and a public one is socially
irreversible even when technically fixed in two minutes.

So the system:

- **never issues a ruling of its own**, never extrapolates past its sources
- **always formulates attributively** — "Shaykh X says in [video, 4:12] …", never the
  impersonal "the ruling is …". This single formatting rule does more work than any
  disclaimer.
- **can always show the Arabic original** next to any translation
- **says plainly when nothing is on file** rather than stretching thin evidence
- leaves disagreement between scholars standing instead of resolving it

These are enforced in the schema and the query path, **not in a prompt**. A prompt can be
talked around; a `WHERE` clause cannot. See "Integrity is structural" below.

## Repo Layout

```
intake/        Contributor-facing. ENGLISH — most contributors are English-speaking.
reference/     Master data: scholars.csv, topics.yml, register schema.
docs/          Design docs. Currently GERMAN (research output) — see "Language".
db/migrations/ SQL migrations. 0001 carries the fields that cannot be retrofitted.
backend/       Python 3.13 + FastAPI. Ingest pipeline, retrieval, API.
frontend/      Next.js App Router. The public library.
```

## Language

- `intake/` and `reference/` — **English.** Contributors read these.
- `CLAUDE.md`, `WORKFLOW.md`, `README.md`, code, comments, commits — **English.**
- `docs/` — currently German, because it is the output of a German-language design
  session. Translate when the repo goes public; not worth doing before.

## Stack

Decided from the research in `docs/ARCHITECTURE.md`, which records what was rejected and
why. Short version:

| Layer | Choice |
|---|---|
| Database | **One Postgres** (ParadeDB image: pgvector + BM25). No separate vector DB. |
| Hosting | One Hetzner VM, plain Docker Compose, Caddy. No PaaS. |
| Backend | Python 3.13, FastAPI. Worker is a second process of the same codebase. |
| Frontend | Next.js App Router, next-intl, Tailwind, Vidstack, TanStack Virtual |
| Boundary | Generated OpenAPI client. The frontend never sees Python. |
| ASR | Soniox (~$0.10/audio hour) |
| Translation drafts / metadata | Claude Haiku via the Batch API |
| Embeddings | BGE-M3 (MIT licence, strongest documented Arabic retrieval) |
| Reranking | Voyage rerank-3-lite |
| Synthesis | Claude Sonnet, `search_result` blocks with native citations |
| Queue | A Postgres table with `SELECT … FOR UPDATE SKIP LOCKED`. ~60 lines. |
| Media | Audio-first, Opus 24 kbit/s mono. Originals bit-identical in cold storage. |

**Do not add a service without a measured reason.** At the realistic corpus size
(~150k vectors) the break-even for a dedicated vector database is roughly fifty times
away. One developer plus a part-time helper has to operate whatever is built.

## Integrity Is Structural, Not Prompted

Five fields carry the weight. **All of them are in migration `0001` even though most of
their logic arrives later** — retrofitting them across published entries means breaking
live URLs and stored citations.

| Field | Level | Does what |
|---|---|---|
| `attribution` | entry | `confirmed` / `probably` / `not_sure`. `not_sure` is never published, however good the transcript. |
| `span_role` | line | `scholar_own` / `questioner` / `quoted_other` / `recited_text` / `unclear`. **Only `scholar_own` is quotable.** |
| `citable` | line | Whether this line's timestamp is human-confirmed. Uncitable lines stay in the index for context but yield no citation. |
| `content_class` | topic | `open` / `sources_only` / `excluded`. `excluded` removes a topic from the public site entirely, not just from the search index — see below. |
| `canonical_id` | entry | Near-duplicates are linked, never deleted. Only the canonical entry is indexed. |

`span_role` exists because of the worst failure mode there is: a scholar saying *"some
claim this is permitted — but that is wrong"*, and retrieval pulling the first half.
Speaker diarisation does not catch it; the scholar is speaking in both halves.

The query path reads a view that already filters on these. The application database user
has no `SELECT` on the base tables — so the filter cannot be forgotten.

### What `excluded` Means

Decided 2026-10-25. The three classes are three different public surfaces, not three
degrees of searchability:

| Class | Browse tree | Entry page and transcript | Retrieval | Synthesis |
|---|---|---|---|---|
| `open` | yes | yes | yes | yes |
| `sources_only` | yes | yes | yes | no |
| `excluded` | no | no — 404 | no | no |

Three reasons `excluded` goes all the way rather than stopping at the index:

1. **Otherwise it is `sources_only` under another name.** If an excluded topic were
   still browsable and citable, the only thing left separating the two classes would be
   synthesis — and that is exactly what `sources_only` already does.
2. **The harm channel is the citable deep link, not the search box.** The topics this
   class exists for — jarḥ wa taʿdīl, ḥizbiyya, fitan, takfīr, wulāt al-amr
   (`docs/RISKS.md`, `docs/ARCHITECTURE.md` "Themen-Sperre") — are dangerous precisely
   because *"Shaykh X said this about person Y, 4:12"* travels as a link. Hiding that
   link from search while serving it from the topic tree protects nothing. A browse
   tree is an invitation.
3. **It is the reversible direction.** Un-excluding a topic later publishes it.
   Un-publishing one later does not retract the URLs already in circulation, and that
   irreversibility is the constraint the whole project bends around.

Exclusion is inherited: a sub-topic of an excluded topic is excluded, and so is an
entry whose topic is excluded, whatever the entry's own fields say.

`segment_citable` in `0001_init.sql` already enforces this for retrieval. **The library
side is not built yet** — `GET /api/v1/topics`, `/entries/{id}` and `/transcript`
currently serve excluded topics like any other. That gate is Phase 1 work, and it
belongs in the repository view, not in the route handlers.

*Which* topic gets which class stays a human decision — see below.

## How Material Flows

There are two intake paths. **Links** go through the Google Form, unchanged from the
original design. **Bulk file uploads** — decided 2026-10-25, the common case in
practice: most contributors have phone-forwarded videos with no source URL at all, often
10–20 at once — go through a dedicated upload page instead, because only that path can
run SHA-256 and fingerprint checks *while the contributor is still there* and let them
listen to a candidate match and decide themselves. A form cannot talk to the backend
mid-submission. Access is an unlisted link, like the two Drive links, no login. **The
page asks only for the sender's name** (decided 2026-10-26): a batch holds files of many
scholars, so *which* scholar and *how sure* are settled when an admin registers the
upload as an entry, where `entry.attribution` starts at `not_sure` and gates publication
— nothing typed at upload time can pre-fill it (migration 0004). Open for the
registration step: the entry id is `<scholar-id>-<6 digits>`, so the admin has to know
the scholar at registration, before anyone transcribes. Detail
and the reasoning for reversing the original no-upload-form decision: `docs/ARCHITECTURE.md`
("Revidiert 2026-10-25").

1. Contributor submits a link (Form) or a batch of files (upload page)
2. Instant duplicate check: source URL / video ID, duration (links) or SHA-256 then
   Chromaprint fingerprint against the corpus, with the contributor deciding on a
   fingerprint candidate before anything is stored (files)
3. Fetch (`yt-dlp`) and normalise (`ffmpeg` → Opus); original to cold storage
4. Audio fingerprint (Chromaprint, one per recording, compared by **bit error rate** —
   a forwarded copy is always re-encoded and never byte-identical; see
   `docs/PIPELINE.md` layer 3). For a file upload this already happened, live, in step 2.
5. ASR → Arabic transcript with timestamps
6. Text dedup (SimHash over normalised Arabic) — catches the same content in a
   different recording, which audio fingerprinting never will
7. Metadata generation (batch, cheap model): title, question, topic, `hukm` as an enum,
   `generality`, Qur'an and hadith references
8. Draft translations DE + EN, line by line
9. **→ appears as a task for a contributor.** Steps 2–8 are automatic: minutes, under 1 cent.
10. Contributor corrects in a Google Doc — a table, one row per moment
11. Admin approves
12. Indexed, live

Steps 1–9 are cheap. **Step 10 is the whole project's cost curve.**

Details and the five dedup layers: `docs/PIPELINE.md`.

## Why There Is No Forced Alignment In Phase 1

Timestamps come out of the ASR run and survive human correction, because the contributor
rules forbid adding, deleting or reordering rows. The validator enforces it mechanically:
monotonic times, format, no time past the duration, row counts equal across languages.

Forced alignment is only needed for importing historical transcripts that have no
timestamps — Phase 3.

## Phases

| Phase | What | Cost |
|---|---|---|
| **0** | Measure before building. See "Week one" below. | ~0 € |
| **1** | The public library. Topic tree, scholar pages, player with synced trilingual transcript, second-accurate deep links. **No AI.** | < 20 €/mo |
| **2** | Retrieval and the answer tool. Gold set first, then measure. | ~160 €/mo at 10k questions |
| **3** | Hardening, historical imports, scale | ~490 €/mo at 50k questions |

**The library ships before the AI, deliberately.** Three independent reasons: contributors
see their work live in week 8 instead of month 9; the AI layer is the part a conservative
audience may reject outright (islamqa has a fatwa against seeking fatāwā from AI); and
Phase 1 needs no scholarly reviewer, because there is nothing to approve but transcripts.

An **MCP server should come before our own chatbot** — then the user's own model does the
answering and our contribution is verifiable sources. See `docs/SHAMELA-ANALYSE.md`.

## The Numbers That Decide Everything

- Corpus target: ~3,000 recordings ≈ 400 audio hours
- Processing the entire corpus: **~37 € ASR + ~9 € translation drafts, one-off**
- **Human review: ~4,000 person-hours ≈ two years at ten contributors × 4 h/week**
- ASR word error rate on old cassette material: **20–40 %**, not the 7 % from benchmarks

The bottleneck is not technical and never will be. Therefore: **deep before broad.**
800–1,500 carefully reviewed entries on the most-asked questions beat 30,000 half-checked
ones — and the second is also the one that produces a public attribution error.

Arabic first everywhere; translate by demand, not by stock.

## Week One — Measure Before Building

Documented in `docs/ARCHITECTURE.md`. The one that matters most: **three contributors,
30 minutes of real audio each, full pass with a stopwatch.** That number sets the corpus
target. Everything planned before it is planned against a guess.

## Decisions Only Humans Make

Never decide these in a session:

- Which scholars are included (`reference/scholars.csv` is a draft)
- `content_class` — which topic gets which class. What the classes *mean* is settled above; which topic falls into which is not, and `reference/topics.yml` does not carry the field yet.
- Whether an entry is `held_back`
- Approving any translation
- Whether living scholars are included, and on what condition

## Version Control

Solo phase: commit directly to `main`, full test suite green before every commit. This
is a deliberate, temporary relaxation of the usual feat-branch rule — see `WORKFLOW.md`
for when and how to switch back.

**Commit messages are compact one-liners. No body, no bullet lists, and no
`Co-Authored-By` trailer — ever, including AI-driven commits.** This overrides any
default attribution behaviour a tool or harness suggests.

## Working In This Repo

- Read `WORKFLOW.md` before the first commit of a session. TDD is non-negotiable for the
  gates listed there.
- Getting oriented: `README.md` → this file → `docs/ARCHITECTURE.md` → `docs/PIPELINE.md`
- `docs/RISKS.md` lists what realistically kills this project. Re-read it before
  proposing anything that increases corpus size or operational surface.
- Secrets never enter the repo. `.env` is gitignored; `.env.example` documents the keys.
- When a decision is made in a session, **write it down here or in `docs/`.** A decision
  that exists only in a conversation does not survive the session.
