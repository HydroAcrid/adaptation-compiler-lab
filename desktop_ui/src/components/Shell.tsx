import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, ChevronDown, FolderGit2, Layers3 } from "lucide-react";
import type { ReactNode } from "react";

import type { Screen, WorkspaceScope } from "../types";
import { BotanicalFlourish } from "./BotanicalFlourish";
import { BrandMark } from "./BrandMark";

const primaryNavigation = [
  { id: "today" as const, label: "Today" },
  { id: "core" as const, label: "Core" },
  { id: "connections" as const, label: "Connections" },
  { id: "settings" as const, label: "Settings" },
];

export function Shell({
  screen,
  activeWorkspace,
  advancedMode,
  onNavigate,
  onWorkspaceChange,
  children,
}: {
  screen: Screen;
  activeWorkspace: WorkspaceScope;
  advancedMode: boolean;
  onNavigate: (screen: Screen) => void;
  onWorkspaceChange: (workspace: WorkspaceScope) => void;
  children: ReactNode;
}) {
  return (
    <div className="window-shell">
      <div aria-hidden="true" className="window-dragbar">
        <span className="window-title">Temper</span>
        <div className="window-controls">
          <span />
          <span />
          <span className="window-close" />
        </div>
      </div>
      <div className="app-layout">
        <header className="folio-masthead">
          <BrandMark />
          <nav aria-label="Primary">
            {primaryNavigation.map((item) => {
              const isActive =
                screen === item.id ||
                ((screen === "suggestion" || screen === "tray") &&
                  item.id === "today");
              return (
                <button
                  aria-current={isActive ? "page" : undefined}
                  className={`folio-index-link ${isActive ? "folio-index-link--active" : ""}`}
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  type="button"
                >
                  <span>{item.label}</span>
                </button>
              );
            })}
            {advancedMode ? (
              <button
                aria-current={screen === "advanced" ? "page" : undefined}
                className={`folio-index-link folio-index-link--advanced ${screen === "advanced" ? "folio-index-link--active" : ""}`}
                onClick={() => onNavigate("advanced")}
                type="button"
              >
                <span>Advanced</span>
              </button>
            ) : null}
          </nav>
          <WorkspacePicker
            activeWorkspace={activeWorkspace}
            onWorkspaceChange={onWorkspaceChange}
          />
        </header>
        <main className="main-content">
          {screen === "core" ? null : (
            <BotanicalFlourish placement="workspace" />
          )}
          {children}
        </main>
      </div>
    </div>
  );
}

const workspaceOptions: Array<{
  id: WorkspaceScope;
  label: string;
  description: string;
}> = [
  {
    id: "all",
    label: "All projects",
    description: "2 active projects",
  },
  {
    id: "Kairn",
    label: "Kairn",
    description: "3 suggestions",
  },
  {
    id: "Green Meadow",
    label: "Green Meadow",
    description: "Ready",
  },
];

function WorkspacePicker({
  activeWorkspace,
  onWorkspaceChange,
}: {
  activeWorkspace: WorkspaceScope;
  onWorkspaceChange: (workspace: WorkspaceScope) => void;
}) {
  const current =
    workspaceOptions.find((option) => option.id === activeWorkspace) ??
    workspaceOptions[0];
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger
        aria-label={`Workspace: ${current.label}`}
        className="workspace-picker-trigger"
      >
        <span aria-hidden="true" className="workspace-picker-icon">
          {activeWorkspace === "all" ? (
            <Layers3 size={17} strokeWidth={1.7} />
          ) : (
            <FolderGit2 size={17} strokeWidth={1.7} />
          )}
        </span>
        <span className="workspace-picker-copy">
          <small>Workspace</small>
          <strong>{current.label}</strong>
        </span>
        <ChevronDown aria-hidden="true" size={14} strokeWidth={1.7} />
      </DropdownMenu.Trigger>
      <DropdownMenu.Content
        align="end"
        className="workspace-picker-menu"
        collisionPadding={12}
        sideOffset={8}
      >
        <DropdownMenu.Label>Workspace view</DropdownMenu.Label>
        {workspaceOptions.map((option) => (
          <DropdownMenu.Item
            className="workspace-picker-item"
            key={option.id}
            onSelect={() => onWorkspaceChange(option.id)}
          >
            <span className="workspace-picker-check">
              {option.id === activeWorkspace ? (
                <Check aria-hidden="true" size={14} />
              ) : null}
            </span>
            <span>
              <strong>{option.label}</strong>
              <small>{option.description}</small>
            </span>
          </DropdownMenu.Item>
        ))}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
