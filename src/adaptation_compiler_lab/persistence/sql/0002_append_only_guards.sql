CREATE TRIGGER records_reject_update
BEFORE UPDATE ON records
BEGIN
    SELECT RAISE(ABORT, 'records are append-only');
END;

CREATE TRIGGER records_reject_delete
BEFORE DELETE ON records
BEGIN
    SELECT RAISE(ABORT, 'records are append-only');
END;

CREATE TRIGGER record_links_reject_update
BEFORE UPDATE ON record_links
BEGIN
    SELECT RAISE(ABORT, 'record links are append-only');
END;

CREATE TRIGGER record_links_reject_delete
BEFORE DELETE ON record_links
BEGIN
    SELECT RAISE(ABORT, 'record links are append-only');
END;

CREATE TRIGGER lifecycle_events_reject_update
BEFORE UPDATE ON lifecycle_events
BEGIN
    SELECT RAISE(ABORT, 'lifecycle events are append-only');
END;

CREATE TRIGGER lifecycle_events_reject_delete
BEFORE DELETE ON lifecycle_events
BEGIN
    SELECT RAISE(ABORT, 'lifecycle events are append-only');
END;

CREATE TRIGGER activation_events_reject_update
BEFORE UPDATE ON activation_events
BEGIN
    SELECT RAISE(ABORT, 'activation events are append-only');
END;

CREATE TRIGGER activation_events_reject_delete
BEFORE DELETE ON activation_events
BEGIN
    SELECT RAISE(ABORT, 'activation events are append-only');
END;

CREATE TRIGGER fixture_sets_reject_update
BEFORE UPDATE ON fixture_sets
BEGIN
    SELECT RAISE(ABORT, 'fixture-set records are immutable');
END;

CREATE TRIGGER fixture_sets_reject_delete
BEFORE DELETE ON fixture_sets
BEGIN
    SELECT RAISE(ABORT, 'fixture-set records are immutable');
END;

CREATE TRIGGER lifecycle_events_require_current_head
BEFORE INSERT ON lifecycle_events
BEGIN
    SELECT CASE
        WHEN NEW.previous_event_id IS NULL AND EXISTS (
            SELECT 1
            FROM lifecycle_events
            WHERE entity_kind = NEW.entity_kind
              AND entity_id = NEW.entity_id
              AND entity_version = NEW.entity_version
        )
        THEN RAISE(ABORT, 'lifecycle event does not extend current head')
        WHEN NEW.previous_event_id IS NOT NULL AND NOT EXISTS (
            SELECT 1
            FROM lifecycle_events AS previous
            WHERE previous.event_id = NEW.previous_event_id
              AND previous.entity_kind = NEW.entity_kind
              AND previous.entity_id = NEW.entity_id
              AND previous.entity_version = NEW.entity_version
              AND previous.sequence = (
                  SELECT MAX(current.sequence)
                  FROM lifecycle_events AS current
                  WHERE current.entity_kind = NEW.entity_kind
                    AND current.entity_id = NEW.entity_id
                    AND current.entity_version = NEW.entity_version
              )
        )
        THEN RAISE(ABORT, 'lifecycle event does not extend current head')
    END;
END;

CREATE TRIGGER activation_events_require_current_head
BEFORE INSERT ON activation_events
BEGIN
    SELECT CASE
        WHEN NEW.previous_event_id IS NULL AND EXISTS (
            SELECT 1 FROM activation_events WHERE environment_id = NEW.environment_id
        )
        THEN RAISE(ABORT, 'activation event does not extend current head')
        WHEN NEW.previous_event_id IS NOT NULL AND NOT EXISTS (
            SELECT 1
            FROM activation_events AS previous
            WHERE previous.event_id = NEW.previous_event_id
              AND previous.environment_id = NEW.environment_id
              AND previous.sequence = (
                  SELECT MAX(current.sequence)
                  FROM activation_events AS current
                  WHERE current.environment_id = NEW.environment_id
              )
        )
        THEN RAISE(ABORT, 'activation event does not extend current head')
    END;
END;

CREATE TRIGGER frozen_release_reject_new_links
BEFORE INSERT ON record_links
WHEN NEW.source_kind = 'release' AND EXISTS (
    SELECT 1
    FROM lifecycle_events
    WHERE entity_kind = NEW.source_kind
      AND entity_id = NEW.source_id
      AND entity_version = NEW.source_version
      AND to_state IN ('released', 'retired', 'revoked')
      AND sequence = (
          SELECT MAX(current.sequence)
          FROM lifecycle_events AS current
          WHERE current.entity_kind = NEW.source_kind
            AND current.entity_id = NEW.source_id
            AND current.entity_version = NEW.source_version
      )
)
BEGIN
    SELECT RAISE(ABORT, 'frozen release membership is immutable');
END;

CREATE TRIGGER validated_target_pack_reject_new_links
BEFORE INSERT ON record_links
WHEN NEW.source_kind = 'target_pack' AND EXISTS (
    SELECT 1
    FROM lifecycle_events
    WHERE entity_kind = NEW.source_kind
      AND entity_id = NEW.source_id
      AND entity_version = NEW.source_version
      AND to_state IN ('validated', 'rejected')
      AND sequence = (
          SELECT MAX(current.sequence)
          FROM lifecycle_events AS current
          WHERE current.entity_kind = NEW.source_kind
            AND current.entity_id = NEW.source_id
            AND current.entity_version = NEW.source_version
      )
)
BEGIN
    SELECT RAISE(ABORT, 'validated target-pack membership is immutable');
END;
