-- ffwatch.db — the conversation manager's system of record.
--
-- Applied by `ffwatch init` and re-applied on every start; every statement is IF NOT EXISTS so
-- this file is idempotent. Column names are fixed by the design document (section 10) and are
-- what the phase-4 web UI will read, so do not rename them casually — the UI is the reason the
-- phase-3 tables (verification, run.patch_path) exist here while phase 1 leaves them empty.
--
-- WAL because there is exactly one writer (ffwatch) and any number of readers (status, the web
-- UI, a human with sqlite3). The default rollback journal would block those readers for the
-- length of every write transaction.

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL
);

-- A conversation is a Discord thread, or — in a text channel — the root of a reply chain.
-- thread_id is the natural key for both cases and is what session_id is derived from, so it
-- carries the UNIQUE constraint rather than id.
CREATE TABLE IF NOT EXISTS conversation (
    id                  INTEGER PRIMARY KEY,
    guild_id            TEXT,
    channel_id          TEXT,
    thread_id           TEXT    NOT NULL UNIQUE,
    root_message_id     TEXT,
    kind                TEXT,                -- bug_report | suggestion | ask | mention | directive
    title               TEXT,
    opener_discord_id   TEXT,
    state               TEXT    NOT NULL DEFAULT 'idle',  -- idle | queued | running | blocked | closed
    session_id          TEXT,
    session_generation  INTEGER NOT NULL DEFAULT 1,
    base_sha            TEXT,
    lane                TEXT,
    in_watermark_id     TEXT,
    out_watermark_id    TEXT,
    verdict             TEXT,
    github_issue        TEXT,
    github_pr           TEXT,
    created_at          TEXT,
    last_activity_at    TEXT
);

-- discord_id UNIQUE is the message-level dedupe: a duplicate doorbell (gateway replay, a
-- catchup sweep overlapping a live event) inserts nothing and therefore cannot create a
-- second turn. It replaces 059's by-message marker files.
CREATE TABLE IF NOT EXISTS message (
    id                      INTEGER PRIMARY KEY,
    conversation_id         INTEGER NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    discord_id              TEXT    NOT NULL UNIQUE,
    direction               TEXT    NOT NULL DEFAULT 'in',   -- in | out
    author_id               TEXT,
    author_name             TEXT,
    is_bot                  INTEGER NOT NULL DEFAULT 0,
    content                 TEXT,
    referenced_discord_id   TEXT,
    turn_id                 INTEGER REFERENCES turn(id) ON DELETE SET NULL,
    created_at              TEXT
);

-- turn_id IS NULL means "not yet claimed by a turn". The scheduler's unclaimed scan is the
-- hot path over this table, hence the composite index rather than one on turn_id alone.
CREATE INDEX IF NOT EXISTS idx_message_unclaimed ON message(conversation_id, turn_id);
CREATE INDEX IF NOT EXISTS idx_message_conversation ON message(conversation_id, id);

-- blob_path is content-addressed (blobs/<sha256[0:2]>/<sha256>), so the same save file posted
-- into three threads is stored once. Discord attachment URLs are signed and expire, which is
-- why the bytes are pulled at ingest and never re-fetched.
CREATE TABLE IF NOT EXISTS attachment (
    id              INTEGER PRIMARY KEY,
    message_id      INTEGER NOT NULL REFERENCES message(id) ON DELETE CASCADE,
    filename        TEXT,
    content_type    TEXT,
    bytes           INTEGER,
    sha256          TEXT,
    blob_path       TEXT,
    kind            TEXT,        -- log | save | image | other
    discord_url     TEXT,
    downloaded_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_attachment_message ON attachment(message_id);
CREATE INDEX IF NOT EXISTS idx_attachment_sha ON attachment(sha256);

-- One turn per scheduling decision. classification_json holds whatever the classifier
-- returned, verbatim; failed_closed is broken out because the reply has to warn about it and
-- the UI has to filter on it.
CREATE TABLE IF NOT EXISTS turn (
    id                      INTEGER PRIMARY KEY,
    conversation_id         INTEGER NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    seq                     INTEGER NOT NULL,
    trigger                 TEXT,
    lane                    TEXT,
    status                  TEXT NOT NULL DEFAULT 'queued',  -- queued | running | done | failed
                                                             -- | timed_out | blocked
    classification_json     TEXT,
    failed_closed           INTEGER NOT NULL DEFAULT 0,
    failed_closed_reason    TEXT,
    queued_at               TEXT,
    started_at              TEXT,
    ended_at                TEXT,
    error                   TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_turn_seq ON turn(conversation_id, seq);
CREATE INDEX IF NOT EXISTS idx_turn_status ON turn(status);

-- container_name is recorded so recovery can address exactly the container this run named and
-- nothing else (design section 14 rule 2). terminal_state NULL means the run is still in
-- flight; at startup that is by definition a crash, because a live run cannot write its own
-- terminal state after being killed.
CREATE TABLE IF NOT EXISTS run (
    id                  INTEGER PRIMARY KEY,
    turn_id             INTEGER NOT NULL REFERENCES turn(id) ON DELETE CASCADE,
    ffbox_run_id        TEXT,
    container_name      TEXT,
    session_id          TEXT,
    resumed             INTEGER NOT NULL DEFAULT 0,
    base_sha            TEXT,
    unity               INTEGER NOT NULL DEFAULT 0,
    tools               TEXT,
    disallowed          TEXT,
    exit_code           INTEGER,
    terminal_state      TEXT,        -- done | failed | timed_out | crashed
    num_turns           INTEGER,
    cost_usd            REAL,
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    cache_read_tokens   INTEGER,
    warmup_secs         REAL,
    agent_secs          REAL,
    stream_path         TEXT,
    patch_path          TEXT         -- phase 3: the harvested bundle/patch
);

CREATE INDEX IF NOT EXISTS idx_run_turn ON run(turn_id);
CREATE INDEX IF NOT EXISTS idx_run_inflight ON run(terminal_state);

-- Its own table, not columns on run, because the harness produces it AFTER the agent exits.
-- The agent must have no way to write its own verification result. Unpopulated until phase 3.
CREATE TABLE IF NOT EXISTS verification (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    ran             INTEGER NOT NULL DEFAULT 0,
    compiled        INTEGER,
    compile_errors  TEXT,
    tests_run       INTEGER,
    tests_passed    INTEGER,
    tests_failed    INTEGER,
    results_path    TEXT,            -- ALWAYS per-invocation; never Unity's shared file
    evidence        TEXT
);

CREATE INDEX IF NOT EXISTS idx_verification_run ON verification(run_id);

-- An INDEX over the session JSONL, not a replacement for it: the file stays source of truth
-- and payload_json keeps full fidelity for every indexed row. One JSONL record can produce
-- several rows (a text block, a thinking block and two tool_use blocks share one uuid), so
-- uuid is deliberately not unique — (run_id, seq) is the ordering key.
CREATE TABLE IF NOT EXISTS transcript_event (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER NOT NULL REFERENCES run(id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,
    uuid            TEXT,
    parent_uuid     TEXT,
    is_sidechain    INTEGER NOT NULL DEFAULT 0,
    agent           TEXT,
    type            TEXT,        -- user | assistant | thinking | tool_use | tool_result
    tool_name       TEXT,
    text            TEXT,
    payload_json    TEXT,
    ts              TEXT
);

CREATE INDEX IF NOT EXISTS idx_transcript_run_seq ON transcript_event(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_transcript_parent ON transcript_event(parent_uuid);

-- Persist before post. Every outbound message exists here before it exists in Discord, so a
-- Discord outage cannot lose one and the web UI gets a moderation queue for free by rendering
-- status='pending'. nonce is the outbound row's uuid, sent to Discord with enforce_nonce so a
-- retry after a crash cannot double-post.
CREATE TABLE IF NOT EXISTS outbound (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER REFERENCES run(id) ON DELETE SET NULL,
    conversation_id INTEGER REFERENCES conversation(id) ON DELETE CASCADE,
    action          TEXT NOT NULL,               -- post | react | edit
    payload_json    TEXT,
    nonce           TEXT NOT NULL UNIQUE,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | rejected | dry
    discord_id      TEXT,
    reject_reason   TEXT,
    created_at      TEXT,
    sent_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbound_status ON outbound(status);
CREATE INDEX IF NOT EXISTS idx_outbound_conversation ON outbound(conversation_id);
