import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const ornamentPath = join(
  process.cwd(),
  "public",
  "assets",
  "ornaments",
  "art-nouveau-french-floral-headpiece.svg",
);
const expectedDigest =
  "a01522b58caad6e954bc3f17e4d58a6cdc482a8c9145d3d524acccfeebb13ddd";

describe("vendored visual assets", () => {
  it("keeps the reviewed public-domain ornament byte exact", () => {
    const asset = readFileSync(ornamentPath);

    expect(createHash("sha256").update(asset).digest("hex")).toBe(
      expectedDigest,
    );
  });

  it("contains no active or externally loaded SVG content", () => {
    const asset = readFileSync(ornamentPath, "utf8");

    expect(asset).not.toMatch(
      /<script|<foreignObject|\bon(?:load|click|error)\s*=|\bhref\s*=|\burl\s*\(/i,
    );
  });
});
