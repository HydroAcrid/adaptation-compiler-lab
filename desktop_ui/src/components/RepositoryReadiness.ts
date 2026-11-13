import type { HubProject, HubState } from "../toolsHub";

export function connectionReadiness(state: HubState) {
  if (!state.indexed) return "preparing";
  if (!state.bridge_configured || !state.native_hooks_configured)
    return "connection_needed";
  return "configured";
}

export function setupImportBlock(state: HubState, repository?: HubProject) {
  if (state.secure_store_ready === false)
    return "Unlock secure storage to import a setup.";
  if (state.cleanup_pending) return "Finish cleanup to import a setup.";
  if (!state.enabled)
    return "Set up automatic workflows before importing a setup.";
  if (state.paused) return "Resume updates to import a setup.";
  if (state.job?.state === "running" && !state.indexed)
    return "Wait for repository setup to finish before importing a setup.";
  if (!state.bridge_configured) return "Connect Codex to import a setup.";
  if (repository?.paused)
    return "Resume updates for this repository to import a setup.";
  if (repository?.pending_recovery)
    return "Finish recovery for this repository to import a setup.";
  return null;
}
