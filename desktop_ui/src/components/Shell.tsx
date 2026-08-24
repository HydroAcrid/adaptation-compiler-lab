import type { ReactNode } from "react";

import type { ProjectName, Screen } from "../types";
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
  activeProject,
  advancedMode,
  onNavigate,
  onProjectChange,
  children,
}: {
  screen: Screen;
  activeProject: ProjectName;
  advancedMode: boolean;
  onNavigate: (screen: Screen) => void;
  onProjectChange: (project: ProjectName) => void;
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
          <div className="folio-runtime-context" aria-label="Current delivery">
            <label className="sr-only" htmlFor="current-project">
              Current project
            </label>
            <select
              aria-label="Current project"
              id="current-project"
              onChange={(event) =>
                onProjectChange(event.target.value as ProjectName)
              }
              value={activeProject}
            >
              <option value="Kairn">Kairn</option>
              <option value="Green Meadow">Green Meadow</option>
            </select>
            <span aria-hidden="true">→</span>
            <strong>Codex</strong>
          </div>
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
