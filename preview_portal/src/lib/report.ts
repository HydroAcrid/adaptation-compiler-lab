import { createPublicKey, timingSafeEqual, verify } from "node:crypto";
import { z } from "zod";
import { canonicalJson, digest } from "@/lib/canonical";

const count = z.number().int().nonnegative();
const reportId = z.string().regex(/^report-[a-f0-9]{32}$/);
const installationId = z.string().regex(/^installation-[a-f0-9]{32}$/);
const sha256Digest = z.string().regex(/^sha256:[a-f0-9]{64}$/);
const signature = z.string().regex(/^[A-Za-z0-9+/]{86}==$/);

export const aggregateReportSchema = z
  .object({
    report_version: z.literal("1.0.0"),
    report_id: reportId,
    installation_id: installationId,
    app_version: z.string().regex(/^[0-9]+\.[0-9]+\.[0-9]+(?:a[0-9]+)?$/),
    platform: z.enum(["windows", "macos"]),
    architecture: z.enum(["x86_64", "arm64"]),
    period_started_at: z.iso.datetime({ offset: true }),
    period_ended_at: z.iso.datetime({ offset: true }),
    active_days: z.number().int().min(0).max(31),
    eligible_interactions: count,
    correct_learning: count,
    false_learning: count,
    missed_learning: count,
    pending_reviews: count,
    resolved_reviews: count,
    activations: count,
    correct_activations: count,
    false_activations: count,
    helped: count,
    hurt: count,
    irrelevant: count,
    repeated_corrections: count,
    maintenance_actions: count,
    projection_size: z
      .object({
        latest_utf8_bytes: z.number().int().min(0).max(12_000),
        maximum_utf8_bytes: z.number().int().min(0).max(12_000)
      })
      .strict()
  })
  .strict()
  .superRefine((report, context) => {
    if (report.correct_learning + report.false_learning > report.eligible_interactions) {
      context.addIssue({ code: "custom", message: "learning totals are incoherent" });
    }
    if (report.correct_activations + report.false_activations > report.activations) {
      context.addIssue({ code: "custom", message: "activation totals are incoherent" });
    }
    if (report.helped + report.hurt + report.irrelevant > report.activations) {
      context.addIssue({ code: "custom", message: "feedback totals are incoherent" });
    }
    if (report.projection_size.latest_utf8_bytes > report.projection_size.maximum_utf8_bytes) {
      context.addIssue({ code: "custom", message: "projection totals are incoherent" });
    }
    if (new Date(report.period_ended_at) < new Date(report.period_started_at)) {
      context.addIssue({ code: "custom", message: "report period is reversed" });
    }
  });

export const aggregateEnvelopeSchema = z
  .object({
    envelope_version: z.literal("1.0.0"),
    report: aggregateReportSchema,
    reporting_key_fingerprint: sha256Digest,
    signature_base64: signature
  })
  .strict();

export type AggregateEnvelope = z.infer<typeof aggregateEnvelopeSchema>;

const ED25519_SPKI_PREFIX = Buffer.from("302a300506032b6570032100", "hex");

export function verifyEnvelope(envelope: AggregateEnvelope, publicKeyBase64: string): boolean {
  const publicKey = Buffer.from(publicKeyBase64, "base64");
  if (publicKey.length !== 32) return false;
  const expectedFingerprint = digest({ reporting_public_key: publicKeyBase64 });
  const left = Buffer.from(expectedFingerprint, "utf8");
  const right = Buffer.from(envelope.reporting_key_fingerprint, "utf8");
  if (left.length !== right.length || !timingSafeEqual(left, right)) return false;
  const key = createPublicKey({
    key: Buffer.concat([ED25519_SPKI_PREFIX, publicKey]),
    format: "der",
    type: "spki"
  });
  return verify(
    null,
    Buffer.from(canonicalJson(envelope.report), "utf8"),
    key,
    Buffer.from(envelope.signature_base64, "base64")
  );
}
