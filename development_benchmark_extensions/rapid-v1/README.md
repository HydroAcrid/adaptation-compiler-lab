# Rapid extension selection screen

Question: does selecting task-relevant source clauses add value over giving the same
agent the upstream guidance directly, beyond its native task-solving ability?

This development-only prototype compares baseline, full direct Ponytail/pstack-how
guidance (the agent can apply relevant advice), and a Temper-style source-clause
selector. The selector can copy only attributed source paragraphs; it cannot invent
implementation hints. All arms receive the identical task and project policy. There
are three fresh fictional tasks, two repetitions and counterbalanced execution order:
18 solver turns plus three selector turns. The current verified configured model and
saved ChatGPT authentication are used without fallback or API keys.

The tasks cover canonical archive validation reuse, a live-view/frozen-export boundary,
and a neutral text correction. The host checks model-produced replacement files in an
offline, resource-limited, read-only Bubblewrap fixture. The original implementation
must fail and the authored repair must pass every task before any model call. Target
prompts exclude the hidden checks and authored repairs. Outputs cannot change tests,
policies or unapproved paths. Raw calls/output stay encrypted outside Git and Obsidian.

The result rule is fixed before execution: a repeated objective improvement over direct
guidance with no baseline/direct regression and no inappropriate neutral guidance is a
reason for a larger pilot. Ties are no incremental quality signal. Regressions reject
this candidate. Instrument failures are reported separately. Two repetitions cannot
support a general speed/token claim; include selector overhead and unknown usage.

This tests declarative guidance composition in a bounded code-generation channel.
It does not install or test native Ponytail hooks, pstack's whole workflow, Pi's runtime,
cross-agent compatibility, market demand or general effectiveness. It does not change
the installed learner, source permissions, release gates or historical evaluations.

`protocol.json` is an unexecuted preparation snapshot. `protocol-validated.json` binds
the final harness after its pre-execution instrument/unit checks. Neither is overwritten.

Run locally from the repository:

```
.venv\Scripts\python.exe scripts/run_extension_screen.py --config <personal-config> --output <new-private-outside-Git-directory>
```

The exact third-party source revisions and MIT licenses are in `sources.json`. This
snapshot is research input, not an installed or product-evaluated capability release.
