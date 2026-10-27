-- 0005_admin — who may work on uploads, and what they did
--
-- CLAUDE.md, "The Admin Workflow". Admins sign in with Google; this table is the list of
-- addresses allowed in, checked on every request, so removing a row locks that person out
-- at once. Every action an admin takes is appended to `admin_log` with who did it.

CREATE TABLE admin (
    -- Stored lower-cased and trimmed, so a lookup is a plain equality and "Yusuf@X.org"
    -- and "yusuf@x.org" cannot become two admins.
    email    text PRIMARY KEY CHECK (email = lower(btrim(email)) AND email <> ''),
    name     text,
    added_at timestamptz NOT NULL DEFAULT now(),
    added_by text
);

-- Append-only by convention and by absence of any code path that updates or deletes it.
CREATE TABLE admin_log (
    id          bigserial PRIMARY KEY,
    at          timestamptz NOT NULL DEFAULT now(),
    admin_email text NOT NULL,
    action      text NOT NULL,
    subject     text,
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX admin_log_at_idx ON admin_log (at DESC);

-- The six-digit part of an entry id ('ibn-uthaymin-000421'). One sequence for the whole
-- archive: race-free, never reused, and an id never changes once published.
CREATE SEQUENCE entry_number_seq;

ALTER TABLE submission
    ADD COLUMN registered_by text,
    ADD COLUMN registered_at timestamptz;
