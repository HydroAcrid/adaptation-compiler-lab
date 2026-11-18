# Persistent repository setup

This development candidate connects the existing persistent controller to the
desktop app and a separate Codex MCP endpoint. It does not add Modes or replace
SkillKit. Owner installation, native checks and release evidence belong to the
exact candidate receipts, not this document.
The first native integration trial is Windows-only. Native macOS packaging,
manager behavior and executable-resource handling need their own platform proof.

## Workflow

1. In **Modes → Repository setup**, choose repositories and the existing
   pstack, Superpowers and Ponytail publishers. Review the exact skill folders,
   registration markers, publisher URLs/roots and private manager destination.
2. Temper provisions pinned, optional-free SkillKit 1.24.0 using an existing
   Node.js 24 installation. npm install scripts are disabled. Manager processes
   use a private home and do not inherit provider credentials.
3. **Connect Codex** previews a separate `temper_hub` MCP entry and a small
   section in the active user instruction file. Other settings and manual text
   are preserved. Start a new chat or use a separately verified supported reload.
4. The ordinary coding agent supplies the repository ID, work goal, task class
   and relative working directory. SkillKit's ranking is advisory. The agent
   inspects the relevant guidance and dependencies, then chooses up to two
   applicable skills, or none. No additional selector model or API fallback runs.
5. Unchanged contexts reuse their profiles. A changed goal or native policy
   clears the previous owned task profile before another selection. A stale
   selection cannot overwrite a profile changed by another task. Concurrent,
   incompatible work should use separate worktrees; one checkout has one current
   native profile. Current requests and native policy remain authoritative.
6. The app's existing five-minute scheduler checks whether an approved-source
   refresh is due; upstream checks run at most every six hours. Updated guidance
   is indexed for the connected agent to recheck at the next applicable task.
   Maintenance does not autonomously execute downloaded skill scripts, install
   framework services, launch extra agents or broaden publisher permission.

The read-only `temper` endpoint remains unchanged. The distinct `temper_hub`
endpoint exposes only status, prepare, inspect and select. It cannot grant
permission, change personal learning, register projects or run arbitrary commands.
Long desktop setup/maintenance operations run outside its IPC request loop. MCP
task operations use their own process and return the bounded operation's result.

## Ownership, recovery and storage

Hub permission is a separate owner-signed decision. A learning registration is a
repo picker entry, never permission to install tools. The grant binds physical
repository identities and exact publisher URLs, refs and skill roots. Device
permissions do not transfer automatically.

Only authenticated public snapshots reach the index. Signed acquisition records
bind revision, canonical cache path, resource tree and license records. The
private manager's full installed tree, Node binary and packaged lock are admitted
together. A changed manager or index fails closed.

Publication stages complete original resources through SkillKit, validates them,
and adds publisher license/provenance records. Digest checks and signed journals
protect existing files and recover interrupted publication. Deleted or edited
managed files are treated as owner changes. Undo retains the previous bundle and
rejects immediate regeneration of the undone update. Stopping permission takes
effect immediately; cleanup preserves edits and reports remaining files even
while permission is disabled.

The Hub uses a 1 GB storage budget, a 512 MB public source cache, bounded profiles
and command receipts, and at most 1,000 recent tool-management events. These are
separate from the append-only personal-learning history. Native manager processes
have time/output bounds and owned-descendant cleanup. Source refreshes preserve
the existing working profile on failure. Repair reinstalls only the private
manager and refreshes already approved sources.

Generated tool folders and registration markers can appear in repository status;
this version does not change Git ignore policy or commit them automatically.
Repository goals are transient inputs; only goal digests are retained. Public
skill text and agent packets are not personal preference evidence. Existing
learning scopes, cutoffs, retention, qualification and history are independent.

## Evidence and remaining proof

Tests exercise source substitution, policy changes including personal skills and
ancestor/subdirectory instructions, stale selections, complete resources,
manual edits/deletions, pause/revoke, rollback, interrupted publication and native
connection recovery. Fake-manager tests establish controller mechanics only.
Native SDK and packaged Tauri checks must be identified separately in private
candidate-bound receipts.

This integration does not establish net user effort saved, coding quality or
real-work helpfulness. The owner-selected Kairn update and website comparison
against native agents with existing managers and SkillKit remains the usefulness
test. Include research, setup, switching, updates, compatibility, recovery, review
and all overhead. Agent runtime and fixture activity are not owner attention.

The combined product remains a development candidate until its applicable
native, installation, portability and actual-work gates pass. Signing and public
distribution have separate requirements. Existing frozen learning evaluation
results do not qualify this Hub, and Hub evidence cannot complete the historical
personalization research protocol.

## Evaluate a check update locally

Maintainers can compare two signed `.temper-setup` files against a trusted
local replay suite. Keep the currently approved package and its recorded digest
and publisher fingerprint. Use those approved values to pin the baseline and
publisher in the replay suite.

```text
uv run python scripts/evaluate_workflow_update.py --baseline baseline.temper-setup --candidate candidate.temper-setup --replay replay.json
```

The replay JSON uses `format: "temper-workflow-replay/v1"`, `baseline_digest`,
`signer_fingerprint`, and a `cases` array. Each case has an `id`, a `files`
array of repository-relative `path` and `text` pairs, and an `expected` object
mapping check IDs to booleans. Use `null` for a missing fixture file. Supply
expected pass and fail outcomes for each check on distinct inputs. Define
expectations independently of the packages being compared.

The evaluator accepts updates to existing check literals from the same approved
publisher. It holds the setup title, item order and identity, guidance, and
check paths and operations fixed. Both versions run against the same synthetic
files in isolated temporary directories. The JSON report gives input digests,
correct outcomes, and case and check IDs for failures and changes. Exit code 0
means the candidate fixed at least one miss and passed the whole suite, 1 means
the update was ineligible, and 2 means an input or usage error.

The report identifies the exact candidate a maintainer evaluated. Evaluation is
offline and leaves active setups untouched.

## Follow workflow updates in Temper

In Tools & workflows, find the repository's active setup and choose **Connect
update source**. Select a folder that your approved publisher or distribution
process can update. Put the publisher's signed candidate in that folder as
`workflow.temper-setup`. Then select a trusted JSON file containing the test
cases for the active setup. Keep that file outside the source folder and supply
it independently of the candidate.

Temper checks the connected folder when you return to the page. Review an
available version to see how many test outcomes the current and proposed
versions got right. The new version must fix at least one miss, pass every
case, and come from the same publisher as your current setup. Choosing **Apply
workflow update** applies the reviewed version to that repository. **Restore
previous setup** works even if the source is unavailable. For another version, reconnect
with trusted test cases pinned to the new active setup.

The source folder can be synced by a distribution process you already trust.
Temper watches that folder through the desktop workflow. Hosted discovery and
delivery of source updates are outside this local integration.
