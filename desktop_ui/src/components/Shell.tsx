import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  Check,
  ChevronDown,
  FolderGit2,
  LayoutDashboard,
  Layers3,
  Settings2,
  SlidersHorizontal,
  Unplug,
  Workflow,
} from "lucide-react";
import { useState, type ReactNode, type RefObject } from "react";

import { pageForScreen, PageVisibility, type Page } from "../pageVisibility";
import type { Screen, WorkspaceScope } from "../types";
import { BrandMark } from "./BrandMark";

const navigation = [
  { id: "today", label: "Overview", icon: LayoutDashboard },
  { id: "core", label: "Personalization", icon: SlidersHorizontal },
  { id: "modes", label: "Tools & workflows", icon: Workflow },
  { id: "connections", label: "Connections", icon: Unplug },
  { id: "settings", label: "Settings", icon: Settings2 },
  { id: "advanced", label: "Advanced", icon: Layers3 },
] as const;

export function Shell({
  screen,
  advancedMode,
  onNavigate,
  previewMode = false,
  pages,
  scrollHost,
}: {
  screen: Screen;
  advancedMode: boolean;
  onNavigate: (screen: Screen) => void;
  previewMode?: boolean;
  pages: Record<Page, ReactNode>;
  scrollHost: RefObject<HTMLElement | null>;
}) {
  const page = pageForScreen(screen);
  const [visited, setVisited] = useState(() => new Set([page]));
  if (!visited.has(page)) {
    setVisited(new Set([...visited, page]));
  }

  return (
    <div className="window-shell">
      {previewMode ? (
        <aside
          aria-label="Browser preview notice"
          className="browser-preview-banner"
        >
          Browser preview · Sample data
        </aside>
      ) : null}
      <div className="app-layout">
        <header className="folio-masthead">
          <BrandMark />
          <nav aria-label="Primary">
            {navigation.map(({ id, label, icon: Icon }) => {
              if (id === "advanced" && !advancedMode) return null;
              const isActive = page === id;
              return (
                <button
                  aria-current={isActive ? "page" : undefined}
                  className={`folio-index-link${id === "advanced" ? " folio-index-link--advanced" : ""}${isActive ? " folio-index-link--active" : ""}`}
                  key={id}
                  onClick={() => onNavigate(id)}
                  type="button"
                >
                  <Icon
                    aria-hidden="true"
                    className="folio-index-icon"
                    size={18}
                    strokeWidth={1.75}
                  />
                  <span>{label}</span>
                </button>
              );
            })}
          </nav>
        </header>
        <main
          aria-label={navigation.find((item) => item.id === page)?.label}
          className="main-content"
          ref={scrollHost}
          tabIndex={-1}
        >
          {navigation.map(({ id }) => {
            if (!visited.has(id)) return null;
            const isActive = id === page;
            return (
              <div
                className={
                  isActive ? "page-view page-view--active" : "page-view"
                }
                data-screen={id}
                hidden={!isActive}
                inert={!isActive}
                key={id}
              >
                <PageVisibility.Provider value={isActive}>
                  {pages[id]}
                </PageVisibility.Provider>
              </div>
            );
          })}
        </main>
      </div>
    </div>
  );
}

export function WorkspacePicker({
  activeWorkspace,
  onWorkspaceChange,
  workspaces,
}: {
  activeWorkspace: WorkspaceScope;
  onWorkspaceChange: (workspace: WorkspaceScope) => void;
  workspaces: Array<{ id: string; label: string }>;
}) {
  const options = [
    {
      id: "all",
      label: "All projects",
    },
    ...workspaces,
  ];
  const current =
    options.find((option) => option.id === activeWorkspace) ?? options[0];
  return (
    <DropdownMenu.Root modal={false}>
      <DropdownMenu.Trigger
        aria-label={`Review project: ${current.label}`}
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
          <small>Review project</small>
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
        <DropdownMenu.Label>Filter suggestions by project</DropdownMenu.Label>
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
            </span>
          </DropdownMenu.Item>
        ))}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
}
