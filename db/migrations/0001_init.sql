-- 0001_init — initial schema
--
-- Carries the fields that cannot be retrofitted once entries are published and their
-- URLs and citations are in circulation: attribution, span_role, citable, canonical_id,
-- and embedding partitioning by model. Most of their logic arrives in later phases.
-- They are here now on purpose. See CLAUDE.md, "Integrity is structural".

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ---------------------------------------------------------------- enums

CREATE TYPE attribution  AS ENUM ('confirmed', 'probably', 'not_sure');
CREATE TYPE visibility   AS ENUM ('draft', 'public', 'held_back');
CREATE TYPE lang         AS ENUM ('ar', 'en', 'de');

-- Only scholar_own may ever be quoted as the scholar's position.
CREATE TYPE span_role    AS ENUM ('scholar_own', 'questioner', 'quoted_other',
                                  'recited_text', 'unclear');

CREATE TYPE review_state AS ENUM ('not_started', 'draft_ready', 'in_progress',
                                  'awaiting_review', 'needs_fixes', 'approved');

-- How a piece of text came to exist. Decides what the site may claim about it.
CREATE TYPE provenance   AS ENUM ('human', 'asr', 'machine_translation', 'imported');

-- Whether a topic may be synthesised over, sources-only, or kept out entirely.
CREATE TYPE content_class AS ENUM ('open', 'sources_only', 'excluded');

CREATE TYPE hukm         AS ENUM ('wajib', 'mandub', 'mubah', 'makruh', 'haram',
                                  'tafsil', 'none');

-- Is this ruling general, or was it given for one concrete case?
CREATE TYPE generality   AS ENUM ('general', 'case_specific', 'unclear');

-- ---------------------------------------------------------------- master data

CREATE TABLE scholar (
    id          text PRIMARY KEY,                      -- 'ibn-uthaymin'
    name_ar     text NOT NULL,
    name_en     text NOT NULL,
    is_person   boolean NOT NULL DEFAULT true,         -- false for committees
    died_h      int,
    died_ce     int,
    note        text
);

CREATE TABLE topic (
    id            text PRIMARY KEY,                    -- 'fiqh' or 'fiqh.taharah'
    parent_id     text REFERENCES topic(id),
    name_ar       text NOT NULL,
    name_en       text NOT NULL,
    content_class content_class NOT NULL DEFAULT 'open'
);

-- ---------------------------------------------------------------- entries

CREATE TABLE entry (
    id                 text PRIMARY KEY,               -- 'uthaymin-000421', never changes
    scholar_id         text NOT NULL REFERENCES scholar(id),
    attribution        attribution NOT NULL DEFAULT 'not_sure',
    visibility         visibility  NOT NULL DEFAULT 'draft',

    title_ar           text,
    title_en           text,
    question_ar        text,
    topic_id           text REFERENCES topic(id),
    hukm               hukm,
    generality         generality NOT NULL DEFAULT 'unclear',

    source_url         text,
    source_platform_id text UNIQUE,                    -- dedup layer 1
    source_kind        text,                           -- official | reshare | private | unknown
    recorded_on        date,
    duration_sec       int,

    sha256             text UNIQUE,                    -- dedup layer 2
    simhash_ar         bigint,                         -- dedup layer 4

    -- Near-duplicates are linked, never deleted. Only the canonical entry is indexed.
    canonical_id       text REFERENCES entry(id),

    submitted_by       text,
    reviewed_by        text,
    reviewed_on        date,
    notes              text,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),

    -- An entry may only be public when attribution is established.
    CONSTRAINT public_requires_attribution
        CHECK (visibility <> 'public' OR attribution <> 'not_sure')
);

CREATE INDEX entry_scholar_idx   ON entry (scholar_id);
CREATE INDEX entry_topic_idx     ON entry (topic_id);
CREATE INDEX entry_canonical_idx ON entry (canonical_id);
CREATE INDEX entry_public_idx    ON entry (visibility) WHERE visibility = 'public';

-- Audio fingerprint windows (dedup layer 3). Overlapping 30s windows, not one per file:
-- a single whole-file print misses the common case, the same fatwa with a different intro.
CREATE TABLE entry_fingerprint (
    entry_id    text NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    window_idx  int  NOT NULL,
    offset_ms   int  NOT NULL,
    fingerprint bytea NOT NULL,
    PRIMARY KEY (entry_id, window_idx)
);
CREATE INDEX entry_fingerprint_lookup ON entry_fingerprint (fingerprint);

-- ---------------------------------------------------------------- transcript

-- The timeline exists once, independent of language. Translations attach to it, so a
-- German sentence always resolves to the same second as its Arabic original.
CREATE TABLE segment (
    id          bigserial PRIMARY KEY,
    entry_id    text NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    idx         int  NOT NULL,                         -- row order, 0-based
    t_start_ms  int  NOT NULL,
    t_end_ms    int,

    span_role   span_role NOT NULL DEFAULT 'unclear',

    -- Is this timestamp human-confirmed? Uncitable segments stay in the index for
    -- context but never produce a citation.
    citable     boolean NOT NULL DEFAULT false,

    UNIQUE (entry_id, idx)
);
CREATE INDEX segment_entry_time_idx ON segment (entry_id, t_start_ms);

CREATE TABLE segment_text (
    segment_id  bigint NOT NULL REFERENCES segment(id) ON DELETE CASCADE,
    lang        lang   NOT NULL,
    text_raw    text   NOT NULL,                       -- as written; what gets displayed
    text_norm   text,                                  -- normalised; what gets searched
    provenance  provenance NOT NULL,
    PRIMARY KEY (segment_id, lang)
);

-- Review state is per language, because material arrives unevenly: some entries have an
-- Arabic transcript already, some are audio only, some have Arabic and English but no German.
CREATE TABLE entry_language (
    entry_id   text NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    lang       lang NOT NULL,
    state      review_state NOT NULL DEFAULT 'not_started',
    assignee   text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (entry_id, lang)
);

-- ---------------------------------------------------------------- retrieval (phase 2)

CREATE TABLE chunk (
    id            bigserial PRIMARY KEY,
    entry_id      text NOT NULL REFERENCES entry(id) ON DELETE CASCADE,
    lang          lang NOT NULL,
    seg_from      int  NOT NULL,
    seg_to        int  NOT NULL,
    text_raw      text NOT NULL,
    text_norm     text NOT NULL
);
CREATE INDEX chunk_entry_idx ON chunk (entry_id, lang);

-- Partitioned by model so an embedder change is a new partition and a config switch,
-- not a migration. The embedder is a one-way street: changing it means re-indexing the
-- whole corpus in three languages. Projects this size break at exactly that moment,
-- because the reindex gets planned as a one-off event.
CREATE TABLE embedding (
    chunk_id  bigint NOT NULL REFERENCES chunk(id) ON DELETE CASCADE,
    model_id  text   NOT NULL,
    vec       halfvec(1024) NOT NULL,
    PRIMARY KEY (chunk_id, model_id)
) PARTITION BY LIST (model_id);

CREATE TABLE embedding_bge_m3 PARTITION OF embedding FOR VALUES IN ('bge-m3');

CREATE TABLE app_config (
    key   text PRIMARY KEY,
    value text NOT NULL
);
INSERT INTO app_config (key, value) VALUES ('active_embedding_model_id', 'bge-m3');

-- ---------------------------------------------------------------- the quotable view
--
-- Everything the answer path is allowed to cite. The application database user gets
-- SELECT on this view and NOT on the base tables, so the filter cannot be forgotten in
-- a query written months from now.

CREATE VIEW segment_citable AS
SELECT s.id         AS segment_id,
       s.entry_id,
       s.idx,
       s.t_start_ms,
       s.t_end_ms,
       e.scholar_id,
       e.topic_id,
       e.attribution,
       st.lang,
       st.text_raw,
       st.text_norm
FROM segment s
JOIN entry e        ON e.id = s.entry_id
JOIN segment_text st ON st.segment_id = s.id
JOIN entry_language el ON el.entry_id = e.id AND el.lang = st.lang
LEFT JOIN topic t   ON t.id = e.topic_id
WHERE e.visibility   = 'public'
  AND e.attribution <> 'not_sure'
  AND e.canonical_id IS NULL          -- variants are never indexed, only linked
  AND s.citable
  AND s.span_role    = 'scholar_own'  -- never quote the questioner or a refuted view
  AND el.state       = 'approved'
  AND COALESCE(t.content_class, 'open') <> 'excluded';

-- ---------------------------------------------------------------- jobs

CREATE TABLE job (
    id           bigserial PRIMARY KEY,
    kind         text NOT NULL,
    payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
    state        text NOT NULL DEFAULT 'pending',
    attempts     int  NOT NULL DEFAULT 0,
    run_after    timestamptz NOT NULL DEFAULT now(),
    locked_until timestamptz,
    -- Proof of possession, set when the job is claimed. Finishing a job requires
    -- presenting it: a worker whose lease lapsed and whose job was handed on must not
    -- be able to mark that job done or reschedule it out from under its new owner.
    locked_by    text,
    last_error   text,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX job_claim_idx ON job (state, run_after) WHERE state = 'pending';

-- ---------------------------------------------------------------- audit

-- Append-only. Who changed what, when. Needed to answer "where did this translation
-- come from" long after the session that produced it.
CREATE TABLE revision_log (
    id          bigserial PRIMARY KEY,
    entity      text NOT NULL,
    entity_id   text NOT NULL,
    action      text NOT NULL,
    actor       text NOT NULL,
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX revision_log_entity_idx ON revision_log (entity, entity_id, created_at);

CREATE RULE revision_log_no_update AS ON UPDATE TO revision_log DO INSTEAD NOTHING;
CREATE RULE revision_log_no_delete AS ON DELETE TO revision_log DO INSTEAD NOTHING;
