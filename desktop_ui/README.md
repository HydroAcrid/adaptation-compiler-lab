# Temper desktop

This package is Temper's React/Tauri desktop client. Inside Tauri it uses the allowlisted
`temper-engine-protocol/v1` bridge to the governed Python engine. In an ordinary browser it uses
synthetic, raw-free data and disables native mutations so screenshots and interaction tests cannot
touch the user's governed store.

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

Native development additionally requires a target-native engine sidecar or
`TEMPER_ENGINE_BINARY`. Release builds must first run `uv run python packaging/build_native.py`
from the repository root; Tauri then embeds separately built, target-suffixed, manifest-bound
`temper-engine` and `temper-hook` sidecars.

Deterministic product states are selected with `?screen=<name>&theme=<light|dark>`. Supported
screens are `onboarding`, `today`, `suggestion`, `core`, `connections`, `settings`,
`advanced`, and `tray`.

The default workspace is `All projects`. Use the custom masthead menu to focus Kairn or Green
Meadow; `?project=kairn` and `?project=green-meadow` select deterministic focused states. Native
account and folder mutations remain intentionally disabled in browser mode because the
Tauri/engine bridge is not present there.

`test:compat` exercises the everyday surfaces at the supported 720×540 minimum in Chromium as a
practical Windows WebView2 proxy. It verifies accessibility, horizontal overflow, console
cleanliness, local-only asset loading, and scope-preserving review and Core-edit behavior.
`test:compat:webkit` runs the same checks through Playwright WebKit when its host libraries are
available. Native Tauri compatibility still requires the later Windows and macOS builds plus
clean-machine tests.

The terminal CLI remains the internal diagnostic and recovery surface. The retired Qt interface is
not part of this package.
