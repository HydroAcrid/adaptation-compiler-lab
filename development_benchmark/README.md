# Milestone 5.5 Codex Development Benchmark

These are newly authored, non-held-out development tasks. They are deliberately separate from the
sealed Milestone 6 Claude feasibility bundle. The task fixtures and independent scorers may be
inspected and revised before a future development iteration; they must never be represented as
held-out or confirmatory evidence.

Each isolated Codex workspace receives only one task's `fixture/` tree, its task prompt, the common
run wrapper, and one frozen condition injected as developer instructions. The `independent/`
scorer is run only after Codex exits and is never copied into the target workspace.

The four tasks cover communication, environment safety, debugging/verification, and research
integrity. Neutral-control checks on every task penalize unrelated files, test tampering, ambient
configuration, and unnecessary scope expansion.
