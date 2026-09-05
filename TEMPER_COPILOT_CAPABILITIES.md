# Temper and GitHub Copilot capabilities

Status: versioned discovery, capability reporting, and governed Copilot CLI delivery implemented
and fixture-verified. Other Copilot surfaces remain file-preview or observation paths.

GitHub Copilot is a family of surfaces, not one uniform runtime. Temper therefore records a
versioned capability matrix and never turns “Copilot is installed” into a claim that capture or
delivery works everywhere.

The reviewed 2026-09-05 contract follows GitHub's official
[custom-instruction support matrix](https://docs.github.com/en/copilot/reference/custom-instructions-support),
[Copilot CLI instruction contract](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions),
and [hooks reference](https://docs.github.com/en/copilot/reference/hooks-reference).

## Product posture by surface

| Surface | Native context Temper understands | Temper delivery posture |
| --- | --- | --- |
| Copilot CLI | Repository, path-specific, agent, and personal instructions | Governed direct delivery through the official local hook |
| GitHub cloud agent | Repository, path-specific, and agent instructions | Confirmed repository-file preview only |
| GitHub code review | Repository, path-specific, and agent instructions | Confirmed repository-file preview only |
| VS Code Chat | Repository, path-specific, and agent instructions | Confirmed repository-file preview only |
| Visual Studio Chat | Repository and path-specific instructions | Confirmed repository-file preview only |
| JetBrains Chat | Repository, path-specific, and personal instructions | Confirmed repository-file preview only |
| Eclipse Chat | Repository-wide instructions | Confirmed repository-file preview only |
| Xcode Chat | Repository and path-specific instructions | Confirmed repository-file preview only |
| GitHub.com Chat | Repository-wide and personal instructions | Observed context; no local session injection |

Temper already discovers the supported repository instruction and skill locations through the
native instruction-environment layer. Those files remain project or agent-native context; they do
not become approved Temper Core knowledge.

## Copilot CLI detection

Temper searches only `PATH` and fixed supported executable names. It executes the read-only version
probe and currently recognizes the reviewed `1.0.54` contract. It does not recursively scan the
machine, install Copilot, initiate OAuth, inspect tokens, or infer sign-in state from an installed
binary.

The connection card therefore distinguishes:

- executable installation and version compatibility;
- authentication, which remains unknown until an official non-interactive read-only status
  contract is verified;
- repository-instruction understanding, which already works; and
- direct Temper delivery, which remains off until the user reviews and applies the local hook
  connection.

Copilot usage follows the user's GitHub plan. Temper's local inspection and future connection
workflow make no provider call.

## Direct-delivery implementation

GitHub's current Copilot CLI hook contract supports `userPromptTransformed`, which can change the
model-facing transformed prompt without altering the prompt shown in the timeline. Temper owns one
dedicated `temper.json` user-hook file and invokes the already bundled `temper-hook` helper
directly—never through a shell. Connection requires an exact redacted diff, explicit 30-day
delivery consent, current application and file digests, and an idempotency key. Disconnect removes
only the Temper-owned file; encrypted original bytes and signed receipts support exact rollback.

Projection preparation occurs outside the hook request. It resolves approved Core against the
current project instruction environment, omits exact native duplicates with lineage, and signs a
15-minute owner/project/environment-bound lease. The hook then rehashes the native environment and
serves only that cached delta through the owner-restricted Tauri transport. It makes no model call,
stores no raw prompt, and returns an exit-success no-op for an unregistered project, expired
consent, absent lease, changed native source, unavailable Temper runtime, or malformed payload.

This first Copilot increment is delivery-only. Temper hashes the transient prompt and session for
a local signed delivery receipt but does not retain the prompt, treat it as learning evidence, or
claim a Copilot source-learning loop. Copilot authentication remains honestly `unknown` because no
official non-interactive status command has been admitted. The reviewed `1.0.54` CLI contract must
match before Connect is offered. No live Copilot smoke is claimed on this host because Copilot CLI
is not installed here.

Other Copilot surfaces remain file-based. Temper may offer an exact digest-bound preview using the
existing governed native-write service, but it cannot claim session delivery or modify a
repository automatically.
