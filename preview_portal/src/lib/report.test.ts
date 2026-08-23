import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import { readFileSync } from "node:fs";
import test from "node:test";
import { canonicalJson, digest } from "./canonical";
import { aggregateEnvelopeSchema, verifyEnvelope } from "./report";
import { readBoundedJson } from "./server";

function fixture() {
  const report = {
    report_version: "1.0.0" as const,
    report_id: `report-${"a".repeat(32)}`,
    installation_id: `installation-${"b".repeat(32)}`,
    app_version: "0.2.0a1",
    platform: "windows" as const,
    architecture: "x86_64" as const,
    period_started_at: "2026-08-01T00:00:00Z",
    period_ended_at: "2026-08-08T00:00:00Z",
    active_days: 4,
    eligible_interactions: 8,
    correct_learning: 7,
    false_learning: 1,
    missed_learning: 0,
    pending_reviews: 0,
    resolved_reviews: 2,
    activations: 4,
    correct_activations: 4,
    false_activations: 0,
    helped: 3,
    hurt: 0,
    irrelevant: 1,
    repeated_corrections: 0,
    maintenance_actions: 2,
    projection_size: { latest_utf8_bytes: 200, maximum_utf8_bytes: 240 }
  };
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const rawPublicKey = publicKey.export({ format: "der", type: "spki" }).subarray(-32);
  const publicKeyBase64 = rawPublicKey.toString("base64");
  const envelope = {
    envelope_version: "1.0.0" as const,
    report,
    reporting_key_fingerprint: digest({ reporting_public_key: publicKeyBase64 }),
    signature_base64: sign(null, Buffer.from(canonicalJson(report), "utf8"), privateKey).toString("base64")
  };
  return { envelope, publicKeyBase64 };
}

test("strict aggregate envelope verifies", () => {
  const { envelope, publicKeyBase64 } = fixture();
  const parsed = aggregateEnvelopeSchema.parse(envelope);
  assert.equal(verifyEnvelope(parsed, publicKeyBase64), true);
});

test("free-form and tampered reports are refused", () => {
  const { envelope, publicKeyBase64 } = fixture();
  assert.equal(aggregateEnvelopeSchema.safeParse({ ...envelope, prompt: "private" }).success, false);
  envelope.report.active_days = 5;
  const parsed = aggregateEnvelopeSchema.parse(envelope);
  assert.equal(verifyEnvelope(parsed, publicKeyBase64), false);
});

test("actual request bytes are bounded even without a content-length header", async () => {
  const request = new Request("https://preview.invalid/api/reports", {
    method: "POST",
    body: JSON.stringify({ payload: "x".repeat(128) })
  });

  assert.deepEqual(await readBoundedJson(request, 32), { ok: false, reason: "too_large" });
});

test("server verifies the exact Python desktop signature vector", () => {
  const fixture = JSON.parse(
    readFileSync(new URL("./fixtures/python-envelope.json", import.meta.url), "utf-8")
  );
  const envelope = aggregateEnvelopeSchema.parse(fixture.envelope);

  assert.equal(verifyEnvelope(envelope, fixture.public_key_base64), true);
});
