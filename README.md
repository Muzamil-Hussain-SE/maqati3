<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/assets/banner-dark.png">
    <img alt="maqati3 (مقاطع): the words of the scholars, linked to the second they were said" src=".github/assets/banner-light.png" width="100%">
  </picture>
</p>

<p align="center">
  <a href="https://github.com/PSchmitz-Valckenberg/maqati3/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/PSchmitz-Valckenberg/maqati3/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License: AGPL-3.0" src="https://img.shields.io/badge/license-AGPL--3.0-047857"></a>
  <img alt="Status: pre-alpha" src="https://img.shields.io/badge/status-pre--alpha-d97706">
  <img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="Next.js 16" src="https://img.shields.io/badge/next.js-16-000000?logo=nextdotjs&logoColor=white">
  <img alt="PostgreSQL 17" src="https://img.shields.io/badge/postgresql-17-4169E1?logo=postgresql&logoColor=white">
  <a href="https://github.com/PSchmitz-Valckenberg/maqati3/issues?q=is%3Aopen+label%3A%22good+first+issue%22"><img alt="Good first issues" src="https://img.shields.io/github/issues/PSchmitz-Valckenberg/maqati3/good%20first%20issue?label=good%20first%20issues&color=7057ff"></a>
</p>

<p align="center">
  <a href="#how-it-works">How it works</a> ·
  <a href="#status">Status</a> ·
  <a href="#run-it-locally">Run it locally</a> ·
  <a href="CONTRIBUTING.md">Contributing</a> ·
  <a href="https://github.com/PSchmitz-Valckenberg/maqati3/milestones">Roadmap</a>
</p>

---

**maqati3** is an open-source archive of the recorded fatāwā of the scholars. Each
recording gets an Arabic transcript and English and German translations, and every line
is anchored to the exact second it was said. On top of that comes a search tool that
answers a question by pointing at the scholars' own words.

The whole product fits in one sentence:

> ### *Show me where he said it.*

## Why

Fatāwā travel today as forwarded clips: cut from a longer answer, re-encoded a dozen
times, without the question that was asked, and often attributed to the wrong person.
Anyone who wants to check what was actually said has to search through hours of audio.

maqati3 does that work once, carefully and in public. It collects recordings, finds
duplicates, gets them transcribed and translated, and lets people review every line
before anything is published. The result is a citation you can follow back to its
source: **Shaykh X says in [recording, 4:12] …**, with the Arabic original one click away.

## What it will never do

The worst mistake this project can make is to put words in a scholar's mouth. So the
system:

- **never issues a ruling of its own**, and never goes beyond what its sources say;
- **always attributes**: *"Shaykh X says in [recording, 4:12] …"*, never *"the ruling is …"*;
- **always shows the Arabic original** next to any translation;
- **says plainly when nothing is on file** instead of stretching thin evidence;
- **leaves disagreement between scholars standing** instead of resolving it.

These rules live in the database schema and the query path, **not in a prompt**. A
prompt can be talked around; a `WHERE` clause cannot. An entry whose attribution is
*not sure* is never published. A line where the scholar quotes someone he disagrees with
is never quoted as his own view. Sensitive topics can be removed from the public site
entirely. The details are in [`CLAUDE.md`](CLAUDE.md), under *Integrity is structural*.

## How it works

```mermaid
flowchart LR
    U["Contributors upload<br/>up to 20 files at once"] --> C{"Already in<br/>the archive?"}
    C -- "exact copy<br/>(SHA-256)" --> R["Refused"]
    C -- "similar recording<br/>(Chromaprint)" --> L["The contributor listens<br/>and decides"]
    C -- "new" --> A
    L -- "different" --> A["Admin dashboard<br/>(Google sign-in)"]
    A -- "register with<br/>the scholar" --> E["Draft entry<br/>attribution: not sure"]
    E -.-> T["Arabic transcript<br/>with timestamps"]
    T -.-> D["Draft translations<br/>English · German"]
    D -.-> V["Line-by-line review<br/>per language"]
    V -.-> P["Public library<br/>every line at its second"]

    classDef built fill:#d1fae5,stroke:#047857,color:#064e3b
    classDef planned fill:#f5f5f4,stroke:#a8a29e,color:#57534e,stroke-dasharray:4 3
    class U,C,R,L,A,E built
    class T,D,V,P planned
```

<sub>Solid: built. Dashed: planned.</sub>

1. **Upload.** Contributors open an unlisted link and send up to twenty phone videos or
   audio files at once. They are only asked for their name.
2. **Live duplicate check.** While the contributor is still on the page, every file is
   compared with the archive and with other pending uploads. An exact copy is refused.
   For a forwarded copy, which is re-encoded and never byte-identical, the audio
   fingerprint is compared by bit error rate. The contributor then listens to both and
   decides.
3. **Admins decide.** Kept uploads wait in a dashboard. An admin watches each one and,
   if it is worth the review time, registers it under a scholar. This creates a draft
   entry whose attribution starts at *not sure*.
4. **Transcribe, translate, review** *(being built)*. The admin triggers the
   transcription and the draft translations. Reviewers then correct them in a table with
   one row per moment, the audio synced to the row, and one language at a time.
5. **Publish** *(Phase 1)*. Approved entries appear in the public library, with deep
   links that land on the exact second.

The deduplication layers are described in [`docs/PIPELINE.md`](docs/PIPELINE.md).

## Screenshots

<table>
  <tr>
    <td width="28%" valign="top"><img src=".github/assets/upload-en.png" alt="The upload page on a phone: one new file, one exact copy that was refused, and one similar recording waiting for the contributor's decision"></td>
    <td width="28%" valign="top"><img src=".github/assets/upload-ar.png" alt="The same upload page in Arabic, laid out right to left"></td>
    <td width="44%" valign="top"><img src=".github/assets/dashboard.png" alt="The admin dashboard: uploads waiting with a player, one flagged as kept despite a match, and two registered entries"></td>
  </tr>
  <tr>
    <td align="center"><sub>Upload: new, exact copy, similar</sub></td>
    <td align="center"><sub>Arabic first, right to left</sub></td>
    <td align="center"><sub>Admin dashboard</sub></td>
  </tr>
</table>

<sub>Synthetic test recordings, a demo scholar and made-up names.</sub>

## Status

Pre-alpha. Nothing is public yet; the upload runs on a provisional server.

| | Part | State |
|---|---|---|
| ✅ | Bulk upload with live duplicate check | built and running |
| ✅ | Admin dashboard: sign in, play, register, discard | built; goes live with the final domain |
| 🔨 | Transcription and draft translations on demand | [next](https://github.com/PSchmitz-Valckenberg/maqati3/milestones) |
| 🔨 | Review editor with a per-language claim and approval | [next](https://github.com/PSchmitz-Valckenberg/maqati3/milestones) |
| 🗓️ | **Phase 1:** the public library: topics, scholars, synced transcript, deep links. No AI. | planned |
| 🗓️ | **Phase 2:** search, an MCP server, and only then an answer tool | planned |

**The library ships before the AI, on purpose.** It is useful on its own, it needs no
scholarly reviewer because there is nothing to approve but transcripts, and it does not
depend on the AI layer, which part of this audience may reject outright.

**The bottleneck is people, not technology.** Transcribing and translating the whole
target corpus costs well under €100. Reviewing it takes thousands of hours. So the plan
is *deep before broad*: a thousand carefully reviewed entries on the questions people
actually ask beat thirty thousand half-checked ones.

## Run it locally

You need [uv](https://docs.astral.sh/uv/), Node 22, Docker, and for the media features
`fpcalc` and `ffmpeg` (`brew install chromaprint ffmpeg`, or
`apt install libchromaprint-tools ffmpeg`).

```bash
# 1. The database (ParadeDB image: Postgres 17 with pgvector). It starts empty.
docker compose up -d --wait db          # 5432 taken? DB_PORT=55432 ..., and use that port below

# 2. The backend
cd backend
export DATABASE_URL=postgresql://maqati3:devonly@127.0.0.1:5432/maqati3
uv sync
uv run python -m maqati3 migrate        # creates the schema
uv run python -m maqati3 seed           # scholars and topics from reference/
UPLOAD_KEY=dev STAGING_DIR=.staging uv run python -m maqati3 serve --port 8000

# 3. The frontend, in a second terminal
cd frontend
npm ci
npm run dev
```

Then open <http://localhost:3000/en/upload#k=dev>. The `#k=` part is the upload key;
without it the page refuses to send. In development, Next's proxy caps uploads at 10 MB;
the server has no such cap.

**Tests.** `cd backend && uv run pytest` runs everything. The database and end-to-end
tests run when `DATABASE_URL` is set and `fpcalc` and `ffmpeg` are installed, and skip
otherwise; CI runs all of them. The frontend has `npm test`, `npm run lint` and
`npx tsc --noEmit`.

Setting up a real server, and the admin sign-in with Google, is described in
[`docs/BETRIEB.md`](docs/BETRIEB.md).

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Database | One PostgreSQL ([ParadeDB](https://www.paradedb.com/): pgvector + BM25) | No separate vector database: one would pay off only at about fifty times the realistic corpus |
| Backend | Python 3.13, FastAPI | One codebase for the API and the worker |
| Frontend | Next.js (App Router), next-intl, Tailwind | Arabic, English, German; right to left by default for Arabic |
| Dedup | SHA-256, Chromaprint by bit error rate, SimHash | Forwarded copies are never byte-identical |
| Transcription | Soniox | Arabic with timestamps at ~$0.10 per audio hour; a bake-off on real material is still due |
| Translation drafts | Claude Haiku, Batch API | Drafts only; a person approves every line |
| Hosting | One Hetzner VM, Docker Compose, Caddy | One developer has to operate it; nothing more |

The reasoning, including everything that was rejected, is in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repository layout

```
backend/        Python 3.13 + FastAPI: upload, dedup, admin API, migrations runner, CLI
frontend/       Next.js: the upload page, the admin dashboard, later the public library
db/migrations/  SQL migrations, forward only. 0001 carries the integrity fields.
reference/      Master data: scholars.csv, topics.yml
deploy/         Docker Compose and Caddy for the server
docs/           Design documents (German for now, translation welcome)
intake/         Guides for contributors and admins
```

## Contributing

Contributions are welcome: code, documentation, testing on phones and in Arabic,
translating the design documents. Start with [`CONTRIBUTING.md`](CONTRIBUTING.md), then
pick an issue labelled
[`good first issue`](https://github.com/PSchmitz-Valckenberg/maqati3/issues?q=is%3Aopen+label%3A%22good+first+issue%22)
or [`help wanted`](https://github.com/PSchmitz-Valckenberg/maqati3/issues?q=is%3Aopen+label%3A%22help+wanted%22).
The roadmap is in the [milestones](https://github.com/PSchmitz-Valckenberg/maqati3/milestones).

This repository is not a place to debate rulings, scholars or groups; see the
[code of conduct](CODE_OF_CONDUCT.md). Security problems go to the
[private report](SECURITY.md), never to a public issue.

## The name

*maqāṭiʿ* (مقاطع) means *clips* or *excerpts*: the short recordings this archive is made
of. The **3** is the Arabic chat alphabet's way of writing the letter ع (*ʿayn*). It is
a working name for now.

## License

The code and the reference data in this repository are licensed under the
[GNU Affero General Public License v3.0](LICENSE). Anyone may use, change and run them.
If you run a modified version as a public service, you must publish your changes.

The recordings, transcripts and translations are not part of this repository, and this
license does not cover them.
