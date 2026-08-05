CREATE TABLE automatic_runtime_learning_review_resolutions (
    resolution_id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL UNIQUE,
    subject_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL UNIQUE,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    resolved_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (queue_id) REFERENCES automatic_runtime_learning_review_queue (queue_id),
    FOREIGN KEY (cycle_id) REFERENCES automatic_runtime_learning_cycles (cycle_id)
) STRICT;

CREATE INDEX automatic_runtime_learning_review_resolutions_by_subject
    ON automatic_runtime_learning_review_resolutions (
        subject_id,
        resolved_at,
        resolution_id
    );

CREATE TRIGGER automatic_runtime_learning_review_resolutions_reject_update
BEFORE UPDATE ON automatic_runtime_learning_review_resolutions
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime learning review resolutions are append-only');
END;

CREATE TRIGGER automatic_runtime_learning_review_resolutions_reject_delete
BEFORE DELETE ON automatic_runtime_learning_review_resolutions
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime learning review resolutions are append-only');
END;
