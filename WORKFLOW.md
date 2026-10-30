# Development Workflow

How work happens in this repo — branching, TDD, commits, and what must never be skipped.
`CLAUDE.md` points here instead of repeating it.

## Branching

**Two paths into `main`** since the repo opened for contributions (2026-10-30):

- **The maintainer commits directly to `main`.** One person has write access and reads
  every commit before it lands, so a branch-per-task buys isolation nobody needs yet.
  The rules below apply in full: TDD discipline does not relax just because the branch
  does.
- **Everyone else works in a fork**, on a `feat/<slug>` or `fix/<slug>` branch, and
  opens a pull request (`CONTRIBUTING.md`). CI must be green and only the maintainer
  merges: **squash** for an ordinary change, so the PR title becomes the one-line commit;
  **rebase** for a test-first change, so its `[RED]` commit lands on `main` as its own
  commit. Merge commits are switched off.

A ruleset on `main` holds this in place on GitHub: no force-push, no deletion, and only
the repository admin may update `main`, whether by pushing or by merging. CI (`.github/
workflows/ci.yml`) runs on every push and pull request with a real Postgres, `fpcalc` and
`ffmpeg`, and fails when a test was skipped.

- Before every commit: the full test suite must be green. There is no separate "landing"
  step to catch a broken commit later — the commit *is* the landing.
- **Never rewrite history that has already been pushed to `origin/main`**: no `rebase`,
  no `--amend`, no force-push. If something needs fixing, fix it forward in a new commit.
  (History *before* it's pushed — e.g. cleaning up a commit made two minutes ago that
  hasn't left this machine — is fine to amend.)
- If a second person gets **write access** to this repository, or solo work needs to try
  something without touching `main` mid-task, the maintainer switches to feature
  branches too: `feat/<short-slug>` off `main`, PR before merging, no direct AI-driven
  commits to `main`. Update this section when that happens — don't let the two models
  coexist undocumented.

## Commits

Compact one-liners. **No body, no bullet lists, no `Co-Authored-By` trailer** — not for
AI-driven commits either. The commit message says what changed, nothing else.

```
feat(ingest): parse [HH:MM:SS] transcript lines
test(dedup): simhash matches across re-encodes [RED]
fix(retrieval): exclude unapproved translations from the index
docs: record the span_role decision
```

Never bundle a test commit and its implementation in the same commit.

## TDD — non-negotiable for integrity-critical logic

Not every line needs a test first. **These do**, without exception:

- Status transitions (the register state machine)
- Publication gates (`attribution`, `visibility`, approval state)
- `span_role` and `citable` filtering — anything that decides what may be quoted
- Deduplication and canonicalisation
- The abstain rule in the answer pipeline
- Cost guards and rate limits

For those, the cycle is:

1. Write a failing test that captures exactly **one** behaviour. Run it. Confirm it
   fails for the right reason.
2. Commit the test alone: `test(<module>): <what> [RED]`
3. Write the minimal implementation that makes it pass. Run. Confirm green.
4. Commit: `feat(<module>): <what>`
5. Refactor if needed, re-run, commit.

Rules:

- One behaviour per test. Name them `test_<what>_<condition>_<expected>`.
- For every state machine: a test for every **valid** transition **and** every invalid
  one. An invalid transition must raise a specific error — never silently succeed.
- For every gate: **write the blocking case before the passing case.** The gate exists
  for the blocking case; testing only the happy path tests nothing.
- Never mock at the boundary under test. Inject fakes only for genuinely external
  systems (Drive API, ASR provider, LLM API).
- Coverage is a side effect of good TDD, not a target.

**Before the first RED test of a task that changes an existing signature or adds a
cross-cutting check: grep all call sites, including test fixtures, for the blast radius.**

## Tests

```bash
cd backend && uv run pytest                  # all
cd backend && uv run pytest tests/<file>     # during a TDD cycle
cd backend && uv run ruff check src tests && uv run mypy src
cd frontend && npm test && npm run lint && npx tsc --noEmit
```

During a red-green-refactor cycle run only the module's own tests. Run the full suite
once before landing, not after every cycle.

## Before landing a branch

1. Full test suite green
2. Lint and type check clean
3. Migrations apply from scratch against an empty database
4. If the data model changed: confirm nothing in `docs/` still describes the old shape

## What must never be done

- Commit secrets, API keys, OAuth tokens, or service-account JSON. Check `git diff
  --staged` before committing anything under `backend/`.
- Commit media files. Audio and video live in object storage, never in git.
- Hand-edit a published entry's `id` or `canonical_id`. Those are referenced by live
  URLs and by stored citations.
- Loosen a publication gate to make a test pass.
