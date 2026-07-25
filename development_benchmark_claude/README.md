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

The completed v1.2 run has now been blind-rated and unblinded. Kevin preferred compiled adaptation
in five pairs, the strong profile in two, and tied one. The result is nevertheless
instrument-limited: every run encountered a Bash permission denial, so the agents could not
reliably perform the required verification. No compiler-v2 success or failure conclusion is
allowed from this run.

The separately authorized two-cell instrument canary then failed closed on its first,
strong-profile cell when trace conformance detected an out-of-manifest Bash command. The compiled
cell did not run and no retry occurred. Enforcement worked, but the runner raised before
persisting the returned failure trace or exact provider cost, revealing a second instrumentation
defect. See `INSTRUMENT_CANARY_RESULT-v1.md`; this attempt contains no condition comparison.

See `PREREGISTRATION-v1.2.json` for the executed design,
`results/kevin-blind-rating-v1.2.json` for the pre-unblinding rating,
`results/unblinded-result-v1.2.json` for the mapping and aggregate result, and
`UNBLINDED_ANALYSIS-v1.2.md` for the condition-level analysis and runner repair.
