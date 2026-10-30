#!/usr/bin/env bash
# One-off: opens the roadmap as GitHub issues. Run after scripts/github-setup.sh, which
# creates the labels and milestones these issues use:   bash scripts/github-issues.sh
# Safe to run again: an issue whose title already exists is skipped.
set -euo pipefail

REPO="PSchmitz-Valckenberg/maqati3"
EXISTING="$(gh issue list -R "$REPO" --state all --limit 500 --json title --jq '.[].title')"

# issue <title> <labels, comma separated> <milestone or ""> ; the body is read from stdin
issue() {
  local title="$1" labels="$2" milestone="$3" body
  body="$(cat)"
  if grep -qxF "$title" <<<"$EXISTING"; then echo "exists   $title"; return; fi
  local args=(-R "$REPO" --title "$title" --body "$body" --label "$labels")
  if [ -n "$milestone" ]; then args+=(--milestone "$milestone"); fi
  gh issue create "${args[@]}" >/dev/null && echo "opened   $title"
}

M1="Admin dashboard live"
M2="Transcription and drafts"
M3="Review in the dashboard"
M4="Phase 1: public library"
M5="Phase 2: search"

# ============================================================== Admin dashboard live

issue "Buy the final domain and point it at the server" "maintainer,area: ops" "$M1" <<'EOF'
Google sign-in pins the redirect address, so the admin dashboard cannot go live on the provisional DuckDNS name (some home routers also block DuckDNS).

**Done when**
- a domain is bought and an A record points at the server
- `DOMAIN` in the server's `.env` is the new name and Caddy has a certificate for it
- the upload link uses the new name

Not open for pull requests. See `docs/BETRIEB.md`.
EOF

issue "Create the Google OAuth client for the admin sign-in" "maintainer,area: ops,blocked" "$M1" <<'EOF'
Needs the final domain first.

**Done when**
- an OAuth client of type *Web application* exists with the redirect URI `https://<domain>/api/v1/admin/auth/callback`
- the client ID and secret are in the server's `.env` only, never in the repo or in an issue
- the steps in `docs/BETRIEB.md`, "Der Admin-Bereich" matched what Google actually showed; fix the doc if not
EOF

issue "Deploy the dashboard to the server and add the first admins" "maintainer,area: ops,blocked" "$M1" <<'EOF'
Blocked by the domain and the Google client.

**Done when**
- `git pull && docker compose up -d --build` has run on the server
- all four admin variables are set (the server refuses to start with only some)
- the first admins are added with `docker compose exec api python -m maqati3 admin add <email>`
- a real sign-in with Google works, which has so far only been tested against a stand-in
- a Google address that is not on the list is refused
EOF

issue "Enable server backups and a cost alert" "maintainer,area: ops" "$M1" <<'EOF'
Before the first link goes to the group: automatic backups of the server and a monthly cost alert at the provider.

**Done when** both are on and the monthly cost ceiling is written down in `docs/BETRIEB.md`.
EOF

issue "Add the Google sign-in variables to .env.example" "good first issue,area: ops" "$M1" <<'EOF'
`.env.example` documents the keys the backend reads, but it does not list the admin sign-in yet: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `PUBLIC_URL`, `SESSION_SECRET`.

**Done when** all four are in `.env.example` with a one-line comment each, matching the table in `docs/BETRIEB.md`, and a note that they belong together (all or none). No real values.
EOF

issue "Try the upload page on real phones, in Arabic" "help wanted,area: frontend" "$M1" <<'EOF'
The upload page was tested in desktop Chrome, with a phone-sized window. Contributors will use real phones, mostly forwarded WhatsApp videos.

**Please test** on iOS Safari and Android Chrome, in Arabic and English: choosing 10 to 20 files, a large video, a lost connection halfway, the player for a similar recording, and long names in right-to-left.

**Done when** each problem found is its own issue, with device, browser and a screenshot.
EOF

issue "Show the admin action log in the dashboard" "help wanted,area: frontend,area: backend" "$M1" <<'EOF'
Every dashboard action (sign-in, register, discard, adding a scholar) is already written to `admin_log`, and `Desk.recent_log` can read it. Nothing shows it yet.

**Done when**
- an admin-only route returns the latest entries (who, what, which upload, when)
- the dashboard shows them below the lists, in all three languages
- tests cover the route being closed without a login
EOF

issue "Rate-limit failed upload-key attempts" "help wanted,area: backend,integrity" "$M1" <<'EOF'
The upload API is open to anyone with the key. A wrong key is only refused; nothing slows down guessing.

**Done when** repeated wrong keys from one address are slowed or blocked for a while, the limit is configurable, and a test shows the blocking case before the passing one. Cost guards and rate limits are in the test-first list in `WORKFLOW.md`.
EOF

issue "Resume interrupted uploads of large files" "help wanted,area: frontend,area: backend" "" <<'EOF'
Videos from phones can be hundreds of megabytes, often over a poor connection. Today an interrupted upload starts again from zero.

Please discuss an approach in the issue first (for example a chunked upload with a resumable offset). It has to keep the checks working: SHA-256 and the fingerprint of the complete file.
EOF

issue "Translate the design documents in docs/ into English" "help wanted,documentation" "" <<'EOF'
`docs/` is German, because it is the output of a German-language design session. The code and the contributor guides are English.

**Pick one document per pull request**, starting with `docs/PIPELINE.md`, then `docs/BETRIEB.md`, then `docs/ARCHITECTURE.md`. Keep the structure and the decisions as they are; this is a translation, not a rewrite. Put the English file next to the German one (`PIPELINE.en.md`) so both stay.
EOF

# ======================================================== Transcription and drafts

issue "Bake-off for transcription on 20 real clips" "needs decision,area: pipeline" "$M2" <<'EOF'
The planned transcription service (Soniox) was chosen from published figures. Published word error rates come from clean read speech; old cassette recordings are far worse.

**Plan** 20 clips from the real target material (cassette, studio, dialect, dense Qur'an recitation, question and answer), several providers, scored separately for word error rate, character error rate, names of scholars and narrators, and timestamp quality.

This decides the review workload for years, so the result and the choice are recorded in `docs/ARCHITECTURE.md`. The decision is the maintainers'.
EOF

issue "Transcription job with a replaceable provider" "area: pipeline,area: backend" "$M2" <<'EOF'
Build the job that turns a registered recording into an Arabic transcript with timestamps.

**Design**
- a `Transcriber` protocol; the Soniox client is one implementation, a fake is the other (the transcription service is a genuinely external system, so a fake is allowed here)
- runs as a job from the existing Postgres queue (`maqati3.db.queue`), with the retry and lease rules that already exist
- the audio is normalised first (ffmpeg, Opus, mono); the original stays untouched

**Done when** a registered entry ends with `segment` rows and an `asr` provenance, and a failed provider call is retried and finally marked dead, not lost.
EOF

issue "Form transcript rows from word timestamps" "area: pipeline,integrity" "$M2" <<'EOF'
The provider returns words with times. The archive needs rows: one per moment, never merged later, because the rows are what a citation points at.

**Rules to settle and test**
- when a row ends (pause length, punctuation, maximum duration)
- timestamps are monotonic and never past the duration (`maqati3.text.validate` already checks this)
- every new row starts `span_role = unclear` and `citable = false`; nothing is quotable until a person has looked at it

Write the failing tests first.
EOF

issue "A Transcribe button in the dashboard, with job status" "area: frontend,area: backend" "$M2" <<'EOF'
An admin registers a recording and then starts transcription deliberately; nothing runs automatically (the gate is review time, not cost).

**Done when**
- a button on a registered entry starts the job; pressing it twice does not start two
- the card shows waiting, running, failed (with the reason) and done
- the action is written to `admin_log`
- all texts exist in English, Arabic and German
EOF

issue "Draft translations into English and German, line by line" "area: pipeline,integrity" "$M2" <<'EOF'
Translate each Arabic row into English and German with a language model (Claude Haiku through the Batch API).

**Hard rules, with tests**
- the row count is identical in every language (`validate_transcripts` enforces it)
- drafts are stored with `machine_translation` provenance and are never public before a person approves them
- the Arabic stays visible next to any translation
- a legal term (haram, makruh, la yanbaghi, al-ahwat) is never smoothed over; the draft keeps the term and the review flags it

The model is a genuinely external system and may be replaced by a fake in tests.
EOF

issue "Check the draft translations for flipped legal nuance" "area: pipeline,integrity,help wanted" "$M2" <<'EOF'
A translation that flips a nuance (makruh rendered as haram, or the other way) is the most serious kind of error in this archive.

Build a small test set of 20 Arabic sentences with legal terms and conditional constructions, and a script that runs the draft translation over them and reports, for a person to judge, where the nuance may have moved. This measures the failure rate and decides whether the ruling must be captured as a separate field (`hukm`, which the schema already has).
EOF

issue "Link near-duplicate transcripts by SimHash after transcription" "area: pipeline,integrity" "$M2" <<'EOF'
Audio fingerprints catch the same recording. They never catch the same content in a different recording. After transcription, compute SimHash over the normalised Arabic (`maqati3.dedup.simhash` exists) and link near-duplicates through `canonical_id`.

**Rules**
- never delete; link only, and only the canonical entry is indexed
- a longer copy with the question included is often the better recording, so the admin chooses which is canonical
- write the case that must not link (two episodes with the same jingle) before the case that must
EOF

issue "Daily spending cap for transcription and translation" "area: backend,integrity" "$M2" <<'EOF'
Transcription and model calls cost money per recording. A bug or a flood of registrations must not turn into a surprise bill.

**Done when** a daily cap (configurable) stops new jobs from starting once reached, the dashboard says so plainly, and tests cover the blocking case first. Cost guards are in the test-first list in `WORKFLOW.md`.
EOF

issue "A worker process for the job queue" "area: backend,area: pipeline" "$M2" <<'EOF'
The queue (`maqati3.db.queue`, `SELECT ... FOR UPDATE SKIP LOCKED`) is built and tested, but nothing consumes it.

**Done when** `python -m maqati3 worker` claims jobs, heartbeats while working, completes or fails them with backoff, and shuts down cleanly on SIGTERM. The Docker Compose stack runs it as a second process of the same image.
EOF

# ======================================================= Review in the dashboard

issue "Review table: one row per moment, audio synced to the row" "area: frontend" "$M3" <<'EOF'
The editor where the real work happens: one row per moment, a column per language, the audio jumping to the row you click and highlighting the row that is playing.

**Constraints**
- rows can be edited, never added, deleted or reordered (that is what keeps timestamps valid)
- Arabic is right to left, numbers and timecodes inside Arabic text are isolated (`bidi-isolate`)
- long recordings stay fast (virtualised list)
- usable on a phone

Discuss the layout in the issue before building; a sketch is enough.
EOF

issue "Per-language claim: show who is working on what" "area: backend,area: frontend,needs decision" "$M3" <<'EOF'
The unit of work is one language of one entry. Whoever takes it shows "in progress: <name>" to everyone, so nobody does the same work twice. An admin without German or English reviews only Arabic.

**Open and decided by the maintainers:** how long a claim lasts, and how someone takes over an abandoned one. Please propose a rule in the comments before any code.
EOF

issue "Approve a language through the review state machine" "area: backend,integrity" "$M3" <<'EOF'
The state machine exists (`maqati3.register.states`). Wire it to the dashboard.

**Rules, test first**
- every valid move and every invalid move has a test; an invalid one raises a specific error
- a translation cannot leave `not_started` until the Arabic is approved
- an entry becomes public only when the Arabic is approved and attribution is not `not_sure` (`can_publish`, and the database constraint behind it)

Write the blocking cases before the passing ones.
EOF

issue "Mark who is speaking: set span_role per row" "area: frontend,area: backend,integrity" "$M3" <<'EOF'
Only a row marked `scholar_own` may be quoted. A scholar saying "some claim this is permitted, but that is wrong" must never be cited by its first half.

**Done when**
- the review table lets a reviewer set `span_role` (scholar's own words, questioner, quoting someone else, recited text, unclear) per row
- a row is `citable` only after a person has confirmed its timestamp
- rows left `unclear` produce no citation

Tests first, blocking case first.
EOF

issue "Write every edit to the revision log" "area: backend,integrity" "$M3" <<'EOF'
`revision_log` is append-only (the database ignores updates and deletes). Every change to a transcript, a translation, a `span_role`, an attribution or an approval must add a row: who, what, before and after.

**Done when** no code path changes reviewed content without logging it, and a test proves that an edit without a log row fails.
EOF

issue "Decide: may the person who corrected a language approve it?" "needs decision" "$M3" <<'EOF'
There is one admin role for now, so yes, and it is logged. Separating the corrector from the approver stays possible. This waits on the maintainers; please add arguments in the comments, not code.
EOF

# ========================================================== Phase 1: public library

issue "Hide excluded topics from the whole library, not only from search" "area: backend,integrity" "$M4" <<'EOF'
For retrieval this is done (`segment_citable`). The library side is not: `GET /api/v1/topics`, `/entries/{id}` and `/transcript` currently serve excluded topics like any other.

**Rules** (`CLAUDE.md`, "What `excluded` means")
- an excluded topic is absent from the topic tree, and its entries and transcripts answer 404
- exclusion is inherited by sub-topics and by entries whose topic is excluded, whatever the entry's own fields say
- the filter lives in the repository view, not in the route handlers, so it cannot be forgotten

Write the failing tests first. *Which* topic gets which class is not part of this issue.
EOF

issue "Entry page with player and synced three-language transcript" "area: frontend" "$M4" <<'EOF'
The main page of the product: the player, and next to it the Arabic transcript with English and German beside it. The playing row is highlighted and clicking a row jumps to its second.

Respect the integrity rules: an unapproved translation is labelled as such, an entry whose attribution is `probably` says so, and the Arabic is always one click away.
EOF

issue "Second-accurate deep links" "area: frontend" "$M4" <<'EOF'
`/entry/<id>?t=252` opens the entry at 4:12 and highlights the row. This is the product's core promise, so it needs a test that a timestamp in the link and a row in the transcript agree.
EOF

issue "Topic tree and scholar pages" "area: frontend,area: backend" "$M4" <<'EOF'
Browse by topic (`reference/topics.yml`) and by scholar. Only public entries appear. Depends on the excluded-topics gate above.
EOF

issue "Isolate timecodes, hadith numbers and years in right-to-left text" "area: frontend,integrity" "$M4" <<'EOF'
A reversed hadith number in Arabic text is a false claim about a source, not a cosmetic bug. Every number run is wrapped in `.bidi-isolate` where it is written into the page.

**Done when** a test renders sample Arabic with hadith numbers, years and timecodes and checks each is isolated, and a lint or helper makes the right thing the easy thing.
EOF

issue "Restore test for the database backup" "area: ops,maintainer" "$M4" <<'EOF'
A backup that has never been restored is a hope. Restore it once into a fresh database, record the steps and the time in `docs/BETRIEB.md`, and have a second person repeat it, so nobody is the only one who can bring the server back.
EOF

issue "Imprint and privacy notice" "maintainer" "$M4" <<'EOF'
A public site needs an imprint and a privacy notice before it goes public. Which legal entity runs the project, and what is stored about visitors and uploaders, is for the maintainers and a lawyer; this issue tracks it. Not open for pull requests.
EOF

issue "Decide which topics are open, sources-only or excluded" "needs decision,maintainer" "$M4" <<'EOF'
`reference/topics.yml` does not carry `content_class` yet. What the three classes mean is settled (`CLAUDE.md`); which topic falls into which is a content decision with consequences beyond the code, and is made by the maintainers together with people of knowledge. Not decided in a pull request.
EOF

issue "Decide which scholars are included" "needs decision,maintainer" "$M4" <<'EOF'
`reference/scholars.csv` is a draft. Which scholars are included, whether living scholars are, and on what condition, are the maintainers' decisions. Corrections of a spelling or a date go through the "Reference data correction" form instead.
EOF

issue "Ask the sources for permission" "maintainer" "$M4" <<'EOF'
Some sources allow redistribution with attribution, some forbid it, some have a machine-readable opt-out. Written permission takes months, so it starts early. Tracked here; the letters and the answers are the maintainers' work.
EOF

# ============================================================== Phase 2: search

issue "Gold set: 150 real questions with the entries that answer them" "help wanted,needs decision" "$M5" <<'EOF'
Before any search is built, write the test it will be measured against: real questions, each with the entry ids that answer it, plus 50 questions that have no answer in the archive and 30 minimal pairs (traveller and resident, for example).

It is written by people with knowledge, not by the developer. Retrieval is built against this set, not the other way round.
EOF

issue "An MCP server that returns sources, before any chatbot" "area: backend" "$M5" <<'EOF'
Let the user's own AI assistant do the answering, while this archive supplies verifiable sources: entry, scholar, row, second, Arabic original. Our contribution is the citation, not the answer.

Open the design in the issue first. It must only ever return what the library view allows (public, approved, `scholar_own`, citable, not excluded).
EOF

issue "Hybrid retrieval over the approved material" "area: backend,area: pipeline,integrity" "$M5" <<'EOF'
Keyword (BM25) plus vector search in one Postgres, reading only the filtered view the query path already has. The application database user has no access to the base tables, so a missing filter cannot happen.

Measured against the gold set, not by feel. Needs the gold set first.
EOF

echo
echo "Done. https://github.com/$REPO/issues"
