import { NextResponse } from "next/server";
import { z } from "zod";
import { secretDigest } from "@/lib/canonical";
import { readBoundedJson, serverSupabase } from "@/lib/server";

const requestSchema = z
  .object({
    invite_code: z.string().regex(/^[A-Z0-9-]{12,80}$/),
    platform: z.enum(["windows", "macos"]),
    architecture: z.enum(["x86_64", "arm64"])
  })
  .strict();

export async function POST(request: Request) {
  const body = await readBoundedJson(request, 2_048);
  if (!body.ok) {
    return NextResponse.json(
      { message: body.reason === "too_large" ? "Request is too large." : "Build request is invalid." },
      { status: body.reason === "too_large" ? 413 : 400 }
    );
  }
  const parsed = requestSchema.safeParse(body.value);
  if (!parsed.success) {
    return NextResponse.json({ message: "Build request is invalid." }, { status: 400 });
  }
  const supabase = serverSupabase();
  const { data: invite } = await supabase
    .from("adaptation_compiler_preview_invites")
    .select("status,expires_at")
    .eq("code_digest", secretDigest(parsed.data.invite_code))
    .maybeSingle();
  if (!invite || invite.status !== "issued" || new Date(invite.expires_at) <= new Date()) {
    return NextResponse.json({ message: "Invitation is unavailable." }, { status: 403 });
  }
  const { data: build } = await supabase
    .from("adaptation_compiler_preview_builds")
    .select("storage_object,sha256_digest,app_version")
    .eq("platform", parsed.data.platform)
    .eq("architecture", parsed.data.architecture)
    .eq("status", "active")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (!build) {
    return NextResponse.json({ message: "No signed build is available yet." }, { status: 404 });
  }
  const { data, error } = await supabase.storage
    .from("adaptation-compiler-preview-builds")
    .createSignedUrl(build.storage_object, 15 * 60);
  if (error) {
    return NextResponse.json({ message: "Build link could not be created." }, { status: 500 });
  }
  return NextResponse.json({
    download_url: data.signedUrl,
    expires_in_seconds: 900,
    sha256_digest: build.sha256_digest,
    app_version: build.app_version
  });
}
