<!-- Title: one line, e.g. "feat(upload): show the matching part of a similar recording" -->

## What and why

<!-- What does this change, and why? Link the issue: "Closes #12". -->

## How it was tested

<!-- Commands you ran, what you tried by hand (which pages, which language, phone or desktop). -->

## Checklist

- [ ] Backend: `uv run ruff check src tests`, `uv run mypy src` and `uv run pytest` are clean
- [ ] Frontend: `npm run lint`, `npx tsc --noEmit` and `npm test` are clean
- [ ] If this touches a gate (publication, attribution, `span_role`/`citable`, dedup, cost limits): the failing test is its own commit, before the fix
- [ ] New interface text exists in English, Arabic **and** German, or I said below which one is missing
- [ ] No secrets, no media files, no edits to an applied migration
- [ ] Docs updated if behaviour or the data model changed
