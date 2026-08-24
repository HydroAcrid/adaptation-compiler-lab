import {
  BrainCircuit,
  CircleUserRound,
  House,
  PlugZap,
  Settings,
  SlidersHorizontal,
} from "lucide-react";
import type { ReactNode } from "react";

import type { Screen } from "../types";
import { BotanicalFlourish } from "./BotanicalFlourish";
import { BrandMark } from "./BrandMark";

const primaryNavigation = [
  { id: "today" as const, label: "Today", icon: House },
  { id: "adaptations" as const, label: "Adaptations", icon: BrainCircuit },
  { id: "connections" as const, label: "Connections", icon: PlugZap },
  { id: "settings" as const, label: "Settings", icon: Settings },
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
        <aside className="sidebar">
          <BrandMark />
          <nav aria-label="Primary">
            {primaryNavigation.map((item) => {
              const Icon = item.icon;
              const isActive =
                screen === item.id ||
                ((screen === "suggestion" || screen === "tray") &&
                  item.id === "today");
              return (
                <button
                  aria-current={isActive ? "page" : undefined}
                  className={`nav-item ${isActive ? "nav-item--active" : ""}`}
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  type="button"
                >
                  <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
          <div className="sidebar-spacer" />
          {advancedMode ? (
            <button
              aria-current={screen === "advanced" ? "page" : undefined}
              className={`nav-item nav-item--subtle ${screen === "advanced" ? "nav-item--active" : ""}`}
              onClick={() => onNavigate("advanced")}
              type="button"
            >
              <SlidersHorizontal
                aria-hidden="true"
                size={18}
                strokeWidth={1.8}
              />
              <span>Advanced</span>
            </button>
          ) : null}
          <div className="local-identity">
            <CircleUserRound aria-hidden="true" size={20} strokeWidth={1.6} />
            <div>
              <strong>Local profile</strong>
              <span>Encrypted on this Mac</span>
            </div>
          </div>
        </aside>
        <main className="main-content">
          <BotanicalFlourish placement="workspace" />
          {children}
        </main>
      </div>
    </div>
  );
}
