create table if not exists public.adaptation_compiler_preview_invites (
  id uuid primary key default gen_random_uuid(),
  email text not null check (char_length(email) <= 254 and position('@' in email) > 1),
  email_normalized text generated always as (lower(email)) stored,
  code_digest text not null unique check (code_digest ~ '^[a-f0-9]{64}$'),
  cohort text not null check (char_length(cohort) between 1 and 80),
  status text not null default 'issued' check (status in ('issued', 'redeemed', 'revoked', 'expired')),
  expires_at timestamptz not null,
  redeemed_at timestamptz,
  created_at timestamptz not null default now(),
  unique (email_normalized, cohort),
  check (expires_at > created_at)
);

create table if not exists public.adaptation_compiler_installations (
  id uuid primary key default gen_random_uuid(),
  installation_id text not null unique check (installation_id ~ '^installation-[a-f0-9]{32}$'),
  invite_id uuid not null references public.adaptation_compiler_preview_invites(id),
  token_digest text not null check (token_digest ~ '^[a-f0-9]{64}$'),
  reporting_public_key_base64 text not null check (reporting_public_key_base64 ~ '^[A-Za-z0-9+/]{43}=$'),
  reporting_key_fingerprint text not null check (reporting_key_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  platform text not null check (platform in ('windows', 'macos')),
  architecture text not null check (architecture in ('x86_64', 'arm64')),
  app_version text not null check (app_version ~ '^[0-9]+\.[0-9]+\.[0-9]+(a[0-9]+)?$'),
  status text not null default 'active' check (status in ('active', 'deleted', 'revoked')),
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  deleted_at timestamptz,
  unique (invite_id)
);

create table if not exists public.adaptation_compiler_aggregate_reports (
  id uuid primary key default gen_random_uuid(),
  installation_id uuid not null references public.adaptation_compiler_installations(id) on delete cascade,
  report_id text not null check (report_id ~ '^report-[a-f0-9]{32}$'),
  report_version text not null check (report_version = '1.0.0'),
  payload jsonb not null check (octet_length(payload::text) <= 32000),
  report_digest text not null check (report_digest ~ '^sha256:[a-f0-9]{64}$'),
  reporting_key_fingerprint text not null check (reporting_key_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  signature_base64 text not null check (signature_base64 ~ '^[A-Za-z0-9+/]{86}==$'),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '90 days'),
  unique (installation_id, report_id),
  check (expires_at <= created_at + interval '90 days')
);

create table if not exists public.adaptation_compiler_report_deletions (
  id uuid primary key default gen_random_uuid(),
  installation_id text not null check (installation_id ~ '^installation-[a-f0-9]{32}$'),
  deleted_report_count integer not null check (deleted_report_count >= 0),
  deleted_at timestamptz not null default now()
);

create table if not exists public.adaptation_compiler_preview_builds (
  id uuid primary key default gen_random_uuid(),
  app_version text not null check (app_version ~ '^[0-9]+\.[0-9]+\.[0-9]+(a[0-9]+)?$'),
  platform text not null check (platform in ('windows', 'macos')),
  architecture text not null check (architecture in ('x86_64', 'arm64')),
  storage_object text not null unique check (char_length(storage_object) between 1 and 500),
  sha256_digest text not null check (sha256_digest ~ '^sha256:[a-f0-9]{64}$'),
  status text not null default 'active' check (status in ('active', 'retired')),
  created_at timestamptz not null default now()
);

create or replace function public.redeem_adaptation_compiler_invite(
  p_invite_id uuid,
  p_installation_id text,
  p_token_digest text,
  p_public_key_base64 text,
  p_public_key_fingerprint text,
  p_platform text,
  p_architecture text,
  p_app_version text
) returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.adaptation_compiler_preview_invites
  set status = 'redeemed', redeemed_at = now()
  where id = p_invite_id and status = 'issued' and expires_at > now();
  if not found then raise exception 'invite unavailable'; end if;
  insert into public.adaptation_compiler_installations (
    installation_id, invite_id, token_digest, reporting_public_key_base64,
    reporting_key_fingerprint, platform, architecture, app_version
  ) values (
    p_installation_id, p_invite_id, p_token_digest, p_public_key_base64,
    p_public_key_fingerprint, p_platform, p_architecture, p_app_version
  );
end;
$$;

create or replace function public.delete_adaptation_compiler_reports(p_installation_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  target_installation text;
  deleted_count integer;
begin
  select installation_id into target_installation
  from public.adaptation_compiler_installations
  where id = p_installation_id and status = 'active'
  for update;
  if target_installation is null then raise exception 'installation unavailable'; end if;
  delete from public.adaptation_compiler_aggregate_reports where installation_id = p_installation_id;
  get diagnostics deleted_count = row_count;
  update public.adaptation_compiler_installations
  set status = 'deleted', deleted_at = now()
  where id = p_installation_id;
  insert into public.adaptation_compiler_report_deletions (
    installation_id, deleted_report_count
  ) values (target_installation, deleted_count);
end;
$$;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'adaptation-compiler-preview-builds',
  'adaptation-compiler-preview-builds',
  false,
  209715200,
  array['application/octet-stream', 'application/x-apple-diskimage']
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

alter table public.adaptation_compiler_preview_invites enable row level security;
alter table public.adaptation_compiler_installations enable row level security;
alter table public.adaptation_compiler_aggregate_reports enable row level security;
alter table public.adaptation_compiler_report_deletions enable row level security;
alter table public.adaptation_compiler_preview_builds enable row level security;

revoke all on public.adaptation_compiler_preview_invites from anon, authenticated;
revoke all on public.adaptation_compiler_installations from anon, authenticated;
revoke all on public.adaptation_compiler_aggregate_reports from anon, authenticated;
revoke all on public.adaptation_compiler_report_deletions from anon, authenticated;
revoke all on public.adaptation_compiler_preview_builds from anon, authenticated;
revoke all on function public.redeem_adaptation_compiler_invite(uuid,text,text,text,text,text,text,text) from public, anon, authenticated;
revoke all on function public.delete_adaptation_compiler_reports(uuid) from public, anon, authenticated;
grant execute on function public.redeem_adaptation_compiler_invite(uuid,text,text,text,text,text,text,text) to service_role;
grant execute on function public.delete_adaptation_compiler_reports(uuid) to service_role;

create index if not exists adaptation_compiler_reports_expiry_idx
  on public.adaptation_compiler_aggregate_reports (expires_at);

create or replace function public.purge_expired_adaptation_compiler_reports()
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare deleted_count integer;
begin
  delete from public.adaptation_compiler_aggregate_reports where expires_at <= now();
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;

revoke all on function public.purge_expired_adaptation_compiler_reports() from public, anon, authenticated;
grant execute on function public.purge_expired_adaptation_compiler_reports() to service_role;
