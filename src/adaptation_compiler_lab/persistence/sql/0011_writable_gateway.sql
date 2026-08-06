CREATE TABLE runtime_notification_inbox (
    entry_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64)
) STRICT;

CREATE TABLE runtime_notification_receipts (
    receipt_id TEXT PRIMARY KEY,
    entry_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (entry_id) REFERENCES runtime_notification_inbox (entry_id)
) STRICT;

CREATE TABLE runtime_watcher_heartbeats (
    heartbeat_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1),
    observed_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    UNIQUE (lease_id, sequence)
) STRICT;

CREATE TABLE runtime_gateway_sessions (
    session_id TEXT PRIMARY KEY,
    subject_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64)
) STRICT;

CREATE TABLE runtime_gateway_turns (
    receipt_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    sequence INTEGER NOT NULL CHECK (sequence >= 1 AND sequence <= 15),
    status TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    UNIQUE (session_id, sequence),
    FOREIGN KEY (session_id) REFERENCES runtime_gateway_sessions (session_id)
) STRICT;

CREATE TABLE runtime_workspace_change_receipts (
    receipt_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    subject_id TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL CHECK (length(raw_sha256) = 64),
    raw_size_bytes INTEGER NOT NULL CHECK (raw_size_bytes >= 0),
    raw_media_type TEXT NOT NULL,
    raw_relative_path TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (session_id) REFERENCES runtime_gateway_sessions (session_id)
) STRICT;

CREATE TABLE runtime_change_application_receipts (
    receipt_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    FOREIGN KEY (session_id) REFERENCES runtime_gateway_sessions (session_id)
) STRICT;

CREATE TABLE runtime_verification_receipts (
    receipt_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    completed_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    UNIQUE (session_id, command_id)
) STRICT;

CREATE INDEX runtime_notification_inbox_by_subject
    ON runtime_notification_inbox (subject_id, created_at, entry_id);
CREATE INDEX runtime_gateway_sessions_by_subject
    ON runtime_gateway_sessions (subject_id, started_at, session_id);

CREATE TRIGGER runtime_notification_inbox_reject_update BEFORE UPDATE ON runtime_notification_inbox
BEGIN SELECT RAISE(ABORT, 'runtime notification inbox is append-only'); END;
CREATE TRIGGER runtime_notification_inbox_reject_delete BEFORE DELETE ON runtime_notification_inbox
BEGIN SELECT RAISE(ABORT, 'runtime notification inbox is append-only'); END;
CREATE TRIGGER runtime_notification_receipts_reject_update BEFORE UPDATE ON runtime_notification_receipts
BEGIN SELECT RAISE(ABORT, 'runtime notification receipts are append-only'); END;
CREATE TRIGGER runtime_notification_receipts_reject_delete BEFORE DELETE ON runtime_notification_receipts
BEGIN SELECT RAISE(ABORT, 'runtime notification receipts are append-only'); END;
CREATE TRIGGER runtime_watcher_heartbeats_reject_update BEFORE UPDATE ON runtime_watcher_heartbeats
BEGIN SELECT RAISE(ABORT, 'runtime watcher heartbeats are append-only'); END;
CREATE TRIGGER runtime_watcher_heartbeats_reject_delete BEFORE DELETE ON runtime_watcher_heartbeats
BEGIN SELECT RAISE(ABORT, 'runtime watcher heartbeats are append-only'); END;
CREATE TRIGGER runtime_gateway_sessions_reject_update BEFORE UPDATE ON runtime_gateway_sessions
BEGIN SELECT RAISE(ABORT, 'runtime gateway sessions are append-only'); END;
CREATE TRIGGER runtime_gateway_sessions_reject_delete BEFORE DELETE ON runtime_gateway_sessions
BEGIN SELECT RAISE(ABORT, 'runtime gateway sessions are append-only'); END;
CREATE TRIGGER runtime_gateway_turns_reject_update BEFORE UPDATE ON runtime_gateway_turns
BEGIN SELECT RAISE(ABORT, 'runtime gateway turns are append-only'); END;
CREATE TRIGGER runtime_gateway_turns_reject_delete BEFORE DELETE ON runtime_gateway_turns
BEGIN SELECT RAISE(ABORT, 'runtime gateway turns are append-only'); END;
CREATE TRIGGER runtime_workspace_changes_reject_update BEFORE UPDATE ON runtime_workspace_change_receipts
BEGIN SELECT RAISE(ABORT, 'runtime workspace changes are append-only'); END;
CREATE TRIGGER runtime_workspace_changes_reject_delete BEFORE DELETE ON runtime_workspace_change_receipts
BEGIN SELECT RAISE(ABORT, 'runtime workspace changes are append-only'); END;
CREATE TRIGGER runtime_change_applications_reject_update BEFORE UPDATE ON runtime_change_application_receipts
BEGIN SELECT RAISE(ABORT, 'runtime change applications are append-only'); END;
CREATE TRIGGER runtime_change_applications_reject_delete BEFORE DELETE ON runtime_change_application_receipts
BEGIN SELECT RAISE(ABORT, 'runtime change applications are append-only'); END;
CREATE TRIGGER runtime_verifications_reject_update BEFORE UPDATE ON runtime_verification_receipts
BEGIN SELECT RAISE(ABORT, 'runtime verification receipts are append-only'); END;
CREATE TRIGGER runtime_verifications_reject_delete BEFORE DELETE ON runtime_verification_receipts
BEGIN SELECT RAISE(ABORT, 'runtime verification receipts are append-only'); END;
