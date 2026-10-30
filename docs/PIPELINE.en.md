# Pipeline and Deduplication

*Internal developer document, English version of PIPELINE.md. `intake/` remains English.*

> **As of 2026-10-27:** Step 10 (correction in Google Docs) and automatic processing immediately after upload are superseded. Admins choose per video in the dashboard whether it is worthwhile, and correct entries in a dedicated table editor. See `CLAUDE.md`, "The Admin Workflow". The five deduplication layers below remain valid as stated.

Goal: The contributor uploads something, everything automated happens on its own, they only perform corrections, the admin approves, and it goes online. And: nothing is processed twice.

---

## 1. The Process, Step by Step

| # | Step | Who/What | Duration | Cost |
|---|---|---|---|---|
| 0 | Submission: link **or** file | Contributor | 1 min | 0 |
| 1 | **Immediate check** source/duration | automatic | < 1 s | 0 |
| 2 | Fetch (`yt-dlp`) + Normalize (`ffmpeg` → Opus 24k mono) | Worker | 1–3 min | 0 |
| 3 | Bit-identical original into cold storage | Worker | — | ~0 |
| 4 | **Audio fingerprint** against existing corpus | Worker | sec. | 0 |
| 5 | Arabic ASR with timestamps | Soniox | ~realtime/5 | $0.10/h |
| 6 | **Text dedup** against existing corpus | Worker | sec. | 0 |
| 7 | **Generate metadata** (see §3) | Haiku Batch | min. | ~$0.001 |
| 8 | Raw translation DE + EN, line-by-line | Haiku Batch | min. | ~$0.003 |
| 9 | Appears in contributor's task list | — | — | — |
| 10 | Correction in document | Contributor | **the actual effort** | — |
| 11 | Approval | Admin | min. | — |
| 12 | Indexing, live | Worker | sec. | ~0 |
| 13 | **Similarity check in index** | Worker | sec. | 0 |

Steps 1–9 are fully automatic. From submission to completed task with Arabic transcript and two raw translations takes only a few minutes and under 1 cent.

**The honest reality:** Step 10 remains the bottleneck. With a 20–40% word error rate on old cassette material, that means 90–180 minutes per audio hour, not 15. Automation does not eliminate the bottleneck; it cuts it in half — but nothing more. Throughput measurements in week 1 determine how large the corpus can realistically become.

---

## 2. Deduplication: Five Layers, from Cheapest to Most Expensive

Each layer catches a different case. None replaces another.

| # | Catches | When | Reaction |
|---|---|---|---|
| **1** | Same online source submitted again | **before** everything else, immediately | block, show existing entry |
| **2** | Byte-identical file | after fetching | block |
| **3** | Same recording, different edit/intro/bitrate | after fetching | flag, admin decides |
| **4** | Same content, different recording | after ASR | flag |
| **5** | Same answer given on a different occasion | after indexing | **not a duplicate** — related |

### Layer 1 — Source and Duration
Normalized source URL and, where available, the platform ID (YouTube video ID, etc.) as a `UNIQUE` column. Catches by far the most common case — two contributors submitting the same link — for zero compute time. Additionally, a soft check *same scholar + duration ± 2 s*, which is displayed as a candidate list rather than a hard block. Duration is an astonishingly strong signal: two independent recordings almost never match to the second.

### Layer 2 — SHA-256
Computed over the original file, before any conversion. Trivial, exact, useless against re-encodes — which is why Layer 3 is necessary.

### Layer 3 — Audio Fingerprint (Chromaprint)
**Revised 2026-10-25, Migration 0003.** The original plan — 30-second windows, matches on byte-identical windows — would not have detected a single forwarded copy. Measured against real speech re-encoded via AAC 64k, MP3 32k, and Opus 24k: window fingerprints of a re-encoded copy are **never** byte-identical (1–9% of bits differ; unrelated speech: ~48%). And every WhatsApp forward is re-encoded. Windows would therefore only find what SHA-256 already finds.

Now: one fingerprint per recording (`fpcalc -raw -length 0`). Alignment via voting over the 32-bit values that survive re-encoding exactly (around half) — accurate to ~0.12 s, meaning an intro of arbitrary length works, not just multiples of 15 s. Confirmation occurs via the bit error rate on the **longest matching run**, not averaged across the entire file: a forwarded compilation containing this and another fatwa must hit; two episodes of a show sharing the same jingle must not.

Hit when: bit error rate ≤ 0.20, run length ≥ 10 s **and** ≥ 50% of the shorter recording. Measured: re-encodings 0.008–0.085, 7-second intro detected precisely (+7.07 s), 40-second excerpt from the middle detected; unrelated recording — even 147 s of silence — shares zero index keys. **Measured on synthetic speech.** Older cassette material is harsher; re-verify thresholds against real recordings.

Index: every eighth value, chosen by value (not by position, otherwise an intro shifts all keys) — roughly one key per second of audio. Candidate flagged at 3 common keys, followed by full comparison.

### Layer 4 — Text (SimHash over Normalized Arabic)
After ASR. 64-bit SimHash over shingles of `text_norm` (tashkeel stripped, alef/hamza unified), Hamming distance ≤ 6 = hit. Catches what audio never catches: **the same fatwa, completely different recording** — different microphone, different occasion, identical wording. With ASR having a 30% error rate, SimHash is far more robust than exact text comparison.

### Layer 5 — Vector Similarity (from Phase 2 onwards)
Cosine > 0.97 on the Arabic document vector. **This is explicitly not a duplicate.** The same scholar answering the same question twice on different occasions represents two legitimate entries — and if the answers diverge, that is in fact one of the most valuable pieces of information in the entire archive.

Nevertheless, it must be handled, for a reason unrelated to tidy housekeeping: if ten copies of the same answer appear in the search results, the user perceives this as consensus among ten scholars. That is an attribution error, not a presentation error. The solution is grouping, not deletion.

---

## 3. Metadata per Clip

Two kinds. Technical metadata is generated during processing; semantic content metadata is produced by an affordable model in batch and confirmed by a human.

**Technical (Steps 2–6):**

```
sha256              Original file
source_platform_id  e.g. YouTube video ID, UNIQUE
duration_sec        to the second
chromaprint         one fingerprint per recording + index keys (Migration 0003)
simhash_ar          64 bits over text_norm
audio_profile       sample rate, channels, estimated SNR
```

`audio_profile` is not an end in itself: heavily compressed old material at 8–16 kHz cannot be cleaned up by any better ASR model. Knowing this early allows routing such clips to a dedicated queue instead of letting a contributor struggle fruitlessly for three hours.

**Semantic Content (Step 7, Haiku Batch, all as suggestions with confidence scores):**

```
title_ar / title_en     short title
question_ar             the question wording, if present in audio
topic / topic_sub       from topics.yml
hukm                    Enum, not prose: wajib|mandub|mubah|makruh|haram|tafsil|kein_urteil
generality              general | case-specific | unclear
speakers[]              recognized speakers (questioner vs. scholar)
mentions[]              mentioned scholars and narrators
quran_refs[]            from ﴿ ﴾ markers, resolved against Tanzil
hadith_refs[]           fuzzy matched against local Hadith corpus
```

`hukm` and `generality` are the two most valuable fields from a risk-analysis perspective. `generality` reflects that an oral fatwa was usually given for a specific case — this is fundamentally unresolvable via retrieval alone, requiring a field verified by a human.

**Technology suffices for similarity comparison. Display requires semantic understanding.**

---

## 4. What Happens on a Hit — Never Delete Automatically

Each entry has `canonical_id`, pointing either to itself or to another entry.

- Only the canonical entry is indexed for search.
- Variants retain their own transcript, source, and provenance.
- The entry page displays "3 further recordings of this answer".
- Which entry is canonical is decided by the admin — machine recommendations: best audio quality, longest version, question included, most official source.

Reasons against automatic deletion:

1. The "copy" is often the **better** recording — longer, includes the question, cleaner audio.
2. Provenance is evidence. A clip from the scholar's official website and the same clip from a Telegram group do not carry equal authority, even if the audio is identical.
3. If one of the recordings diverges, that is the most interesting information in the archive and must under no circumstances disappear silently.

---

## 5. Where This Intersects with the Form

A Google Form **cannot** validate live. Providing feedback like "we already have this" before submission requires a custom webpage.

Nonetheless, do not build this immediately, for a simple reason: **on day one the corpus is empty, so dedup has zero value.** It becomes valuable once several hundred entries exist — and by then the backend will be in place anyway.

**Phase 1 — Apps Script in Google Sheets.** An `onFormSubmit` trigger, ~50 lines, costs nothing and runs without a backend:

1. Normalizes the submitted URL, extracts the video ID
2. Compares against all existing rows
3. Writes `possible_duplicate_of` with the existing ID on a match
4. Automatically emails the contributor: *"We may already have this one — see entry X. If yours is a different recording, reply and tell us."*

This catches Layer 1, by far the most common case, before anyone invests time into it.

**Phase 2 — Custom Upload Page.** Live checking during input, progress indicators, immediate feedback. Approximately 3–5 developer days, sensible once the backend is running.

---

## 6. Implementation Order

| When | What |
|---|---|
| **immediately, without backend** | Apps Script: URL normalization + duration comparison + email to contributor |
| **Phase 1, Weeks 2–3** | SHA-256 and Chromaprint on ingest, `canonical_id` in schema from the start |
| **Phase 1, Week 3** | SimHash after ASR |
| **Phase 1, Week 4** | Metadata generation in batch, as suggestions with confidence scores |
| **Phase 2** | Vector similarity, grouping in search results, custom upload page |

`canonical_id` and `sha256` belong in the **first** migration, even if dedup logic runs weeks later. Retroactively introducing canonicalization across a thousand published entries breaks a thousand links.
