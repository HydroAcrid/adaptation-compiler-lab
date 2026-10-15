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
