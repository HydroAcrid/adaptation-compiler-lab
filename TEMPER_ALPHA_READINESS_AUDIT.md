# Temper alpha readiness audit

Date: 2026-08-24
Scope: React visual prototype, governed-engine boundary, platform compatibility, dependency safety,
and external-user admission. The deferred Milestone 6 study was not accessed.

## Verdict

**Temper is ready to recruit a small set of design partners for interviews, screenshot review, and
an eventual private alpha. It is not yet ready to invite people to install or rely on the desktop
product.**

The visual direction is coherent and the tested prototype interactions are healthy. The customer
renderer is still synthetic, however: it has no Tauri shell, no sidecar handshake, no live governed
snapshot, no native enrollment, and no signed installer. Several controls intentionally depict
future connection, consent, telemetry, tray, and task actions without implementing them. Shipping
that surface would create a misleading product, even though the underlying Python engine and Qt
diagnostic client are substantially further along.

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

## Evidence that currently passes

- Frozen dependency installation with the exact pnpm lock.
- Prettier, ESLint, strict TypeScript, 20 component/asset tests, and the optimized Vite build.
- Eight Windows/WebView2-proxy compatibility checks at 720×540.
- Twenty-eight Chromium visual/accessibility scenes in both themes and compact/wide layouts.
- React prototype and invitation-portal production dependency audits: no known vulnerabilities;
  the prototype's production licenses are 0BSD, ISC, MIT, and OFL-1.1.
- Local-only font, ornament, and product-mark loading with exact asset digests and active-content
  rejection.
- Full locked Python formatting, linting, typing, tests, and source/wheel builds.

Playwright WebKit is configured as a practical macOS rendering proxy, but this WSL host lacks the
administrator-installed GTK/GStreamer libraries needed to launch it. That is an environment
limitation, not a passing macOS result. Actual WKWebView behavior must be verified in the native
Apple Silicon Tauri build.

## External-user blockers

### Product blockers

- Build the Tauri 2 shell, restrictive capabilities, tray/window lifecycle, and sidecar
  supervision.
- Implement and golden-test `temper-engine-protocol/v1`, beginning with a read-only raw-free
  `snapshot.get` handshake.
- Replace every synthetic customer-facing state with typed engine presentation models. No inert
  Connect, Manage, Add project, consent, telemetry, Apply, tray, or notification action may ship.
- Complete prospective first-run identity, consent, and project registration with learning and
  telemetry still off by default.
- Wire the signed review, scope, revoke, undo, feedback, and stale-snapshot paths before exposing
  mutations.
- Refresh and verify the Codex connector; do not claim ambient delivery into arbitrary existing
  Codex tasks.

### Platform and release blockers

- Add Windows WebView2 and native macOS WKWebView build lanes; the current Chromium result is only
  a proxy.
- Implement macOS Keychain parity and verify Windows CurrentUser DPAPI through the Tauri path.
- Add continuous integration for frontend, Python, protocol, security, and native platform gates.
- Pass keyboard-only and screen-reader manual audits in addition to axe.
- Produce clean Windows x64 and Apple Silicon builds, then test install, upgrade, recovery, and
  uninstall on clean machines.
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

The next engineering slice remains the smallest honest one: a Tauri shell plus a read-only,
version-checked `snapshot.get` path from the existing Python application service. External
installation begins only after the complete product and platform blockers above are closed.
