import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const assets = [
  {
    path: join(process.cwd(), "public", "assets", "brand", "temper-wind.svg"),
    digest: "5447a3d08ed9a9b49c11fbd16d07f863aaab88a55b722b5597ab61af90086ec6",
  },
  {
    path: join(
      process.cwd(),
      "public",
      "assets",
      "ornaments",
      "antique-acanthus-corner.svg",
    ),
    digest: "cefed89f0b17b5b5cff6ea5c4a921cad65b81a8e6a9acf38e7bcc491d2f14997",
  },
  {
    path: join(
      process.cwd(),
      "public",
      "assets",
      "ornaments",
      "core-knowledge-tree.svg",
    ),
    digest: "0ee7f8ab03b30a816cb04cf07a4c1670e029603c859c23bb05ec774c43993d01",
  },
];

describe("vendored visual assets", () => {
  it("keeps the reviewed and sanitized CC0 vectors byte exact", () => {
    for (const asset of assets) {
      const contents = readFileSync(asset.path);
      expect(createHash("sha256").update(contents).digest("hex")).toBe(
        asset.digest,
      );
    }
  });

  it("contains no active or externally loaded SVG content", () => {
    for (const asset of assets) {
      const contents = readFileSync(asset.path, "utf8");
      expect(contents).not.toMatch(
        /<!DOCTYPE|<script|<foreignObject|\bon(?:load|click|error)\s*=|\bhref\s*=|\burl\s*\(/i,
      );
    }
  });
});
