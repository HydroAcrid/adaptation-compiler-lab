# Native fixes and immediate evaluation — October 12, 2026

Functional Windows candidate `448ab1b831bce05fc89012ee84a76bbacb8ad689` is installed.
The terminal CLI contains the same functional repair. Developer driver `43194bf`
adds owner-requested rapid testing without changing personal background learning.
No GitHub CI pipelines ran. Draft PR #92 remains in development, stacked on #91.

The compiled workflow exposed and repaired three actual defects:

- Refresh timestamps and derived review ages changed the snapshot digest on every
  read, rejecting valid registration and review clicks. State bindings now omit only
  those display fields; actual state, consent expiry, undo eligibility and preferences
  still invalidate a stale click.
- Review and Discard tried to validate stored JSON timestamps as Python datetime
  objects. Both now use strict JSON-mode validation of the encrypted baseline.
- Runtime and gateway SQLite connections stayed open until garbage collection.
  Both ledgers now explicitly close them, preserving commit and rollback behavior.

470 targeted Python tests passed with four platform-only skips. The foreground
driver subsequently passed ten tests, including immediate execution beyond the
background allowance, quota refusal, separate bindings, interruption and failure
handling. Changed source and checks passed typing/lint/format.

Fresh native engine/hook, desktop UI/app and NSIS builds passed. Previous binaries
were preserved. The installed candidate passed two disposable-profile starts and
configured-engine admission. Secure storage is available, configuration/protected
envelope/history bytes are unchanged, zero personal habits, and grants, learning,
personalization and automatic serving remain off. Read-only terminal status loads.

`scripts/validate_installed_windows_workflow.py` passed against both the newly
compiled and installed engine. It exercises consent refusal/confirmation, prospective
registration, stale-state rejection, replay, restart, fixture-bundle Apply/Discard,
failed postflight rollback, encrypted export, wrong-passphrase rejection, same-owner
identity and history recovery, path rebinding, and a restored restart. It uses disposable
fictional state, makes zero provider calls and removes successful temporary state.
One earlier failed check's partial temporary residue remains outside Git/vault;
automatic review blocked recursive cleanup with only "blocked by policy" as its reason.

These are same-host native engine checks. The bundles are constructed fixtures,
not model-generated tasks. Rendered desktop controls/dialog interaction, independent
installation, trusted signing, native loading/following and everyday usefulness
remain separate gates.

Installed artifact SHA-256:

| Artifact | SHA-256 |
|---|---|
| Engine | `5dd5d86c1a47d3224a3b0db84ef6b498fc81d7194df09c9219e038afe56654c3` |
| Hook | `d4d05f6bd40c5d005ddc55a47d602761c0037b96f7ce8db87ea5794bf73fe937` |
| App | `a9a7767c4f919f7f1dbc3687b4a294923b62a385b999159c711488be784c7bc4` |
| Installer | `34af9d3a34e2c8eeadf0c309feb3c70df647526c823f13346078dfa08aa8db66` |

## Fixed scoring does not require slow execution

Frozen means fixed cases, expected labels, model contract, lifecycle defaults and
scoring before execution. It protects against moving the goalposts. The five-minute
and 12-session limits belong to personal background learning. Reusing those limits
for owner-requested developer evaluation unnecessarily delayed feedback.

The original paced v3 run remains intact with seven completed cases. The separate
foreground run uses the same 120 fictional cases/140 phases, exact configured model
and effort, host/scorer and native contract. Its signed execution binding also
includes the foreground driver digest. Runs and results are not combined. Analyses
run sequentially with fresh known subscription capacity of at least 20%; there is no
API-key fallback, silent model substitution, personal capture or native publication.
Interrupted/failed phases and binding changes require attention, not silent retries.

Read foreground progress without model inference:

```powershell
.venv\Scripts\python.exe scripts/run_owner_habit_evaluation.py --config <existing-config>
```

Add `--run-now` for an explicit owner-requested run. Its results cannot install
serving calibration or complete historical explicit-feedback/real-work gates. Early
execution found correct stable-habit detection but false hypotheses from task and
repository constraints. Final counts belong in the signed private report and concise
shared checkpoint; do not change labels or tune defaults against those results.

The owner authorized daily continuation through the app heartbeat, at 17:00 in the
configured timezone. It stays quiet during routine progress/deferral, reports
meaningful results, completion, actionable failure or required input, and pauses
after the full series completes.

Both currently active Windows chats exercised native read-only Temper MCP access.
Their applicable profiles are empty. The Mac is unavailable for fresh validation
or synchronization; its checkout/runtime were not changed. Production human-input
attribution remains unresolved, and no alternative submission route or permission
was added. Finish/review the website before LinkedIn preparation; public posting
still requires an explicit request.
