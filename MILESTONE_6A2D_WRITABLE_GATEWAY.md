# Milestone 6A.2D — Writable Automatic Adaptation Gateway

Status: **implemented and live-conformant in an isolated development canary; ordinary-use evidence gate remains active**

Date: 2026-08-07

## Outcome

Milestone 6A.2D closes the main instrument gap discovered during the first ordinary-use dogfood
activation. The product can now poll authorized completed Codex Desktop interactions in a
restart-safe background process and deliver an approved compact adaptation into a fresh,
multi-turn Codex session that operates on a disposable writable Git worktree. Changes never land
in the canonical repository automatically: they become an encrypted, digest-bound review bundle
that the owner must explicitly apply against the unchanged baseline.

This is an instrument and product-runtime increment. It does not reset or satisfy the frozen
Milestone 6A.2C longitudinal evidence criteria. The first false activation remains counted, the
semantic detector remains in review mode, and synthetic gateway tests are not evidence of correct
ordinary-use learning. The deferred external Claude study remains sealed and optional.

## Exact workflow

1. A same-user watcher polls the already pinned Codex app-server source immediately and then at a
   configured idle cadence. It holds one renewable lease, records raw-free heartbeats, backs off
   with jitter, and advances the existing hashed source cursor only after all durable sinks
   acknowledge.
2. Only exact user-authored messages from registered, terminal, post-cutoff tasks enter semantic
   interpretation. The semantic model remains a proposal-only sensor with no tools or ambient
   context. Exact quote support, source authority, route, secret, scope, policy, lifecycle, and
   conflict checks remain deterministic.
3. Ambiguous applicability stays narrow and review-required. A current requested topic is not a
   reusable preference; unexpressed private intent cannot become authority. Review approval still
   requires explicit confirmation that the behavior may influence future sessions.
4. Review, update, removal, and runtime-failure notices enter an append-only local inbox. Optional
   Windows toasts use four fixed generic strings and reveal no behavior, path, project, or raw
   evidence on the lock screen.
5. A governed gateway freezes one release, projection, project, model, effort, permission set, and
   baseline at session start. `runtime session run` provides one-shot use; `runtime session chat`
   provides up to 15 turns with `/status`, `/finish`, and `/abort`. Learning approved during a
   session applies only to later sessions.
6. The gateway requires a clean canonical Git repository and creates a detached worktree beneath
   one explicit runtime root. A Windows target requires that root on a local `/mnt/<drive>` volume;
   it may not fall back to the read-only WSL UNC topology.
7. Codex receives a fresh auth-only home, saved ChatGPT authentication, no API keys, no dynamic
   tools or capability roots, `approvalPolicy=never`, an implicitly writable exact CWD, no extra
   writable roots, and network denial. The thread request omits `environments`: in the pinned
   protocol, an empty array disables the execution environment rather than removing ambient
   integrations. Any model, CWD, sandbox, root, network, or instruction-source drift fails before
   a turn.
8. Verification commands are fixed, phase-scoped argv arrays with time, output, address-space,
   process, CPU, and file limits. API-key and research-key environment variables are scrubbed. A
   baseline-safe subset runs before execution and task-result checks run only after the edit.
9. After the agent exits, all file changes are captured with add/modify/delete operation, before
   and after digests, modes, binary status, exact base commit/tree, projection/release bindings,
   and encrypted full bytes. Symlink changes, `.git`, secret/config roots, traversal, submodule
   mutation, files over 5 MB, and bundles over 25 MB fail closed.
10. `tests`, `pyproject.toml`, and `uv.lock` are protected verifier inputs by default. The agent
    cannot rewrite them to forge success. The bundle is applied to a second clean detached
    worktree and the registered commands run independently there. Failing evidence remains
    recorded and the verification worktree is destroyed.
11. `runtime changes show` decrypts the local bundle for explicit review. `runtime changes apply`
    requires the exact expected HEAD, a clean canonical tree, matching before-bytes and modes, and
    a valid encrypted bundle. Application is all-or-nothing, reruns independent verification, and
    restores every touched file on failure. Verification receipts and the application decision
    commit atomically; a recording failure also restores the files. A second apply/discard decision
    is refused. `discard` records a durable no-change decision.
12. Structured session events, user/agent turns, and change bytes remain AES-256-GCM encrypted
    outside Git for the existing 30-day raw retention window. The ledger stores only typed
    receipts, digests, counts, and raw references. Temporary homes and worktrees must be torn down
    after success, failure, timeout, or interruption.

## Credential boundary

`runtime credentials enroll` validates the existing external Ed25519 key, its passphrase, and the
separate AES key, then protects their locators/passphrase with Windows CurrentUser DPAPI. DPAPI
entropy binds the envelope to the subject, security-relevant configuration digest, and signer
fingerprint. The envelope is outside Git and is revocable with `runtime credentials revoke`.

The runtime never places decrypted values in process arguments or child environments. If Windows
interop/DPAPI is unavailable, the envelope moved accounts or machines, its bytes changed, its
binding changed, or enrollment was revoked, unattended operation fails closed. Initial enrollment,
watcher installation, and permanent startup are always explicit user actions.

## Commands

- `runtime configure-gateway`
- `runtime credentials enroll|status|revoke`
- `runtime watcher install|uninstall|start|stop|status|run`
- `runtime inbox list|show|acknowledge`
- `runtime session run|chat`
- `runtime changes show|apply|discard`
- `runtime gateway-report`

The existing `runtime poll`, one-turn `runtime run`, review, undo, feedback, and gate commands remain
backward compatible. Configuration v1.3 adds the disposable workspace root, WSL distribution,
watcher cadence, notification mode, gateway limits/model, fixed verification commands, and
protected verifier paths. Versions 1.1 and 1.2 remain readable and require explicit
`configure-gateway` before writable use.

## Persistence and portable contracts

Migration 0011 adds append-only inbox, notification, heartbeat, gateway-session, turn,
verification, change-bundle, and change-application records. Operational watcher lease files are
renewable and deliberately separate from immutable evidence.

The automatic-runtime schema bundle now includes credential-envelope metadata, watcher lease and
heartbeat, notification entries/receipts, gateway sessions/turns/metrics, workspace baselines and
leases, file/change receipts, verification specifications/results, and application receipts.

## Verification boundary

Automated coverage includes:

- DPAPI-equivalent encryption binding, identity/config/fingerprint mismatch, tamper, and revoke;
- real CurrentUser DPAPI round trip when Windows executable interop is available;
- watcher exclusivity, renewal, retry/backoff, cursor-safe failure, raw-free notice allowlists,
  notification deduplication, and no-signal suppression;
- strict writable/network-denied Codex start and read-only downgrade refusal;
- clean detached worktree creation, exact baseline binding, dirty-tree refusal, symlink and path
  escape rejection, add/modify/delete/mode/binary capture, and size ceilings;
- protected-verifier input rejection, clean independent execution, command timeouts/resource
  limits on POSIX and Windows, failing-result preservation, phase-specific receipt identity,
  stale-head and duplicate-decision refusal, atomic application evidence, all-or-nothing apply,
  and rollback;
- schema snapshots, migration drift/idempotency, and compatibility with the existing runtime.

The live development canary used the saved ChatGPT subscription and pinned Luna target with no API
key. A fresh session created exactly one requested JSON file in a disposable worktree; independent
postflight checks passed; the encrypted bundle exposed the exact one-file diff; and explicit apply
to the isolated canary repository succeeded. A duplicate apply was refused. The canary also exposed
and drove repairs for a Windows-only import, disabled environment access, verification phase
conflation, configuration-binding drift, and application-receipt collision. No user project,
provider-billed API call, automatic tool, persistent `AGENTS.md`, preset, or sealed benchmark
material was used or changed.

## Remaining evidence work

The product now has the mechanism needed to accumulate credible ordinary-use evidence, but the
6A.2C gate is not complete. Continue real use across the frozen interaction/date/activation
requirements and classify every learning decision and completed activation. Metrics are segmented
as `6A.2D-v1`; pre-gateway records remain unchanged. Only after the existing gate passes should
calibrated unattended promotion be reconsidered. Milestone 6B Portable Specialty Presets follows
runtime reliability; the sealed Claude study is not a prerequisite.
