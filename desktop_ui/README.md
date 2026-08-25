# Temper desktop prototype

This package is the visual acceptance gate for Temper's React/Tauri desktop rebuild. It uses
synthetic, raw-free data and does not connect to the governed Python engine.

```bash
pnpm install --frozen-lockfile
pnpm dev
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm test:compat
pnpm test:visual
```

Deterministic product states are selected with `?screen=<name>&theme=<light|dark>`. Supported
screens are `onboarding`, `today`, `suggestion`, `core`, `connections`, `settings`,
`advanced`, and `tray`.

The default workspace is `All projects`. Use the custom masthead menu to focus Kairn or Green
Meadow; `?project=kairn` and `?project=green-meadow` select deterministic focused states. Native
account and folder mutations are intentionally disabled in this browser-only package because the
Tauri/engine bridge is not present.

`test:compat` exercises the everyday surfaces at the supported 720×540 minimum in Chromium as a
practical Windows WebView2 proxy. It verifies accessibility, horizontal overflow, console
cleanliness, local-only asset loading, and scope-preserving review and Core-edit behavior.
`test:compat:webkit` runs the same checks through Playwright WebKit when its host libraries are
available. Native Tauri compatibility still requires the later Windows and macOS builds plus
clean-machine tests.

The Qt interface remains the internal diagnostic application until the React/Tauri surface has
passed the later engine-parity gate.
