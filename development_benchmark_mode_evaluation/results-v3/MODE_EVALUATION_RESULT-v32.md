# Temper Capability Mode Evaluation

This is a bounded same-agent development comparison, not a general product or cross-model claim.

| Mode | Gate | Diagnostics (Core → Mode) | Neutral (Core → Mode) | Blind quality (Core / Mode / Tie) | Projection bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| frontend-studio | PASS | 6 → 6 | 3 → 3 | 0 / 1 / 4 | 995 |
| research-analyst | FAIL | 9 → 9 | 3 → 3 | 0 / 0 / 5 | 872 |
| secure-backend | FAIL | 8 → 8 | 6 → 6 | 1 / 1 / 3 | 892 |

## Task-level matrix

| Mode | Task | Kind | Automated | Blind quality | Core | Mode |
| --- | --- | --- | --- | --- | ---: | ---: |
| frontend-studio | frontend-01-settings | diagnostic | tie | tie | 0/4 | 0/4 |
| frontend-studio | frontend-02-review-queue | diagnostic | tie | tie | 3/3 | 3/3 |
| frontend-studio | frontend-03-onboarding | diagnostic | tie | tie | 3/3 | 3/3 |
| frontend-studio | frontend-04-neutral-parser | neutral_control | tie | core-plus-mode | 0/3 | 0/3 |
| frontend-studio | frontend-05-neutral-research | neutral_control | tie | tie | 3/3 | 3/3 |
| research-analyst | research-01-version | diagnostic | tie | tie | 3/3 | 3/3 |
| research-analyst | research-02-conflict | diagnostic | tie | tie | 3/3 | 3/3 |
| research-analyst | research-03-negative | diagnostic | tie | tie | 3/3 | 3/3 |
| research-analyst | research-04-neutral-css | neutral_control | tie | tie | 0/3 | 0/3 |
| research-analyst | research-05-neutral-refactor | neutral_control | tie | tie | 3/3 | 3/3 |
| secure-backend | secure-01-tenant | diagnostic | tie | core-plus-mode | 2/3 | 2/3 |
| secure-backend | secure-02-webhook | diagnostic | tie | tie | 3/3 | 3/3 |
| secure-backend | secure-03-redaction | diagnostic | tie | tie | 3/3 | 3/3 |
| secure-backend | secure-04-neutral-layout | neutral_control | tie | core-only | 3/3 | 3/3 |
| secure-backend | secure-05-neutral-copy | neutral_control | tie | tie | 3/3 | 3/3 |

All target and judge sessions used saved ChatGPT authentication. Provider-billed calls: 0. The deferred external-validation study remained sealed and unaccessed.
