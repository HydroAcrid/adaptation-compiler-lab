CREATE TABLE governance_objects (
    governance_type TEXT NOT NULL CHECK (
        governance_type IN (
            'signer_identity',
            'consent_receipt',
            'capture_receipt',
            'governance_event'
        )
    ),
    object_id TEXT NOT NULL,
    schema_version TEXT NOT NULL CHECK (schema_version = '1.0'),
    subject_id TEXT NOT NULL,
    signer_identity_id TEXT NOT NULL,
    key_fingerprint TEXT NOT NULL CHECK (length(key_fingerprint) = 71),
    canonicalization_version TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    signature_base64 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    retention_until TEXT,
    PRIMARY KEY (governance_type, object_id)
) STRICT;

CREATE INDEX governance_objects_by_subject
    ON governance_objects (subject_id, governance_type, created_at, object_id);
CREATE INDEX governance_objects_by_signer
    ON governance_objects (signer_identity_id, created_at, object_id);
CREATE INDEX governance_objects_by_digest ON governance_objects (content_sha256);

CREATE TRIGGER governance_objects_reject_update
BEFORE UPDATE ON governance_objects
BEGIN
    SELECT RAISE(ABORT, 'governance objects are append-only');
END;

CREATE TRIGGER governance_objects_reject_delete
BEFORE DELETE ON governance_objects
BEGIN
    SELECT RAISE(ABORT, 'governance objects are append-only');
END;
