# Temper desktop third-party notices

## Tauri NSIS installer template

- Bundled file: `src-tauri/windows/installer-template.nsi`
- Project: [Tauri](https://github.com/tauri-apps/tauri)
- Component: `tauri-bundler` 2.9.4
- Tag commit: `8909f221d1515955fc843808032bdc5d62209c96`
- License: [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) or
  [MIT](https://opensource.org/license/mit/)
- Upstream canonical-LF SHA-256:
  `20f4ecc730defb71f1342eaeaec4021df13be3d843abba0effe88ea5835fa079`
- Vendored canonical-LF SHA-256:
  `aa0378477b4ee5e260f07bba4bf11343218634c15d70c1254144e60a31055ea1`
- Modifications: set the visible current-user default to
  `%LOCALAPPDATA%\\Programs\\Temper`; remove the generic uninstaller “delete app data” control
  and its deletion branch because Temper evidence and preferences require the governed product
  deletion flow. The package uninstaller preserves governed state.

## Typefaces

Temper self-hosts both fonts at build time. No runtime font request is made.

- **Newsreader Variable 5.3.0** — editorial display and behavioral clauses; distributed through
  [`@fontsource-variable/newsreader`](https://fontsource.org/fonts/newsreader) under the
  [SIL Open Font License 1.1](https://openfontlicense.org/open-font-license-official-text/).
- **Instrument Sans Variable 5.3.0** — interface text and metadata; distributed through
  [`@fontsource-variable/instrument-sans`](https://fontsource.org/fonts/instrument-sans) under the
  [SIL Open Font License 1.1](https://openfontlicense.org/open-font-license-official-text/).

## Agent connection marks

Temper bundles provider marks only beside the corresponding Codex and Claude Code connection
status. They are descriptive identifiers, not Temper branding and not an endorsement or
partnership claim. The paths are bundled in `src/components/AgentBrandMark.tsx`; Temper makes no
runtime request for them.

- **OpenAI knot** — sourced from Simple Icons 15.15.0
  ([upstream SVG](https://cdn.jsdelivr.net/npm/simple-icons@15.15.0/icons/openai.svg)); Simple
  Icons is distributed under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
  OpenAI retains trademark rights and requires relevant, unaltered, non-endorsing use under its
  [brand guidelines](https://openai.com/brand/). Temper removes only the SVG wrapper and title,
  keeps the vector path unchanged, and renders the monochrome mark beside “Codex.”
- **Claude starburst** — sourced from Simple Icons 16.28.0
  ([upstream SVG](https://cdn.jsdelivr.net/npm/simple-icons@16.28.0/icons/claude.svg)); Simple
  Icons is distributed under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/).
  Anthropic retains trademark rights and publishes official assets through its
  [press kit](https://www.anthropic.com/press-kit). Temper removes only the SVG wrapper and title,
  keeps the vector path unchanged, and renders the mark in Claude's Crail color beside “Claude
  Code.”

## Temper wind mark

- Bundled file: `public/assets/brand/temper-wind.svg`
- Work: _Wind_
- Artist: NicholasJudy567
- Source: [Openclipart](https://openclipart.org/detail/327796)
- License: [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)
- Uploaded by the artist: 2021-02-04
- Retrieved: 2026-08-24
- Upstream SHA-256: `3713e78f807bc60987b3f44319302ce5f6d6a31e1111ee1e2883acf5f0e15722`
- Vendored SHA-256: `5447a3d08ed9a9b49c11fbd16d07f863aaab88a55b722b5597ab61af90086ec6`
- Modifications: removed the XML declaration, physical dimensions, editor IDs, and presentation
  attributes while retaining the original view box, group transform, and complete vector path.
  Temper renders it as a CSS mask so the mark inherits the copper accent in every theme.

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

## Core knowledge tree

- Bundled file: `public/assets/ornaments/core-knowledge-tree.svg`
- Work: _Tree and roots silhouette_
- Source: [FreePNGImg](https://freepngimg.com/svg/99050-tree-and-roots-silhouette)
- License: [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/)
- Retrieved: 2026-08-24
- Upstream SHA-256: `b957698ba38af1644b74e2f2ec1ded88b727a83946b44bb6aa041814c4cf23d4`
- Vendored SHA-256: `0ee7f8ab03b30a816cb04cf07a4c1670e029603c859c23bb05ec774c43993d01`
- Modifications: optimized and sanitized with SVGO 4.0.1; removed the XML declaration, external
  DTD, editor metadata, physical dimensions, and unused attributes while retaining the original
  vector paths and view box. Temper applies color, opacity, placement, and clipping through a CSS
  mask.
