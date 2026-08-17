# Milestone 6A.2L — Naïve-Agent Persona Evaluation

Status: **framework complete; v1 evaluator gate invalid; no Temper comparison claim**

## Purpose

Milestone 6A.2L implements a scalable synthetic evaluator for a question that genuine dogfood
cannot answer quickly: given one fictional person's documented behavior and one current scenario,
can fresh context-free agents distinguish appropriate governed learning from stale, over-broad, or
less useful alternatives?

The frozen lattice contains six fictional personas, four cumulative checkpoints per persona, 24
cases, 48 reversed-order xhigh judgments, and max adjudication only on disagreement. Every role is
limited to exactly one persona. Judge sessions receive no repository, user configuration, rules,
memories, skills, plugins, MCP servers, tools, web search, prior transcript, condition name, expected
answer, or previous judgment. Temporary configuration and workspace state are destroyed after each
role.

This is synthetic development evidence. It does not count toward ordinary-use dogfood and cannot
establish genuine personalization or cross-agent transfer.

## Frozen v1 result

- six isolated Sol/xhigh static-profile author sessions;
- 48 isolated Sol/xhigh judge sessions;
- nine fresh Sol/max adjudicator sessions;
- 63 accepted sessions and zero provider-billed calls;
- 461,988 input, 68,096 cached input, 25,633 output, and 16,623 reasoning-output tokens;
- 79.2% independent agreement on both learning state and target-visible guidance;
- 6/6 correct final learning-state sentinels and 6/6 correct guidance sentinels;
- nine of 24 cases required at least one adjudication, or 37.5%;
- zero false neutral-scope activations and zero revoked/superseded reference leaks;
- compiled reference projections had a 243-byte maximum and 110.5-byte median;
- strong static guidance had a 128.5-byte median.

The result digest is
`sha256:f4a0ac45b654815c0f4288cbf043c06df7b6149ef3d11fe0585d22e5ae37b20e`.

## Why the gate is invalid

The preregistration required no more than 25% of *cases* to require max adjudication. V1 reached
37.5%, so the condition comparison is suppressed even though both individual track agreement rates
exceeded 75% and every sentinel passed.

This exposed a design mismatch: with two judgments per case, two separate tracks can each meet 75%
agreement while their union causes more than 25% of cases to require adjudication. That rule must
not be weakened after observing v1. A fresh v2 must preregister adjudication stability per track.

V1 also used deterministic reference compiled projections derived from the frozen synthetic trait
specification. It did not execute 18 planned live Luna semantic-sensor sessions. Therefore even a
valid judge result could calibrate the evaluator and projection comparison only; it could not prove
end-to-end semantic extraction. This deviation is permanently recorded and v1 cannot be promoted
into a product-performance result.

## What worked

- One-persona role requests fail before execution if they contain zero or multiple personas.
- Model-authored choices contain no trusted IDs. The host binds persona, case, packet, track, and
  anonymous alternative IDs from frozen inputs.
- Replica two reverses both candidate order and track order.
- Adjudicators receive the original anonymous packet and never earlier votes.
- Strong profiles see only one persona's chronological approved synthetic evidence.
- Raw traces are encrypted outside Git; committed receipts contain only digests and usage.
- Every accepted role used saved ChatGPT authentication and the pinned Codex binary.

## Fresh v2 requirement

V2 must use fresh scenarios and a new seed, run the actual isolated semantic sensor, generate
compiled material only from sensor output plus deterministic policy, retain one persona per session,
and measure adjudication per track. V1 inputs, outputs, receipts, and thresholds remain immutable.
