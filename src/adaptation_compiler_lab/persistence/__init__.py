"""Model-agnostic local persistence for adaptation compiler records."""

from adaptation_compiler_lab.persistence.fixtures import (
    FixtureBundle,
    FixtureLoader,
    FixtureLoadResult,
)
from adaptation_compiler_lab.persistence.migrations import Migration, MigrationRunner
from adaptation_compiler_lab.persistence.records import (
    ActivationEvent,
    FixtureSet,
    LifecycleEvent,
    RecordKey,
    RecordLink,
    StoredRecord,
    sha256_text,
)
from adaptation_compiler_lab.persistence.sqlite import (
    SqliteUnitOfWork,
    SqliteUnitOfWorkFactory,
)

__all__ = [
    "ActivationEvent",
    "FixtureBundle",
    "FixtureLoadResult",
    "FixtureLoader",
    "FixtureSet",
    "LifecycleEvent",
    "Migration",
    "MigrationRunner",
    "RecordKey",
    "RecordLink",
    "SqliteUnitOfWork",
    "SqliteUnitOfWorkFactory",
    "StoredRecord",
    "sha256_text",
]
