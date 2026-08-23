import { createClient } from "@supabase/supabase-js";
import { randomBytes, timingSafeEqual } from "node:crypto";
import { secretDigest } from "@/lib/canonical";

export function serverSupabase() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) throw new Error("preview storage is unavailable");
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
}

export function bearerToken(request: Request): string | null {
  const authorization = request.headers.get("authorization");
  if (!authorization?.startsWith("Bearer ")) return null;
  const value = authorization.slice("Bearer ".length);
  return /^[A-Za-z0-9_-]{43}$/.test(value) ? value : null;
}

export function tokenMatches(token: string, expectedDigest: string): boolean {
  const left = Buffer.from(secretDigest(token), "hex");
  const right = Buffer.from(expectedDigest, "hex");
  return left.length === right.length && timingSafeEqual(left, right);
}

export function createInstallationToken(): string {
  return randomBytes(32).toString("base64url");
}

export async function readBoundedJson(
  request: Request,
  maximumBytes = 32_000
): Promise<
  { ok: true; value: unknown } | { ok: false; reason: "too_large" | "invalid" }
> {
  const declared = request.headers.get("content-length");
  if (declared !== null) {
    const contentLength = Number(declared);
    if (!Number.isInteger(contentLength) || contentLength < 0 || contentLength > maximumBytes) {
      return { ok: false, reason: "too_large" };
    }
  }
  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.byteLength > maximumBytes) return { ok: false, reason: "too_large" };
  try {
    return { ok: true, value: JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)) };
  } catch {
    return { ok: false, reason: "invalid" };
  }
}
