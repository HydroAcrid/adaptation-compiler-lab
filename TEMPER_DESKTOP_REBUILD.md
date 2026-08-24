# Temper desktop rebuild

Status: React visual prototype complete on 2026-08-24; governed backend wiring is intentionally
blocked on owner visual acceptance.

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

- the everyday Today, Adaptations, Connections, and Settings surfaces;
- a one-decision suggestion sheet with suggested and project-only scope choices;
- five-step new-user onboarding;
- explicit Codex and Claude source/target/cost language;
- exact aggregate-report preview with reporting off by default;
- a hidden Advanced task/diff surface;
- tray and notification previews;
- system, light, and dark theme behavior; and
- an original, noninteractive botanical line motif that gives dark mode a restrained old-world
  identity without introducing a licensed artwork dependency; and
- compact-window behavior down to the proposed 760×560 review size.

The visual package has no engine, filesystem, process, credential, Supabase, Codex, Claude, or
sealed-study access. It cannot mutate governed state. The screenshot suite covers eight product
scenes in both themes plus primary compact and wide-window states. All 20 browser scenes pass the
same axe accessibility audit. See the [visual gallery](desktop_ui/docs/VISUAL_GALLERY.md).

The ornamental layer is presentation only: it is authored for Temper, marked `aria-hidden`, accepts
no input, remains behind product content, and is deliberately quieter in light mode. Third-party
marketplace artwork may be used as mood reference but is never copied, bundled, fetched, or required
at runtime.

## Locked product behavior

- Customer-facing naming is **Temper**; internal Python and research identities remain stable.
- The default application is tray-first and quiet. Closing hides it; quitting is explicit.
- Ordinary users see four destinations and one primary action at a time.
- Notifications open a decision sheet and never approve, reject, or revoke directly.
- Advanced mode is opt-in and contains diagnostics, provenance metadata, and the governed task lab.
- No Presets route appears until Milestone 6B has real governed preset types.
- No account is required. Project registration is explicit and prospective.
- Raw evidence never crosses the presentation boundary.
- Telemetry is independent, unchecked, raw-free, previewable, and deletable.
- Agent capability labels must distinguish observation, managed delivery, and ambient delivery.

## Next implementation slice after acceptance

Create the Tauri foundation without changing evidence or artifact schemas:

1. add a minimal Tauri 2 Rust shell around the accepted React assets;
2. implement the tray/window lifecycle and restrictive renderer capability policy;
3. introduce `temper-engine-protocol/v1` and a Python read-only `snapshot.get` endpoint;
4. supervise the development Python sidecar and verify the protocol/version handshake;
5. replace synthetic Today data with the existing raw-free application-service snapshot; and
6. add Rust/Python/TypeScript golden contract tests before enabling any mutation.

No Claude hook, telemetry upload, QML retirement, native signing claim, or Milestone 6 custody work
belongs in that first wired slice.

## Prototype verification

From `desktop_ui/`:

```bash
pnpm install --frozen-lockfile
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm test:visual
```

Repository-wide Python, portal, build, schema, migration, and safety checks remain required before
the prototype branch can merge. Passing the prototype gate is design and frontend-instrument
evidence only; it is not a signed Tauri alpha and does not advance the longitudinal product gate.
