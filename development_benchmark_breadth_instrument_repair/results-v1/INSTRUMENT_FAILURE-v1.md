# Milestone 6A.4 Clean Gate — Instrument Failure

This eight-run packet is invalid for adaptation comparison.

- All eight pinned Luna sessions completed their structured trace contracts.
- All eight sessions made no registered source change and could not run task tests.
- Every anonymous response reported the same pre-command blocker:
  `bwrap: Can't mkdir /workspace/.agents: Read-only file system`.
- The v2 outer runner removed visible workspace control mountpoints, but the pinned Codex CLI's
  nested sandbox requires those empty mountpoints to initialize.
- Both blinded conditions were affected uniformly.
- No judge was run and no condition mapping was revealed.
- No retry occurred under this frozen contract.
- No API key, provider-billed call, or deferred external-validation material was used.

The repair must preserve this packet unchanged, use a new versioned runner and contract, provide
empty ephemeral control mountpoints only during execution, remove their host mountpoints before
scoring, and pass a synthetic edit-and-test smoke before another comparison.
