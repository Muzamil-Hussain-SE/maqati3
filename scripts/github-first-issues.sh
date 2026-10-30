#!/usr/bin/env bash
# One-off: more small, well-bounded issues for newcomers.   bash scripts/github-first-issues.sh
# Safe to run again: an issue whose title already exists is skipped.
set -euo pipefail

REPO="PSchmitz-Valckenberg/maqati3"
EXISTING="$(gh issue list -R "$REPO" --state all --limit 500 --json title --jq '.[].title')"

issue() {
  local title="$1" labels="$2" body
  body="$(cat)"
  if grep -qxF "$title" <<<"$EXISTING"; then echo "exists   $title"; return; fi
  gh issue create -R "$REPO" --title "$title" --body "$body" --label "$labels" >/dev/null && echo "opened   $title"
}

issue "Replace the create-next-app README in frontend/" "good first issue,documentation,area: frontend" <<'EOF'
`frontend/README.md` is still the text `create-next-app` generated. It tells nobody how this frontend works.

**Done when** it is a short README (under a page) that says what the frontend is, how to run it (`npm ci`, `npm run dev`, the `API_ORIGIN` proxy and the 10 MB limit of the dev proxy, see `docs/BETRIEB.md`), where the pages and the texts live (`src/app/[locale]`, `messages/{en,ar,de}.json`), and how to run `npm run lint`, `npx tsc --noEmit` and `npm test`.
EOF

issue "Remove the unused create-next-app images from frontend/public" "good first issue,area: frontend" <<'EOF'
`frontend/public` holds `file.svg`, `globe.svg`, `next.svg`, `vercel.svg` and `window.svg` from the project template. Nothing in `frontend/src` refers to them.

**Done when** the five files are deleted, `npm run build` still passes, and the pull request says how you checked that nothing uses them.
EOF

issue "Add a favicon and app icon" "good first issue,area: frontend" <<'EOF'
The pages have no icon, so browsers show a default one. Add a simple, readable icon for maqati3 (the Arabic letter م, or the "3", in the green used on the README banner, `#047857`) as `src/app/icon.svg` (Next.js picks it up by convention).

**Done when** the tab shows the icon in light and dark browser themes, and the pull request includes a screenshot.
EOF

issue "Add a language switcher to the upload page and the dashboard" "good first issue,area: frontend" <<'EOF'
The three languages are reachable only by editing the address (`/en/`, `/ar/`, `/de/`). A contributor who opened the link in the wrong language has no way to change it.

**Done when**
- a small control on `/{locale}/upload` and `/{locale}/admin` switches between English, Arabic and German and stays on the same page
- the upload link's `#k=` fragment survives the switch (test this; without it the page refuses to send)
- the language names are written in their own language (English, العربية, Deutsch) and work with the keyboard
- Arabic still lays out right to left, with logical CSS properties only (`ms-`, `me-`, `text-start`)
EOF

issue "Add an .editorconfig" "good first issue,area: ops" <<'EOF'
Python files use 4 spaces and a 100-column limit (ruff), the frontend uses 2 spaces. Editors do not know that unless a file tells them.

**Done when** `.editorconfig` at the repository root sets charset, final newline, trailing whitespace and indent size per language (Python 4, TypeScript, JSON, YAML and Markdown 2, SQL 4) to match what the code already does. No existing file needs to change.
EOF

issue "Test that the upload link's key is never sent to the server in the address" "good first issue,area: frontend,integrity" <<'EOF'
The upload key lives behind `#` in the link so it never reaches server logs or referrers (`docs/BETRIEB.md`). `parseUploadKey` reads it, and the page sends it as the `X-Upload-Key` header, and only the media preview uses `?k=`.

**Done when** a test in `frontend/src/lib/uploads/` asserts that the upload, decision and check calls put the key in the header and not in the URL, and that only `mediaUrl` puts it in the query. Tests for `batch.ts` are the model.
EOF

issue "Translate docs/COSTS.md into English" "good first issue,help wanted,documentation" <<'EOF'
Part of #13. `docs/COSTS.md` (117 lines) is German. Add `docs/COSTS.en.md` next to it and keep the German file.

Keep the structure, the tables and every number exactly; this is a translation, not a rewrite. Terms that appear in the code (`not_sure`, `content_class`) stay as they are. Please do not translate more than this one document per pull request.
EOF

issue "Translate docs/SETUP-GOOGLE.md into English" "good first issue,help wanted,documentation" <<'EOF'
Part of #13. `docs/SETUP-GOOGLE.md` (94 lines) is German and is marked as partly superseded. Add `docs/SETUP-GOOGLE.en.md` next to it, keeping the "superseded" note at the top. Translation only; do not change what the steps say.
EOF

issue "Translate docs/RISKS.md into English" "help wanted,documentation" <<'EOF'
Part of #13. `docs/RISKS.md` (259 lines) lists what could realistically end this project. It contains statements about sources and legal questions, so precision matters more than speed.

Add `docs/RISKS.en.md` next to the German file. Translate faithfully; do not soften, shorten or add anything. Anything you are unsure of goes into a comment on the pull request instead of being guessed. Please take only this document in one pull request.
EOF

issue "Check the relative links in the Markdown files" "good first issue,documentation" <<'EOF'
The README, CONTRIBUTING.md, WORKFLOW.md and the files in `docs/` link to each other and to files in the repository (some of them were renamed from masdar to maqati3).

**Done when** every relative link in the Markdown files resolves to an existing file or heading, broken ones are fixed, and the pull request lists what was wrong. A small script that checks them is welcome but optional.
EOF

echo
echo "Done. https://github.com/$REPO/issues?q=is%3Aopen+label%3A%22good+first+issue%22"
