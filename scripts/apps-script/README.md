# Apps Script — duplicate pre-check

`duplicate-check.gs` runs inside the register spreadsheet and catches the most common
duplicate case — two contributors submitting the same link — before anyone spends work
on it. It needs no backend and can run from day one.

## Install

1. Open the register spreadsheet → **Extensions → Apps Script**
2. Paste `duplicate-check.gs`, save
3. Run `testNormalisation` once from the editor. It will ask for permission (the script
   reads the sheet and sends mail as you) and then print three PASS lines to the log.
   **If any line says FAIL, stop and fix it before installing the trigger.**
4. **Triggers → Add trigger** → function `onFormSubmit`, source *From spreadsheet*,
   event type *On form submit*

## What it does

On every submission: normalises the source URL (YouTube IDs across all their URL shapes,
tracking parameters stripped for everything else), compares against every earlier row,
and on a hit writes the matching entry into `possible_duplicate_of` with a cell note,
then emails the contributor.

The email deliberately invites a correction — a second recording of the same fatwa is
often the better one (longer, cleaner, or with the question included where the other
starts at the answer). Those get linked, not dropped.

## Limits

Catches layer 1 only: the same online source. The same recording re-uploaded under a
different link, or the same fatwa from a different recording, needs audio fingerprinting
and text comparison — those live in the backend. See `docs/PIPELINE.md`.

Column names at the top of the file must match the sheet's header row exactly. Rename a
column in the sheet, change it there too.
