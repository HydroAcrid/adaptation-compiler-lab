# Persona v3.1 Replacement Smoke — Analysis

The new fixture removed the earlier preference/procedure and addition/correction ambiguity. That
worked for the strong static profile, which scored 2/2 exactly. The compiled sensor still failed.

| Lane | Correct active claims | Exact | Result |
| --- | ---: | --- | --- |
| Strong static profile | 2/2 | Yes | Correct preference, procedure, lineage, and scopes. |
| Compiled sensor | 0/2 | No | Turn 2 routed as example; turn 6 was rejected as ambiguous. |

The sensor correctly rejected all five task-only messages. Its two durable interpretations both
used `example_intent=endorsed_for_reuse` and `scope_hint=permanent_profile`. Turn 2 therefore routed
to example. Turn 6 combined endorsed-example intent with a triggered sequence, producing multiple
route candidates and failing deterministic review. Host-owned scope still prevented cross-project
leakage.

The repeated example error persisted after an explicit prompt clarification, so wording alone is
not the best explanation. The structured-output schema encoded four overlapping learning shapes in
this order: example, workflow, fact, norm. A valid preference or procedure could also satisfy the
first example branch by changing one enum value. This makes the response format itself a likely
source of route bias.

The minimal remediation is mechanical and route-neutral: use one complete learning-object schema
with all independent semantic feature enums, plus the separate exact-revocation object. Local
binding and deterministic routing continue to reject feature vectors that support no route or more
than one route. One isolated Luna diagnostic on this same public calibration fixture can test the
schema mechanism; its result is instrument evidence only, not a replacement or effectiveness win.
