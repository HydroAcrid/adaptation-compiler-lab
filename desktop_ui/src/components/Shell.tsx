import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Check, ChevronDown, FolderGit2, Layers3 } from "lucide-react";
import type { ReactNode } from "react";

import type { Screen, WorkspaceScope } from "../types";
import { BotanicalFlourish } from "./BotanicalFlourish";
import { BrandMark } from "./BrandMark";

const primaryNavigation = [
  { id: "today" as const, label: "Today" },
  { id: "core" as const, label: "Core" },
  { id: "modes" as const, label: "Modes" },
  { id: "connections" as const, label: "Connections" },
  { id: "settings" as const, label: "Settings" },
];

export function Shell({
  screen,
  activeWorkspace,
  advancedMode,
  onNavigate,
  onWorkspaceChange,
  workspaces,
  previewMode = false,
  children,
}: {
  screen: Screen;
  activeWorkspace: WorkspaceScope;
  advancedMode: boolean;
  onNavigate: (screen: Screen) => void;
  onWorkspaceChange: (workspace: WorkspaceScope) => void;
  workspaces: Array<{ id: string; label: string; description: string }>;
  previewMode?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="window-shell">
      {previewMode ? (
        <aside
          aria-label="Browser preview notice"
          className="browser-preview-banner"
        >
          Browser preview · sample data · controls do not change your local
          Temper state
        </aside>
      ) : null}
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
            workspaces={workspaces}
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

function WorkspacePicker({
  activeWorkspace,
  onWorkspaceChange,
  workspaces,
}: {
  activeWorkspace: WorkspaceScope;
  onWorkspaceChange: (workspace: WorkspaceScope) => void;
  workspaces: Array<{ id: string; label: string; description: string }>;
}) {
  const options = [
    {
      id: "all",
      label: "All projects",
      description: workspaces.length
        ? `${workspaces.length} registered project${workspaces.length === 1 ? "" : "s"}`
        : "No registered projects",
    },
    ...workspaces,
  ];
  const current =
    options.find((option) => option.id === activeWorkspace) ?? options[0];
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
        {options.map((option) => (
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
