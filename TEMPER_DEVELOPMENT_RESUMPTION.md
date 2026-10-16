# Temper development resumption

## Current Codex integration

The October 6 audit found Windows Codex `0.160.1` and macOS Codex `0.157.0`.
Native product inspection, setup, and recovery now select an exact platform-specific
product pin. macOS no longer falls back to the Linux research executable. Historical
research locks and the Windows `0.153.1` contract remain unchanged.

Each new product pin binds the executable hash, exact version, full generated schema
bundle digest, and fourteen selected request/response snapshots. Pickup and delivery
select snapshots from the pinned version and reject changed snapshot bytes. Native
instruction manifests use the configured target version; the default legacy adapter
contract remains available for existing callers.

New setup and recovery copy the admitted pin into content-addressed runtime storage
before credential enrollment. This avoids binding persisted configurations to Nuitka's
temporary onefile extraction directory. Recovery stages the pin with the rest of the
runtime before committing the final configuration and credential binding.

## Validation

- Windows: live schema-validated initialize and account/read using saved ChatGPT
  authentication, without a model turn.
- macOS: the same read-only exchange against the installed `0.157.0` executable,
  recorded in the Mac conformance commit.
- Windows: disposable native onboarding with real DPAPI enrollment, persistent pin
  verification, and a configured/secure-store-ready snapshot after service restart.
- Focused Windows suite: 182 passed, one host-dependent symlink test skipped.
- Frozen pin suite: nine tests passed on WSL, including its POSIX-only checks.
- Ruff and mypy passed for the changed implementation and regression tests.
- Combined-source Mac validation passed 126 focused tests and native disposable
  onboarding with Keychain enrollment, restart, and exact temporary-key cleanup.
- Windows Apply validation found an additional baseline-byte mismatch under Git
  checkout conversion. Baseline reads now use Git's worktree filters, preserving
  exact LF/CRLF bytes for application and rollback. Eleven gateway tests passed on
  both Windows and WSL, with one platform-dependent skip on each. The gateway module
  typechecks with POSIX stubs; native Windows stubs still report pre-existing POSIX
  resource/signal attribute errors.

These results validate source behavior and bounded native services. They do not prove
a full rendered desktop workflow, a model-backed task/feedback loop, or independent
clean-machine installation.

## Existing runtime migration

October 7 update: combined candidate `56e2028` passed all seven CI gates and is now
installed on both native hosts. Windows endpoint migration preserved identity, policy
expiry, projects/cutoffs, and history bytes and restored protected-key access. It did
not enable persistent consent. The following October 6 audit remains historical;
see `TEMPER_AUTONOMY_IMPLEMENTATION.md` for the current implementation checkpoint.

The audited personal Windows runtime still references a removed Codex executable and
a removed onefile pin path. Its consent expired September 27. Loading the dashboard
does not establish delivery readiness. This change does not rewrite that configuration,
renew consent, reset its signed lineage, or discard historical evidence.

Next, prepare a reviewed migration using the supported credential rebind and signed
governance paths, with exact configuration preview and preservation of identity,
cutoffs, cursors, and historical evidence. Obtain owner confirmation for renewed
personal consent. Use disposable runtime fixtures for development until that migration
is concrete and verified.

## Remaining native package checks

The Mac audit also found an unsealed linker-signed app bundle. The candidate's engine
and hook hashes matched its manifest, but `codesign --verify` failed because the complete
bundle lacked a resource seal. That package defect is separate from Codex conformance.
The repair seals the completed development app before constructing its DMG, and
development admission verifies the complete staged app and mounted DMG copy. A copied
recorded candidate passed native development smoke with the repair, retaining the
exact engine and hook hashes. Trusted distribution still requires Developer
ID/notarization and independent validation. A fresh combined source build remains
separate from this repaired historical-artifact trial.

Continue with the native installed-app walkthrough, independent package checks, the
existing ordinary-use protocol and Base-versus-Temper comparison, and supported
cross-machine transfer/recovery tests. Keep claims about each gate separate.
