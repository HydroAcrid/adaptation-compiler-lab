# Public source — October 12, 2026

The owner authorized making `HydroAcrid/adaptation-compiler-lab` and `HydroAcrid/kairn`
public. GitHub's settings API applied both changes, and unauthenticated repository reads
confirmed `private: false` and `visibility: public` for each existing repository. History,
default branches and research branches were preserved. No release, download, LinkedIn
post, source-history rewrite or GitHub CI run was initiated.

A private mirror of every remote Git ref was scanned using the official Gitleaks 8.30.1
Linux package after its published SHA-256 checksum was verified. Redacted reports and
temporary recovery records stayed outside both repositories and the shared vault.

Temper's six historical scanner findings were duplicate sightings of a test idempotency
key, a fake token in a credential rejection fixture, and an Ed25519 type declaration.
Kairn's 31 sightings were cache/source hashes and fictional benchmark examples: detector
test strings, localhost CSRF examples, and malformed private-key samples. The latter were
checked with a PEM parser and were not parseable private keys. Historical raw-named
benchmark artifacts were also checked for source provenance and runtime/private-file paths;
they are lab/public-source benchmark materials rather than personal runtime conversations.

Available historical Actions logs were downloaded for read-only scanning. Temper had
54 available logs from 57 runs; Kairn had 48 available logs from 95 runs. All available logs
produced zero secret findings. The remaining logs were unavailable or expired and were
not claimed as inspected. Unredacted temporary scanner detail was removed after classification.
Scanner results are a scoped pre-publication check, not proof that no sensitive string can exist.

Public source availability does not change product evidence. Temper's autonomous serving
gate remains closed; Kairn's unpromoted semantic research remains separate from its shipping
npm beta. Commits on development branches and draft PRs remain reviewable source work.
