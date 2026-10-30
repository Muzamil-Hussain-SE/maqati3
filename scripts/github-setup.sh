#!/usr/bin/env bash
# One-off setup of the GitHub side of the repository: labels, milestones, merge settings,
# security features and the ruleset that keeps `main` in the maintainer's hands.
#
# Run it once, as the repository admin, after `gh auth login`:   bash scripts/github-setup.sh
# It is safe to run again: labels are overwritten, milestones that exist are skipped, and
# the ruleset is replaced by name.
set -euo pipefail

REPO="PSchmitz-Valckenberg/maqati3"

label() { gh label create "$1" -R "$REPO" --color "$2" --description "$3" --force >/dev/null && echo "label      $1"; }

milestone() {
  if gh api "repos/$REPO/milestones?state=all&per_page=100" --jq '.[].title' | grep -qxF "$1"; then
    echo "milestone  $1 (exists)"
  else
    gh api "repos/$REPO/milestones" -f title="$1" -f description="$2" >/dev/null && echo "milestone  $1"
  fi
}

echo "== labels"
label "area: backend"  1D76DB "Python, FastAPI, database access"
label "area: frontend" 5319E7 "Next.js pages, translations, right-to-left layout"
label "area: pipeline" 0E8A16 "Transcription, translation drafts, deduplication, the job queue"
label "area: ops"      6E7781 "Server, deployment, CI"
label "area: data"     BFD4F2 "Schema, migrations, reference data"
label "integrity"      B60205 "Touches a publication gate, attribution, span_role/citable or dedup: failing test first"
label "needs decision" D93F0B "Waits on a decision the maintainers make, not something to settle in a pull request"
label "maintainer"     3B3B3B "Only the maintainer can do this: accounts, the server, outreach"
label "blocked"        FBCA04 "Waits on another issue"

echo "== milestones"
milestone "Admin dashboard live"      "A domain, the Google sign-in and the dashboard on the server, so admins can register uploads."
milestone "Transcription and drafts"  "One button per registered recording: transcribed in Arabic with timestamps, with draft translations in English and German."
milestone "Review in the dashboard"   "One row per moment with the audio synced, a claim per language, and approval with the publication gates enforced."
milestone "Phase 1: public library"   "Topic tree, scholar pages, and the entry page with a synced trilingual transcript and second-accurate deep links. No AI."
milestone "Phase 2: search"           "A gold set first, then retrieval, an MCP server, and only then an answer tool."

echo "== repository settings"
gh repo edit "$REPO" \
  --description "Open-source archive of recorded fatawa: Arabic transcripts with English and German translations, every line anchored to the second. Show me where he said it." \
  --enable-wiki=false \
  --enable-projects=false \
  --enable-discussions=true \
  --enable-merge-commit=false \
  --enable-squash-merge=true \
  --enable-rebase-merge=true \
  --delete-branch-on-merge=true \
  --add-topic arabic --add-topic islam --add-topic fatwa --add-topic transcription \
  --add-topic fastapi --add-topic nextjs --add-topic postgresql --add-topic chromaprint \
  --add-topic audio-fingerprinting --add-topic rtl --add-topic open-source
echo "settings   done"

echo "== security"
gh api -X PUT "repos/$REPO/private-vulnerability-reporting" >/dev/null && echo "private vulnerability reporting on"
gh api -X PUT "repos/$REPO/vulnerability-alerts" >/dev/null && echo "dependabot alerts on"
gh api -X PUT "repos/$REPO/automated-security-fixes" >/dev/null && echo "dependabot security updates on"
# A pull request from someone new does not run CI until the maintainer approves it.
gh api -X PUT "repos/$REPO/actions/permissions/fork-pr-contributor-approval" \
  -f approval_policy=all_external_contributors >/dev/null && echo "CI for outside contributors needs approval"

echo "== ruleset on main"
EXISTING=$(gh api "repos/$REPO/rulesets" --jq '.[] | select(.name=="main is the maintainer'"'"'s") | .id' || true)
if [ -n "$EXISTING" ]; then gh api -X DELETE "repos/$REPO/rulesets/$EXISTING" >/dev/null; fi
# `update` restricts who may move main at all, by push or by merge. Only the bypass list
# (the repository admin role, id 5) may. `non_fast_forward` forbids force-push, `deletion`
# forbids deleting the branch. Everyone else works in a fork and opens a pull request.
gh api "repos/$REPO/rulesets" --input - >/dev/null <<'JSON'
{
  "name": "main is the maintainer's",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [ { "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always" } ],
  "rules": [ { "type": "update" }, { "type": "non_fast_forward" }, { "type": "deletion" } ]
}
JSON
echo "ruleset    active"

echo
echo "Still by hand (GitHub has no API for it):"
echo "  Settings > General > Social preview: upload .github/assets/social-preview.png"
