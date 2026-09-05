# Mode Evaluation v3 Blind-Judge Attempt Failure

Status: target grid complete and integrity-valid; judging incomplete; condition mapping unrevealed.

All 30 frozen Luna/medium target cells completed. Every trial retained exact activation,
deactivation, workspace teardown, and integrity validity. Twenty-two trials were behavior-
conformant; the other eight are preserved as ordinary task failures. The blind target report digest
is `sha256:09218344b7f8c12aab6eb07defa53c70f843a97fe826477177ebe3d271fdf097`.

The first fresh condition-blind judge returned a valid structured answer, but Codex `0.153.1` also
emitted its deterministic startup item stating that Code Mode was unavailable because the judge
correctly disabled its execution host. The historical trace parser classified every non-reasoning,
non-answer item as tool use, so it rejected this benign startup diagnostic as if the judge had used
a tool. A separate minimal diagnostic reproduced the exact event shape. No judge receipt was
written, the other two judges did not run, and no condition identity was revealed.

The 30 target records must not be rerun or replaced. Any judge repair must recognize only that exact
benign startup diagnostic, continue rejecting every genuine tool or unknown item, bind this blind-
report digest before inference, and pass a separate tool-free trace smoke before new judges run.
