# Setting up the Drive — checklist for the admin

Four folders. Contributors never open any of them.

```
FATAWA ARCHIVE/
├── 1 START HERE/     the guides. Read-only for everyone.
├── 2 SUBMISSIONS/    the form drops uploads here by itself. Nobody touches it.
├── 3 LIBRARY/        one folder per entry. Admin only.
│   └── ibn-uthaymin/
│       └── uthaymin-000421/
│           ├── media.mp3
│           └── (the entry Doc lives here too)
└── 4 REGISTER/       the sheet + scholars.csv + topics.yml
```

## Steps

1. Create a **Shared Drive** (not a personal folder). A shared drive survives one person
   leaving; a personal folder does not. This matters more than it seems — a volunteer
   project loses people.
2. Create the four folders above.
3. Upload the contents of `intake/` into `1 START HERE/`.
4. Build the Google Form from `FORM-SETUP.md`. Point its file-upload destination at
   `2 SUBMISSIONS/`.
5. Link form responses to a sheet, put the sheet in `4 REGISTER/`, add the admin columns
   from `REGISTER.md` to the right of the form's columns.
6. Set **data validation** (dropdowns) on `attribution`, all three `status_*`, `priority`
   and `visibility`. This is what prevents typos from becoming data problems later.
7. Protect the form's own columns so nobody overwrites a submission by accident.
8. Upload `scholars.csv` and `topics.yml` into `4 REGISTER/`.
9. Create one filter view per contributor (see `REGISTER.md`).

## Permissions

| Who | What |
|---|---|
| Contributors | **Commenter** on the Shared Drive, **Editor** only on their own entry Docs and their status cells |
| Admin / reviewer | Editor everywhere |
| The form | Anyone with the link, sign-in required for file upload |

Do not give contributors edit rights on the whole drive. Not out of mistrust — one
accidental drag of a folder on a phone can scatter hundreds of entries, and nobody will
notice for weeks.

## Before letting ten people loose

Run the first **20 entries yourself with two contributors**. A convention that works on
paper breaks against real material in ways nobody predicts. Ten people filing things wrong
for three weeks costs far more than changing the setup now.
