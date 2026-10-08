# Ordinary Codex input-origin admission — October 8, 2026

Production human-message attribution is not admitted. The native factory has no
provenance verifier or conversation reader for the new learning lane, so it stops
before capture. A signed receipt validator is implemented; it is not a producer of
trustworthy origin facts. The supported clients cannot presently supply those facts.

## Audited surfaces

| Surface | Evidence | Admission result |
|---|---|---|
| Windows 0.162.0-alpha.2 and retained 0.160.1 | Exact binary/schema pins; `UserMessageThreadItem` exposes type, id, content, clientId. | No positive human-origin witness. |
| Apple Silicon macOS 0.157.0 | Native contract and exact binary previously validated; same four message fields. | No positive human-origin witness. |
| Thread source/originator | Metadata identifies thread creation context, not the producer of every later message. | Cannot establish human origin. |
| UserPromptSubmit hook | Documented event-specific fields are turn ID and prompt; common fields identify session, working directory, hook event, model, permissions, transcript. | Event name does not attest a human producer. |
| Stop continuation | Official documentation describes a generated continuation prompt acting as a new user prompt. | Counterexample to user-prompt-as-human attribution. |
| Known coordination function output | Explicit send-message/delegation tool provenance identifies automation. | May exclude delegated input; its absence cannot prove human input. |

Hook facts were checked against the current
[official hooks documentation](https://learn.chatgpt.com/docs/hooks#userpromptsubmit)
and its [Stop continuation behavior](https://learn.chatgpt.com/docs/hooks#stop).
The inference is that these documented fields alone cannot distinguish all human
and automated inputs. This is a bounded finding about the inspected interfaces;
it is not a claim that future Codex versions or an additional supported interface
can never provide reliable origin information.

`test_provenance_admission.py` verifies the pinned schemas and synthetic negative
controls. Those fixtures cannot count as successful real human/automated client
admission. Client IDs, thread metadata, hook names, caller-provided origin labels,
and self-asserted signatures must remain excluded as positive witnesses.

## Evidence required to unblock the current product

A supported source producer must distinguish human input from automated/delegated
input independently of caller-supplied prompt fields. The verified record must bind
the actual message and text to the exact client/version/binary, project and task.
Both real human and automated fixture paths must pass on Windows and macOS before
that producer is admitted. Unknown origin must continue to be excluded.

The existing signed receipt boundary can bind and check such verified records; it
must not sign a guessed human label into apparent authority. The eventual adapter
must use the existing prospective conversation source, not a second raw capture
system. Keep ambiguous material and programmatic coordination outside personal
preference evidence; raw private fixtures must stay encrypted outside Git/vault.

Enabling learning does not resolve this missing source fact. A new input UI, general
keyboard monitoring, or an alternative capture source would change the approved
ordinary-Codex scope and permissions. None was installed as a workaround. Until a
supported producer route exists, verified read-only status/context remains usable,
while capture and automatic serving remain disabled.

## Native submission counterexample

After Kevin resumed the attribution task, metadata-only inspection of the actual
Windows/Mac Temper chats found `internal_chat_message_metadata_passthrough` fields
omitted by public thread history. Direct text had `content_item_kinds=["user.text"]`;
goal, environment and instruction records had different kinds. Received Mac
coordinator messages remained function outputs. These observations initially made
the sideband look like a possible origin witness.

A real Windows counterexample against the exact `0.162.0-alpha.2` binary disproved
that interpretation. A plain programmatic `turn/start` created both a `user.text`
record and a native UserMessage completion event. The caller could also claim a
desktop client name during initialization. Separately, a programmatic raw-item
injection preserved caller-provided `user.text` metadata outside an active turn.
Thus these fields label content and do not independently prove a human submission.

The Mac counterpart then reproduced the same programmatic `user.text` marker and
UserMessage event on exact native `0.157.0`, using driver commit `a079fa5` with script
SHA-256 `ae09d0cd5cf405dc78023ef2fdb1ecfa1a43e2ad638b6f24bc5c74f92afe68e3`.
Its binary SHA-256 was `61b0194f3bb6534439c8d26a3ed57d0805f84b884588b761795323eeb92fcf70`.

The probes used fictional text, a disposable auth-only home and workspace, disabled
capabilities, exact model/effort and subscription-capacity checks. The final input
probe was interrupted after its input event. Private authentication/state were
deleted on exit; no personal capture, grant, publication, or CI occurred. The Mac
checkout and registered bridge remained at `4bd400d`; the temporary driver was removed.

Reliable positive attribution needs an independent record from the submission
boundary. A Temper-controlled composer could create a separate producer record
before forwarding the message to Codex, while the existing Codex conversation
adapter remains the capture system. This changes the selected source/input route
and needs an owner workflow decision. It must expose no agent-callable operation
that can simply assert a human origin, preserve project/source/category permission,
and pass actual human and automated native fixtures before admission. Keeping the
existing Codex composer unchanged remains unsupported by the inspected metadata.

The input-route question is pending with Kevin. No submission bridge or new source
permission has been created. The signed receipt validator does not itself establish
that a UI submission was human; a new producer still needs a reviewed native boundary
and actual human-versus-automation fixtures before it can grant that classification.
