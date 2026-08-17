# Persona instrument hardening

This directory contains only raw-free deterministic Milestone 6A.2L.1 artifacts:

- `CALIBRATION-REPORT-v1.json` records the disposable nine-check calibration;
- `V2-SUPERSESSION.json` preserves the original v2 preregistration while marking it superseded
  before execution;
- `V2.1-PREREGISTRATION.json` freezes the corrected roles, pins, sample size, limits, validity
  gates, and failure policy; and
- `V1-IMMUTABILITY-MANIFEST.json` binds the unchanged v1 files by SHA-256 digest.

No v2.1 persona, scenario, private oracle, condition mapping, seed, agent output, or raw trace is
present. The calibration is instrument conformance only and cannot support a Temper performance
claim.
