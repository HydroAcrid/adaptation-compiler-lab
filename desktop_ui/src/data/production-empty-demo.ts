import type {
  AgentConnection,
  CapabilityModeSummary,
  CoreItem,
  PortableProfilePreview,
  RegisteredProject,
  Suggestion,
} from "../types";
import type { ProfileExportPreview, ProfileImportPreview } from "../engine";

// Production desktop builds never bundle development personas or sample records.
// The actual native state comes exclusively from the local engine protocol.
export const suggestions: Suggestion[] = [];
export const coreItems: CoreItem[] = [];
export const connections: AgentConnection[] = [];
export const projects: RegisteredProject[] = [];
export const modes: CapabilityModeSummary[] = [];
export const workspaceOptions: Array<{
  id: string;
  label: string;
  description: string;
}> = [];
export const modeProjects: Array<{ id: string; label: string }> = [];
export const profileExportPreview:
  (ProfileExportPreview & PortableProfilePreview) | null = null;
export const profileImportPreview:
  (ProfileImportPreview & PortableProfilePreview) | null = null;
