import { randomBytes } from "node:crypto";
import { NextResponse } from "next/server";
import { z } from "zod";
import { digest, secretDigest } from "@/lib/canonical";
import { createInstallationToken, readBoundedJson, serverSupabase } from "@/lib/server";

const requestSchema = z
  .object({
    invite_code: z.string().regex(/^[A-Z0-9-]{12,80}$/),
    platform: z.enum(["windows", "macos"]),
    architecture: z.enum(["x86_64", "arm64"]),
    app_version: z.string().regex(/^[0-9]+\.[0-9]+\.[0-9]+(?:a[0-9]+)?$/),
    reporting_public_key_base64: z.string().regex(/^[A-Za-z0-9+/]{43}=$/)
  })
  .strict();

export async function POST(request: Request) {
  const body = await readBoundedJson(request, 4_096);
  if (!body.ok) {
    return NextResponse.json(
      { message: body.reason === "too_large" ? "Request is too large." : "Invitation request is invalid." },
      { status: body.reason === "too_large" ? 413 : 400 }
    );
  }
  const parsed = requestSchema.safeParse(body.value);
  if (!parsed.success) {
    return NextResponse.json({ message: "Invitation request is invalid." }, { status: 400 });
  }
  const supabase = serverSupabase();
  const inviteDigest = secretDigest(parsed.data.invite_code);
  const { data: invite } = await supabase
    .from("adaptation_compiler_preview_invites")
    .select("id,status,expires_at")
    .eq("code_digest", inviteDigest)
    .maybeSingle();
  if (!invite || invite.status !== "issued" || new Date(invite.expires_at) <= new Date()) {
    return NextResponse.json({ message: "Invitation is unavailable." }, { status: 403 });
  }
  const token = createInstallationToken();
  const installationId = `installation-${randomBytes(16).toString("hex")}`;
  const publicKeyFingerprint = digest({
    reporting_public_key: parsed.data.reporting_public_key_base64
  });
  const { error } = await supabase.rpc("redeem_adaptation_compiler_invite", {
    p_invite_id: invite.id,
    p_installation_id: installationId,
    p_token_digest: secretDigest(token),
    p_public_key_base64: parsed.data.reporting_public_key_base64,
    p_public_key_fingerprint: publicKeyFingerprint,
    p_platform: parsed.data.platform,
    p_architecture: parsed.data.architecture,
    p_app_version: parsed.data.app_version
  });
  if (error) {
    return NextResponse.json({ message: "Invitation could not be redeemed." }, { status: 409 });
  }
  return NextResponse.json({ installation_id: installationId, installation_token: token });
}
