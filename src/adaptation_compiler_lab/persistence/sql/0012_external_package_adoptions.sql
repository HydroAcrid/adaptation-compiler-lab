CREATE TABLE automatic_runtime_external_adoptions (
    resolution_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    package_digest TEXT NOT NULL CHECK (length(package_digest) = 64),
    item_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('approved', 'rejected')),
    resolved_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    UNIQUE (subject_id, package_digest, item_id)
) STRICT;

CREATE INDEX automatic_runtime_external_adoptions_by_subject
    ON automatic_runtime_external_adoptions (subject_id, resolved_at, resolution_id);

CREATE TRIGGER automatic_runtime_external_adoptions_reject_update
BEFORE UPDATE ON automatic_runtime_external_adoptions
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime external adoptions are append-only');
END;

CREATE TRIGGER automatic_runtime_external_adoptions_reject_delete
BEFORE DELETE ON automatic_runtime_external_adoptions
BEGIN
    SELECT RAISE(ABORT, 'automatic runtime external adoptions are append-only');
END;
