# Temper alpha readiness audit

Date: 2026-08-26
Scope: React/Tauri product slice, governed-engine boundary, platform compatibility, dependency safety,
and external-user admission. The deferred Milestone 6 study was not accessed.

## Verdict

**Temper is ready to recruit a small set of design partners for interviews, screenshot review, and
an eventual private alpha. It is not yet ready to invite people to install or rely on the desktop
product.**

The visual direction is coherent and the implemented product slice is healthy. Tauri now
supervises the local Python engine, loads a live raw-free snapshot, performs offline encrypted
profile portability through native file dialogs, and exposes one exact-task Frontend Studio Mode.
Native enrollment, Connections mutations, the complete review/revoke/undo/feedback loop, secure
two-platform credential parity, and signed installers remain incomplete. Several browser-only
controls still depict future behavior and are explicitly disabled. Shipping before those gaps
close would still create a misleading product.

## Findings repaired during this audit

1. **Suggestion scope widening.** `Keep` widened a Kairn-scoped proposal to all coding work. The
   action now means `Keep as suggested`, applies the displayed scope exactly, and offers a
   project-only alternative only when it is genuinely narrower.
2. **Core scope widening.** The Core editor said it could narrow scope but allowed a Kairn-only
   item to become global or move to another project. Project-only items now expose only their
   current scope; global items may still be narrowed.
3. **Invalid Core edits.** Empty names or descriptions could be saved. Both fields are required,
   blank submissions are disabled, and saved wording is trimmed.
4. **Minimum-window dark contrast.** At 720×540, browser-default color inheritance made some
   headings and emphasized text black against the dark surface. Explicit theme colors now preserve
   WCAG contrast at the supported minimum.
5. **System-theme chrome.** Theme changes now update the document theme color, and System mode
   listens for operating-system appearance changes instead of sampling only once.
6. **Coverage gap.** A second compatibility harness now exercises onboarding, Today, review,
   Core, Connections, and Settings at 720×540, checks accessibility and horizontal overflow,
   rejects console errors and non-local requests, and probes scope-preserving mutations.
7. **Invitation-portal dependencies.** The production audit found seven high-severity advisories in
   the old Next.js/Sharp/PostCSS tree. Next.js is now 16.2.11, the matching ESLint configuration is
   pinned, patched Sharp and PostCSS versions are enforced, and the portal declares its exact
   Turbopack root. The rebuilt production tree has no known vulnerability.
8. **Multi-project ambiguity.** The native two-item select looked platform-inconsistent, omitted
   concurrent work, and did not make state changes obvious. The custom workspace menu now defaults
   to All projects, exposes both focused repository views, visibly changes Today and Core, and is
   covered in its open and closed states. Browser-only native account and folder actions are
   disabled and explained instead of behaving like broken controls.
9. **Core dialog click interception.** The Core dialog rendered beneath its modal overlay, so
   actual Chromium pointer events could not reach import or Mode controls even though DOM-only
   tests passed. The dialog now shares the overlay-safe stacking layer and real-browser interaction
   tests cover import preview and Mode disclosure.
10. **Sidecar import collision.** Building from the packaging directory allowed a local
    `platform.py` to shadow Python's standard library. A dedicated packaging entry point now
    establishes only the repository source root before importing the engine.
11. **Unbounded failed-engine wait.** The Rust bridge previously blocked on a line read when a
    compiled child failed before producing a frame. Reads are now bounded to 15 seconds; timeout or
    channel closure kills and reaps the child and joins the reader before returning a sanitized
    error.
12. **Compiled-runtime compatibility.** Nuitka 2.8.10 accepted Python 3.12 PEP 695 generic
    functions but produced a sidecar that failed at runtime. The seven affected internal helpers
    now use behaviorally equivalent `TypeVar` contracts, and the native builder must execute and
    validate the compiled engine handshake before writing its release manifest.

## Evidence that currently passes

- Frozen dependency installation with the exact pnpm lock.
- Prettier, ESLint, strict TypeScript, 33 component/engine tests, and the optimized Vite build.
- Nine Windows/WebView2-proxy compatibility checks at 720×540.
- Thirty-four Chromium visual/accessibility/interaction scenes in both themes and compact/wide layouts.
- React prototype and invitation-portal production dependency audits: no known vulnerabilities;
  the prototype's production licenses are 0BSD, ISC, MIT, and OFL-1.1.
- Local-only font, ornament, and product-mark loading with exact asset digests and active-content
  rejection.
- Full locked Python formatting, linting, typing, tests, and source/wheel builds.
- A real Windows x64 Nuitka sidecar completes ten clean unconfigured handshakes in 1.02–1.19
  seconds with exact protocol, version, and schema binding and mutations disabled.
- The Tauri CI matrix exercises Rust clippy/tests and the React contract on Linux, Windows, and
  macOS; a separate Windows job builds an internal NSIS candidate and a clean runner installs,
  handshakes, launches, uninstalls, verifies binary removal, and cleans any bounded temporary
  residue.

Playwright WebKit is configured as a practical macOS rendering proxy, but this WSL host lacks the
administrator-installed GTK/GStreamer libraries needed to launch it. That is an environment
limitation, not a passing macOS result. Actual WKWebView behavior must be verified in the native
Apple Silicon Tauri build.

## External-user blockers

### Product blockers

- Replace remaining synthetic customer-facing state with typed engine presentation models. No inert
  Connect, Manage, Add project, consent, telemetry, Apply, tray, or notification action may ship.
- Complete prospective first-run identity, consent, and project registration with learning and
  telemetry still off by default.
- Wire the signed review, scope, revoke, undo, feedback, and stale-snapshot paths before exposing
  mutations.
- Refresh and verify the Codex connector; do not claim ambient delivery into arbitrary existing
  Codex tasks.

### Platform and release blockers

- Complete native macOS WKWebView and Apple Silicon package validation; Chromium remains only a
  browser proxy for that platform.
- Implement macOS Keychain parity and verify Windows CurrentUser DPAPI through the Tauri path.
- Expand the release workflow beyond the native contract and Windows package smoke to cover every
  Python, protocol, security, signing, and portal gate in one provenance-bound release job.
- Pass keyboard-only and screen-reader manual audits in addition to axe.
- Add Windows upgrade/recovery coverage and produce the Apple Silicon build, then test install,
  upgrade, recovery, and uninstall on clean machines.
- Obtain Authenticode and Apple Developer ID credentials; notarize and staple the macOS artifact.
- Complete naming/trademark clearance and native icon exports before public branding claims.

### Evidence blockers

- Finish the unchanged genuine 6A.2C ordinary-use gate and the frozen Base-versus-Temper
  comparison. This is not required to continue engineering, but it is required before marketing
  broad automatic-learning effectiveness.
- Keep automatic promotion off until the signed shadow policy and genuine-use admission criteria
  pass. The current synthetic evidence supports ranking recommendations, not broad silent learning.

## Invitation boundary

Safe now:

- Post reviewed screenshots and a truthful product explanation.
- Recruit three to five design partners for interviews and an invite waitlist.
- Conduct guided prototype walkthroughs while clearly labeling the data as synthetic.

Not safe yet:

- Offer a downloadable desktop alpha.
- Ask external users to connect real Codex or Claude accounts through this React prototype.
- Claim that the desktop app is continuously learning from their work today.
- Distribute an unsigned installer or collect governed user data through the synthetic renderer.

The next engineering slice is still native onboarding and truthful Connections: governed
identity/key initialization, explicit prospective project registration, Codex inspection, and
delegated Claude inspection without handling provider credentials. In parallel, a real
Authenticode identity can be acquired and connected to the already fail-closed package gate.
External installation begins only after the complete product and platform blockers above are
closed; an unsigned clean-machine smoke is engineering evidence, not distribution approval.
