# Milestone 6A.2F — Managed Local Bootstrap

Status: implemented, fully verified, and activated for local prospective dogfood.

## Product decision

Internal dogfood must not make the owner manually generate, locate, export, or repeatedly supply
cryptographic keys. That ceremony slows learning and does not improve the experiment. The runtime
still needs authenticated governance and encrypted raw evidence, so the protection remains while
the key-management user experience disappears.

This milestone does not introduce an unsigned or plaintext development mode.

## Managed credentials

`runtime init` now defaults to `--credential-mode managed`. It generates independent Ed25519 and
AES-256 key material in memory and immediately seals both into a Windows CurrentUser DPAPI
envelope bound to the exact subject, signer fingerprint, and complete no-secret runtime config.
No private-key file, raw-key file, passphrase, or `ACLAB_*` environment variable is created. The
config, logs, receipts, and child processes contain no secret bytes.

The existing `--credential-mode external` and `runtime credentials enroll` path remains readable
and usable for compatibility and deliberate research custody. Existing v1 external-reference
envelopes and new v2 managed-key envelopes unlock through the same fail-closed store.

## Lost-credential succession

`runtime credentials rebootstrap` is an explicit recovery boundary for a runtime whose original
credentials are unavailable. It requires `--confirm-lost-credentials` and a different empty state
root. It then:

1. refuses to proceed if the predecessor still has an enrolled envelope;
2. leaves the predecessor config, ledger, raw store, and encrypted payload bytes unchanged;
3. generates a new signer identity, policy, and managed encryption key;
4. copies only no-secret project/runtime configuration;
5. clears old registration signatures and starts one root policy covering the known projects;
6. resets every source boundary to the new prospective capture cutoff;
7. initializes an empty ledger and copies no evidence, artifacts, releases, or feedback; and
8. writes a new-signer-authorized `RuntimeSuccessorReceipt` recording that prior payload recovery
   is unavailable, history was not mutated, and evidence was not copied.

This is a new lineage, not cryptographic rotation and not recovery of the old keys. The successor
receipt is signed only by the new identity and says so through its semantics. It never claims old-
key continuity.

## Fast internal workflow

For a new runtime:

```text
aclab runtime init ...
```

No credential flags or environment variables are needed on Windows. For the current dogfood state:

```text
aclab runtime credentials rebootstrap \
  --config <old-state>/config.json \
  --successor-state-root <new-empty-state> \
  --confirm-lost-credentials
```

After checking `credentials status`, projects may be registered prospectively and polling may
begin. Rebootstrap itself does not read task content, install the watcher, modify source threads,
modify repositories, activate a capability preset, or access sealed Milestone 6 custody.

## Verification target

Success requires:

- v1 external envelope compatibility and v2 managed envelope round trips;
- no secret material in config or envelope JSON;
- wrong subject/config/signer bindings and ciphertext tampering fail closed;
- missing confirmation and nonempty/same successor roots fail closed;
- predecessor bytes remain unchanged;
- successor signer and policy are fresh, all project cutoffs are prospective, and no evidence is
  copied;
- successor receipt binding and signature tampering are rejected;
- real same-user Windows DPAPI unlock works; and
- the complete quality, schema, migration, credential, private-path, raw-payload, and sealed-custody
  checks pass.

## Live local result

On 2026-08-11, the native Windows runtime created a managed successor for the unavailable-key
6A.2C state. The predecessor remained present and unchanged by the command. The successor reported
`evidence_copied=false`, `historical_state_mutated=false`, and
`prior_payload_recovery=unavailable`; same-user DPAPI status then unlocked successfully without any
`ACLAB_*` environment variables.

Green Meadow and Kairn were registered read-only with registration digests
`sha256:21a9ffa971294a8c7e792f230af5306427cdbb26f0b7946ba422be76eb380e2e` and
`sha256:226e30ee94cdcd7ccdbb7df7f84f12a0036b65dacbcfb822d26fb313a2bd9cfd`.
Metadata-only previews still reported two historical tasks, zero prospectively eligible tasks, and
zero content reads in each project. The first three-project poll appended zero items, advanced only
the raw-free source checkpoint, and left generation, artifacts, reviews, activations, and feedback
at zero. The watcher remains uninstalled.

## Scope boundary

This milestone improves local product ergonomics only. It does not weaken encryption, remove
signatures, recover unavailable ciphertext, create a generic secrets platform, automate promotion,
change the semantic detector, run provider-billed calls, or alter/reveal the deferred Milestone 6
study.
