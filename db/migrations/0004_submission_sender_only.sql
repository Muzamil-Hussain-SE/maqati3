-- 0004_submission_sender_only — an upload says who sent it, and nothing about the scholar
--
-- Decided 2026-10-26, after the first look at the upload page: contributors upload many
-- files of different scholars at once, and cannot be asked per file. Which scholar it is,
-- and how sure anyone is, is settled when an admin registers the upload as an entry --
-- where `entry.attribution` starts at 'not_sure' and gates publication. So nothing a
-- contributor types at upload time can pre-fill or weaken that, which is also why these
-- columns go instead of staying as unused claims.
--
-- Safe to drop: nothing real had been uploaded when this ran (the submission table was
-- empty on the one deployed server).

ALTER TABLE submission
    DROP CONSTRAINT kept_names_a_scholar,
    DROP CONSTRAINT kept_says_how_sure,
    DROP COLUMN scholar_id,
    DROP COLUMN scholar_other,
    DROP COLUMN topic_id,
    DROP COLUMN claimed_attribution,
    DROP COLUMN source_note,
    DROP COLUMN note;

-- The one thing still asked: who sent it, so the admin knows whom to ask about a file.
ALTER TABLE submission
    ADD CONSTRAINT kept_names_its_sender
        CHECK (state = 'awaiting_decision' OR nullif(btrim(contributor), '') IS NOT NULL);
