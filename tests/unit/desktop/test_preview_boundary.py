"""Static safety checks for the isolated Supabase/Vercel preview boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[3]
MIGRATION = ROOT / "supabase" / "migrations" / "202608230001_adaptation_compiler_preview.sql"
PORTAL = ROOT / "preview_portal" / "src"


def test_preview_tables_are_isolated_and_client_access_is_revoked() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    tables = (
        "adaptation_compiler_preview_invites",
        "adaptation_compiler_installations",
        "adaptation_compiler_aggregate_reports",
        "adaptation_compiler_report_deletions",
        "adaptation_compiler_preview_builds",
    )

    for table in tables:
        assert f"alter table public.{table} enable row level security" in sql
        assert f"revoke all on public.{table} from anon, authenticated" in sql
    assert "kairn_telemetry" not in sql
    assert "beta_invites" not in sql


def test_preview_retention_and_private_storage_are_database_enforced() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    assert "interval '90 days'" in sql
    assert "purge_expired_adaptation_compiler_reports" in sql
    assert "'adaptation-compiler-preview-builds'" in sql
    assert "false," in sql


def test_server_routes_never_expose_service_role_to_client_components() -> None:
    route_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((PORTAL / "app" / "api").rglob("*.ts"))
    )
    page_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((PORTAL / "app").glob("*.tsx"))
    )

    assert "SUPABASE_SERVICE_ROLE_KEY" not in page_sources
    assert "serverSupabase" in route_sources
    assert "NEXT_PUBLIC_SUPABASE_URL" not in page_sources


def test_report_schema_explicitly_blocks_unknown_fields() -> None:
    schema = (PORTAL / "lib" / "report.ts").read_text(encoding="utf-8")

    assert schema.count(".strict()") >= 3
    for forbidden in ("prompt", "output", "repository", "project", "evidence", "path"):
        assert f"{forbidden}:" not in schema.lower()


def test_report_route_uses_internal_uuid_for_foreign_key() -> None:
    route = (PORTAL / "app" / "api" / "reports" / "route.ts").read_text(encoding="utf-8")

    assert '.select("id,installation_id,token_digest,reporting_public_key_base64,status")' in route
    assert "installation_id: installation.id" in route
