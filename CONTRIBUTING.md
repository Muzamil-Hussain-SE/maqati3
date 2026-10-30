# Contributing to maqati3

As-salāmu ʿalaykum, and thank you for wanting to help. This page explains how work gets
into this repository: what to pick up, how to set up, which rules are strict, and how a
pull request gets merged.

Please read the [code of conduct](CODE_OF_CONDUCT.md) first. It is short.

## The one thing to understand first

This archive will put sentences in front of people as *the words of a scholar*. A fatwa
attributed to the wrong scholar, a translation that flips a nuance, or a quote taken out
of the situation it was given in is a real harm. Once it is public, it cannot be taken
back, even if the fix takes two minutes.

So a few parts of the code are guarded more strictly than usual: the publication gates,
attribution, which lines may be quoted (`span_role`, `citable`), deduplication, and cost
limits. If your change touches one of them, the rules in [Tests](#tests) apply without
exception. Issues in these areas carry the label
[`integrity`](https://github.com/PSchmitz-Valckenberg/maqati3/labels/integrity). The
reasoning is in [`CLAUDE.md`](CLAUDE.md), under *Integrity is structural*.

## Scope

The archive is of the scholars of Ahl as-Sunnah wal-Jamāʿah, upon the Salafi methodology.
Pull requests and issues that propose widening or changing that scope are closed; it is
the maintainers' decision, not a code question.

## Ways to help

- **Code.** Pick an issue labelled
  [`good first issue`](https://github.com/PSchmitz-Valckenberg/maqati3/issues?q=is%3Aopen+label%3A%22good+first+issue%22)
  or [`help wanted`](https://github.com/PSchmitz-Valckenberg/maqati3/issues?q=is%3Aopen+label%3A%22help+wanted%22).
- **Arabic and right-to-left.** Try the pages in Arabic on a real phone and report
  anything that reads wrong, is mirrored wrong, or puts numbers in the wrong order.
- **Documentation.** The design documents in `docs/` are in German; translating them into
  English is a tracked issue.
- **Reference data.** A misspelt name or a wrong date in `reference/` is worth an issue.
  Please include a source.

Issues labelled `needs decision` or `maintainer` are not open for pull requests. They
wait on a decision or an account only the maintainer has. Ideas and opinions in the
comments are still welcome.

## Decisions that are not made in a pull request

Some questions are content decisions with consequences beyond the code. They are made by
the people responsible for the project, never in a pull request:

- which scholars are included (`reference/scholars.csv` is a draft), and whether and how
  living scholars are;
- which topic is `open`, `sources_only` or `excluded`;
- whether an entry is held back;
- approving any transcript or translation.

A pull request that settles one of these on the side will be closed, however good the
code is. Open an issue instead.

## Before you start

1. **Comment on the issue** you want to take, so two people do not build the same thing.
2. **For anything larger than a bug fix, agree on the approach first** in the issue. A
   short plan in a comment saves a rewritten pull request.
3. **Keep it small.** One concern per pull request.

## Set up

You need [uv](https://docs.astral.sh/uv/), Node 22 and Docker. For the media tests you
also need `fpcalc` and `ffmpeg`:

```bash
brew install chromaprint ffmpeg                  # macOS
sudo apt install libchromaprint-tools ffmpeg     # Debian, Ubuntu
```

The database, the backend and the frontend are started as in the README's
[*Run it locally*](README.md#run-it-locally). In short:

```bash
docker compose up -d --wait db
export DATABASE_URL=postgresql://maqati3:devonly@127.0.0.1:5432/maqati3
cd backend && uv sync && uv run python -m maqati3 migrate && uv run python -m maqati3 seed
cd ../frontend && npm ci
```

The database starts empty on purpose: `migrate` creates the schema, exactly as on the
server. If you already run a Postgres on port 5432, start this one with
`DB_PORT=55432 docker compose up -d --wait db` and use that port in `DATABASE_URL`.

## Tests

Run these before you push. CI runs the same, with a real Postgres, `fpcalc` and `ffmpeg`,
and fails if a test was skipped.

```bash
cd backend
uv run ruff check src tests
uv run mypy src
uv run pytest                 # with DATABASE_URL set, the database tests run too

cd frontend
npm run lint
npx tsc --noEmit
npm test
```

**Test first, for these areas, without exception:**

- state transitions (the review state machine)
- publication gates (`attribution`, `visibility`, approval)
- `span_role` and `citable`: anything that decides what may be quoted
- deduplication and canonical entries
- the abstain rule in the answer pipeline
- cost guards and rate limits

For those, commit the failing test on its own first (`test(<module>): <what> [RED]`),
then the implementation that makes it pass. For a gate, write the case that must be
**blocked** before the case that passes; the gate exists for the blocked case. Do not
mock the thing under test; fakes are for genuinely external systems (the transcription
service, the LLM, Google). The full rules are in [`WORKFLOW.md`](WORKFLOW.md).

## Style

- **Python**: ruff and mypy in strict mode, both clean. Names say what a thing is for.
  Comments explain *why*, not *what*.
- **TypeScript**: ESLint clean. Use logical CSS properties (`ms-`, `me-`, `ps-`,
  `text-start`) instead of `left` and `right`, so the Arabic layout mirrors correctly.
- **Text in the interface** goes into `frontend/messages/{en,ar,de}.json`, **in all three
  languages**. If you cannot write one of them, say so in the pull request and someone
  will fill it in. Never merge a key that exists in only one language.
- **Numbers in Arabic text** (timestamps, hadith numbers, years) are isolated with
  `bidi-isolate`. A reversed hadith number is a false claim about a source.
- **Language**: code, comments, commit messages and pull requests are in English.

## Commits and pull requests

1. Fork the repository and create a branch: `feat/<short-name>` or `fix/<short-name>`.
2. Commit messages are **one line**, in this style, with no body:

   ```
   feat(upload): show the matching part of a similar recording
   fix(admin): keep the scholar choice after a failed register
   test(gates): a not_sure entry is never public [RED]
   docs: explain the dev database port
   ```

3. Open the pull request against `main` and fill in the template. Write the title in the
   same one-line style; it usually becomes the commit message on `main`.
4. CI must be green. On a first pull request, the maintainer starts CI by hand. That is
   how GitHub protects against untrusted code, and says nothing about you.
5. **Only the maintainer merges.** Usually the pull request is squashed into one commit.
   A test-first change is merged with its commits kept, so the failing test stays visible
   in the history.

Never do these, in any pull request:

- commit secrets, API keys or `.env` files;
- commit audio or video files;
- edit a migration that has already been applied. Add a new one instead;
- change the `id` or `canonical_id` of an entry;
- loosen a publication gate to make a test pass.

## License

By contributing, you agree that your contribution is licensed under the
[AGPL-3.0](LICENSE), like the rest of the repository. There is no separate agreement to
sign.
