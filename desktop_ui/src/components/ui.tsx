import * as Switch from "@radix-ui/react-switch";
import type { ButtonHTMLAttributes, ReactNode } from "react";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  tone?: "primary" | "secondary" | "quiet" | "danger";
  icon?: ReactNode;
}

export function Button({
  tone = "secondary",
  icon,
  className = "",
  children,
  ...props
}: ButtonProps) {
  return (
    <button className={`button button--${tone} ${className}`} {...props}>
      {icon}
      <span>{children}</span>
    </button>
  );
}

export function StatusPill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "positive" | "neutral" | "attention";
}) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>;
}

export function Toggle({
  checked,
  onCheckedChange,
  label,
  description,
  disabled = false,
}: {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  label: string;
  description?: string;
  disabled?: boolean;
}) {
  return (
    <div className="toggle-row">
      <div className="toggle-copy">
        <span className="toggle-label">{label}</span>
        {description ? (
          <span className="toggle-description">{description}</span>
        ) : null}
      </div>
      <Switch.Root
        aria-label={label}
        checked={checked}
        className="switch-root"
        disabled={disabled}
        onCheckedChange={onCheckedChange}
      >
        <Switch.Thumb className="switch-thumb" />
      </Switch.Root>
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="section-heading">
      {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
      <h1>{title}</h1>
      {description ? <p>{description}</p> : null}
    </div>
  );
}

export function Divider() {
  return <div aria-hidden="true" className="divider" />;
}
