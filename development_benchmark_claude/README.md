# Claude Haiku compiler-v2 development gate

This benchmark asks the product question directly:

> Why use an adaptation compiler instead of writing one excellent profile?

It compares only the frozen strong static profile and compiler v2. Compiler v2 is generated
deterministically from the already-approved artifacts and their exact passed evaluation cases. It
renders each behavior as `Do`, `Check before completion`, and `Failure signs`, retaining lineage
outside the target-visible text. It does not copy the profile or task solutions.

The four tasks are fresh, non-held-out development tasks covering communication, debugging and
verification, environment safety, and research integrity. Each condition runs twice on each task
in a fresh Claude Code session using the exact pinned Haiku model, for 16 runs total.

Kevin receives eight anonymous paired comparisons. Condition identities and automated scores stay
sealed until all ratings are recorded. The compiler has a product-performance advantage only if it
beats or ties the profile on behavior and preference, does not regress neutral controls, and keeps
its smaller material footprint. This is descriptive cross-agent development evidence, not the
frozen Milestone 6 study and not proof of a universal thesis.

See `PREREGISTRATION.json` for the exact frozen design, material digests, budgets, and decision
rule.
