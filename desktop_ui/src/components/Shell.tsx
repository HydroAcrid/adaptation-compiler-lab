import type { ReactNode } from "react";

import type { Screen } from "../types";
import { BotanicalFlourish } from "./BotanicalFlourish";
import { BrandMark } from "./BrandMark";

const primaryNavigation = [
  { id: "today" as const, label: "Today", index: "01" },
  { id: "adaptations" as const, label: "Adaptations", index: "02" },
  { id: "connections" as const, label: "Connections", index: "03" },
  { id: "settings" as const, label: "Settings", index: "04" },
];

export function Shell({
  screen,
  advancedMode,
  onNavigate,
  children,
}: {
  screen: Screen;
  advancedMode: boolean;
  onNavigate: (screen: Screen) => void;
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
                  <span aria-hidden="true" className="folio-index-number">
                    {item.index}
                  </span>
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
                <span aria-hidden="true" className="folio-index-number">
                  05
                </span>
                <span>Advanced</span>
              </button>
            ) : null}
          </nav>
          <div className="folio-runtime-context" aria-label="Current delivery">
            <span>Kairn</span>
            <span aria-hidden="true">→</span>
            <strong>Codex</strong>
          </div>
          <div
            className="local-seal"
            title="Local profile, encrypted on this Mac"
          >
            <span aria-hidden="true" />
            <span>
              Local
              <br />
              encrypted
            </span>
          </div>
        </header>
        <main className="main-content">
          <BotanicalFlourish placement="workspace" />
          {children}
        </main>
      </div>
    </div>
  );
}
