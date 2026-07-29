# Judge amendment v1.1

The first isolated judge attempt failed closed before a successful terminal event and produced no
decision or receipt. The target episodes, anonymous outputs, automated scores, blind bindings, and
condition mapping remain unchanged.

The repaired schema replaces nullable arbitrary per-task output-ID winners with the closed labels
`first`, `second`, and `tie`. The overall choice is constrained to the two exact anonymous output
IDs or `tie`. The ordered anonymous output IDs remain mandatory bindings in every task rating. This
is a judge-instrument repair only; it does not alter target evidence or reveal condition identity.

One replacement tool-free `gpt-5.6-sol`/xhigh judge attempt is allowed using a new local output and
configuration root. Provider-billed calls remain zero.
