"""First-party Secure Backend temporary capability Mode."""

from adaptation_compiler_lab.modes.models import (
    CapabilityMode,
    ModeClause,
    ModeClauseCategory,
    ModeTargetCompatibility,
)

SECURE_BACKEND_MODE = CapabilityMode(
    mode_id="secure-backend",
    mode_version="1.0.0",
    name="Secure Backend",
    summary=(
        "A threat-aware backend workflow for bounded authority, safe data, and failure recovery."
    ),
    publisher="Temper",
    source_revision="temper-secure-backend-1.0.0",
    source_license="First-party private alpha",
    applicable_task_classes=("backend", "data_service", "security_review"),
    compatible_target_families=("claude-code", "codex"),
    target_compatibility=(
        ModeTargetCompatibility(
            target_family="codex",
            version_constraint="0.153.1",
            delivery_surface="temper-managed-task",
        ),
    ),
    clauses=(
        ModeClause(
            clause_id="secure-backend-authorization",
            claim_key="backend.authorization",
            category=ModeClauseCategory.SECURITY,
            text=(
                "Enforce authentication and object-level authorization at the trusted boundary; "
                "derive identity and tenant scope from verified server-side state."
            ),
        ),
        ModeClause(
            clause_id="secure-backend-data",
            claim_key="backend.data-protection",
            category=ModeClauseCategory.DATA_PROTECTION,
            text=(
                "Minimize sensitive data, validate untrusted input, parameterize storage access, "
                "and keep credentials and private values out of logs and client responses."
            ),
        ),
        ModeClause(
            clause_id="secure-backend-failure",
            claim_key="backend.failure-handling",
            category=ModeClauseCategory.FAILURE_HANDLING,
            text=(
                "Make retries, duplicate delivery, partial failure, and cancellation explicit; use "
                "idempotency and atomic state transitions where repeated work could cause harm."
            ),
        ),
        ModeClause(
            clause_id="secure-backend-threat-model",
            claim_key="backend.threat-model",
            category=ModeClauseCategory.THREAT_MODEL,
            text=(
                "Identify assets, trust boundaries, attacker-controlled inputs, and abuse paths "
                "before choosing the smallest effective control."
            ),
        ),
        ModeClause(
            clause_id="secure-backend-validation",
            claim_key="backend.validation",
            category=ModeClauseCategory.VALIDATION,
            text=(
                "Test authorization denial, cross-tenant isolation, replay, malformed input, and "
                "failure recovery in addition to the successful path."
            ),
        ),
    ),
    maximum_projection_utf8_bytes=1700,
)
