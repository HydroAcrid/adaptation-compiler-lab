# Systematic Debugging — declarative safe subset

Source: `obra/superpowers`, commit
`b36e0829c6d0140e93cfef2ca599b1b07d4a7797`,
`skills/systematic-debugging/SKILL.md` (MIT).

This condition preserves the upstream workflow before Temper compilation. Examples that inspect
credentials, invoke external tools or skills, or assume provider-specific capabilities are omitted.
No new capability or permission is granted.

## Core principle

Always find the root cause before attempting a fix. A symptom workaround is not a root-cause
repair.

## Phase 1: Root-cause investigation

Before changing code:

1. Read the complete error, warning, and stack trace. Record relevant paths, lines, and error codes.
2. Reproduce the behavior consistently. Record the exact steps and whether it happens every time.
   If it is not reproducible, gather more evidence rather than guessing.
3. Check relevant recent changes and environmental differences.
4. At relevant component boundaries, inspect what enters and exits, then identify the first boundary
   where state becomes incorrect.
5. Trace a bad value backward to its source. Fix the source rather than its downstream symptom.

## Phase 2: Pattern analysis

Before selecting a repair:

1. Find a nearby working example.
2. Read the complete relevant implementation rather than skimming it.
3. List the differences between working and broken paths without assuming a small difference is
   irrelevant.
4. Identify dependencies and assumptions made by the broken code.

## Phase 3: Hypothesis and test

1. State one falsifiable root-cause hypothesis and the evidence supporting it.
2. Test that hypothesis with the smallest discriminating check and one variable at a time.
3. If the evidence rejects it, return to investigation and form a new hypothesis. Do not stack a
   second speculative fix on the first.
4. Say what remains unknown rather than pretending uncertainty has been resolved.

## Phase 4: Repair and verify

1. Create or run the smallest failing reproduction before applying the repair.
2. Make one focused change addressing the confirmed cause. Avoid unrelated cleanup.
3. Rerun the focused reproduction after the change.
4. Run the bounded regression suite covering the changed behavior.
5. Report the commands and current outcomes accurately. Never claim a check that did not run.
6. If the repair fails, stop and return to live evidence rather than adding another speculative
   change.

When repeated attempts expose new coupling or require broad rewrites, question the architecture
instead of continuing to patch symptoms.
