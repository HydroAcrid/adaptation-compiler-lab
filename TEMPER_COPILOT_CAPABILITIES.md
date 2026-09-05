# Temper and GitHub Copilot capabilities

Status: versioned discovery and capability reporting implemented; direct Copilot CLI delivery is
the next connector increment.

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
| Copilot CLI | Repository, path-specific, agent, and personal instructions | Official local hook is available; Temper connector not enabled yet |
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
- direct Temper delivery, which remains disconnected in this increment.

Copilot usage follows the user's GitHub plan. Temper's local inspection and future connection
workflow make no provider call.

## Direct-delivery boundary

GitHub's current Copilot CLI hook contract supports `userPromptTransformed`, which can rewrite the
model-facing transformed prompt without altering the text shown in the user's timeline. This is
the only currently documented local direct-delivery candidate in Temper's matrix.

Before enabling it, Temper must add the same guarantees used for Claude:

- an exact user-level hook diff and explicit connection decision;
- a signed, expiring, project-bound projection lease;
- native instruction-environment rehash and least-delta compilation;
- owner-restricted local transport with a fast no-op when Temper is absent;
- no model call in the hook path;
- exact removal of only Temper-owned hook entries; and
- fixture validation against the pinned Copilot CLI contract.

Other Copilot surfaces remain file-based. Temper may offer an exact digest-bound preview using the
existing governed native-write service, but it cannot claim session delivery or modify a
repository automatically.
