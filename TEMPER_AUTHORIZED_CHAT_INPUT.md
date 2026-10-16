# Owner-authorized conversation input — October 14, 2026

The owner chose the existing Codex/ChatGPT composer and explicitly accepted messages
carried between user-authorized agent conversations as valid learning input. The absence
of native human-versus-automation attribution must not block this opted-in workflow.

This changes the original strict-human-only observation policy. It does not establish
human authorship, extend source permissions automatically, or make generated memory,
tool results, quoted material or repository requirements independent personal choices.

Implementation decision: add an explicit versioned learning-grant policy for owner-trusted
conversation inputs in selected registered projects. Keep the strict verified-human route
and legacy grants intact. Record uncertain authorship as owner-authorized conversation
input; infer scoped style habits from it without labeling statements as expressed human
preferences. Retain task independence, prospective cutoffs, encryption/retention, current
instruction precedence, pause/revoke/undo and release gates. Default serving stays off.

The existing source connector and background worker remain the capture path. No Temper
composer, fabricated human-origin receipt, historical backfill, web-ChatGPT capture or
additional agent/client integration is introduced by choosing the existing composer.

Semantic eligibility changes require a new evaluation version. Historical human-only
results remain historical; previously disallowed automated inputs remain disallowed
without the new owner-authorized grant. Trusted relays must be covered by dedicated
positive and negative controls, including self-reinforcement and scope/correction cases.

## Candidate validation

The v14 trusted-conversation development screen reused eight previously seen fictional
sequences (nine analysis phases): five eligible detections, zero false positives or
misses, and the affected changing habit paused. This is a small development screen,
not fresh prospective calibration or a general accuracy claim. It used saved ChatGPT
authentication and explicitly selected Sol at medium effort; no paid API fallback.

Selected local checks passed: 395 Windows tests with two platform skips, 38 focused
WSL tests, 80 renderer tests and 15 Rust tests. The compiled native engine passed
disposable setup/registration, trusted grant/restart/pause/revocation, Apply/Discard/
rollback and encrypted recovery checks. No model call or personal-runtime mutation
was made by that workflow. Fresh Mac and independent installation checks remain open.

The current Windows Codex executable was replaced by its updater without a version
change. A fresh generated-schema comparison admitted its exact new binary digest;
unknown binaries remain refused. The existing personal endpoint was rebound while
preserving identity and historical evidence. Expired legacy consent was not renewed.

Personal onboarding is a separate operation after candidate review and installation.
It must select existing registered projects, record a new prospective cutoff and keep
personalization off. No historical conversations are imported and no active chat is
claimed to have loaded an adaptation. The desktop must remain running for its existing
five-minute background worker. All packages and checks are local; no GitHub CI is used.
