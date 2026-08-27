# Temper desktop rebuild

Status: React visual direction accepted in PR #53. The Tauri/engine foundation, offline profile
portability, Frontend Studio Mode, their actual Core/Modes surfaces, native first-run setup,
existing-runtime adoption, prospective project registration, and truthful Codex/Claude inspection
are implemented. The full review/mutation loop, macOS credential parity, Qt retirement, Apple
Silicon internal package, and trusted external signing gate remain in the continuous completion
sequence.

## Tauri foundation

The native shell uses a pinned Tauri 2 release, restrictive CSP and capability manifest, and a
persistent Rust-supervised Python engine connection over bounded framed NDJSON. It handshakes
before loading the existing raw-free `DesktopApplicationService` snapshot. A native renderer
never receives demo suggestions; the browser URL remains a synthetic visual-review surface.

React now receives live Core and project summaries in Tauri. Native file dialogs mediate encrypted
profile export/import so renderer code never sees a path. Import is previewed and staged inactive;
another installation's signature proves origin but grants no instruction authority. The Modes
route loads an evaluated raw-free catalog and can launch the first-party Frontend Studio Mode for
one exact registered project through the existing fresh governed Codex gateway. The permanent Core
is restored whether that task succeeds or fails.

Native compilation is checked on Linux, Windows, and macOS runners. This WSL host can run the
Python and React checks but cannot install its missing GTK/WebKit headers without an interactive
sudo password. That is recorded as an environment limitation, not a passing local native-build
claim.

## Architecture decision

Temper's customer desktop will use React/Vite inside a Tauri 2 shell. The existing Python package
remains the governed engine and raw-data boundary. Tauri will supervise a versioned Python sidecar,
own the tray and native notifications, and expose only typed allowlisted commands to the renderer.
The separate Next.js preview portal remains web-only and will never become the desktop runtime or a
remote governed-data dashboard.

Electron is not retained as a parallel implementation. PySide6/QML remains an internal diagnostic
surface until Tauri reaches typed-service, recovery, and native-package parity; removing Qt before
that gate would discard a working recovery path.

## Visual acceptance prototype

`desktop_ui/` is a real React 19/Vite package backed only by deterministic synthetic data. It
contains:

- the everyday Today, Core, Connections, and Settings surfaces;
- a one-decision suggestion sheet with suggested and project-only scope choices;
- a calm ranked queue that keeps one suggestion in focus while showing the next two as a textual
  index rather than a bulk-review dashboard;
- separate evidence-strength and automation-safety language, plus an off-by-default automatic
  low-risk learning control;
- five-step new-user onboarding;
- explicit Codex and Claude source/target/cost language;
- exact aggregate-report preview with reporting off by default;
- a hidden Advanced task/diff surface;
- tray and notification previews;
- system, light, and dark theme behavior; and
- a Quiet Folio visual language that replaces the conventional sidebar, card grid, green success
  banner, icon tiles, and status pills on the defining Today, review, and Core surfaces with
  restrained editorial typography, one current statement, a focused suggestion, plain
  scope/source/status context, and readable approved knowledge;
- a custom workspace control with an All projects default plus Kairn and Green Meadow focus views;
  Today visibly summarizes concurrent work while focused views continue excluding another
  project's guidance;
- a user-facing Core that groups preferences, stable memories, procedures, and reusable skills,
  filters them by applicable repository, and prototypes focused edit, rescope, remove, and undo;
- self-hosted Newsreader and Instrument Sans variable typefaces under the SIL Open Font License;
- professionally drawn CC0 acanthus and rooted-tree assets, cropped as asymmetric edge growth,
  that give dark mode a restrained old-world identity without a runtime network or
  commercial-asset dependency; and
- a CC0 wind silhouette rendered as Temper's copper product mark in the masthead, onboarding, and
  tray instead of a letter monogram; and
- compact-window behavior down to the proposed 760×560 review size.

The visual package has no engine, filesystem, process, credential, Supabase, Codex, Claude, or
sealed-study access. Its working edit and project controls mutate synthetic in-memory presentation
state only. The screenshot suite covers eight product scenes in both themes, both registered
project contexts, a three-item suggestion queue, Today at compact and wide widths, and compact
suggestion/Core states plus the open workspace menu. All 30 browser scenes pass their required visual, accessibility, and
overflow checks. See
the [visual gallery](desktop_ui/docs/VISUAL_GALLERY.md).

The ornamental layer is presentation only: it is vendored locally with exact upstream and
sanitized digests plus a CC0 notice, marked `aria-hidden`, accepts no input, remains behind product
content, and is deliberately quieter in light mode. The ornamental vocabulary informs page
structure rather than surrounding cards. Third-party marketplace artwork may be used as mood
reference but is never copied, fetched, or required at runtime.

Everyday presentation is product-first, not governance-first. Persistent encryption badges,
numeric navigation, proposal identifiers, maker stamps, and the full runtime projection register
were removed after owner review because they looked like research-instrument metadata. Encryption,
digests, lineage, and exact delivery receipts remain available in Settings or Advanced when they
answer a real user question.

## Locked product behavior

- Customer-facing naming is **Temper**; internal Python and research identities remain stable.
- The default application is tray-first and quiet. Closing hides it; quitting is explicit.
- Ordinary users see Today, Core, Connections, and Settings, with one primary action at a time.
- Core is the plain-language view over governed artifacts; it does not create a second memory
  store, weaken lineage, or expose raw evidence.
- Notifications open a decision sheet and never approve, reject, or revoke directly.
- Evidence strength and automation eligibility are different properties. Strongly supported
  procedures, global rules, conflicts, exceptions, and revocations still require review.
- Automatic low-risk learning is off by default. The prototype shows the proposed narrow,
  project-scoped, reversible preference class; engine mutation remains blocked pending shadow-mode
  and genuine-use admission under [the confidence policy](TEMPER_CONFIDENCE_POLICY.md).
- Advanced mode is opt-in and contains diagnostics, provenance metadata, and the governed task lab.
- Core owns encrypted offline profile export/import. Temporary expertise remains a separate Modes
  surface and lower-authority lifecycle; Frontend Studio is the first real built-in Mode.
- No account is required. Project registration is explicit and prospective.
- Raw evidence never crosses the presentation boundary.
- Telemetry is independent, unchecked, raw-free, previewable, and deletable.
- Agent capability labels must distinguish observation, managed delivery, and ambient delivery.
- A suggestion decision may preserve its displayed scope or narrow it to the current project; it
  may never silently widen scope. Core editing follows the same monotonic narrowing rule.

## Next implementation slice

Wire live review decisions, monotonic scope narrowing, revoke, 24-hour undo, activation feedback,
consent renewal, preferences, bounded polling, tray behavior, and notifications through the same
typed application services. Do not add a Claude hook, telemetry upload, or external installer
claim until its separate security and release gate passes.

## Prototype verification

From `desktop_ui/`:

```bash
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm test:compat
pnpm build
pnpm test:visual
```

Repository-wide Python, portal, build, schema, migration, and safety checks remain required before
each branch can merge. Passing these gates proves the implemented desktop slice is internally
coherent; it is not a signed external Tauri alpha and does not advance the longitudinal
product-effectiveness gate.
See [`TEMPER_ALPHA_READINESS_AUDIT.md`](TEMPER_ALPHA_READINESS_AUDIT.md) for the external-user
admission decision and remaining product/platform blockers.
