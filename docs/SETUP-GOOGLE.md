# Google access — step by step

The backend reads the Drive folder and the register sheet, and writes transcript drafts
into the entry documents. This is the fiddliest piece of setup, so here it is as a
checklist. ~20 minutes, once.

**Use an OAuth refresh token of a human account, not a service account.** A service
account has no Drive storage of its own, so anything it creates belongs to nobody and
fails with `storageQuotaExceeded` the moment the backend writes a document. Create a
dedicated project Google account for this (see `intake/DRIVE-SETUP.md`) and authorise
that one — not your personal account.

## 1. Google Cloud project

1. <https://console.cloud.google.com> → new project, e.g. `maqati3`
2. **APIs & Services → Library**, enable all three:
   - Google Drive API
   - Google Docs API
   - Google Sheets API
3. **APIs & Services → OAuth consent screen**
   - User type: **External**, publishing status **Testing** is fine
   - Add the project Google account under **Test users** — without this the consent
     flow fails with `access_denied` and the error does not say why
   - Scopes: add `.../auth/drive` and `.../auth/spreadsheets`

## 2. OAuth client

**Credentials → Create credentials → OAuth client ID → Desktop app.**

Desktop, not Web: the desktop flow uses a loopback redirect, so there is no redirect URI
to register and no HTTPS callback to host. Note the client ID and secret.

## 3. Get the refresh token

> The two helper commands below are not written yet — they land with the Drive client
> in week 2. Until then this section describes the intended flow, not something you can
> run today. Steps 1, 2 and 4 you can do now.

Run once, locally, signed in as the project account:

```bash
cd backend
uv run python -m maqati3.scripts.google_auth
```

It opens a browser, you approve, it prints the refresh token. Paste all three values
into `.env`:

```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REFRESH_TOKEN=...
```

The refresh token does not expire while the consent screen stays in **Testing** and the
account keeps approving — but it **is revoked** if the account's password changes or
access is withdrawn. If Drive calls start failing with `invalid_grant`, that is what
happened: re-run the command.

## 4. Folder and sheet IDs

From the URLs:

```
https://drive.google.com/drive/folders/1AbC...XyZ      -> DRIVE_ROOT_FOLDER_ID
https://docs.google.com/spreadsheets/d/1DeF...UvW/edit -> REGISTER_SHEET_ID
```

Share both with the project account as **Editor**.

## 5. Verify

```bash
cd backend && uv run python -m maqati3.scripts.google_check
```

Lists the four top-level folders and the register's header row. If that works, the
backend has everything it needs from Google.

## Things that cost an afternoon if you do not know them

- **`supportsAllDrives=true` and `includeItemsFromAllDrives=true` on every single Drive
  call.** Omit them on one call and that call silently returns nothing for a shared
  drive — no error, just an empty list.
- **Never join Drive files to register rows by filename.** Contributors rename things.
  The entry ID is the only stable key.
- **Polling, not push.** Drive push notifications need a public HTTPS endpoint and the
  channels expire and must be renewed. `changes.list` with a stored `startPageToken`
  every few minutes does the same job with none of that.
- Quota is 400 million units/day and free. This project will not come close.
