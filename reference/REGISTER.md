# The register

One sheet. One row per entry. It is the **only** source of truth for where things stand —
not the folder, not the file name, not a message in the group.

The first columns are written by the Google Form automatically. The rest are added to the
right and are filled by the admin and the contributors.

Built so it can be read by software later without rework: fixed column names, fixed value
lists, no colour as meaning, no merged cells, no second header row.

## Columns

**From the form** — `timestamp` · `email` · `submitted_by` · `scholar` · `scholar_other` ·
`source_url` · `sure_it_is_him` · `topic` · `question` · `uploaded_file` ·
`has_transcript` · `notes_from_submitter`

**Added by the admin:**

| Column | Values / format | Who |
|---|---|---|
| `id` | `<scholar-id>-<6 digits>` — permanent | admin |
| `attribution` | `Confirmed` · `Probably` · `Not sure` | admin |
| `topic_sub` | ids from `topics.yml`, separated by `;` | admin |
| `duration_sec` | number | admin / automatic |
| `priority` | `1`–`5`, 1 = first | admin |
| `status_ar` | see list below | contributor |
| `assignee_ar` | name | admin |
| `status_en` | see list below | contributor |
| `assignee_en` | name | admin |
| `status_de` | see list below | contributor |
| `assignee_de` | name | admin |
| `doc_link` | link to the entry Doc | admin |
| `audio_link` | link to the audio | admin |
| `reviewer` | name | admin |
| `reviewed_on` | `YYYY-MM-DD` | admin |
| `visibility` | `Draft` · `Public` · `Held back` | admin |
| `notes` | free text — review feedback, reasons for holding back | admin |

## Status values (one set per language)

```
Not started              nothing there yet
Draft ready              machine draft exists, not checked by anyone
In progress              someone is working on it
Done – waiting review    finished, waiting for the admin
Needs fixes              sent back  (reason goes in notes)
Approved                 cleared
```

Allowed moves:

```
Not started ──> Draft ready ──> In progress ──> Done – waiting review ──> Approved
                                     ^                      │
                                     └──── Needs fixes ◄─────┘
```

## Two hard rules

1. **`status_en` / `status_de` may only leave `Not started` once `status_ar` is
   `Approved`.** Otherwise someone translates a version that is still changing.
2. **`visibility` = `Public` requires `attribution` ≠ `Not sure` **and** `status_ar` =
   `Approved`.** Unapproved translations simply don't show — the entry is Arabic-only until
   they are. That is the normal case, not a defect.

## Why status is per language and not per entry

The material arrives unevenly: some has an Arabic transcript already, some is audio only,
some has Arabic and English but no German. A pipeline that runs step 1 to 7 in order cannot
represent that. Three independent status columns can — and they make it possible to
prioritise translation by demand rather than by stock.

## Contributor views

Nobody browses the full sheet. Each contributor gets a **filter view** on their own name:

```
assignee_ar = "Yusuf"  OR  assignee_en = "Yusuf"  OR  assignee_de = "Yusuf"
```

showing: scholar · title · `audio_link` · `doc_link` · their status cell · `notes`.
That view is "Link 2" from `START-HERE.md`. It is the only part of the sheet they see.
