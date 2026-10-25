-- 0003_fingerprint_per_recording — layer 3 compares whole recordings by bit error rate
--
-- 0001 stored one fingerprint per 30 s window and looked windows up by exact byte
-- equality. Measured on real speech, a re-encoded copy's windows are never byte-
-- identical (1-9 % of bits differ; unrelated speech ~48 %), and every forwarded clip
-- is re-encoded. So that scheme could only have caught what the SHA-256 already does.
-- See backend/src/masdar/dedup/fingerprint.py for the comparison that replaces it.
--
-- Now: one fingerprint per recording, plus a sample of its items as lookup keys. A key
-- is an unsigned 32-bit Chromaprint item, hence bigint. Both window tables were still
-- empty -- nothing had ever been fingerprinted -- so dropping them loses no data.

DROP TABLE submission_fingerprint;
DROP TABLE entry_fingerprint;

CREATE TABLE entry_fingerprint (
    entry_id  text PRIMARY KEY REFERENCES entry(id) ON DELETE CASCADE,
    algorithm smallint NOT NULL,                   -- fingerprints of different algorithms never compare
    items     bytea NOT NULL CHECK (octet_length(items) % 4 = 0)
);

CREATE TABLE entry_fingerprint_key (
    key      bigint NOT NULL,
    entry_id text   NOT NULL REFERENCES entry_fingerprint(entry_id) ON DELETE CASCADE,
    PRIMARY KEY (key, entry_id)
);
CREATE INDEX entry_fingerprint_key_owner ON entry_fingerprint_key (entry_id);

CREATE TABLE submission_fingerprint (
    sha256    text PRIMARY KEY REFERENCES submission(sha256) ON DELETE CASCADE,
    algorithm smallint NOT NULL,
    items     bytea NOT NULL CHECK (octet_length(items) % 4 = 0)
);

CREATE TABLE submission_fingerprint_key (
    key    bigint NOT NULL,
    sha256 text   NOT NULL REFERENCES submission_fingerprint(sha256) ON DELETE CASCADE,
    PRIMARY KEY (key, sha256)
);
CREATE INDEX submission_fingerprint_key_owner ON submission_fingerprint_key (sha256);
