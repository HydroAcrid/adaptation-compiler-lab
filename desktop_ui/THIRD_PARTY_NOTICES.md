# Temper desktop third-party assets

## Typefaces

Temper self-hosts both fonts at build time. No runtime font request is made.

- **Newsreader Variable 5.3.0** — editorial display and behavioral clauses; distributed through
  [`@fontsource-variable/newsreader`](https://fontsource.org/fonts/newsreader) under the
  [SIL Open Font License 1.1](https://openfontlicense.org/open-font-license-official-text/).
- **Instrument Sans Variable 5.3.0** — interface text and metadata; distributed through
  [`@fontsource-variable/instrument-sans`](https://fontsource.org/fonts/instrument-sans) under the
  [SIL Open Font License 1.1](https://openfontlicense.org/open-font-license-official-text/).

## Antique corner ornament

- Bundled file: `public/assets/ornaments/antique-acanthus-corner.svg`
- Work: _Antique corner ornament_
- Artist: Darkmoon-Art
- Source: [Openclipart](https://openclipart.org/detail/333685/antique-corner-ornament)
- License: [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/); Openclipart states that
  every uploaded work is released under CC0 and may be modified or used commercially
- Uploaded by the artist: 2021-10-11
- Retrieved: 2026-08-24
- Upstream SHA-256: `f63f1527fabe1018d374d75514f10ce4d09d6f3a649940f9e040545c9d4a71f1`
- Vendored SHA-256: `cefed89f0b17b5b5cff6ea5c4a921cad65b81a8e6a9acf38e7bcc491d2f14997`
- Modifications: removed the XML declaration, external DTD, physical dimensions, and generator
  metadata; retained the original vector paths, view box, and aspect-ratio behavior. Temper applies
  color, opacity, placement, rotation, and clipping at render time through a CSS mask.

The file and fonts are bundled locally. Temper does not hotlink, fetch, or execute remote visual
assets at runtime.
