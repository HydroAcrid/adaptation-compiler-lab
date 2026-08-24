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
pnpm test:visual
```

Deterministic product states are selected with `?screen=<name>&theme=<light|dark>`. Supported
screens are `onboarding`, `today`, `suggestion`, `adaptations`, `connections`, `settings`,
`advanced`, and `tray`.

The Qt interface remains the internal diagnostic application until the React/Tauri surface has
passed the later engine-parity gate.
