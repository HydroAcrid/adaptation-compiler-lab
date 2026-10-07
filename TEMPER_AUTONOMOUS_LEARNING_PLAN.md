# Temper autonomous learning from ordinary work

Status: product direction accepted October 6, 2026; implementation and calibration pending.

October 7 implementation checkpoint: the baseline candidates are installed, Windows
endpoint migration is verified, and the first autonomy backend and desktop controls
are implemented on a separate branch. Live capture and serving remain disabled because
current clients cannot attest human origin. See [implementation status](TEMPER_AUTONOMY_IMPLEMENTATION.md)
for verified work and the remaining gates. The historical design-only authorization
statement below is superseded by owner implementation decisions D-301 and D-302.

Temper should learn useful work habits from normal collaboration. Users should not need special
phrases, a preference questionnaire, or approval for every routine adaptation. After one scoped
onboarding consent, the intended everyday mode observes eligible work, develops hypotheses,
tests them, applies supported low-risk behavior, and keeps inspection and undo available.

## Existing foundation and required extension

The current semantic detector understands informal feedback, but its learning must be entailed by
an exact user message. It does not yet establish autonomous habit inference across several tasks.
The existing review-first path, calibrated explicit-feedback path, signed standing policies,
evaluation cases, scoped projections, delivery receipts, and revocation remain useful foundations.

Add a separate inferred-habit lane. Observations support a provisional behavioral hypothesis;
they are not converted into an explicit user instruction. The standing policy authorizes the
bounded trial and promotion, while the record preserves that the behavior was inferred.

## Observe ordinary collaboration

Start with attributable user messages in registered, consented work sessions: recurring requests,
corrections, accepted alternatives, and changes in requested detail or workflow. Later support
attributable user edits or choices through explicitly enabled connectors. Git authorship alone
cannot distinguish human edits from agent-authored commits.

For example, repeated requests to shorten status updates can support a preference for concise
status updates without the user saying that preference applies forever. It does not establish
that every document should be short. Repeated rejection of generic names can support a naming
preference for future suggestions without authorizing bulk renames.

Count independent episodes and relevant counterexamples. Several messages in one task, copied
content, repeated agent suggestions, or an agent echoing Temper's own projection are not separate
support. Silence and the absence of complaints are not approval or evidence of satisfaction.

Project instructions, repository conventions, tool output, and agent text may explain context
or limit a hypothesis; they do not become personal authority. A project requiring pnpm is not
evidence that the owner prefers pnpm everywhere. Observation remains confined to the enabled
projects, agents, and source categories rather than arbitrary computer activity.

## Evaluate and adapt with little interruption

1. Gather supported observations and alternative explanations in the background.
2. Maintain provisional hypotheses with evidence, contradictions, proposed scope, and risk.
3. Evaluate whether a hypothesis is stable and useful in its proposed context. Calibrate
   confidence using prospective validation rather than accepting a model's confidence number.
4. When the owner's standing policy permits it, trial a supported low-risk adaptation in the
   narrowest useful scope. Otherwise retain it provisionally without nagging the user.
5. Check eligible outcomes, repeated corrections, scope leakage, and review/maintenance effort.
   Promote successful behavior within the authorized category, or narrow/retire unsuccessful
   behavior with preserved history and an accessible undo path.

The first automatic categories should be communication detail, presentation style, and routine
work preferences that are easy to reverse. Requirements involving permissions, credentials,
security, privacy, external actions, or material capability changes cannot be learned into
authorization. Inferred habits cannot weaken required checks or override current instructions.

Broader personal applicability needs evidence across appropriate independent contexts and policy
coverage. Project-specific evidence stays project-specific. New contradictions reduce confidence;
the system should notice a changing habit rather than enforce an old preference indefinitely.

## User experience

Normal work is the input. The user enables the permitted learning sources and automatic categories
once, then continues using the agent normally. Keep a quiet, inspectable account of what changed,
why it is believed, where it applies, and how to undo it. Optional summaries can group changes;
do not require a notification or a decision after every observation.

Show explicit preferences separately from inferred habits. Offer a scope/conflict preview and
connect each adaptation to its observable check or owner feedback. Distinguish delivery,
compliance, and helpfulness: an instruction being delivered is not proof that it was followed.
Machine-checkable behavior can use approved existing verification; subjective preferences can
use feedback. Unmeasured outcomes remain unmeasured.

Ask only for a consequential ambiguity that must be resolved, an unsupported source or category,
or an action outside existing authority. Sparse evidence can remain provisional without a question.
Review-only operation remains available, but it is not the target everyday experience.

## Validation and implementation sequence

After closing the current native compatibility/restart blockers, prototype this narrow learning
loop before adding more Modes or general agent coverage. Design a separately versioned prospective
evaluation containing natural conversations without explicit preference markers, repeated
task-specific constraints, quoted statements, self-reinforcing agent output, changing habits,
unrelated projects, and neutral tasks.

Measure useful detection without prompting, false durable learning, wrong-scope activation,
adaptation to changed habits, repeat corrections per eligible opportunity, interruption frequency,
time to useful adaptation, and net time saved after review and maintenance. Compare with native
memory and a maintained static profile. Preserve cold-start performance when evidence is sparse.

Keep the existing research protocols and their results unchanged. New inferred-habit observations
do not retroactively count as explicit-feedback evidence or pass the old ordinary-use gate.
Automatic serving requires its own calibrated release and an enabled signed policy. This plan
does not enable capture, renew personal consent, modify the current runtime, or authorize provider
sessions, external publication, or a new source of user data.
