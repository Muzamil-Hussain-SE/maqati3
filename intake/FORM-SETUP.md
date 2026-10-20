# Google Form "Submit material" — exact setup

This is the only thing most contributors will ever touch. Build it exactly like this, then
link the responses to the register sheet.

**Settings:** collect email addresses = on · allow file upload = on · one response per
person = **off** (they submit many) · confirmation message = see bottom.

---

| # | Question | Type | Required | Options / help text |
|---|---|---|---|---|
| 1 | Your name | Dropdown | yes | The contributors' names. Add new ones as people join. |
| 2 | Which scholar? | Dropdown | yes | From `scholars.csv`, plus a final option **"Not in the list"** |
| 3 | If not in the list, who? | Short answer | no | Only fill if you picked "Not in the list" |
| 4 | Link to where you found it | Short answer | yes | *Help text: "YouTube, Telegram, a website — wherever you got it. If you really don't know, write 'unknown' and explain below."* |
| 5 | Are you sure it is really this scholar? | Multiple choice | yes | `Yes — official channel or website` / `Pretty sure` / `Not sure` |
| 6 | What is it about? | Dropdown | yes | The 8 main topics from `topics.yml`, plus **"Not sure"** |
| 7 | The question being asked, if you know it | Paragraph | no | Arabic or English, whatever you have |
| 8 | Upload the file | File upload | no | *Help text: "Only if it is not available online. A link is enough."* Allow video + audio, max 1 file, up to 1 GB |
| 9 | Does it already have a transcript? | Multiple choice | yes | `No` / `Yes, Arabic` / `Yes, Arabic + English` / `Yes, other` |
| 10 | Anything we should know? | Paragraph | no | *Help text: "e.g. the recording starts with 10s of music, or the sound is bad after 3 minutes."* |

**Confirmation message:**

> Jazākallāhu khayran. The admin will review this shortly. You can submit another one with
> the same link.

---

## Why these ten and not more

Every extra field costs submissions. These ten are the ones that cannot be reconstructed
later by anyone else:

- **4 (source link)** — without it the entry is worthless to us; nobody else can find it again.
- **5 (attribution)** — only the person who found it knows how solid the source felt.
- **9 (existing transcript)** — decides whether the entry costs 10 minutes or 4 hours of
  human work. This is the single most valuable scheduling signal we get.

Everything else — ID, duration, exact date, sub-topics — the admin or the system fills in.
Never ask a contributor for something a machine can work out.

---

## Where the answers go

Form responses land in a sheet automatically. Add these columns **to the right** of the
form's own columns — the form never writes there, only the admin and the contributors do:

`id` · `attribution` · `priority` · `status_ar` · `assignee_ar` · `status_en` ·
`assignee_en` · `status_de` · `assignee_de` · `doc_link` · `audio_link` · `reviewer` ·
`reviewed_on` · `visibility` · `notes`

See `REGISTER.md` for what each one means.

Uploaded files land in a folder the form creates by itself. Leave it alone — the admin
moves them into the library when registering.
