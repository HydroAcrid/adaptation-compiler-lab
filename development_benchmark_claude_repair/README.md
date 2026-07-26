# Claude Public Benchmark Repair

This directory contains a new, public, non-held-out development benchmark. It does not rewrite the
completed `development_benchmark_claude` tasks or results.

The repair targets two measurement defects observed after the v2.9 blind ratings:

- the communication visible tests did not require POSIX shell-literal path rendering; and
- the environment-safety visible tests did not exercise recursive differences, source/destination
  containment, unique backups, or exact restoration.

Independent checks are scenario-granular: an exception in one behavioral scenario fails that
check without collapsing unrelated checks to false. The `conformance` directory contains
intentionally defective and reference implementations used only by local benchmark tests. Those
files are not copied into target workspaces.

The benchmark remains separate from Milestone 6 custody. It compares only the frozen strong static
profile and frozen compiled adaptation material, one run per condition on each of two tasks.

## Blind-run status

The preregistered four-cell Haiku run completed with 4/4 valid records. The condition mapping,
objective scores, token use, and actual cost remain sealed until Kevin rates both anonymous pairs.
The public [blind packet](results/blind-rating-packet-v1.0.md) is bound to the minimized
[blind-run receipt](results/blind-run-receipt-v1.0.json). Raw traces, the private plan, scores, and
provider accounting remain encrypted outside the repository.

No frozen condition material was changed, and neither the held-out Milestone 6 tasks nor their
custody state were accessed.
