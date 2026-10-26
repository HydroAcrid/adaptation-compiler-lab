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
