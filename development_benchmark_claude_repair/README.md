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
