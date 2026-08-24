import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const ornamentPath = join(
  process.cwd(),
  "public",
  "assets",
  "ornaments",
  "antique-acanthus-corner.svg",
);
const expectedDigest =
  "cefed89f0b17b5b5cff6ea5c4a921cad65b81a8e6a9acf38e7bcc491d2f14997";

describe("vendored visual assets", () => {
  it("keeps the reviewed and sanitized CC0 ornament byte exact", () => {
    const asset = readFileSync(ornamentPath);

    expect(createHash("sha256").update(asset).digest("hex")).toBe(
      expectedDigest,
    );
  });

  it("contains no active or externally loaded SVG content", () => {
    const asset = readFileSync(ornamentPath, "utf8");

    expect(asset).not.toMatch(
      /<!DOCTYPE|<script|<foreignObject|\bon(?:load|click|error)\s*=|\bhref\s*=|\burl\s*\(/i,
    );
  });
});
