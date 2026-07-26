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

## Result

The preregistered four-cell Haiku run completed with 4/4 valid records. A fresh isolated
`gpt-5.6-sol` Codex CLI context at `xhigh` reasoning rated the two anonymous pairs from only the
fixed rating contract and blind packet. It had no project, host-home, tool, prior-context,
condition-mapping, objective-score, or Milestone 6 access.

The checksum-bound rating was persisted and pushed before unblinding. The compiled adaptation tied
the strong static profile on communication and won environment safety. Both conditions passed
8/8 objective, 9/9 diagnostic, and 8/8 neutral checks. The four Claude calls cost exactly
USD $0.33626555.

The public [blind packet](results/blind-rating-packet-v1.0.md) is bound to the minimized
[blind-run receipt](results/blind-run-receipt-v1.0.json), the durable
[isolated rating](results/isolated-ai-rating-v1.0.json), and the final
[unblinded result](results/unblinded-result-v1.0.json). Raw traces and private inputs remain
encrypted outside the repository. See `CLAUDE_REPAIR_ISOLATED_ANALYSIS.md` for the interpretation
and limitations.

No frozen condition material was changed, and neither the held-out Milestone 6 tasks nor their
custody state were accessed.
