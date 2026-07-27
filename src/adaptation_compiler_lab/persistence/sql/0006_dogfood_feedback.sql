CREATE TABLE dogfood_feedback (
    feedback_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    stage INTEGER NOT NULL CHECK (stage BETWEEN 1 AND 3),
    task_id TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('helped', 'hurt', 'irrelevant')),
    recorded_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64)
) STRICT;

CREATE INDEX dogfood_feedback_by_subject
    ON dogfood_feedback (subject_id, recorded_at, feedback_id);

CREATE TRIGGER dogfood_feedback_reject_update
BEFORE UPDATE ON dogfood_feedback
BEGIN
    SELECT RAISE(ABORT, 'dogfood feedback is append-only');
END;

CREATE TRIGGER dogfood_feedback_reject_delete
BEFORE DELETE ON dogfood_feedback
BEGIN
    SELECT RAISE(ABORT, 'dogfood feedback is append-only');
END;
