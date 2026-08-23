import { NextResponse } from "next/server";
import { digest } from "@/lib/canonical";
import { aggregateEnvelopeSchema, verifyEnvelope } from "@/lib/report";
import { bearerToken, readBoundedJson, serverSupabase, tokenMatches } from "@/lib/server";

export async function POST(request: Request) {
  const body = await readBoundedJson(request);
  if (!body.ok) {
    return NextResponse.json(
      { message: body.reason === "too_large" ? "Report is too large." : "Report is invalid." },
      { status: body.reason === "too_large" ? 413 : 400 }
    );
  }
  const token = bearerToken(request);
  const parsed = aggregateEnvelopeSchema.safeParse(body.value);
  if (!token || !parsed.success) {
    return NextResponse.json({ message: "Report is invalid." }, { status: 400 });
  }
  const supabase = serverSupabase();
  const { data: installation } = await supabase
    .from("adaptation_compiler_installations")
    .select("id,installation_id,token_digest,reporting_public_key_base64,status")
    .eq("installation_id", parsed.data.report.installation_id)
    .maybeSingle();
  if (
    !installation ||
    installation.status !== "active" ||
    !tokenMatches(token, installation.token_digest) ||
    !verifyEnvelope(parsed.data, installation.reporting_public_key_base64)
  ) {
    return NextResponse.json({ message: "Report authorization failed." }, { status: 403 });
  }
  const { error } = await supabase.from("adaptation_compiler_aggregate_reports").insert({
    installation_id: installation.id,
    report_id: parsed.data.report.report_id,
    report_version: parsed.data.report.report_version,
    payload: parsed.data.report,
    report_digest: digest(parsed.data.report),
    reporting_key_fingerprint: parsed.data.reporting_key_fingerprint,
    signature_base64: parsed.data.signature_base64
  });
  if (error?.code === "23505") {
    return NextResponse.json({ status: "already_received" });
  }
  if (error) {
    return NextResponse.json({ message: "Report could not be stored." }, { status: 500 });
  }
  return NextResponse.json({ status: "accepted" }, { status: 201 });
}

export async function DELETE(request: Request) {
  const token = bearerToken(request);
  const installationId = new URL(request.url).searchParams.get("installation_id");
  if (!token || !installationId || !/^installation-[a-f0-9]{32}$/.test(installationId)) {
    return NextResponse.json({ message: "Deletion request is invalid." }, { status: 400 });
  }
  const supabase = serverSupabase();
  const { data: installation } = await supabase
    .from("adaptation_compiler_installations")
    .select("id,installation_id,token_digest,status")
    .eq("installation_id", installationId)
    .maybeSingle();
  if (!installation || installation.status !== "active" || !tokenMatches(token, installation.token_digest)) {
    return NextResponse.json({ message: "Deletion authorization failed." }, { status: 403 });
  }
  const { error } = await supabase.rpc("delete_adaptation_compiler_reports", {
    p_installation_id: installation.id
  });
  if (error) {
    return NextResponse.json({ message: "Reports could not be deleted." }, { status: 500 });
  }
  return NextResponse.json({ status: "deleted" });
}
