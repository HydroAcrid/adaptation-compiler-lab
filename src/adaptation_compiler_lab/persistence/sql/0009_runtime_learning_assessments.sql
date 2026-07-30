CREATE TABLE automatic_runtime_learning_assessments (
    assessment_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    cycle_id TEXT NOT NULL UNIQUE,
    outcome TEXT NOT NULL CHECK (outcome IN ('correct', 'false_positive', 'missed')),
    recorded_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (cycle_id) REFERENCES automatic_runtime_learning_cycles (cycle_id)
) STRICT;

CREATE INDEX automatic_runtime_learning_assessments_by_subject
    ON automatic_runtime_learning_assessments (subject_id, recorded_at, assessment_id);

CREATE TRIGGER automatic_runtime_learning_assessments_reject_update
BEFORE UPDATE ON automatic_runtime_learning_assessments
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime learning assessments are append-only');
END;

CREATE TRIGGER automatic_runtime_learning_assessments_reject_delete
BEFORE DELETE ON automatic_runtime_learning_assessments
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime learning assessments are append-only');
END;
