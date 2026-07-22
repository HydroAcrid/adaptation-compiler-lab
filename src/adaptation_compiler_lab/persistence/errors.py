"""Persistence-specific errors with stable, user-presentable meanings."""


class PersistenceError(Exception):
    """Base class for persistence failures."""


class MigrationError(PersistenceError):
    """A database migration could not be safely applied."""


class MigrationDriftError(MigrationError):
    """An already-applied migration no longer matches its bundled source."""


class MigrationSequenceError(MigrationError):
    """The bundled migration sequence is missing, duplicated, or out of order."""


class DatabaseVersionError(MigrationError):
    """The database contains migrations newer than this application understands."""


class IntegrityError(PersistenceError):
    """Stored data violated a persistence-level integrity invariant."""


class RecordConflictError(IntegrityError):
    """An immutable key was reused for different content."""


class RecordNotFoundError(PersistenceError):
    """An exact record version was not found."""


class HistoryConflictError(IntegrityError):
    """An append-only history event did not extend the current head."""


class FixtureConflictError(IntegrityError):
    """A fixture-set identifier was reused for a different manifest."""
