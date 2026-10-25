-- 0002_submission — bulk uploads waiting to be registered as entries
--
-- docs/ARCHITECTURE.md, "Revidiert 2026-10-25". A submission is a file a contributor
-- uploaded that was not rejected as a byte-identical duplicate. It is not an entry:
-- an admin still assigns the permanent id and decides attribution
-- (intake/ADMIN-GUIDE.md). What the contributor said about it is stored as a claim.
--
-- Dedup layers 2 and 3 check submissions exactly as they check entries. The common case
-- is one WhatsApp clip saved by several brothers, who all upload it before anyone has
-- registered the first copy; checking entries alone would let every copy through.

-- awaiting_decision: triaged, the contributor has not said keep or drop yet.
-- kept:              the contributor sent it in; waits for an admin.
-- registered:        an admin made an entry of it (entry_id says which).
-- A dropped upload is deleted, not marked: nothing about it is worth keeping.
CREATE TYPE submission_state AS ENUM ('awaiting_decision', 'kept', 'registered');

CREATE TABLE submission (
    sha256              text PRIMARY KEY,           -- dedup layer 2, and the upload page's key
    original_name       text NOT NULL,
    staged_path         text NOT NULL,
    duration_ms         int  NOT NULL CHECK (duration_ms >= 0),
    state               submission_state NOT NULL DEFAULT 'awaiting_decision',

    -- Match keys of every fingerprint candidate shown at upload time. Non-empty on a
    -- kept submission means the contributor heard the match and kept it anyway: the
    -- first thing an admin should look at.
    candidate_keys      text[] NOT NULL DEFAULT '{}',

    -- What the contributor said. Claims, not facts: attribution on the entry is the
    -- admin's call, however sure the contributor was.
    contributor         text,
    scholar_id          text REFERENCES scholar(id),
    scholar_other       text,                       -- "not in the list"
    topic_id            text REFERENCES topic(id),
    claimed_attribution attribution,
    source_note         text,                       -- where it came from, even "a WhatsApp group"
    note                text,

    entry_id            text UNIQUE REFERENCES entry(id),
    received_at         timestamptz NOT NULL DEFAULT now(),
    decided_at          timestamptz,

    CONSTRAINT registered_names_its_entry
        CHECK ((state = 'registered') = (entry_id IS NOT NULL)),
    -- The form's one field that can never be reconstructed later: whose words these are.
    CONSTRAINT kept_names_a_scholar
        CHECK (state = 'awaiting_decision'
               OR scholar_id IS NOT NULL
               OR nullif(btrim(scholar_other), '') IS NOT NULL),
    CONSTRAINT kept_says_how_sure
        CHECK (state = 'awaiting_decision' OR claimed_attribution IS NOT NULL)
);

CREATE INDEX submission_state_idx ON submission (state);

-- Same shape as entry_fingerprint, so a candidate search treats both alike.
CREATE TABLE submission_fingerprint (
    sha256      text NOT NULL REFERENCES submission(sha256) ON DELETE CASCADE,
    window_idx  int  NOT NULL,
    offset_ms   int  NOT NULL,
    fingerprint bytea NOT NULL,
    PRIMARY KEY (sha256, window_idx)
);
CREATE INDEX submission_fingerprint_lookup ON submission_fingerprint (fingerprint);
