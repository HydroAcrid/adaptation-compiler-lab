CREATE TABLE automatic_runtime_states (
    state_digest TEXT PRIMARY KEY CHECK (length(state_digest) = 64),
    subject_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK (generation >= 0),
    created_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    UNIQUE (subject_id, generation)
) STRICT;

CREATE TABLE automatic_runtime_cycles (
    cycle_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    observation_id TEXT NOT NULL,
    disposition TEXT NOT NULL,
    prior_state_digest TEXT NOT NULL CHECK (length(prior_state_digest) = 64),
    resulting_state_digest TEXT NOT NULL CHECK (length(resulting_state_digest) = 64),
    created_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    UNIQUE (subject_id, observation_id)
) STRICT;

CREATE TABLE automatic_runtime_review_queue (
    queue_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (cycle_id) REFERENCES automatic_runtime_cycles (cycle_id)
) STRICT;

CREATE TABLE automatic_runtime_governance_events (
    event_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (cycle_id) REFERENCES automatic_runtime_cycles (cycle_id)
) STRICT;

CREATE TABLE automatic_runtime_feedback (
    feedback_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('helped', 'hurt', 'irrelevant')),
    recorded_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (cycle_id) REFERENCES automatic_runtime_cycles (cycle_id)
) STRICT;

CREATE INDEX automatic_runtime_states_by_subject
    ON automatic_runtime_states (subject_id, generation);

CREATE INDEX automatic_runtime_cycles_by_subject
    ON automatic_runtime_cycles (subject_id, created_at, cycle_id);

CREATE INDEX automatic_runtime_review_queue_by_subject
    ON automatic_runtime_review_queue (subject_id, created_at, queue_id);

CREATE INDEX automatic_runtime_governance_events_by_subject
    ON automatic_runtime_governance_events (subject_id, occurred_at, event_id);

CREATE INDEX automatic_runtime_feedback_by_subject
    ON automatic_runtime_feedback (subject_id, recorded_at, feedback_id);

CREATE TRIGGER automatic_runtime_states_reject_update
BEFORE UPDATE ON automatic_runtime_states
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime states are append-only');
END;

CREATE TRIGGER automatic_runtime_states_reject_delete
BEFORE DELETE ON automatic_runtime_states
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime states are append-only');
END;

CREATE TRIGGER automatic_runtime_cycles_reject_update
BEFORE UPDATE ON automatic_runtime_cycles
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime cycles are append-only');
END;

CREATE TRIGGER automatic_runtime_cycles_reject_delete
BEFORE DELETE ON automatic_runtime_cycles
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime cycles are append-only');
END;

CREATE TRIGGER automatic_runtime_review_queue_reject_update
BEFORE UPDATE ON automatic_runtime_review_queue
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime review queue is append-only');
END;

CREATE TRIGGER automatic_runtime_review_queue_reject_delete
BEFORE DELETE ON automatic_runtime_review_queue
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime review queue is append-only');
END;

CREATE TRIGGER automatic_runtime_governance_events_reject_update
BEFORE UPDATE ON automatic_runtime_governance_events
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime governance events are append-only');
END;

CREATE TRIGGER automatic_runtime_governance_events_reject_delete
BEFORE DELETE ON automatic_runtime_governance_events
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime governance events are append-only');
END;

CREATE TRIGGER automatic_runtime_feedback_reject_update
BEFORE UPDATE ON automatic_runtime_feedback
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime feedback is append-only');
END;

CREATE TRIGGER automatic_runtime_feedback_reject_delete
BEFORE DELETE ON automatic_runtime_feedback
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime feedback is append-only');
END;
