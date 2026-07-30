CREATE TABLE automatic_runtime_learning_cycles (
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

CREATE TABLE automatic_runtime_learning_review_queue (
    queue_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (cycle_id) REFERENCES automatic_runtime_learning_cycles (cycle_id)
) STRICT;

CREATE TABLE automatic_runtime_learning_governance_events (
    event_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (cycle_id) REFERENCES automatic_runtime_learning_cycles (cycle_id)
) STRICT;

CREATE TABLE automatic_runtime_task_activations (
    activation_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    state_digest TEXT NOT NULL CHECK (length(state_digest) = 64),
    activated_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (state_digest) REFERENCES automatic_runtime_states (state_digest)
) STRICT;

CREATE TABLE automatic_runtime_activation_governance_events (
    event_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    activation_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (activation_id) REFERENCES automatic_runtime_task_activations (activation_id)
) STRICT;

CREATE TABLE automatic_runtime_target_delivery_acknowledgements (
    acknowledgement_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    activation_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('completed', 'failed')),
    acknowledged_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (activation_id) REFERENCES automatic_runtime_task_activations (activation_id)
) STRICT;

CREATE TABLE automatic_runtime_source_checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    committed_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    UNIQUE (subject_id, source_id, sequence)
) STRICT;

CREATE TABLE automatic_runtime_activation_feedback (
    feedback_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    activation_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('helped', 'hurt', 'irrelevant')),
    recorded_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (activation_id) REFERENCES automatic_runtime_task_activations (activation_id)
) STRICT;

CREATE INDEX automatic_runtime_learning_cycles_by_subject
    ON automatic_runtime_learning_cycles (subject_id, created_at, cycle_id);

CREATE INDEX automatic_runtime_learning_review_queue_by_subject
    ON automatic_runtime_learning_review_queue (subject_id, created_at, queue_id);

CREATE INDEX automatic_runtime_learning_events_by_subject
    ON automatic_runtime_learning_governance_events (subject_id, occurred_at, event_id);

CREATE INDEX automatic_runtime_task_activations_by_subject
    ON automatic_runtime_task_activations (subject_id, activated_at, activation_id);

CREATE INDEX automatic_runtime_activation_events_by_subject
    ON automatic_runtime_activation_governance_events (subject_id, occurred_at, event_id);

CREATE INDEX automatic_runtime_delivery_acknowledgements_by_subject
    ON automatic_runtime_target_delivery_acknowledgements (
        subject_id,
        acknowledged_at,
        acknowledgement_id
    );

CREATE INDEX automatic_runtime_source_checkpoints_by_subject
    ON automatic_runtime_source_checkpoints (subject_id, source_id, sequence);

CREATE INDEX automatic_runtime_activation_feedback_by_subject
    ON automatic_runtime_activation_feedback (subject_id, recorded_at, feedback_id);

CREATE TRIGGER automatic_runtime_learning_cycles_reject_update
BEFORE UPDATE ON automatic_runtime_learning_cycles
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime learning cycles are append-only');
END;

CREATE TRIGGER automatic_runtime_learning_cycles_reject_delete
BEFORE DELETE ON automatic_runtime_learning_cycles
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime learning cycles are append-only');
END;

CREATE TRIGGER automatic_runtime_learning_review_queue_reject_update
BEFORE UPDATE ON automatic_runtime_learning_review_queue
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime learning review queue is append-only');
END;

CREATE TRIGGER automatic_runtime_learning_review_queue_reject_delete
BEFORE DELETE ON automatic_runtime_learning_review_queue
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime learning review queue is append-only');
END;

CREATE TRIGGER automatic_runtime_learning_events_reject_update
BEFORE UPDATE ON automatic_runtime_learning_governance_events
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime learning events are append-only');
END;

CREATE TRIGGER automatic_runtime_learning_events_reject_delete
BEFORE DELETE ON automatic_runtime_learning_governance_events
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime learning events are append-only');
END;

CREATE TRIGGER automatic_runtime_task_activations_reject_update
BEFORE UPDATE ON automatic_runtime_task_activations
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime task activations are append-only');
END;

CREATE TRIGGER automatic_runtime_task_activations_reject_delete
BEFORE DELETE ON automatic_runtime_task_activations
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime task activations are append-only');
END;

CREATE TRIGGER automatic_runtime_activation_events_reject_update
BEFORE UPDATE ON automatic_runtime_activation_governance_events
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime activation events are append-only');
END;

CREATE TRIGGER automatic_runtime_activation_events_reject_delete
BEFORE DELETE ON automatic_runtime_activation_governance_events
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime activation events are append-only');
END;

CREATE TRIGGER automatic_runtime_delivery_acknowledgements_reject_update
BEFORE UPDATE ON automatic_runtime_target_delivery_acknowledgements
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime delivery acknowledgements are append-only');
END;

CREATE TRIGGER automatic_runtime_delivery_acknowledgements_reject_delete
BEFORE DELETE ON automatic_runtime_target_delivery_acknowledgements
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime delivery acknowledgements are append-only');
END;

CREATE TRIGGER automatic_runtime_source_checkpoints_reject_update
BEFORE UPDATE ON automatic_runtime_source_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime source checkpoints are append-only');
END;

CREATE TRIGGER automatic_runtime_source_checkpoints_reject_delete
BEFORE DELETE ON automatic_runtime_source_checkpoints
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime source checkpoints are append-only');
END;

CREATE TRIGGER automatic_runtime_activation_feedback_reject_update
BEFORE UPDATE ON automatic_runtime_activation_feedback
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime activation feedback is append-only');
END;

CREATE TRIGGER automatic_runtime_activation_feedback_reject_delete
BEFORE DELETE ON automatic_runtime_activation_feedback
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime activation feedback is append-only');
END;
