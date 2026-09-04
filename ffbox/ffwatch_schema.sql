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
    kind                TEXT,                -- bug_report | suggestion | ask | mention
                                             -- | directive | operator_dm | shell | web
                                             -- shell and web are the LOCAL kinds: no Discord
                                             -- side. See LOCAL_KINDS in ffwatch.py, which is
                                             -- what enforces that. They take the dev lane,
                                             -- like an operator directive does; what makes
                                             -- them different is the absence of a thread, not
                                             -- a lane of their own.
    -- Which watch entry this conversation belongs to, recorded at ingest from the doorbell
    -- rather than reverse-mapped from a channel id later. It is what venue and engage are
    -- looked up by (design/trusted_ingress_design.txt section 5). NULL for a conversation that
    -- belongs to no watched channel: a mention somewhere else, a DM, a shell prompt.
    watch_alias         TEXT,
    title               TEXT,
    opener_discord_id   TEXT,
    state               TEXT    NOT NULL DEFAULT 'idle',  -- idle | queued | running | blocked | closed
    -- 1 when the conversation IS a Discord thread, so thread_id is a channel id and a reply
    -- can be posted straight to it. 0 for a reply chain in a text channel, where thread_id is
    -- the ROOT MESSAGE id and posting there would 404 — that reply goes to channel_id with
    -- --reply-to. The sender cannot tell these apart from the ids alone.
    is_thread           INTEGER NOT NULL DEFAULT 0,
    session_id          TEXT,
    session_generation  INTEGER NOT NULL DEFAULT 1,
    base_sha            TEXT,
    -- answer | triage | fix | dev. Written by queue_turn from the LAST turn queued, so it is a
    -- convenience for the list view; turn.lane is the per-turn truth. There was a fifth value,
    -- `shell`, until the local ingress was folded into dev (schema v8, 2026-08-23) — init_schema
    -- rewrites any row that still says it, because the web page builds its lane filter from
    -- DISTINCT over this column and would otherwise keep offering a lane nothing can produce.
    lane                TEXT,
    in_watermark_id     TEXT,
    out_watermark_id    TEXT,
    verdict             TEXT,
    -- How far the web UI has been read through: the value COALESCE(last_activity_at,
    -- created_at) had at the moment somebody ticked this conversation off, or NULL for one
    -- nobody has. A TIMESTAMP AND NOT A FLAG, deliberately: a flag would leave a thread you
    -- triaged on Monday marked read after a player replies to it on Tuesday, and the unread
    -- queue exists to show you exactly that. `read_through < last_activity_at` is the
    -- definition of "something has happened since you looked", so new activity un-reads the
    -- row on its own and ticking it again records the newer moment. Nothing in the pipeline
    -- reads this column — ffwatch owns the write, ffweb is the only reader — but it lives
    -- here rather than in a file beside the database so the record travels with the record.
    read_through        TEXT,
    -- THE BRANCH THIS CONVERSATION OWNS, claimed by the first run of it that actually pushes
    -- and never reassigned. A conversation is one piece of work however many turns it takes,
    -- so turn 4's fix belongs on the same branch as turn 3's, in front of the same reviewer,
    -- under the same pull request. Before this column each publishing run invented its own
    -- name — the published name carries the run id — and a conversation that took three
    -- attempts left three branches on origin, two of them abandoned, with no way to tell from
    -- the outside which one was current.
    --
    -- Its presence is also what CHANGES THE NEXT LAUNCH: a conversation with a branch starts
    -- its next run on that branch's head rather than at the pinned base sha, and the agent is
    -- told to commit onto it rather than to make one. NULL means no run of this conversation
    -- has published yet, which is the normal state for anything that only ever answered a
    -- question.
    --
    -- Written only after the push succeeds, so it names a branch that exists on origin. That
    -- is deliberately not true of run.branch, which is written at launch as the name the
    -- container was told to start on; `pushed` is what makes that one real.
    branch              TEXT,
    -- WHICH KIND OF AGENT CONTAINER runs this conversation's turns: 'ffagent' or 'ffdev'.
    --
    -- SETTLED BY THE OPENING TURN and never moved afterwards, which is why the web page offers
    -- the choice on its new-prompt box and not on its reply box. A conversation is pinned to a
    -- base sha, resumes one session transcript and owns one branch; changing the class under it
    -- would change the clocks that session has been running under and, once the two classes
    -- differ on base_ref, the tree its transcript has been citing file:line positions against.
    --
    -- NOT NULL DEFAULT 'ffagent', so every conversation that predates classes reads as what it
    -- actually was, and ffweb's SELECT DISTINCT filter dropdowns never see a blank.
    --
    -- A DISCORD conversation gets no dropdown either: it is opened in the class the "discord"
    -- section's user_pool/operator_pool pair names, chosen by whether the account that opened
    -- it is in trust.operators. Same rule as everywhere else -- whoever OPENED it decides, and
    -- an operator answering later in a stranger's thread does not promote it.
    agent_class         TEXT NOT NULL DEFAULT 'ffagent',
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
    created_at              TEXT,
    -- Was the bot spoken to: @-mentioned, or this is a reply to one of its own messages.
    -- Computed at ingest from the fetched message and stored, because the engagement gate
    -- needs it long after the raw Discord payload is gone, and because "being spoken to" is
    -- the one signal that decides a turn without asking a model
    -- (design/trusted_ingress_design.txt section 5).
    addressed               INTEGER NOT NULL DEFAULT 0,
    -- Set only when the gate declined this message: 'none', plus why. A declined message stays
    -- turn_id NULL so it still reads as history, and this column is what stops the scheduler
    -- reconsidering it on every pass. NULL means "not declined" and says nothing about whether
    -- a turn was made.
    gate                    TEXT,
    gate_reason             TEXT
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
    error                   TEXT,
    -- The triage turn whose AUTOFIX verdict enqueued this one (design section 13). It is also
    -- the dedupe key: one fix turn per triage verdict, however many times the scheduler runs.
    parent_turn_id          INTEGER REFERENCES turn(id) ON DELETE SET NULL,
    -- The base sha this turn deliberately moved OFF. A conversation pins its base for its
    -- lifetime; escalating to the fix lane is the one moment that re-bases, and the prompt has
    -- to say so or the model reasons from line numbers gathered against the older tree
    -- (design section 6).
    rebased_from            TEXT,
    -- Harness instruction for a turn nobody sent a message for — the autofix hand-off carries
    -- the triager's change outline here, since there is no new Discord message to carry it.
    note                    TEXT,
    -- WHO asked and WHERE the answer goes (design/trusted_ingress_design.txt sections 3 and 4).
    -- Both are decided by the host from config and from Discord's authenticated author id, with
    -- no model involved, and both are recorded so the web page can show why a run was allowed
    -- to say what it said. tier is a property of the TURN, not of the conversation: a player
    -- replying under an operator's message must not inherit their clearance.
    trust_tier              TEXT,            -- operator | player
    trust_actor             TEXT,            -- the snowflake, or the unix user for a shell turn
    trust_reason            TEXT,
    venue                   TEXT             -- public | private
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
    patch_path          TEXT,        -- the harvested patch, for a human to read
    -- Publication (design section 17). Every one of these comes from git or from the GitHub API
    -- response, never from the agent's summary, so they stay correct when the summary claims a
    -- branch that was never pushed or a PR that was never opened.
    bundle_path         TEXT,
    changed_files       INTEGER,
    branch              TEXT,
    pushed              INTEGER NOT NULL DEFAULT 0,
    pr_number           INTEGER,
    pr_url              TEXT,
    -- Why there is no branch, or why there is a branch but no pull request. Confidence and a
    -- failed verification gate the PR, never the branch: work is always published so it cannot
    -- be lost, and only the proposal to merge is withheld.
    no_branch_reason    TEXT,
    no_pr_reason        TEXT,
    verify_secs         REAL,
    -- The branch this run's work was based on, which is what its pull request targets. NULL
    -- when nothing was published, or when the base could not be established and the default
    -- was used.
    pr_base             TEXT,
    -- WAS THE BRANCH ALREADY ON ORIGIN when this run pushed to it? 0 for the turn that created
    -- it, 1 for every later turn of the same conversation, which adds commits to a branch a
    -- reviewer may already be reading. Written at publish time from conversation.branch, read
    -- back by the reply so it says "created" or "updated" and never guesses which.
    branch_existed      INTEGER NOT NULL DEFAULT 0,
    -- WHICH CLAUDE SUBSCRIPTION PAID FOR THIS RUN (v15), as the secrets.env variable holding
    -- its token: CLAUDE_CODE_OAUTH_TOKEN2, say. The NAME, never the token, and never a bare
    -- number either — the pool skips blank slots, so "the second key" and
    -- "CLAUDE_CODE_OAUTH_TOKEN2" stop meaning the same thing the moment somebody revokes the
    -- first, and only one of the two is still true afterwards.
    --
    -- NULL on a box holding one account, where there is nothing to record, and on every row
    -- written before the column existed.
    claude_key          TEXT
);

CREATE INDEX IF NOT EXISTS idx_run_turn ON run(turn_id);
CREATE INDEX IF NOT EXISTS idx_run_inflight ON run(terminal_state);

-- Its own table, not columns on run, because the harness produces it AFTER the agent exits.
-- The agent must have no way to write its own verification result: the container task deletes
-- anything at the report path before running, and by then the agent process is gone.
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
    evidence        TEXT,
    -- ran=0 because there was nothing to test, which is not the same fact as ran=0 because the
    -- suite could not be run. Only the second is a warning worth showing a human.
    skipped         INTEGER NOT NULL DEFAULT 0
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
--
-- 'approved' is the approval-before-send state (config approve_before_send). With that flag
-- on, the sender only sends rows a human — `ffwatch approve <id>`, later the web UI — has
-- moved out of 'pending'; with it off, 'pending' is sent directly and 'approved' never occurs.
CREATE TABLE IF NOT EXISTS outbound (
    id              INTEGER PRIMARY KEY,
    run_id          INTEGER REFERENCES run(id) ON DELETE SET NULL,
    conversation_id INTEGER REFERENCES conversation(id) ON DELETE CASCADE,
    action          TEXT NOT NULL,               -- post | react | unreact | edit | ask
                                                 -- | thread-create
    payload_json    TEXT,
    nonce           TEXT NOT NULL UNIQUE,
    -- 'undeliverable' is the split reply's private half with nowhere to go (design section 7):
    -- terminal, never retried, and deliberately not 'pending', because `ffwatch approve`
    -- releases those and releasing this one would try the same closed DM again.
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | sent | rejected
                                                      -- | dry | undeliverable
    discord_id      TEXT,
    reject_reason   TEXT,
    created_at      TEXT,
    sent_at         TEXT,
    -- Retry bookkeeping. A transient failure leaves the row retryable with backoff computed
    -- from last_attempt_at; after max_send_attempts it is rejected rather than retried forever.
    attempts        INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    last_error      TEXT,
    -- The placeholder id the container's shim printed for this intent, so a run's own log and
    -- the real Discord id can be lined up afterwards.
    local_id        TEXT
);

CREATE INDEX IF NOT EXISTS idx_outbound_status ON outbound(status);
CREATE INDEX IF NOT EXISTS idx_outbound_conversation ON outbound(conversation_id);

-- WHEN THIS BOX STARTED WATCHING A CHANNEL (schema v13). One row per alias in the config's
-- `watch` block, written by the first ffwatch invocation that sees the alias and never
-- rewritten after that.
--
-- The problem it solves: sweep() re-reads every watched channel with no notion of when the
-- watching began, so adding an alias that has been live for months made its entire visible
-- history arrive as new — up to sweep_limit active threads, each of which "opens a thread"
-- and is therefore answered whatever the engagement policy says. That is what happened to
-- #dev-chat, and the only fix available at the time was to not attach the channel.
--
-- watermark_id is a Discord snowflake, so it is a TIME: nothing minted at or before it can
-- produce a turn. '0' means no cutoff at all, which is what an alias gets on its FIRST sighting
-- when the database already holds conversations for it — the upgrade path, where a channel this
-- box has been answering for months meets this table for the first time.
--
-- `attached` is what makes a RE-attach different from a restart. A channel dropped from the
-- watch block is recorded as detached rather than forgotten, so putting it back five years
-- later stamps a fresh watermark and joins it as the new channel it has become. Without the
-- flag, "have I seen this alias before" is the only question the table can answer, and the
-- answer would be yes to a channel nobody has read in five years.
--
-- To take a cutoff back and let the backlog in, delete the row (or set watermark_id to '0')
-- and restart: the next sweep re-reads the channel and nothing is gated.
CREATE TABLE IF NOT EXISTS watch_attach (
    alias        TEXT PRIMARY KEY,
    attached_at  TEXT NOT NULL,
    watermark_id TEXT NOT NULL,
    attached     INTEGER NOT NULL DEFAULT 1,
    detached_at  TEXT
);
