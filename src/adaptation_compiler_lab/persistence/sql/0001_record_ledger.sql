CREATE TABLE records (
    record_kind TEXT NOT NULL,
    record_id TEXT NOT NULL,
    record_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    canonicalization_version TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    content_sha256 TEXT NOT NULL CHECK (length(content_sha256) = 64),
    created_at TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    privacy_class TEXT NOT NULL,
    benchmark_role TEXT NOT NULL,
    PRIMARY KEY (record_kind, record_id, record_version)
) STRICT;

CREATE INDEX records_by_subject_kind
    ON records (subject_id, record_kind, record_id, record_version);
CREATE INDEX records_by_benchmark_role
    ON records (benchmark_role, record_kind, record_id, record_version);
CREATE INDEX records_by_digest ON records (content_sha256);

CREATE TABLE record_links (
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_version TEXT NOT NULL,
    target_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_version TEXT NOT NULL,
    relation TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
    created_at TEXT NOT NULL,
    PRIMARY KEY (
        source_kind,
        source_id,
        source_version,
        relation,
        target_kind,
        target_id,
        target_version
    ),
    UNIQUE (source_kind, source_id, source_version, relation, ordinal),
    FOREIGN KEY (source_kind, source_id, source_version)
        REFERENCES records (record_kind, record_id, record_version) ON DELETE RESTRICT,
    FOREIGN KEY (target_kind, target_id, target_version)
        REFERENCES records (record_kind, record_id, record_version) ON DELETE RESTRICT
) STRICT;

CREATE INDEX record_links_by_target
    ON record_links (target_kind, target_id, target_version, relation);

CREATE TABLE lifecycle_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    entity_version TEXT NOT NULL,
    from_state TEXT,
    to_state TEXT NOT NULL,
    previous_event_id TEXT REFERENCES lifecycle_events (event_id) ON DELETE RESTRICT,
    actor_id TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    event_sha256 TEXT NOT NULL CHECK (length(event_sha256) = 64),
    FOREIGN KEY (entity_kind, entity_id, entity_version)
        REFERENCES records (record_kind, record_id, record_version) ON DELETE RESTRICT
) STRICT;

CREATE INDEX lifecycle_events_by_entity
    ON lifecycle_events (entity_kind, entity_id, entity_version, sequence);

CREATE TABLE activation_events (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    environment_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK (
        action IN ('canary', 'activate', 'rollback', 'deactivate', 'expire')
    ),
    release_kind TEXT,
    release_id TEXT,
    release_version TEXT,
    target_pack_kind TEXT,
    target_pack_id TEXT,
    target_pack_version TEXT,
    previous_event_id TEXT REFERENCES activation_events (event_id) ON DELETE RESTRICT,
    actor_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    canonical_json TEXT NOT NULL CHECK (json_valid(canonical_json)),
    event_sha256 TEXT NOT NULL CHECK (length(event_sha256) = 64),
    CHECK (
        (release_kind IS NULL AND release_id IS NULL AND release_version IS NULL)
        OR
        (release_kind = 'release' AND release_id IS NOT NULL AND release_version IS NOT NULL)
    ),
    CHECK (
        (target_pack_kind IS NULL AND target_pack_id IS NULL AND target_pack_version IS NULL)
        OR
        (
            target_pack_kind = 'target_pack'
            AND target_pack_id IS NOT NULL
            AND target_pack_version IS NOT NULL
        )
    ),
    CHECK (
        (
            action IN ('canary', 'activate', 'rollback')
            AND release_kind IS NOT NULL
            AND target_pack_kind IS NOT NULL
        )
        OR
        (
            action IN ('deactivate', 'expire')
            AND release_kind IS NULL
            AND target_pack_kind IS NULL
        )
    ),
    FOREIGN KEY (release_kind, release_id, release_version)
        REFERENCES records (record_kind, record_id, record_version) ON DELETE RESTRICT,
    FOREIGN KEY (target_pack_kind, target_pack_id, target_pack_version)
        REFERENCES records (record_kind, record_id, record_version) ON DELETE RESTRICT
) STRICT;

CREATE INDEX activation_events_by_environment
    ON activation_events (environment_id, sequence);

CREATE TABLE fixture_sets (
    fixture_set_id TEXT PRIMARY KEY,
    manifest_sha256 TEXT NOT NULL CHECK (length(manifest_sha256) = 64),
    loader_version TEXT NOT NULL,
    record_count INTEGER NOT NULL CHECK (record_count >= 0),
    link_count INTEGER NOT NULL CHECK (link_count >= 0),
    lifecycle_event_count INTEGER NOT NULL CHECK (lifecycle_event_count >= 0),
    activation_event_count INTEGER NOT NULL CHECK (activation_event_count >= 0),
    loaded_at TEXT NOT NULL
) STRICT;
